"""G1 Humanizer Gate — 9-category AI writing pattern detection and rewriting.

Detects and rewrites common AI-generated text patterns:

    1. overused_adverbs       — 过度副词 (importantly, notably, significantly)
    2. hollow_intros           — 空洞引言 (In today's world, It's worth noting)
    3. vague_subjects          — 笼统主语 (We must, We need to)
    4. filler_connectors       — 废话连接词 (Furthermore, Moreover, Additionally)
    5. long_conjunctions       — 过长并列结构
    6. template_conclusions    — 模板化总结 (In conclusion, To sum up)
    7. overacademic_vocabulary — 过度学术化词汇 (utilize → use)
    8. absolute_assertions     — 绝对化断言 (always, never, everyone knows)
    9. repetitive_structures   — 重复性结构

    Categories 2-4, 6-8 also match Chinese AI-taste patterns (空洞开头,
    笼统主语, 句首废话连接词, 模板化总结, 官腔黑话, 绝对化表述); the
    sentence splitter handles Chinese sentence-enders (。！？) so all
    sentence-based checks work on Chinese text.

When ``gate_context["_mock_results"]`` is present, each check's result is
driven from that dict instead of running real detection — making the gate
fully deterministic for unit testing.

Humanize→verify closed loop (issue #62, Wave-B B4): when enabled via
``gate_context["config"]["gates"]["humanizer"]["verify_loop"]``
(``enabled: true``, ``max_iterations`` >= 1, default 3), the rewritten
output is verified with the deterministic AI-taste detector from
``automedia.detectors`` and the gate iterates rewrite→verify up to the
budget.  The result then exposes ``detector_score`` (final ai_score) and
``verify_iterations``.  The loop is OFF by default and never changes the
result shape when disabled.
"""

from __future__ import annotations

import os
import re
from typing import Any

from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result
from automedia.gates.base import BaseGate
from automedia.gates.llm_helpers import LLMCheckResult, llm_check_with_fallback

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "overused_adverbs",
    "hollow_intros",
    "vague_subjects",
    "filler_connectors",
    "long_conjunctions",
    "template_conclusions",
    "overacademic_vocabulary",
    "absolute_assertions",
    "repetitive_structures",
]

# Pattern 1: Overused adverbs
_OVERUSED_ADVERBS: list[str] = [
    "importantly",
    "notably",
    "significantly",
    "essentially",
    "fundamentally",
    "undoubtedly",
    "remarkably",
    "exceptionally",
    "particularly",
    "critically",
    "crucially",
    "inherently",
    "unquestionably",
]
_ADVERB_RE = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in _OVERUSED_ADVERBS) + r")\b",
    re.IGNORECASE,
)

# Pattern 2: Hollow intros
_HOLLOW_INTROS: list[str] = [
    r"(?i)^In today'?s world[,.]?\s*",
    r"(?i)^It'?s worth noting that\s*",
    r"(?i)^It is worth noting that\s*",
    r"(?i)^It goes without saying that\s*",
    r"(?i)^In the modern era[,.]?\s*",
    r"(?i)^With the advent of\s+[\w\s]+[,.]?\s*",
    r"(?i)^It'?s important to note that\s*",
    r"(?i)^In this day and age[,.]?\s*",
    r"(?i)^As we all know[,.]?\s*",
    r"(?i)^Needless to say[,.]?\s*",
    # Chinese hollow intros (空洞开头) — sentence-initial AI-taste openers
    r"^值得注意的是[，,]?",
    r"^值得一提的是[，,]?",
    r"^总的来说[，,]?",
    r"^众所周知[，,]?",
    r"^不难发现[，,]?",
    r"^在当今社会[，,]?",
    r"^在当今时代[，,]?",
    r"^我们需要认识到[，,]?",
    r"^不可否认的是[，,]?",
    r"^随着[^。！？，,]+的发展[，,]?",
]
_HOLLOW_INTRO_RES: list[re.Pattern[str]] = [re.compile(p) for p in _HOLLOW_INTROS]

