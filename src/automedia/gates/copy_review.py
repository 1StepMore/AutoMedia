"""G2 Copy Review Gate — 5-round structural copy quality review.

Rounds:
    1. clarity         — 句子复杂度, 术语过多, 模糊词汇
    2. tone            — 品牌语调一致性 (based on context brand_profile)
    3. so_what         — 内容是否回答了"所以呢?" (reader value)
    4. evidence        — 论断是否有数据/来源支撑
    5. specificity     — 用抽象词还是具体例子

When ``gate_context["_mock_results"]`` is present, each check's result is
driven from that dict instead of running real detection — making the gate
fully deterministic for unit testing.
"""

from __future__ import annotations

import json
import re
from typing import Any, cast

from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result
from automedia.gates.base import BaseGate
from automedia.gates.llm_helpers import LLMCheckResult, llm_check_with_fallback


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "clarity",
    "tone",
    "so_what",
    "evidence",
    "specificity",
]


_EXPECTED_MAP: dict[str, str] = {
    "clarity": "Content is clear with no jargon or vague words",
    "tone": "Content tone matches the brand profile",
    "so_what": "Content answers 'why should the reader care?'",
    "evidence": "Claims are backed by data or sources",
    "specificity": "Abstract buzzwords are balanced by concrete examples",
}




# ---------------------------------------------------------------------------
# Round 1: Clarity — sentence complexity, jargon, vague words
# ---------------------------------------------------------------------------

# Overly long sentence threshold (words)
_LONG_SENTENCE_THRESHOLD = 35

# Jargon / domain-specific buzzwords that bloat copy
_JARGON_WORDS: list[str] = [
    "synergy",
    "leverage",
    "paradigm",
    "ecosystem",
    "holistic",
    "stakeholder",
    "bandwidth",
    "deliverable",
    "scalable",
    "actionable",
    "cross-functional",
    "best-of-breed",
    "mission-critical",
    "low-hanging fruit",
    "move the needle",
    "circle back",
    "deep dive",
    "thought leadership",
    "value proposition",
    "core competency",
]
_JARGON_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _JARGON_WORDS) + r")\b",
    re.IGNORECASE,
)

# Vague / filler words that weaken clarity
_VAGUE_WORDS: list[str] = [
    "very",
    "really",
    "quite",
    "just",
    "basically",
    "actually",
    "literally",
    "stuff",
    "things",
    "various",
    "several",
    "numerous",
    "somehow",
    "somewhat",
    "rather",
    "fairly",
    "pretty much",
    "a lot",
]
_VAGUE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _VAGUE_WORDS) + r")\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _check_clarity(content: str) -> CheckResult:
    """Round 1: Check clarity — sentence complexity, jargon, vague words."""
    name = "clarity"
    if not content.strip():
        return {"name": name, "passed": True, "detail": "empty content"}

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(content.strip()) if s.strip()]
    issues: list[str] = []

    # 1a. Long sentences
    long_count = 0
    for sent in sentences:
        word_count = len(sent.split())
        if word_count > _LONG_SENTENCE_THRESHOLD:
            long_count += 1
    if long_count:
        issues.append(f"{long_count} sentence(s) exceed {_LONG_SENTENCE_THRESHOLD} words")

    # 1b. Jargon
    jargon_matches = _JARGON_RE.findall(content)
    if jargon_matches:
        found = sorted(set(m.lower() for m in jargon_matches))
        issues.append(f"{len(jargon_matches)} jargon term(s): {', '.join(found[:5])}")

    # 1c. Vague words
    vague_matches = _VAGUE_RE.findall(content)
    if vague_matches:
        found = sorted(set(m.lower() for m in vague_matches))
        issues.append(f"{len(vague_matches)} vague word(s): {', '.join(found[:5])}")

    if not issues:
        return {"name": name, "passed": True, "detail": "content is clear"}
    return {"name": name, "passed": False, "detail": "; ".join(issues)}


# ---------------------------------------------------------------------------
# Round 2: Tone — brand voice consistency
# ---------------------------------------------------------------------------

# Default tone keywords if brand_profile is missing
_DEFAULT_TONE_KEYWORDS: dict[str, list[str]] = {
    "professional": ["therefore", "consequently", "established", "proven"],
    "casual": ["hey", "awesome", "cool", "gonna", "wanna"],
    "enthusiastic": ["amazing", "incredible", "fantastic", "love", "excited"],
    "authoritative": ["must", "shall", "mandate", "require", "decree"],
}

# Tones that conflict — e.g. professional vs. casual
_TONE_CONFLICTS: dict[str, set[str]] = {
    "professional": {"casual"},
    "casual": {"professional", "authoritative"},
    "authoritative": {"casual"},
    "enthusiastic": set(),
}


