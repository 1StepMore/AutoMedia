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
from typing import Any

from structlog import get_logger

from automedia.core.llm_client import llm_complete_structured_safe
from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result
from automedia.gates.base import BaseGate
from automedia.gates.llm_helpers import G0CheckResult, LLMCheckResult, llm_check_with_fallback
from automedia.prompts import load_prompt

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


def _run_plausibility_check(
    content: str,
    topic: str,
    platform: str = "",
) -> dict[str, Any] | None:
    """Run LLM-based plausibility check when no source material is available.

    Uses the LLM's general knowledge to flag factually questionable claims.

    Parameters
    ----------
    content:
        The generated content to evaluate.
    topic:
        The article topic (passed into the prompt for context).

    Returns
    -------
    dict[str, Any] | None
        A full ``build_gate_result`` dict on success, or ``None`` on failure
        (the caller should fall back to ``"skipped"`` status).
    """
    try:
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

        if result.passed:
            detail = "All claims appear factually plausible based on general knowledge"
        else:
            detail = "; ".join(result.issues) if result.issues else "Questionable claims found"

        check: CheckResult = {
            "name": check_name,
            "passed": result.passed,
            "detail": detail,
        }

        return build_gate_result(
            [check],
            gate="G0",
            expected_map={
                check_name: "All claims are factually plausible based on general knowledge"
            },
            confidence=result.confidence,
            method="llm",
            status="completed",
        )

    except Exception:
        log.warning(
            "LLM plausibility check failed, falling back to skipped",
            exc_info=True,
        )
        return None


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
    _failure_mode = "stop"

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
                plausibility_result = _run_plausibility_check(content, topic, platform=platform)
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

            return build_gate_result(
                checks,
                gate="G0",
                expected_map=_EXPECTED_MAP,
                confidence=round(
                    sum(1 for c in checks if c["passed"]) / len(checks) if checks else 0.0,
                    4,
                ),
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

            return build_gate_result(
                checks,
                gate="G0",
                expected_map=_EXPECTED_MAP,
                confidence=confidence,
                method=method,
            )

        checks = _run_deterministic_checks(content, source_url, source_data)
        return build_gate_result(
            checks,
            gate="G0",
            expected_map=_EXPECTED_MAP,
            confidence=round(
                sum(1 for c in checks if c["passed"]) / len(checks) if checks else 0.0,
                4,
            ),
            method="deterministic",
        )