# Pattern 3: Vague subjects
_VAGUE_SUBJECTS: list[str] = [
    r"(?i)^We must\b",
    r"(?i)^We need to\b",
    r"(?i)^We should\b",
    r"(?i)^One should\b",
    r"(?i)^It is important to\b",
    r"(?i)^It is essential to\b",
    r"(?i)^It is crucial to\b",
    # Chinese vague subjects (笼统主语)
    r"^我们应该",
    r"^我们必须",
    r"^我们需要",
    r"^大家都要",
]
_VAGUE_SUBJECT_RES: list[re.Pattern[str]] = [re.compile(p) for p in _VAGUE_SUBJECTS]

# Pattern 4: Filler connectors (sentence-initial)
_FILLER_CONNECTORS: list[str] = [
    "Furthermore",
    "Moreover",
    "Additionally",
    "In addition",
    "Consequently",
    "Nevertheless",
    "Nonetheless",
    "Notwithstanding",
    "Subsequently",
    "Henceforth",
]
_FILLER_RE = re.compile(
    r"(?i)^(?:" + "|".join(re.escape(c) for c in _FILLER_CONNECTORS) + r")[,.]?\s+",
)

# Pattern 4b: Chinese filler connectors — sentence-initial, but Chinese has
# no whitespace after punctuation, so the suffix rule differs from _FILLER_RE
_CN_FILLER_CONNECTORS: list[str] = [
    "更为重要的是",
    "与此同时",
    "总而言之",
    "综上所述",
    "由此可见",
    "另一方面",
    "更重要的是",
    "一方面",
    "此外",
    "然而",
    "因此",
    "首先",
    "其次",
    "最后",
]
_CN_FILLER_RE = re.compile(
    r"^(?:" + "|".join(re.escape(c) for c in _CN_FILLER_CONNECTORS) + r")[，,]?",
)

# Pattern 5: Long conjunctions (3+ "and"/"or" in a single sentence)
_LONG_CONJUNCTION_RE = re.compile(
    r"(?:\b(?:and|or)\b.*?){3,}",
    re.IGNORECASE | re.DOTALL,
)

# Pattern 6: Template conclusions
_TEMPLATE_CONCLUSIONS: list[str] = [
    r"(?i)^In conclusion[,.]?\s*",
    r"(?i)^To sum up[,.]?\s*",
    r"(?i)^To summarize[,.]?\s*",
    r"(?i)^In summary[,.]?\s*",
    r"(?i)^All in all[,.]?\s*",
    r"(?i)^In essence[,.]?\s*",
    r"(?i)^To conclude[,.]?\s*",
    r"(?i)^Wrapping up[,.]?\s*",
    # Chinese template conclusions (模板化总结) — longer phrases first so that
    # e.g. 总而言之 wins over its prefix 总之
    r"^综上所述[，,]?",
    r"^总而言之[，,]?",
    r"^由此可见[，,]?",
    r"^总的来说[，,]?",
    r"^总之[，,]?",
]
_TEMPLATE_CONCLUSION_RES: list[re.Pattern[str]] = [re.compile(p) for p in _TEMPLATE_CONCLUSIONS]

# Pattern 7: Over-academic vocabulary (word → replacement)
_ACADEMIC_REPLACEMENTS: dict[str, str] = {
    "utilize": "use",
    "utilises": "uses",
    "utilizes": "uses",
    "utilised": "used",
    "utilized": "used",
    "utilising": "using",
    "utilizing": "using",
    "leverage": "use",
    "leverages": "uses",
    "leveraged": "used",
    "leveraging": "using",
    "facilitate": "help",
    "facilitates": "helps",
    "facilitated": "helped",
    "facilitating": "helping",
    "commence": "start",
    "commences": "starts",
    "commenced": "started",
    "commencing": "starting",
    "implement": "carry out",
    "implements": "carries out",
    "implemented": "carried out",
    "implementing": "carrying out",
    "endeavor": "try",
    "endeavors": "tries",
    "endeavoured": "tried",
    "paradigm": "model",
    "synergy": "teamwork",
    "holistic": "comprehensive",
    "multifaceted": "complex",
    "pivotal": "key",
    "robust": "strong",
    "paradigms": "models",
}
_ACADEMIC_WORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _ACADEMIC_REPLACEMENTS) + r")\b",
    re.IGNORECASE,
)