def _check_tone(content: str, brand_profile: dict[str, Any] | None) -> CheckResult:
    """Round 2: Check brand tone consistency."""
    name = "tone"
    if not content.strip():
        return {"name": name, "passed": True, "detail": "empty content"}

    if not brand_profile:
        return {"name": name, "passed": True, "detail": "no brand_profile provided"}

    target_tone: str = brand_profile.get("tone", "")
    if not target_tone:
        return {"name": name, "passed": True, "detail": "no tone specified in brand_profile"}

    target_tone = target_tone.lower().strip()
    content_lower = content.lower()

    # Check for conflicting tone markers
    conflicting_tones = _TONE_CONFLICTS.get(target_tone, set())
    issues: list[str] = []

    for conflicting in conflicting_tones:
        keywords = _DEFAULT_TONE_KEYWORDS.get(conflicting, [])
        found = [kw for kw in keywords if kw in content_lower]
        if found:
            issues.append(f"conflicting '{conflicting}' tone markers found: {', '.join(found[:3])}")

    # Check target tone keywords are present
    target_keywords = _DEFAULT_TONE_KEYWORDS.get(target_tone, [])
    if target_keywords:
        present = [kw for kw in target_keywords if kw in content_lower]
        if not present:
            issues.append(f"expected '{target_tone}' tone but no matching keywords found")

    if not issues:
        return {"name": name, "passed": True, "detail": f"tone matches '{target_tone}' profile"}
    return {"name": name, "passed": False, "detail": "; ".join(issues)}


# ---------------------------------------------------------------------------
# Round 3: So What — does the content answer "why should I care?"
# ---------------------------------------------------------------------------

_VALUE_PATTERNS: list[str] = [
    r"benefit(?:s|ed|ing)?",
    r"sav(?:e|es|ed|ing)",
    r"reduc(?:e|es|ed|ing|tion)",
    r"increase[sd]?|increasing",
    r"improv(?:e|es|ed|ing|ement)",
    r"gain(?:s|ed|ing)?",
    r"result(?:s|ed|ing)?",
    r"outcome[sd]?",
    r"because",
    r"so that",
    r"means you",
    r"you get",
    r"you can",
    r"helps? you",
    r"enables? you",
    r"empowers? you",
    r"leads? to",
    r"results? in",
    r"percent",
    r"%",
    r"roi",
    r"revenue",
    r"growth",
    r"efficiency",
    r"advantage[sd]?",
    r"fast(?:er|est)?",
    r"lower(?:s|ed|ing)?",
]
_VALUE_RE = re.compile(
    r"(?:" + "|".join(_VALUE_PATTERNS) + r")",
    re.IGNORECASE,
)


def _check_so_what(content: str) -> CheckResult:
    """Round 3: Does the content answer 'So what?' (reader value)."""
    name = "so_what"
    if not content.strip():
        return {"name": name, "passed": True, "detail": "empty content"}

    value_matches = _VALUE_RE.findall(content)
    if len(value_matches) >= 2:
        return {
            "name": name,
            "passed": True,
            "detail": f"found {len(value_matches)} value indicator(s)",
        }

    # Check for question-answer patterns (engagement signals)
    if re.search(r"\?[^?]{20,}", content, re.DOTALL):
        return {"name": name, "passed": True, "detail": "found Q&A engagement pattern"}

    return {
        "name": name,
        "passed": False,
        "detail": "content doesn't clearly answer 'why should the reader care?'",
    }


# ---------------------------------------------------------------------------
# Round 4: Evidence — are claims backed by data/sources?
# ---------------------------------------------------------------------------

_CLAIM_PATTERNS: list[str] = [
    r"\b\w+\s+(?:is|are|was|were)\s+(?:the\s+)?(?:best|worst|largest|smallest|fastest|most|least)\b",
    r"\bstudies?\s+show\b",
    r"\bresearch\s+(?:shows?|suggests?|indicates?|proves?)\b",
    r"\bexperts?\s+(?:say|believe|agree|argue|claim)\b",
    r"\bit\s+is\s+(?:well-known|widely accepted|proven|clear)\b",
    r"\beveryone\s+knows\b",
    r"\bundeniably\b",
    r"\bwithout\s+a\s+doubt\b",
]
_CLAIM_RE = re.compile("|".join(_CLAIM_PATTERNS), re.IGNORECASE)

# Data / evidence indicators
_EVIDENCE_PATTERNS: list[str] = [
    r"\d+%",  # percentages
    r"\$[\d,.]+",  # dollar amounts
    r"\d+[,.]?\d*\s*(?:million|billion|trillion)",  # large numbers
    r"(?:according to|per|as reported by)\s+",  # attribution
    r"(?:study|report|survey|data|analysis)\s+(?:by|from|showing)",  # source reference
    r"(?:source|reference|citation):",
    r"(?:https?://|www\.)",  # URLs
    r"(?:20|19)\d{2}",  # year references
]
_EVIDENCE_RE = re.compile("|".join(_EVIDENCE_PATTERNS), re.IGNORECASE)


