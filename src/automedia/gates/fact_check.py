"""G0 Fact-Check Gate — 5-step verification pipeline.

Steps:
    1. 来源追溯 (Source Trace) — content references source_url
    2. 数字验证 (Number Verification) — numbers match source_data
    3. 时间线 (Timeline) — event timeline is logically consistent
    4. 引文 (Quotes) — quotes match original text
    5. 实体 (Entities) — key entity names are correct

When ``gate_context["_mock_results"]`` is present, each check's result is
driven from that dict instead of calling the LLM provider — making the gate
fully deterministic for unit testing.

When ``gate_context["config"]["enable_llm"]`` is ``True`` (default), the gate
attempts LLM-based evaluation via :func:`llm_check_with_fallback` before
falling back to the deterministic substring-matching logic.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, ClassVar

from structlog import get_logger

from automedia.core.llm_client import llm_complete_structured_safe
from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result
from automedia.gates.base import BaseGate
from automedia.gates.hook_claims_rewrite import hedge_hook_claims
from automedia.gates.llm_helpers import (
    G0CheckResult,
    G0RewriteResult,
    LLMCheckResult,
    llm_check_with_fallback,
)
from automedia.prompts import load_prompt
from automedia.prompts.hook_claims import HookClaimHit, hook_area_violations

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CHECK_NAMES: list[str] = [
    "source_trace",
    "number_verification",
    "timeline",
    "quotes",
    "entities",
]


_EXPECTED_MAP: dict[str, str] = {
    "source_trace": "Content references the source URL domain",
    "number_verification": "All key numbers match the source data",
    "timeline": "Event dates are chronologically consistent",
    "quotes": "Quotes match the original source text",
    "entities": "Key entity names match the source data",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_deterministic_checks(
    content: str,
    source_url: str,
    source_data: dict[str, Any],
) -> list[CheckResult]:
    """Run all 5 deterministic checks and return the check dicts."""
    return [
        _check_source_trace(content, source_url, source_data),
        _check_number_verification(content, source_data),
        _check_timeline(content, source_data),
        _check_quotes(content, source_data),
        _check_entities(content, source_data),
    ]


# ---------------------------------------------------------------------------
# Number normalization helpers (used by _check_number_verification)
# ---------------------------------------------------------------------------

# Window radius (in characters) around a label occurrence in which a number
# phrase is examined for contradictions. Phrases are contiguous, so the radius
# only bounds how far qualifiers/units may extend.
_WINDOW_RADIUS = 20

# Chinese number qualifiers that may precede a figure ("约82.7亿" ≈ "roughly
# 82.7 hundred million"). Stripped from the left before parsing; longest
# prefixes first so "达到" wins over "达".
_NUMBER_QUALIFIER_PREFIXES: tuple[str, ...] = ("大约", "达到", "超过", "约", "近", "达")

# Chinese unit suffixes that may follow a figure ("82.7亿元", "12%", "50人").
# Longest suffixes are tried first ("万元" before "万", "美元" before "元").
# NOTE: this is a *strip* list only — magnitude conversion is intentionally
# NOT applied (see _normalize_number): 87.2亿 and 87.2 both normalize to 87.2.
_NUMBER_UNIT_SUFFIXES: tuple[str, ...] = (
    "万元",
    "美元",
    "元",
    "亿",
    "万",
    "%",
    "％",
    "人",
    "家",
    "个",
    "台",
)

# Single characters that may sit between a label and its number phrase on
# either side (qualifiers, light connectors, whitespace). Punctuation such as
# "，" "。" "、" stops the scan, so unrelated figures are never inspected.
_NUMBER_GLUE_CHARS: frozenset[str] = frozenset("约大约近达达到超过为是了 （(：: \t")

# Unit suffixes flattened to single characters for the left/right phrase scans.
_UNIT_SUFFIX_CHARS: frozenset[str] = frozenset("".join(_NUMBER_UNIT_SUFFIXES))

# Number token: digits with optional thousands separators and decimal part.
_NUMBER_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

# Label candidates used by the reverse-direction check. English source labels
# map to common Chinese glosses so proximity checks still fire against Chinese
# content. This is a documented *heuristic* pinned by tests, NOT an NLP
# solution: only these exact strings are recognized, and short glosses like
# "率"/"用户" may occasionally match inside unrelated words (效率, 汇率, ...).
_NUMBER_LABEL_GLOSS: dict[str, tuple[str, ...]] = {
    "market_size": ("规模", "市场规模"),
    "revenue": ("营收", "收入", "销售额"),
    "growth_rate": ("增长", "增幅", "增速"),
    "user_count": ("用户", "用户数"),
    "price": ("价格", "单价"),
    "percentage": ("占比", "比例", "百分比"),
    "total": ("总量", "总额", "总数"),
    "rate": ("率",),
}


def _normalize_number(text: str) -> float | None:
    """Normalize a Chinese/plain number token to ``float``.

    Strips leading qualifiers (约/大约/近/达/达到/超过), trailing unit
    suffixes (亿/万/元/万元/%/％/美元/人/家/个/台) and thousands separators,
    then parses as float. Returns ``None`` when the remainder is not a number.

    Known limitation (intentional): 亿/万 magnitude conversion is NOT applied
    — "87.2亿" and "87.2" both normalize to 87.2, so this helper cannot tell
    "87.2亿" apart from "87.2" (documented; out of scope for the heuristic).
    """
    s = text.strip()
    if not s:
        return None

    # Strip leading qualifiers, repeatedly ("大约近82.7").
    stripped = True
    while stripped:
        stripped = False
        for prefix in _NUMBER_QUALIFIER_PREFIXES:
            if s.startswith(prefix):
                s = s[len(prefix) :]
                stripped = True
                break

    # Strip trailing unit suffixes, repeatedly ("82.7亿元" → "82.7").
    stripped = True
    while stripped:
        stripped = False
        for suffix in _NUMBER_UNIT_SUFFIXES:
            if s.endswith(suffix):
                s = s[: -len(suffix)]
                stripped = True
                break

    # Remove thousands separators (commas between digits).
    s = re.sub(r"(?<=\d),(?=\d)", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def _numbers_close(a: float | None, b: float | None) -> bool:
    """Return True when both numbers parse and agree within float noise."""
    if a is None or b is None:
        return False
    return abs(a - b) < 1e-9


def _left_number_phrase(content: str, label_start: int) -> str | None:
    """Return the number phrase immediately left of a label occurrence, or None.

    A phrase is ``[qualifier]* [digits] [unit]*`` directly adjacent to the
    label ("82.7亿元规模" → "82.7亿元"). Any non-glue character (punctuation,
    ordinary text) ends the scan, which is what keeps unrelated figures out.
    """
    i = label_start - 1
    limit = max(0, label_start - _WINDOW_RADIUS)
    # Unit suffixes, right-to-left.
    while i >= limit and content[i] in _UNIT_SUFFIX_CHARS:
        i -= 1
    num_end = i + 1
    # Digits and separators.
    while i >= limit and (content[i].isdigit() or content[i] in ".,"):
        i -= 1
    num_start = i + 1
    if num_start >= num_end:
        return None
    # Qualifiers / connectors.
    while i >= limit and content[i] in _NUMBER_GLUE_CHARS:
        i -= 1
    return content[i + 1 : num_end]


def _right_number_phrase(content: str, label_end: int) -> str | None:
    """Return the number phrase immediately right of a label occurrence, or None.

    Same phrase shape as :func:`_left_number_phrase`, mirrored ("市场规模达
    87.2亿元" → "达87.2亿元").
    """
    j = label_end
    limit = min(len(content), label_end + _WINDOW_RADIUS)
    # Qualifiers / connectors.
    while j < limit and content[j] in _NUMBER_GLUE_CHARS:
        j += 1
    num_start = j
    # Digits and separators.
    while j < limit and (content[j].isdigit() or content[j] in ".,"):
        j += 1
    num_end = j
    if num_start >= num_end:
        return None
    # Unit suffixes.
    while j < limit and content[j] in _UNIT_SUFFIX_CHARS:
        j += 1
    return content[num_start:j]


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_source_trace(content: str, source_url: str, source_data: dict[str, Any]) -> CheckResult:
    """Step 1: Verify that *content* references the *source_url* domain."""
    name = "source_trace"
    if not source_url:
        return {"name": name, "passed": True, "detail": "no source_url to verify"}

    # Extract domain from source_url for matching
    from urllib.parse import urlparse

    parsed = urlparse(source_url)
    domain = parsed.netloc.lower()

    # Simple heuristic: domain or a notable fragment should appear in content
    content_lower = content.lower()
    if domain in content_lower or domain.replace("www.", "") in content_lower:
        return {
            "name": name,
            "passed": True,
            "detail": f"source domain '{domain}' found in content",
        }

    # Fallback: check if source_data contains any reference text
    reference_text = source_data.get("reference_text", "")
    if reference_text and reference_text.lower() in content_lower:
        return {"name": name, "passed": True, "detail": "reference text found in content"}

    return {
        "name": name,
        "passed": False,
        "detail": f"source domain '{domain}' not found in content",
    }


def _check_number_verification(content: str, source_data: dict[str, Any]) -> CheckResult:
    """Step 2: Verify that numbers in *content* match *source_data.key_numbers*.

    Bidirectional check per key (label, expected_value):

    * Forward (containment): the expected value must appear in content,
      normalized (thousands separators / trailing zeros tolerated).
    * Reverse (proximity): every occurrence of the label (or a Chinese gloss
      of it, see ``_NUMBER_LABEL_GLOSS``) is examined for a directly adjacent
      number phrase; any phrase that normalizes to a different value than
      ``expected_value`` is reported as a contradiction. Numbers not adjacent
      to a matched label are never inspected.
    """
    name = "number_verification"
    key_numbers: dict[str, str] = source_data.get("key_numbers", {})

    if not key_numbers:
        return {"name": name, "passed": True, "detail": "no key_numbers to verify"}

    mismatches: list[str] = []
    for label, expected_value in key_numbers.items():
        expected_str = str(expected_value)
        expected_num = _normalize_number(expected_str)

        # Forward direction: source value must appear in content.
        if expected_str not in content:
            found = False
            if expected_num is not None:
                for token in _NUMBER_TOKEN_RE.finditer(content):
                    if _numbers_close(_normalize_number(token.group(0)), expected_num):
                        found = True
                        break
            if not found:
                mismatches.append(f"expected '{label}'={expected_str} not found in content")

        # Reverse direction: numbers adjacent to a matching label must agree.
        if expected_num is None:
            continue  # numeric comparison impossible; forward check already ran

        content_lower = content.lower()
        candidates = (label.lower(), *(_NUMBER_LABEL_GLOSS.get(label, ())))
        details: set[str] = set()
        for candidate in candidates:
            start = 0
            while True:
                idx = content_lower.find(candidate, start)
                if idx == -1:
                    break
                for phrase in (
                    _left_number_phrase(content, idx),
                    _right_number_phrase(content, idx + len(candidate)),
                ):
                    if phrase is None:
                        continue
                    num = _normalize_number(phrase)
                    if num is not None and not _numbers_close(num, expected_num):
                        token_match = _NUMBER_TOKEN_RE.search(phrase)
                        shown_num = token_match.group(0) if token_match else phrase
                        details.add(
                            f"content value {shown_num} for '{label}' "
                            f"contradicts source value {expected_str}"
                        )
                start = idx + len(candidate)
        mismatches.extend(sorted(details))

    if mismatches:
        return {"name": name, "passed": False, "detail": "; ".join(mismatches)}
    return {"name": name, "passed": True, "detail": f"all {len(key_numbers)} key_numbers verified"}


# ---------------------------------------------------------------------------
# Timeline date parsing helpers (used by _check_timeline)
# ---------------------------------------------------------------------------

_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_CN_FULL_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_CN_YEAR_MONTH_RE = re.compile(r"(\d{4})年(\d{1,2})月(?!\d{1,2}日)")
_CN_MONTH_DAY_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")


def _iter_content_dates(content: str, pub_dt: datetime) -> list[tuple[str, datetime]]:
    """Parse ISO and Chinese dates from *content*, deduplicated by date.

    Chinese forms handled:

    * "X年X月X日" and "X年X月" — explicit year, parsed as-is
    * "X月X日" — year inferred from ``pub_dt.year``; when the parsed month is
      11+ months after the published month (classic Dec/Jan rollover), the
      year is decremented so "12月31日" in a January article refers to the
      previous December.
    """
    found: list[tuple[str, datetime]] = []

    for m in _ISO_DATE_RE.finditer(content):
        try:
            found.append((m.group(0), datetime.fromisoformat(m.group(0))))
        except ValueError:
            continue

    # Full "X年X月X日" spans shadow the bare "X月X日" pattern inside them.
    full_spans: list[tuple[int, int]] = []
    for m in _CN_FULL_DATE_RE.finditer(content):
        year, month, day = (int(g) for g in m.groups())
        try:
            found.append((m.group(0), datetime(year, month, day)))
        except ValueError:
            continue
        full_spans.append(m.span())

    for m in _CN_YEAR_MONTH_RE.finditer(content):
        year, month = (int(g) for g in m.groups())
        try:
            found.append((m.group(0), datetime(year, month, 1)))
        except ValueError:
            continue

    for m in _CN_MONTH_DAY_RE.finditer(content):
        if any(s <= m.start() < e for s, e in full_spans):
            continue
        month, day = (int(g) for g in m.groups())
        year = pub_dt.year
        if month - pub_dt.month >= 11:
            year -= 1
        try:
            found.append((m.group(0), datetime(year, month, day)))
        except ValueError:
            continue

    unique: list[tuple[str, datetime]] = []
    seen: set[tuple[int, int, int]] = set()
    for raw, dt in found:
        key = (dt.year, dt.month, dt.day)
        if key in seen:
            continue
        seen.add(key)
        unique.append((raw, dt))
    return unique


def _check_timeline(content: str, source_data: dict[str, Any]) -> CheckResult:
    """Step 3: Verify that event dates in *content* are chronologically consistent."""
    name = "timeline"
    published_date: str = source_data.get("published_date", "")

    if not published_date:
        return {"name": name, "passed": True, "detail": "no published_date to check against"}

    # Try to parse the published_date
    try:
        pub_dt = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return {
            "name": name,
            "passed": True,
            "detail": f"cannot parse published_date: {published_date}",
        }

    # Strip timezone so naive content dates compare safely (an aware
    # published_date previously crashed the comparison with TypeError).
    if pub_dt.tzinfo is not None:
        pub_dt = pub_dt.replace(tzinfo=None)

    future_dates: list[str] = []
    for _raw, d in _iter_content_dates(content, pub_dt):
        if d > pub_dt:
            future_dates.append(d.strftime("%Y-%m-%d"))

    if future_dates:
        return {
            "name": name,
            "passed": False,
            "detail": f"dates after publication found: {future_dates}",
        }
    return {"name": name, "passed": True, "detail": "timeline consistent"}


def _check_quotes(content: str, source_data: dict[str, Any]) -> CheckResult:
    """Step 4: Verify that quotes in *content* match *source_data.quotes*."""
    name = "quotes"
    source_quotes: list[str] = source_data.get("quotes", [])

    if not source_quotes:
        return {"name": name, "passed": True, "detail": "no source quotes to verify"}

    content_lower = content.lower()
    missing: list[str] = [
        quote[:60] for quote in source_quotes if quote.lower() not in content_lower
    ]

    if missing:
        return {
            "name": name,
            "passed": False,
            "detail": f"{len(missing)} quote(s) not found in content",
        }
    return {"name": name, "passed": True, "detail": f"all {len(source_quotes)} quotes verified"}


def _check_entities(content: str, source_data: dict[str, Any]) -> CheckResult:
    """Step 5: Verify that key entity names in *content* match *source_data.entities*."""
    name = "entities"
    source_entities: list[str] = source_data.get("entities", [])

    if not source_entities:
        return {"name": name, "passed": True, "detail": "no source entities to verify"}

    content_lower = content.lower()
    missing: list[str] = [
        entity for entity in source_entities if entity.lower() not in content_lower
    ]

    if missing:
        return {"name": name, "passed": False, "detail": f"entities not found: {missing}"}
    return {"name": name, "passed": True, "detail": f"all {len(source_entities)} entities verified"}


# ---------------------------------------------------------------------------
# Plausibility check (no source material)
# ---------------------------------------------------------------------------

# #626 — the plausibility check used to fail marketing copy for ordinary
# rhetoric ("提高点击率" / "抓住眼球"), which is the *skeleton* of marketing
# text, not a factual defect.  The criteria now separate two things:
#
# A. an outcome-promise *token* hit is downgraded to advisory when the same
#    paragraph carries an evidence anchor (source, hedge, or number+unit);
# D. only a *verifiable assertion* may fail — a quantified outcome, a time
#    promise, or a ranking/comparative with no source/hedge anchor.
#
# Causal/rhetorical strength is advisory-only.  The direction is deliberate:
# a false pass is acceptable, a false kill is not.

# A source anchor makes a claim checkable by the reader.
_SOURCE_ANCHOR_RE = re.compile(
    r"据[^，。；\n]{0,24}(?:报告|研究|数据|统计|调查|显示|表明|指出)"
    r"|(?:报告|研究|数据|统计|调查)(?:显示|表明|指出|发现)"
    r"|(?:Gartner|IDC|Forrester|McKinsey|Nielsen|QuestMobile|CNNIC)"
    r"|(?:麦肯锡|艾瑞|尼尔森|国家统计局|世界银行)"
    r"|来源\s*[:：]"
)

# A conditional or negated claim is hedged: it promises effort/process, not a
# guaranteed outcome.
_CONDITIONAL_ANCHOR_RE = re.compile(
    r"不一定|未必|并非|并不是|不能保证|无法保证|并不能|很难保证|"
    r"需要时间|需要努力|需要投入|需要积累|"
    r"除非|如果|假如|可能|或许|往往|大多数|多数|通常|一般来说|仅供参考"
)

# A concrete number carrying a unit.  This anchors a *token* hit, but it does
# not by itself exempt a verifiable assertion: a number that quantifies the
# promise (「提升 300%」/「7 天见效」) still fails under (D).
_NUMBER_UNIT_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|％|倍|天|周|个月|月|年|小时|分钟|秒|"
    r"万|亿|元|人|家|个|次|项|条|份|款|GB|MB|G)"
)

_OUTCOME_WORDS = (
    "提升|提高|增长|增加|降低|减少|节省|达到|超过|翻倍|见效|学会|掌握|"
    "搞定|完成|打造|实现|达成|逆袭|成功|销量|转化|收入|回报|利润|效率|"
    "速度|成本|点击率"
)

# Quantified outcome: 「提升 300%」/「300% 销量」/「增长 2 倍」.
_QUANTIFIED_OUTCOME_RE = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:%|％|倍)[^，。；\n]{0,8}(?:" + _OUTCOME_WORDS + r"))"
    r"|(?:(?:" + _OUTCOME_WORDS + r")[^，。；\n]{0,8}\d+(?:\.\d+)?\s*(?:%|％|倍))"
)

# Time promise: 「7 天见效」/「5 分钟内打造」/「30 天学会」.
_TIME_PROMISE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:天|周|个月|月|年|小时|分钟|秒)[内之]?[^，。；\n]{0,8}"
    r"(?:" + _OUTCOME_WORDS + r"|见效|上手|瘦|减|赚|蜕变)"
)

# Ranking / comparative: 「行业第一」/「比 X 快 2 倍」/「最好」.
_RANKING_RE = re.compile(
    r"行业第一|全国第一|全球第一|世界第一|排名第一|第一名|销量第一|"
    r"最(?:好|佳|优|强|快|高|低|便宜)|"
    r"比[^，。；\n]{0,12}(?:快|高|低|强|多|少|好)[^，。；\n]{0,4}\d+\s*(?:%|％|倍)"
)

# Soft rhetorical tokens from the shared ban list: used as ordinary marketing
# modifiers they are not verifiable assertions.  They are advisory even without
# an explicit anchor (「播客音频，轻松打造品牌影响力」); a quantified promise
# containing them (「轻松提升 300%」) is still a verifiable assertion and fails.
_SOFT_RHETORICAL_TOKENS: frozenset[str] = frozenset(
    {"轻松", "轻松搞定", "爆款", "达人", "精准"}
)

# Causal / rhetorical strength: the ordinary skeleton of marketing copy.
# Flagged by the judge it is downgraded to advisory, never a failure.
_RHETORICAL_STRENGTH_RE = re.compile(
    r"扮演[^，。；\n]{0,8}角色|发挥[^，。；\n]{0,8}作用|"
    r"抓住[^，。；\n]{0,6}眼球|吸引[^，。；\n]{0,6}(?:眼球|注意)|"
    r"提高[^，。；\n]{0,8}(?:点击率|转化率|曝光|关注|销量)|"
    r"与用户互动|互动[^，。；\n]{0,6}过程|"
    r"重要角色|关键作用|很重要|事半功倍|"
    r"瞬间|轻松|爆款|达人|精准"
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;\n])")


def _has_source_anchor(text: str) -> bool:
    return bool(_SOURCE_ANCHOR_RE.search(text))


def _has_conditional_anchor(text: str) -> bool:
    return bool(_CONDITIONAL_ANCHOR_RE.search(text))


def _has_numeric_anchor(text: str) -> bool:
    return bool(_NUMBER_UNIT_RE.search(text))


def _claim_has_evidence_anchor(text: str) -> bool:
    """Token hit + same-paragraph evidence anchor → advisory (#626 A)."""
    return (
        _has_source_anchor(text)
        or _has_conditional_anchor(text)
        or _has_numeric_anchor(text)
    )


def _is_verifiable_assertion(text: str) -> bool:
    """A claim a reader can verify or refute (#626 D).

    Only quantified outcomes, time promises and rankings/comparatives qualify.
    Causal or rhetorical strength (「扮演重要角色」/「抓住眼球」/「提高点击率」)
    is not a verifiable assertion and is never failed.
    """
    return bool(
        _QUANTIFIED_OUTCOME_RE.search(text)
        or _TIME_PROMISE_RE.search(text)
        or _RANKING_RE.search(text)
    )


def _is_rhetorical_strength(text: str) -> bool:
    """Causal/rhetorical strength — advisory-only, never a fail."""
    return bool(_RHETORICAL_STRENGTH_RE.search(text))


def _iter_sentences(content: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(content or "") if part.strip()]


def _find_verifiable_assertions(content: str) -> list[str]:
    """Unanchored verifiable assertions — the only deterministic fail scope.

    A sourced assertion (「据 Gartner 2025 报告…」) or a hedged one
    (「并不能保证…」) is checkable but not questionable, so it is not failed.
    """
    found: list[str] = []
    for sentence in _iter_sentences(content):
        if not _is_verifiable_assertion(sentence):
            continue
        if _has_source_anchor(sentence) or _has_conditional_anchor(sentence):
            continue
        found.append(sentence)
    return found


def _issue_is_fail_worthy(text: str) -> bool:
    """Whether a judge-flagged claim is inside the fail scope (#626 D).

    Sourced/hedged claims and rhetorical strength are advisory.  Any other
    concrete factual claim (e.g. 「The Earth is flat」) keeps the pre-existing
    behaviour and still fails.
    """
    if _has_source_anchor(text) or _has_conditional_anchor(text):
        return False
    if _is_verifiable_assertion(text):
        return True
    return not _is_rhetorical_strength(text)


def _flagged_claim_texts(result: G0CheckResult) -> list[str]:
    """Sentence-level texts a judge flagged, falling back to issue strings."""
    texts: list[str] = []
    for issue in result.structured_issues or []:
        sentence = issue.get("sentence")
        if isinstance(sentence, str) and sentence.strip():
            texts.append(sentence.strip())
    texts.extend(str(issue) for issue in result.issues)
    return texts


def _build_hook_claim_failure(
    violations: list[HookClaimHit],
    advisories: list[str] | None = None,
) -> dict[str, Any]:
    """Deterministic plausibility failure naming the banned hook tokens (#520).

    The hook-claim criteria share the HOOK CLAIMS ban list with the content
    writer (``automedia/prompts/hook_claims.py`` — the one copy): a pure
    guarantee-style hook is rejected here without an LLM round-trip, while a
    hedged, checkable statement of the same intent yields no hits and
    continues to the LLM judge. The result shape mirrors the LLM path exactly
    (one ``plausibility_check`` check) so gate-report consumers see one shape.
    """
    tokens_by_area: dict[str, list[str]] = {}
    for hit in violations:
        bucket = tokens_by_area.setdefault(hit.area, [])
        if hit.token not in bucket:
            bucket.append(hit.token)
    locations = "；".join(f"{area}: {'、'.join(tokens)}" for area, tokens in tokens_by_area.items())
    first_sentence = violations[0].text
    check: CheckResult = {
        "name": "plausibility_check",
        "passed": False,
        "detail": (
            "outcome-promise token(s) in hook area "
            f"({locations}) — 「{first_sentence}」 promises an outcome the "
            "reader cannot verify rather than stating a hedged, checkable "
            "observation (same shared HOOK CLAIMS ban list as the content "
            "writer constraint)"
        ),
    }
    # Additive sentence hint so the persisted reason points at the offending
    # block directly (same key the LLM path enriches).
    check["sentence"] = first_sentence
    gate_result = build_gate_result(
        [check],
        gate="G0",
        expected_map={
            "plausibility_check": (
                "Hook-area claims are hedged and checkable — no outcome-promise "
                "token from the shared HOOK CLAIMS ban list"
            )
        },
        confidence=0.0,
        method="deterministic",
        status="completed",
    )
    gate_result["error"] = _build_failure_reason([check])
    if advisories:
        gate_result["advisories"] = list(advisories)
    return gate_result


def _build_verifiable_assertion_failure(
    assertions: list[str],
    advisories: list[str] | None = None,
) -> dict[str, Any]:
    """Deterministic failure for an unanchored verifiable assertion (#626 D).

    Unlike the token path, this fires on what the sentence *claims* — a
    specific number/percentage/time promise or a ranking/comparative with no
    source or hedge in the same sentence.  Rhetorical strength never reaches
    this branch.
    """
    first = assertions[0]
    check: CheckResult = {
        "name": "plausibility_check",
        "passed": False,
        "detail": (
            "verifiable assertion(s) without a source anchor — "
            f"「{first}」 makes a specific, checkable claim (number / time "
            "promise / ranking) that the content does not support"
        ),
        "sentence": first,
    }
    hints = _issue_details(first)
    if hints.get("number"):
        check["number"] = hints["number"]
    gate_result = build_gate_result(
        [check],
        gate="G0",
        expected_map={
            "plausibility_check": (
                "Verifiable assertions carry a source/hedge anchor; rhetorical "
                "strength is advisory only"
            )
        },
        confidence=0.0,
        method="deterministic",
        status="completed",
    )
    gate_result["error"] = _build_failure_reason([check])
    if advisories:
        gate_result["advisories"] = list(advisories)
    return gate_result


def _run_plausibility_check(
    content: str,
    topic: str,
    platform: str = "",
    gate_context: GateContext | dict[str, Any] | None = None,
    rewrite_allowed: bool = False,
) -> dict[str, Any] | None:
    """Run LLM-based plausibility check when no source material is available.

    Uses the LLM's general knowledge to flag factually questionable claims.

    Parameters
    ----------
    content:
        The generated content to evaluate.
    topic:
        The article topic (passed into the prompt for context).
    gate_context:
        The full gate context — forwarded to :func:`_finalize_failure` so a
        failing plausibility check gets the same one-shot rewrite the
        source-data path gets (#520: the rewrite template's rule 5 hunts the
        very tokens the hook-claim criteria flag; without it a deterministic
        rejection is unrecoverable because the quality retry would re-judge
        the same text).
    rewrite_allowed:
        Whether the one-shot rewrite may be attempted (``enable_llm``).

    Returns
    -------
    dict[str, Any] | None
        A full ``build_gate_result`` dict on success, or ``None`` on failure
        (the caller should fall back to ``"skipped"`` status).
    """
    try:
        # Deterministic hook-claim criteria (#520 phase 2): the same HOOK
        # CLAIMS ban list the content writer is held to, scanned over the
        # same hook areas. Guarantee-style hooks are rejected here directly;
        # hedged, checkable statements pass through to the LLM judge below,
        # whose prompt carries the same list plus the explicit rule that a
        # hedged, checkable statement is not questionable.
        advisories: list[str] = []
        failing_violations: list[HookClaimHit] = []
        for hit in hook_area_violations(content):
            if _claim_has_evidence_anchor(hit.text):
                advisories.append(
                    f"outcome-promise token 「{hit.token}」 in {hit.area} has an "
                    f"evidence anchor — advisory only: 「{hit.text}」"
                )
            elif _is_rhetorical_strength(hit.text) and not _is_verifiable_assertion(
                hit.text
            ):
                # A token used as ordinary marketing rhetoric (「轻松打造品牌
                # 影响力」) is not a verifiable assertion — advisory only, even
                # without an explicit anchor (#626 D).  A guarantee/absolute
                # token still fails here; quantified promises are caught by the
                # verifiable-assertion scan below.
                advisories.append(
                    f"outcome-promise token 「{hit.token}」 in {hit.area} is "
                    f"rhetorical strength, not a verifiable assertion — advisory "
                    f"only: 「{hit.text}」"
                )
            else:
                failing_violations.append(hit)
        if failing_violations:
            return _finalize_failure(
                _build_hook_claim_failure(failing_violations, advisories),
                gate_context or {},
                rewrite_allowed=rewrite_allowed,
            )

        verifiable_assertions = _find_verifiable_assertions(content)
        if verifiable_assertions:
            return _finalize_failure(
                _build_verifiable_assertion_failure(verifiable_assertions, advisories),
                gate_context or {},
                rewrite_allowed=rewrite_allowed,
            )

        prompt = load_prompt(
            "fact_check_g0_plausibility",
            content=content,
            topic=topic,
            platform=platform,
        )

        result = llm_complete_structured_safe(
            prompt,
            response_format=G0CheckResult,
        )

        check_name = "plausibility_check"

        llm_passed = result.passed
        if result.passed:
            detail = "All claims appear factually plausible based on general knowledge"
        else:
            # #626 D: the judge may only fail verifiable assertions.  Rhetorical
            # or causal strength (「扮演重要角色」/「抓住眼球」/「提高点击率」)
            # is downgraded to an advisory instead of killing the gate.  A
            # concrete factual claim the judge rejects (e.g. 「The Earth is
            # flat」) keeps the pre-existing fail behaviour.
            flagged = _flagged_claim_texts(result)
            fail_worthy = [text for text in flagged if _issue_is_fail_worthy(text)]
            if not fail_worthy:
                llm_passed = True
                advisories.extend(
                    f"judge flagged non-verifiable claim (advisory only): {issue}"
                    for issue in result.issues
                )
                detail = "No verifiable assertions found questionable"
            else:
                detail = "; ".join(result.issues) if result.issues else "Questionable claims found"

        check: CheckResult = {
            "name": check_name,
            "passed": llm_passed,
            "detail": detail,
        }

        gate_result = build_gate_result(
            [check],
            gate="G0",
            expected_map={
                check_name: "All claims are factually plausible based on general knowledge"
            },
            confidence=result.confidence,
            method="llm",
            status="completed",
        )
        if advisories:
            gate_result["advisories"] = list(advisories)
        if gate_result.get("passed") is False:
            _enrich_failing_checks_with_issue_details([check], result.structured_issues)
            gate_result["error"] = _build_failure_reason([check])
            return _finalize_failure(
                gate_result,
                gate_context or {},
                rewrite_allowed=rewrite_allowed,
                structured_issues=result.structured_issues,
            )
        return gate_result

    except Exception:
        log.warning(
            "LLM plausibility check failed, falling back to skipped",
            exc_info=True,
        )
        return None


# ---------------------------------------------------------------------------
# Issue #219 — structured failure reason + one-shot rewrite
# ---------------------------------------------------------------------------

_ISSUE_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*%?")
_ISSUE_SENTENCE_RE = re.compile(r"[「『“\"]([^」』”\"\n]+)[」』”\"]")


def _issue_details(text: str) -> dict[str, Any]:
    """Derive sentence/number/missing-citation hints from issue *text*.

    Returns only the keys it can establish; callers attach them additively to
    a failing check and never overwrite an existing key.
    """
    details: dict[str, Any] = {}
    number_match = _ISSUE_NUMBER_RE.search(text)
    if number_match:
        number = number_match.group(0).strip()
        if number:
            details["number"] = number
    sentence_match = _ISSUE_SENTENCE_RE.search(text)
    if sentence_match:
        sentence = sentence_match.group(1).strip()
        if sentence:
            details["sentence"] = sentence
    lowered = text.lower()
    if "citation" in lowered or "source material" in lowered:
        details["missing_citation"] = True
    return details


def _enrich_failing_checks_with_issue_details(
    checks: list[CheckResult],
    structured_issues: list[dict[str, Any]] | None = None,
) -> None:
    """Additively attach sentence/number/missing_citation to failing checks.

    Heuristics read each failing check's own ``detail``; explicit
    ``structured_issues`` entries returned by the LLM (the richest source)
    then override the first failing check.  Passing checks are untouched and
    existing keys are never renamed or removed.
    """
    failing = [check for check in checks if not check.get("passed")]
    if not failing:
        return
    for check in failing:
        hints = _issue_details(str(check.get("detail", "")))
        number = hints.get("number")
        if isinstance(number, str) and number:
            check["number"] = number
        sentence = hints.get("sentence")
        if isinstance(sentence, str) and sentence:
            check["sentence"] = sentence
        if hints.get("missing_citation") is True:
            check["missing_citation"] = True
    for issue in structured_issues or []:
        target = failing[0]
        structured_sentence = issue.get("sentence")
        if isinstance(structured_sentence, str) and structured_sentence.strip():
            target["sentence"] = structured_sentence
        structured_number = issue.get("number")
        if isinstance(structured_number, str) and structured_number.strip():
            target["number"] = structured_number
        structured_missing = issue.get("missing_citation")
        if structured_missing is not None:
            target["missing_citation"] = bool(structured_missing)


def _build_failure_reason(checks: list[CheckResult]) -> str:
    """Compose a non-empty failure summary naming the failing checks.

    Every failing check contributes ``name: detail`` (with a derivable
    number/sentence hint appended), so a persisted reason points at the
    offending sentence and figure instead of a bare "failed".
    """
    fragments: list[str] = []
    for check in checks:
        if check.get("passed"):
            continue
        name = str(check.get("name", "?"))
        detail = str(check.get("detail", "")).strip()
        fragment = f"{name}: {detail}" if detail else name
        hints = _issue_details(detail)
        if hints.get("number"):
            fragment += f" [number={hints['number']}]"
        if hints.get("sentence"):
            fragment += f" [sentence={hints['sentence']}]"
        fragments.append(fragment)
    if not fragments:
        return "G0 fact-check failed: no specific reason reported"
    return "G0 fact-check failed — " + "; ".join(dict.fromkeys(fragments))


def _attempt_g0_rewrite(content: str, reason: str) -> str | None:
    """Request one structured rewrite; return content or ``None`` (fail-closed).

    Any provider/parse exception or an empty result yields ``None`` so the
    caller emits no ``modified_content``; the failing result still carries its
    structured ``error``.
    """
    try:
        prompt = load_prompt(
            "fact_check_g0_rewrite",
            content=content,
            failure_reason=reason,
        )
        rewrite = llm_complete_structured_safe(prompt, response_format=G0RewriteResult)
    except Exception:
        log.warning("G0 rewrite attempt failed (fail-closed)", exc_info=True)
        return None
    rewritten = getattr(rewrite, "rewritten_content", None)
    if not isinstance(rewritten, str) or not rewritten.strip():
        log.warning("G0 rewrite returned empty content (fail-closed)")
        return None
    # #598: hedge the closed token list deterministically — an LLM rewrite that
    # leaves a banned token in the hook area would re-detect it on retry.
    hedged = hedge_hook_claims(rewritten)
    leftover = hook_area_violations(hedged)
    if leftover:
        log.warning(
            "g0.hedge_leftover",
            tokens=sorted({hit.token for hit in leftover}),
        )
    return hedged


def _finalize_failure(
    result: dict[str, Any],
    gate_context: GateContext | dict[str, Any],
    *,
    rewrite_allowed: bool,
    structured_issues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attach a structured reason and (once) a one-shot rewrite to *result*.

    Passing results are returned unchanged (``error`` stays ``None``).  A
    failing result always gains a non-empty ``error``.  When *rewrite_allowed*
    and no rewrite has been attempted yet in this run, exactly one structured
    rewrite is requested: the attempt flag is set BEFORE the call, so a failed
    call can never produce a second attempt.
    """
    if result.get("passed") is not False:
        return result
    checks: list[CheckResult] = result.get("checks") or []
    _enrich_failing_checks_with_issue_details(checks, structured_issues)
    if not result.get("error"):
        result["error"] = _build_failure_reason(checks)
    if not rewrite_allowed or gate_context.get("_g0_rewrite_attempted"):
        return result
    gate_context["_g0_rewrite_attempted"] = True
    content = str(gate_context.get("content", "") or "").strip()
    if not content:
        return result
    rewritten = _attempt_g0_rewrite(content, str(result["error"]))
    if rewritten:
        result["modified_content"] = rewritten
    return result


# ---------------------------------------------------------------------------
# G0FactCheck gate
# ---------------------------------------------------------------------------


class G0FactCheck(BaseGate):
    """G0 Fact-Check Gate — 5-step verification of content against source data.

    ``gate_context`` expected keys:
        - ``topic``: str — topic of the content
        - ``content``: str — generated content to fact-check
        - ``source_data``: dict with keys:
            - ``url``: str
            - ``published_date``: str (ISO format)
            - ``key_numbers``: dict[str, str]
            - ``entities``: list[str]
            - ``quotes``: list[str]
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing without an LLM.
    """

    _gate_name = "G0"
    _failure_mode = "retry"
    max_quality_retries: ClassVar[int | None] = 1
    halt_on_exhaustion: ClassVar[bool] = True
    # #626 C: a G0 failure is recorded, but it must not erase the downstream
    # gates (G1/G2/G3/G6/H0) from the report.  They judge their own dimensions
    # and each must report its own verdict; the failure stays visible on G0.
    continue_on_exhaustion: ClassVar[bool] = True

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run 5-step fact-check and return structured result."""
        content: str = gate_context.get("content", "")
        source_data: dict[str, Any] | None = gate_context.get("source_data")
        source_url: str = (source_data or {}).get("url", "")

        config: dict[str, Any] = gate_context.get("config", {})
        enable_llm: bool = config.get("enable_llm", True) if isinstance(config, dict) else True

        # Detect target platform for platform-scoped prompt overrides
        brand_platforms: list[str] = gate_context.get("brand_platforms", [])
        platform: str = brand_platforms[0] if brand_platforms else ""

        # When no source material is provided, attempt LLM plausibility check or skip
        if not source_data:
            if enable_llm:
                topic: str = gate_context.get("topic", "")
                plausibility_result = _run_plausibility_check(
                    content,
                    topic,
                    platform=platform,
                    gate_context=gate_context,
                    rewrite_allowed=enable_llm,
                )
                if plausibility_result is not None:
                    return plausibility_result

            return {
                "passed": True,
                "gate": "G0",
                "status": "skipped",
                "reason": "No source material provided — factual verification skipped",
            }

        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        if mock_results is not None:
            checks: list[CheckResult] = []
            for name in _CHECK_NAMES:
                if name in mock_results:
                    mock = mock_results[name]
                    checks.append(
                        {
                            "name": name,
                            "passed": bool(mock["passed"]),
                            "detail": str(mock.get("detail", "")),
                        }
                    )
                else:
                    checks.append({"name": name, "passed": True, "detail": ""})

            return _finalize_failure(
                build_gate_result(
                    checks,
                    gate="G0",
                    expected_map=_EXPECTED_MAP,
                    confidence=round(
                        sum(1 for c in checks if c["passed"]) / len(checks) if checks else 0.0,
                        4,
                    ),
                ),
                gate_context,
                rewrite_allowed=False,
            )

        if enable_llm:
            # Mutable container captures per-step checks from deterministic fallback closure
            captured_checks: list[CheckResult] = []

            def _deterministic_fn(_text: str) -> LLMCheckResult:
                det_checks = _run_deterministic_checks(content, source_url, source_data)
                captured_checks.extend(det_checks)
                return {
                    "passed": all(c["passed"] for c in det_checks),
                    "issues": [c["detail"] for c in det_checks if not c["passed"]],
                }

            llm_result = llm_check_with_fallback(
                text=content,
                check_type="fact_check",
                prompt_template_name="fact_check_g0",
                deterministic_fn=_deterministic_fn,
                source_data=source_data,
                platform=platform,
            )

            method = llm_result.get("method", "deterministic")

            if method == "deterministic" and captured_checks:
                checks = captured_checks
            else:
                passed = llm_result["passed"]
                issues = llm_result.get("issues", [])
                detail = (
                    "; ".join(issues)
                    if issues
                    else ("verified by LLM" if passed else "fact-check failed")
                )
                checks = [
                    {"name": name, "passed": passed, "detail": detail} for name in _CHECK_NAMES
                ]

            confidence = llm_result.get("confidence")
            if confidence is None:
                confidence = round(
                    sum(1 for c in checks if c["passed"]) / len(checks) if checks else 0.0,
                    4,
                )

            log.info("G0 fact-check method=%s passed=%s", method, llm_result["passed"])

            return _finalize_failure(
                build_gate_result(
                    checks,
                    gate="G0",
                    expected_map=_EXPECTED_MAP,
                    confidence=confidence,
                    method=method,
                ),
                gate_context,
                rewrite_allowed=enable_llm,
                structured_issues=llm_result.get("structured_issues", []),
            )

        checks = _run_deterministic_checks(content, source_url, source_data)
        return _finalize_failure(
            build_gate_result(
                checks,
                gate="G0",
                expected_map=_EXPECTED_MAP,
                confidence=round(
                    sum(1 for c in checks if c["passed"]) / len(checks) if checks else 0.0,
                    4,
                ),
                method="deterministic",
            ),
            gate_context,
            rewrite_allowed=False,
        )