# Pattern 7b: Chinese officialese / buzzwords (官腔黑话) — detection only;
# \b boundaries do not apply between CJK characters, so a separate regex is
# used. 生态 is guarded so the legitimate 生态系统 is not flagged.
_CN_ACADEMIC_PATTERNS: list[str] = [
    r"赋能",
    r"抓手",
    r"闭环",
    r"颗粒度",
    r"底层逻辑",
    r"生态(?!系统)",
]
_CN_ACADEMIC_RE = re.compile("|".join(_CN_ACADEMIC_PATTERNS))

# Pattern 8: Absolute assertions
_ABSOLUTE_PATTERNS: list[str] = [
    r"\balways\b",
    r"\bnever\b",
    r"\beveryone knows\b",
    r"\bundeniably\b",
    r"\bwithout exception\b",
    r"\babsolutely\b",
    r"\bno one can deny\b",
    r"\bit is universally\b",
    r"\bthere is no doubt\b",
    # Chinese absolute assertions (绝对化表述) — multi-char strong forms only,
    # so neutral technical uses of 绝对/必然 (绝对值, 必然事件) stay unflagged
    r"毫无疑问",
    r"毋庸置疑",
    r"一定会",
    r"永远不会",
    r"所有人都",
    r"没有任何人",
    r"唯一的方法",
    r"绝对不可能",
    r"必然会",
]
_ABSOLUTE_RE = re.compile(
    "|".join(_ABSOLUTE_PATTERNS),
    re.IGNORECASE,
)

# Pattern 9: Repetitive structures — same word starting 3+ consecutive sentences
#
# Sentence splitter: splits after English [.!?] followed by whitespace (as
# before) AND after Chinese sentence-enders 。！？ — where the next character
# is a CJK character the split is zero-width because Chinese text has no
# spaces. English-only text behaves exactly as the previous regex.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])(?:\s+|(?=[\u4e00-\u9fff]))")


_EXPECTED_MAP: dict[str, str] = {
    "overused_adverbs": "No overused adverbs in content",
    "hollow_intros": "No hollow introductory phrases",
    "vague_subjects": "No vague/generic subject constructions",
    "filler_connectors": "No filler connectors at sentence starts",
    "long_conjunctions": "No overly long conjunction chains",
    "template_conclusions": "No template-style conclusion phrases",
    "overacademic_vocabulary": "No over-academic vocabulary",
    "absolute_assertions": "No absolute assertion patterns",
    "repetitive_structures": "No repetitive sentence-opening structures",
}

# ---------------------------------------------------------------------------
# Humanize→verify closed loop config (issue #62, Wave-B B4)
# ---------------------------------------------------------------------------

_VERIFY_LOOP_ENV = "AUTOMEDIA_HUMANIZER_VERIFY_LOOP"
_VERIFY_LOOP_DEFAULT_ITERATIONS = 3


def _resolve_verify_loop_config(config: dict[str, Any] | None) -> tuple[bool, int]:
    """Resolve the humanize→verify loop toggle, returning (enabled, max_iterations).

    Primary source — the merged config in ``gate_context["config"]``:

        gates:
          humanizer:
            verify_loop:
              enabled: false      # bool, default False (loop OFF by default)
              max_iterations: 3   # int, default 3, coerced to >= 1

    Backstop — env var ``AUTOMEDIA_HUMANIZER_VERIFY_LOOP`` (any value other
    than ``""`` or ``"0"`` enables the loop with the config/default budget).
    """
    cfg = config if isinstance(config, dict) else {}
    gates_cfg = cfg.get("gates")
    humanizer_cfg = gates_cfg.get("humanizer") if isinstance(gates_cfg, dict) else None
    vloop_cfg = humanizer_cfg.get("verify_loop") if isinstance(humanizer_cfg, dict) else None
    vloop = vloop_cfg if isinstance(vloop_cfg, dict) else {}

    enabled = bool(vloop.get("enabled", False))
    env_flag = os.environ.get(_VERIFY_LOOP_ENV, "")
    if env_flag.strip() not in ("", "0"):
        enabled = True

    try:
        max_iterations = int(vloop.get("max_iterations", _VERIFY_LOOP_DEFAULT_ITERATIONS))
    except (TypeError, ValueError):
        max_iterations = _VERIFY_LOOP_DEFAULT_ITERATIONS
    return enabled, max(1, max_iterations)


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_overused_adverbs(content: str) -> CheckResult:
    """Check 1: Detect overused adverbs."""
    matches = _ADVERB_RE.findall(content)
    if not matches:
        return {"name": "overused_adverbs", "passed": True, "detail": "no overused adverbs found"}
    found = list(set(m.lower() for m in matches))
    return {
        "name": "overused_adverbs",
        "passed": False,
        "detail": f"found {len(matches)} overused adverb(s): {', '.join(sorted(found))}",
    }