def _check_evidence(content: str) -> CheckResult:
    """Round 4: Are claims backed by data/sources?"""
    name = "evidence"
    if not content.strip():
        return {"name": name, "passed": True, "detail": "empty content"}

    claims = _CLAIM_RE.findall(content)
    if not claims:
        return {"name": name, "passed": True, "detail": "no strong claims detected"}

    # Claims found — check for evidence nearby
    evidence = _EVIDENCE_RE.findall(content)
    if evidence:
        return {
            "name": name,
            "passed": True,
            "detail": (
                f"{len(claims)} claim(s) found, {len(evidence)} evidence indicator(s) present"
            ),
        }

    return {
        "name": name,
        "passed": False,
        "detail": f"{len(claims)} claim(s) found but no supporting data or sources",
    }


# ---------------------------------------------------------------------------
# Round 5: Specificity — abstract words vs concrete examples
# ---------------------------------------------------------------------------

_ABSTRACT_WORDS: list[str] = [
    "innovative",
    "cutting-edge",
    "state-of-the-art",
    "world-class",
    "best-in-class",
    "next-generation",
    "industry-leading",
    "game-changing",
    "revolutionary",
    "transformative",
    "breakthrough",
    "disruptive",
    "unprecedented",
    "unique",
    "solutions",
    "strategies",
    "approaches",
    "methods",
    "frameworks",
    "initiatives",
]
_ABSTRACT_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _ABSTRACT_WORDS) + r")\b",
    re.IGNORECASE,
)

_CONCRETE_INDICATORS: list[str] = [
    r"\d+%",  # percentages
    r"\$[\d,.]+",  # dollar amounts
    r"\d+[xX]\b",  # multipliers like 3x
    r"\b\d+\s*(?:day|week|month|hour|minute|year)s?\b",  # time frames
    r"(?:for example|such as|e\.g\.|like|including)\b",  # exemplification
    r"(?:specifically|in particular|namely)\b",  # specification
]
_CONCRETE_RE = re.compile("|".join(_CONCRETE_INDICATORS), re.IGNORECASE)


def _check_specificity(content: str) -> CheckResult:
    """Round 5: Is the copy using abstract buzzwords or concrete examples?"""
    name = "specificity"
    if not content.strip():
        return {"name": name, "passed": True, "detail": "empty content"}

    abstract_matches = _ABSTRACT_RE.findall(content)
    concrete_matches = _CONCRETE_RE.findall(content)

    if not abstract_matches:
        return {"name": name, "passed": True, "detail": "no abstract buzzwords detected"}

    # Abstract words found — are there enough concrete indicators to balance?
    abstract_count = len(abstract_matches)
    concrete_count = len(concrete_matches)

    if concrete_count >= abstract_count:
        return {
            "name": name,
            "passed": True,
            "detail": (
                f"{abstract_count} abstract word(s) balanced by"
                f" {concrete_count} concrete indicator(s)"
            ),
        }

    found = sorted(set(m.lower() for m in abstract_matches))
    return {
        "name": name,
        "passed": False,
        "detail": (
            f"{abstract_count} abstract word(s) but only"
            f" {concrete_count} concrete example(s):"
            f" {', '.join(found[:5])}"
        ),
    }


# ---------------------------------------------------------------------------
# Rewriting helpers
# ---------------------------------------------------------------------------


