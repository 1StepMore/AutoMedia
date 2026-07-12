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

When ``gate_context["_mock_results"]`` is present, each check's result is
driven from that dict instead of running real detection — making the gate
fully deterministic for unit testing.
"""

from __future__ import annotations

import re
from typing import Any

from automedia.gates._context import GateContext
from automedia.gates._result import build_gate_result
from automedia.gates.base import BaseGate

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
]
_ABSOLUTE_RE = re.compile(
    "|".join(_ABSOLUTE_PATTERNS),
    re.IGNORECASE,
)

# Pattern 9: Repetitive structures — same word starting 3+ consecutive sentences
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


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
# Individual check functions
# ---------------------------------------------------------------------------


def _check_overused_adverbs(content: str) -> dict[str, Any]:
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


def _check_hollow_intros(content: str) -> dict[str, Any]:
    """Check 2: Detect hollow introductory phrases."""
    sentences = _SENTENCE_SPLIT_RE.split(content.strip())
    found: list[str] = []
    for sent in sentences:
        for pat in _HOLLOW_INTRO_RES:
            m = pat.search(sent)
            if m:
                found.append(m.group().strip().rstrip(",."))
                break
    if not found:
        return {"name": "hollow_intros", "passed": True, "detail": "no hollow intros found"}
    return {
        "name": "hollow_intros",
        "passed": False,
        "detail": f"found {len(found)} hollow intro(s): {', '.join(found[:5])}",
    }


def _check_vague_subjects(content: str) -> dict[str, Any]:
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


def _check_filler_connectors(content: str) -> dict[str, Any]:
    """Check 4: Detect filler connectors at sentence starts."""
    sentences = _SENTENCE_SPLIT_RE.split(content.strip())
    found: list[str] = []
    for sent in sentences:
        m = _FILLER_RE.match(sent)
        if m:
            found.append(m.group().strip().rstrip(",."))
    if not found:
        return {"name": "filler_connectors", "passed": True, "detail": "no filler connectors found"}
    return {
        "name": "filler_connectors",
        "passed": False,
        "detail": f"found {len(found)} filler connector(s): {', '.join(found)}",
    }


def _check_long_conjunctions(content: str) -> dict[str, Any]:
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


def _check_template_conclusions(content: str) -> dict[str, Any]:
    """Check 6: Detect template-style conclusion phrases."""
    sentences = _SENTENCE_SPLIT_RE.split(content.strip())
    found: list[str] = []
    for sent in sentences:
        for pat in _TEMPLATE_CONCLUSION_RES:
            m = pat.search(sent)
            if m:
                found.append(m.group().strip().rstrip(",."))
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


def _check_overacademic_vocabulary(content: str) -> dict[str, Any]:
    """Check 7: Detect over-academic vocabulary."""
    matches = _ACADEMIC_WORD_RE.findall(content)
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


def _check_absolute_assertions(content: str) -> dict[str, Any]:
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


def _check_repetitive_structures(content: str) -> dict[str, Any]:
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
            # Normalize: lowercase, strip punctuation
            first = re.sub(r"[^\w]", "", words[0]).lower()
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


def _rewrite_content(content: str) -> str:
    """Apply all rewriting rules to produce a more human-sounding version."""
    text = content

    # 1. Remove overused adverbs
    text = _ADVERB_RE.sub("", text)

    # 2. Remove hollow intros
    for pat in _HOLLOW_INTRO_RES:
        text = pat.sub("", text)

    # 3. Remove vague subjects (replace with empty — will be cleaned up)
    for pat in _VAGUE_SUBJECT_RES:
        text = pat.sub("", text)

    # 4. Remove filler connectors at sentence starts
    text = _FILLER_RE.sub("", text)

    # 5. Long conjunctions — no simple rewrite, just flag (handled by check)

    # 6. Remove template conclusions
    for pat in _TEMPLATE_CONCLUSION_RES:
        text = pat.sub("", text)

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

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``modified_content``,
        ``error``.
    """

    _gate_name = "G1"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run 9-category AI pattern detection and return structured result."""
        content: str = gate_context.get("content", "")
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

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

        checks: list[dict[str, Any]] = []
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

        # If any check failed, produce a rewritten version
        all_passed = all(c["passed"] for c in checks)
        modified_content: str | None = None
        if not all_passed and content:
            modified_content = _rewrite_content(content)

        return build_gate_result(
            checks,
            gate="G1",
            expected_map=_EXPECTED_MAP,
            modified_content=modified_content,
        )