def _check_hollow_intros(content: str) -> CheckResult:
    """Check 2: Detect hollow introductory phrases."""
    sentences = _SENTENCE_SPLIT_RE.split(content.strip())
    found: list[str] = []
    for sent in sentences:
        for pat in _HOLLOW_INTRO_RES:
            m = pat.search(sent)
            if m:
                found.append(m.group().strip().rstrip(",，."))
                break
    if not found:
        return {"name": "hollow_intros", "passed": True, "detail": "no hollow intros found"}
    return {
        "name": "hollow_intros",
        "passed": False,
        "detail": f"found {len(found)} hollow intro(s): {', '.join(found[:5])}",
    }


def _check_vague_subjects(content: str) -> CheckResult:
    """Check 3: Detect vague/generic subject constructions."""
    sentences = _SENTENCE_SPLIT_RE.split(content.strip())
    found: list[str] = []
    for sent in sentences:
        for pat in _VAGUE_SUBJECT_RES:
            m = pat.search(sent)
            if m:
                found.append(m.group().strip())
                break
    if not found:
        return {"name": "vague_subjects", "passed": True, "detail": "no vague subjects found"}
    return {
        "name": "vague_subjects",
        "passed": False,
        "detail": f"found {len(found)} vague subject(s): {', '.join(found[:5])}",
    }


def _check_filler_connectors(content: str) -> CheckResult:
    """Check 4: Detect filler connectors at sentence starts."""
    sentences = _SENTENCE_SPLIT_RE.split(content.strip())
    found: list[str] = []
    for sent in sentences:
        m = _FILLER_RE.match(sent)
        if m is None:
            m = _CN_FILLER_RE.match(sent)
        if m:
            found.append(m.group().strip().rstrip(",，."))
    if not found:
        return {"name": "filler_connectors", "passed": True, "detail": "no filler connectors found"}
    return {
        "name": "filler_connectors",
        "passed": False,
        "detail": f"found {len(found)} filler connector(s): {', '.join(found)}",
    }


def _check_long_conjunctions(content: str) -> CheckResult:
    """Check 5: Detect overly long conjunction chains."""
    sentences = _SENTENCE_SPLIT_RE.split(content.strip())
    found: list[str] = []
    for sent in sentences:
        # Count "and"/"or" occurrences in a single sentence
        and_count = len(re.findall(r"\band\b", sent, re.IGNORECASE))
        or_count = len(re.findall(r"\bor\b", sent, re.IGNORECASE))
        if and_count + or_count >= 3:
            snippet = sent[:80] + ("..." if len(sent) > 80 else "")
            found.append(snippet)
    if not found:
        return {
            "name": "long_conjunctions",
            "passed": True,
            "detail": "no long conjunction chains found",
        }
    return {
        "name": "long_conjunctions",
        "passed": False,
        "detail": f"found {len(found)} sentence(s) with 3+ conjunctions",
    }


def _check_template_conclusions(content: str) -> CheckResult:
    """Check 6: Detect template-style conclusion phrases."""
    sentences = _SENTENCE_SPLIT_RE.split(content.strip())
    found: list[str] = []
    for sent in sentences:
        for pat in _TEMPLATE_CONCLUSION_RES:
            m = pat.search(sent)
            if m:
                found.append(m.group().strip().rstrip(",，."))
                break
    if not found:
        return {
            "name": "template_conclusions",
            "passed": True,
            "detail": "no template conclusions found",
        }
    return {
        "name": "template_conclusions",
        "passed": False,
        "detail": f"found {len(found)} template conclusion(s): {', '.join(found)}",
    }