def _rewrite_content(content: str) -> str:
    """Apply targeted rewrites to improve copy quality."""
    text = content

    # 1. Remove jargon
    text = _JARGON_RE.sub(lambda m: _soften_jargon(m), text)

    # 2. Remove vague words
    text = _VAGUE_RE.sub("", text)

    # 3. Soften abstract buzzwords
    _abstract_soften: dict[str, str] = {
        "innovative": "new",
        "cutting-edge": "modern",
        "state-of-the-art": "advanced",
        "world-class": "high-quality",
        "best-in-class": "leading",
        "next-generation": "updated",
        "industry-leading": "top-performing",
        "game-changing": "significant",
        "revolutionary": "major",
        "transformative": "impactful",
        "breakthrough": "notable advance",
        "disruptive": "bold",
        "unprecedented": "rare",
        "unique": "distinctive",
        "solutions": "offerings",
        "strategies": "plans",
        "approaches": "methods",
        "methods": "steps",
        "frameworks": "structures",
        "initiatives": "efforts",
    }

    def _replace_abstract(m: re.Match[str]) -> str:
        word = m.group(0)
        lower = word.lower()
        replacement = _abstract_soften.get(lower, word)
        if word[0].isupper():
            replacement = replacement[0].upper() + replacement[1:]
        return replacement

    text = _ABSTRACT_RE.sub(_replace_abstract, text)

    # Clean up extra whitespace
    text = re.sub(r"  +", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    text = text.strip()

    return text


def _soften_jargon(m: re.Match[str]) -> str:
    """Replace jargon term with simpler alternative."""
    _jargon_replacements: dict[str, str] = {
        "synergy": "teamwork",
        "leverage": "use",
        "paradigm": "model",
        "ecosystem": "network",
        "holistic": "comprehensive",
        "stakeholder": "participant",
        "bandwidth": "capacity",
        "deliverable": "output",
        "scalable": "expandable",
        "actionable": "practical",
        "cross-functional": "team-wide",
        "best-of-breed": "top-quality",
        "mission-critical": "essential",
        "low-hanging fruit": "easy wins",
        "move the needle": "make progress",
        "circle back": "follow up",
        "deep dive": "thorough review",
        "thought leadership": "expertise",
        "value proposition": "key benefit",
        "core competency": "strength",
    }
    word = m.group(0)
    lower = word.lower()
    replacement = _jargon_replacements.get(lower, word)
    if word[0].isupper():
        replacement = replacement[0].upper() + replacement[1:]
    return replacement




# ---------------------------------------------------------------------------
# G2CopyReview gate
# ---------------------------------------------------------------------------


class G2CopyReview(BaseGate):
    """G2 Copy Review Gate — 5-round structural copy quality review.

    ``gate_context`` expected keys:
        - ``content``: str — text to review
        - ``brand_profile`` (optional): dict with keys:
            - ``tone``: str — target tone (professional, casual, enthusiastic, authoritative)
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing without running real detection.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``modified_content``,
        ``error``.
    """

    _gate_name = "G2"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run 5-round copy review and return structured result.

        When ``enable_llm`` is ``True`` (the default, configurable via
        ``gate_context["config"]``), attempts LLM-based evaluation first.
        On LLM failure, falls back to the deterministic keyword-matching
        checks.  When ``_mock_results`` is present, always uses the
        deterministic path for test compatibility.
        """
        content: str = gate_context.get("content", "")
        brand_profile: dict[str, Any] | None = gate_context.get("brand_profile")
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")
        config: dict[str, Any] = gate_context.get("config", {})
        enable_llm: bool = config.get("enable_llm", True) if isinstance(config, dict) else True

        if mock_results is not None:
            return self._run_deterministic(content, brand_profile, mock_results)

        if enable_llm and content.strip():
            brand_guidelines: str = json.dumps(brand_profile) if brand_profile else ""
            llm_result = llm_check_with_fallback(
                text=content,
                check_type="copy_review",
                prompt_template_name="copy_review_g2",
                deterministic_fn=lambda text: cast(LLMCheckResult, self._run_deterministic(  # type: ignore[arg-type]
                    text, brand_profile, None,
                )),
                brand_guidelines=brand_guidelines,
            )

            if llm_result.get("method") == "llm":
                all_passed = llm_result["passed"]
                modified_content: str | None = None
                if not all_passed and content:
                    modified_content = _rewrite_content(content)

                result = build_gate_result(
                    self._build_llm_checks(llm_result),
                    gate="G2",
                    expected_map=_EXPECTED_MAP,
                    modified_content=modified_content,
                )
                result["method"] = "llm"
                result["tone_score"] = llm_result.get("tone_score", 1.0)
                result["brand_compliance"] = llm_result.get("brand_compliance", True)
                return result

            return cast(dict[str, Any], llm_result)

        return self._run_deterministic(content, brand_profile, mock_results)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_deterministic(
        self,
        content: str,
        brand_profile: dict[str, Any] | None,
        mock_results: dict[str, dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Run the 5-round keyword-matching review (deterministic path)."""
        check_fns: list[tuple[str, Any]] = [
            ("clarity", lambda: _check_clarity(content)),
            ("tone", lambda: _check_tone(content, brand_profile)),
            ("so_what", lambda: _check_so_what(content)),
            ("evidence", lambda: _check_evidence(content)),
            ("specificity", lambda: _check_specificity(content)),
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

        # If any check failed, produce a rewritten version
        all_passed = all(c["passed"] for c in checks)
        modified_content: str | None = None
        if not all_passed and content:
            modified_content = _rewrite_content(content)

        return build_gate_result(
            checks,
            gate="G2",
            expected_map=_EXPECTED_MAP,
            modified_content=modified_content,
        )

    @staticmethod
    def _build_llm_checks(llm_result: LLMCheckResult) -> list[CheckResult]:
        """Convert LLM result into a checks list for standard format."""
        passed: bool = llm_result["passed"]
        issues: list[str] = llm_result.get("issues", [])
        detail = (
            "; ".join(issues)
            if issues
            else ("all checks passed" if passed else "issues found")
        )
        return [{"name": "llm_review", "passed": passed, "detail": detail}]