def _check_overacademic_vocabulary(content: str) -> CheckResult:
    """Check 7: Detect over-academic vocabulary."""
    matches = _ACADEMIC_WORD_RE.findall(content)
    matches.extend(_CN_ACADEMIC_RE.findall(content))
    if not matches:
        return {
            "name": "overacademic_vocabulary",
            "passed": True,
            "detail": "no over-academic words found",
        }
    found = list(set(m.lower() for m in matches))
    return {
        "name": "overacademic_vocabulary",
        "passed": False,
        "detail": f"found {len(matches)} over-academic word(s): {', '.join(sorted(found))}",
    }


def _check_absolute_assertions(content: str) -> CheckResult:
    """Check 8: Detect absolute assertion patterns."""
    matches = _ABSOLUTE_RE.findall(content)
    if not matches:
        return {
            "name": "absolute_assertions",
            "passed": True,
            "detail": "no absolute assertions found",
        }
    found = list(set(m.strip() for m in matches))
    return {
        "name": "absolute_assertions",
        "passed": False,
        "detail": f"found {len(matches)} absolute assertion(s): {', '.join(sorted(found))}",
    }


def _check_repetitive_structures(content: str) -> CheckResult:
    """Check 9: Detect repetitive sentence-opening structures."""
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(content.strip()) if s.strip()]
    if len(sentences) < 3:
        return {
            "name": "repetitive_structures",
            "passed": True,
            "detail": "too few sentences to check",
        }

    # Check for 3+ consecutive sentences starting with the same word
    opening_words: list[str] = []
    for sent in sentences:
        words = sent.split()
        if words:
            first_raw = words[0]
            cjk = re.search(r"[\u4e00-\u9fff]", first_raw)
            if cjk is not None and cjk.start() == 0:
                # CJK text has no spaces — use the first character as the opening
                first = first_raw[0]
            else:
                # Normalize: lowercase, strip punctuation
                first = re.sub(r"[^\w]", "", first_raw).lower()
            opening_words.append(first)

    # Find runs of same opening word
    run_word = ""
    run_count = 0
    max_run_word = ""
    max_run = 0
    for w in opening_words:
        if w == run_word:
            run_count += 1
        else:
            if run_count > max_run:
                max_run = run_count
                max_run_word = run_word
            run_word = w
            run_count = 1
    if run_count > max_run:
        max_run = run_count
        max_run_word = run_word

    if max_run >= 3:
        return {
            "name": "repetitive_structures",
            "passed": False,
            "detail": f"'{max_run_word}' starts {max_run} consecutive sentences",
        }
    return {
        "name": "repetitive_structures",
        "passed": True,
        "detail": "no repetitive structures found",
    }


# ---------------------------------------------------------------------------
# Rewriting helpers
# ---------------------------------------------------------------------------

# Rewrite-time sentence-boundary patterns.
#
# The check-time patterns are anchored with "^" and applied per-sentence, so
# they match at the start of EVERY sentence. _rewrite_content applies them to
# the whole text, where "^" only matches at position 0 — mid-text sentence
# starts were never rewritten (issue #74: de-AI pass rate 33.3%). These
# rewrite-time versions re-anchor at any sentence boundary instead.
_SENTENCE_BOUNDARY = r"(?:\A|(?<=[.!?。！？]))\s*"


def _unanchor_pattern(source: str) -> tuple[str, str]:
    """Split a pattern into ``(inline_flags, body)`` with the leading ``^`` removed.

    Python requires inline flags (``(?i)``) at the very start of the pattern,
    so they are returned separately and re-prepended before the boundary
    prefix by :func:`_rewrite_patterns`.
    """
    flags = ""
    body = source
    flag_match = re.match(r"\(\?[aiLmsux]+\)", body)
    if flag_match:
        flags = flag_match.group(0)
        body = body[flag_match.end() :]
    if body.startswith("^"):
        body = body[1:]
    return flags, body


def _rewrite_patterns(patterns: list[re.Pattern[str]]) -> list[re.Pattern[str]]:
    """Re-anchor check-time sentence patterns at any sentence boundary.

    The prefix consumes the whitespace after sentence punctuation; the
    replacement callback in :func:`_rewrite_content` puts one space back when
    whitespace was actually consumed, so English sentences never fuse
    ("fast.we") and Chinese text gains no spurious space after 。！？.
    """
    out: list[re.Pattern[str]] = []
    for pat in patterns:
        flags, body = _unanchor_pattern(pat.pattern)
        out.append(re.compile(flags + _SENTENCE_BOUNDARY + body))
    return out


_REWRITE_HOLLOW_RES = _rewrite_patterns(_HOLLOW_INTRO_RES)
_REWRITE_VAGUE_RES = _rewrite_patterns(_VAGUE_SUBJECT_RES)
_REWRITE_FILLER_RES = _rewrite_patterns([_FILLER_RE, _CN_FILLER_RE])
_REWRITE_TEMPLATE_RES = _rewrite_patterns(_TEMPLATE_CONCLUSION_RES)


def _remove_sentence_initial(match: re.Match[str]) -> str:
    """Replacement for sentence-initial removal that preserves sentence spacing.

    The boundary prefix consumed any whitespace between the punctuation and
    the removed phrase; restore a single space when that happened so
    "fast. Furthermore" -> "fast. we" rather than "fast.we". CJK text has no
    space to consume, so nothing is added.
    """
    text = match.string
    if (
        match.group(0)
        and match.group(0)[0].isspace()
        and match.start() > 0
        and text[match.start() - 1] in ".!?。！？"
    ):
        return " "
    return ""


def _rewrite_content(content: str) -> str:
    """Apply all rewriting rules to produce a more human-sounding version."""
    text = content

    # 1. Remove overused adverbs
    text = _ADVERB_RE.sub("", text)

    # 2. Remove hollow intros at any sentence start
    for pat in _REWRITE_HOLLOW_RES:
        text = pat.sub(_remove_sentence_initial, text)

    # 3. Remove vague subjects (replace with empty — will be cleaned up)
    for pat in _REWRITE_VAGUE_RES:
        text = pat.sub(_remove_sentence_initial, text)

    # 4. Remove filler connectors at sentence starts
    for pat in _REWRITE_FILLER_RES:
        text = pat.sub(_remove_sentence_initial, text)

    # 5. Long conjunctions — no simple rewrite, just flag (handled by check)

    # 6. Remove template conclusions at any sentence start
    for pat in _REWRITE_TEMPLATE_RES:
        text = pat.sub(_remove_sentence_initial, text)

    # 7. Replace over-academic vocabulary
    def _replace_academic(m: re.Match[str]) -> str:
        word = m.group(0)
        lower = word.lower()
        replacement = _ACADEMIC_REPLACEMENTS.get(lower, word)
        # Preserve capitalization
        if word[0].isupper():
            replacement = replacement[0].upper() + replacement[1:]
        return replacement

    text = _ACADEMIC_WORD_RE.sub(_replace_academic, text)

    # 8. Soften absolute assertions
    _absolute_soften: dict[str, str] = {
        "always": "often",
        "never": "rarely",
        "everyone knows": "many believe",
        "undeniably": "arguably",
        "without exception": "in most cases",
        "absolutely": "largely",
        "no one can deny": "many would agree",
        "it is universally": "it is widely",
        "there is no doubt": "there is strong evidence",
        "毫无疑问": "可以说",
        "毋庸置疑": "可以说",
        "一定会": "可能会",
        "永远不会": "通常不会",
        "所有人都": "大多数人",
        "没有任何人": "很少有人",
        "唯一的方法": "比较有效的方法",
        "绝对不可能": "基本不可能",
        "必然会": "很可能会",
    }

    def _soften_absolute(m: re.Match[str]) -> str:
        matched = m.group(0).strip()
        lower = matched.lower()
        for pattern, replacement in _absolute_soften.items():
            if pattern in lower:
                # Preserve leading case
                if matched[0].isupper():
                    return replacement[0].upper() + replacement[1:]
                return replacement
        return matched

    text = _ABSOLUTE_RE.sub(_soften_absolute, text)

    # Clean up extra whitespace
    text = re.sub(r"  +", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    text = text.strip()

    return text


# ---------------------------------------------------------------------------
# G1Humanizer gate
# ---------------------------------------------------------------------------


class G1Humanizer(BaseGate):
    """G1 Humanizer Gate — 9-category AI writing pattern detection and rewriting.

    ``gate_context`` expected keys:
        - ``content``: str — text to check for AI patterns
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing without running real detection.
        - ``config`` (optional): dict with optional key ``enable_llm``
          (default ``True``) — when ``True``, attempts LLM-based evaluation
          first, falling back to deterministic regex detection.
        - ``config["gates"]["humanizer"]["verify_loop"]`` (optional): dict
          with ``enabled`` (bool, default ``False``) and ``max_iterations``
          (int, default 3, minimum 1) — when enabled, the rewritten output
          is verified with the deterministic AI-taste detector and the
          result gains ``detector_score`` + ``verify_iterations`` (issue
          #62, Wave-B B4).  Env backstop: ``AUTOMEDIA_HUMANIZER_VERIFY_LOOP``
          (any value other than ``""``/``"0"``) enables the loop.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``modified_content``,
        ``error`` — plus, when the verify loop is enabled, ``detector_score``
        (float) and ``verify_iterations`` (int).
    """

    _gate_name = "G1"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run 9-category AI pattern detection and return structured result.

        When ``enable_llm`` is ``True`` (the default, configurable via
        ``gate_context["config"]``), attempts LLM-based evaluation first.
        On LLM failure, falls back to deterministic regex checks.
        When ``_mock_results`` is present, skips LLM and uses the
        deterministic path directly for test compatibility.
        """
        content: str = gate_context.get("content", "")
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")
        config: dict[str, Any] = gate_context.get("config", {})
        enable_llm: bool = config.get("enable_llm", True) if isinstance(config, dict) else True
        verify_enabled, max_iterations = _resolve_verify_loop_config(config)

        # Detect target platform for platform-scoped prompt overrides
        brand_platforms: list[str] = gate_context.get("brand_platforms", [])
        platform: str = brand_platforms[0] if brand_platforms else ""

        # ------------------------------------------------------------------
        # Mock path — skip LLM entirely, use deterministic with overrides
        # ------------------------------------------------------------------
        if mock_results is not None:
            checks = self._run_deterministic(content, mock_results)
            modified_content, verify_extra = self._finalize_rewrite(
                content,
                checks,
                verify_enabled=verify_enabled,
                max_iterations=max_iterations,
            )
            return build_gate_result(
                checks,
                gate="G1",
                expected_map=_EXPECTED_MAP,
                modified_content=modified_content,
                **verify_extra,
            )

        # ------------------------------------------------------------------
        # LLM path — try AI evaluation, fall back to deterministic
        # ------------------------------------------------------------------
        if enable_llm and content.strip():
            # Mutable container to capture per-step checks from fallback
            captured_checks: list[CheckResult] = []

            def _deterministic_fn(_text: str) -> LLMCheckResult:
                det_checks = self._run_deterministic(content, None)
                captured_checks.extend(det_checks)
                return {
                    "passed": all(c["passed"] for c in det_checks),
                    "issues": [c["detail"] for c in det_checks if not c["passed"]],
                }

            llm_result = llm_check_with_fallback(
                text=content,
                check_type="humanizer",
                prompt_template_name="humanizer_g1",
                deterministic_fn=_deterministic_fn,
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
                    else ("verified by LLM" if passed else "humanizer check failed")
                )
                checks = [
                    {"name": name, "passed": passed, "detail": detail} for name in _CHECK_NAMES
                ]

            modified_content, verify_extra = self._finalize_rewrite(
                content,
                checks,
                verify_enabled=verify_enabled,
                max_iterations=max_iterations,
            )

            return build_gate_result(
                checks,
                gate="G1",
                expected_map=_EXPECTED_MAP,
                modified_content=modified_content,
                method=method,
                **verify_extra,
            )

        # ------------------------------------------------------------------
        # Deterministic-only path (enable_llm=False or empty content)
        # ------------------------------------------------------------------
        checks = self._run_deterministic(content, None)
        modified_content, verify_extra = self._finalize_rewrite(
            content,
            checks,
            verify_enabled=verify_enabled,
            max_iterations=max_iterations,
        )
        return build_gate_result(
            checks,
            gate="G1",
            expected_map=_EXPECTED_MAP,
            modified_content=modified_content,
            **verify_extra,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _finalize_rewrite(
        self,
        content: str,
        checks: list[CheckResult],
        *,
        verify_enabled: bool,
        max_iterations: int,
    ) -> tuple[str | None, dict[str, Any]]:
        """Compute the final ``modified_content`` and verify-loop extras (B4).

        Runs the normal rewrite when any check failed, then — only when
        *verify_enabled* — the humanize→verify closed loop.  Returns
        ``(final_content, extras)`` where *extras* carries ``detector_score``
        and ``verify_iterations`` when the loop ran, and is empty otherwise
        (so the toggle-off result dict stays byte-identical).
        """
        all_passed = all(c["passed"] for c in checks)
        modified_content = None
        if not all_passed and content:
            modified_content = _rewrite_content(content)
        final_content, detector_score, verify_iterations = self._run_verify_loop(
            content,
            modified_content,
            enabled=verify_enabled,
            max_iterations=max_iterations,
        )
        extras: dict[str, Any] = {}
        if verify_enabled:
            extras["detector_score"] = detector_score
            extras["verify_iterations"] = verify_iterations
        return final_content, extras

    def _run_verify_loop(
        self,
        content: str,
        modified_content: str | None,
        *,
        enabled: bool,
        max_iterations: int,
    ) -> tuple[str | None, float | None, int]:
        """Humanize→verify closed loop over the candidate output (issue #62, B4).

        When *enabled* is False this is a pure pass-through returning
        ``(modified_content, None, 0)`` — the detector is never invoked.

        When enabled, the candidate (the rewrite if one happened, else the
        original content) is verified with the deterministic AI-taste
        detector and the rewrite is repeated with the detector's verdict as
        feedback up to *max_iterations* times.  Returns
        ``(final_content, detector_score, verify_iterations)`` where
        ``detector_score`` is the FINAL output's ai_score.

        Termination is guaranteed three ways: the detector passes, the
        rewrite stops making progress (identical consecutive outputs), or
        the iteration budget is exhausted.
        """
        if not enabled:
            return modified_content, None, 0

        # Local import: automedia.detectors.deterministic imports this
        # module at load time (the 9 check functions), so a module-level
        # import here would form an import cycle.  By the time execute()
        # runs, every module is fully loaded — the local import is safe.
        from automedia.detectors import DeterministicTasteDetector

        detector = DeterministicTasteDetector()
        if modified_content is not None:
            rewrote = True
            candidate = modified_content
        else:
            rewrote = False
            candidate = content
        for i in range(1, max_iterations + 1):
            result = detector.detect(candidate)
            if result["passed"] or i >= max_iterations:
                return (candidate if rewrote else None), result["ai_score"], i
            next_candidate = _rewrite_content(candidate)
            if next_candidate == candidate:
                # No progress — stop to guarantee termination.
                return (candidate if rewrote else None), result["ai_score"], i
            rewrote = True
            candidate = next_candidate
        # Unreachable (max_iterations >= 1), present for the type checker.
        return None, 0.0, max_iterations

    def _run_deterministic(
        self,
        content: str,
        mock_results: dict[str, dict[str, Any]] | None,
    ) -> list[CheckResult]:
        """Run the 9-category regex detection (deterministic path).

        When *mock_results* is provided, individual check results are
        driven from the mock dict instead of running real detection.
        """
        check_fns: list[tuple[str, Any]] = [
            ("overused_adverbs", lambda: _check_overused_adverbs(content)),
            ("hollow_intros", lambda: _check_hollow_intros(content)),
            ("vague_subjects", lambda: _check_vague_subjects(content)),
            ("filler_connectors", lambda: _check_filler_connectors(content)),
            ("long_conjunctions", lambda: _check_long_conjunctions(content)),
            ("template_conclusions", lambda: _check_template_conclusions(content)),
            ("overacademic_vocabulary", lambda: _check_overacademic_vocabulary(content)),
            ("absolute_assertions", lambda: _check_absolute_assertions(content)),
            ("repetitive_structures", lambda: _check_repetitive_structures(content)),
        ]

        checks: list[CheckResult] = []
        for name, fn in check_fns:
            if mock_results is not None and name in mock_results:
                mock = mock_results[name]
                checks.append(
                    {
                        "name": name,
                        "passed": bool(mock["passed"]),
                        "detail": str(mock.get("detail", "")),
                    }
                )
            else:
                checks.append(fn())
        return checks
