"""G6 Tone Check Gate — brand tone consistency validation.

Evaluates content against the brand's tone guidelines using LLM-based
analysis with a deterministic keyword-matching fallback.

When ``gate_context["_mock_results"]`` is present, the result is
driven from that dict instead of running real detection — making the gate
fully deterministic for unit testing.
"""

from __future__ import annotations

import json
from typing import Any, cast

from structlog import get_logger

from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result
from automedia.gates.base import BaseGate
from automedia.gates.llm_helpers import LLMCheckResult, llm_check_with_fallback

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "tone_consistency",
]

_EXPECTED_MAP: dict[str, str] = {
    "tone_consistency": "Content tone matches brand tone guidelines",
}

# ---------------------------------------------------------------------------
# Deterministic fallback — keyword-based tone matching
# ---------------------------------------------------------------------------

# Tone indicator keywords for common brand personalities
_TONE_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "professional": {
        "positive": [
            "therefore", "consequently", "established", "proven",
            "research", "analysis", "data", "evidence",
            "recommend", "suggest",
        ],
        "negative": [
            "hey", "awesome", "cool", "gonna", "wanna",
            "super", "literally", "insane",
        ],
    },
    "casual": {
        "positive": [
            "hey", "awesome", "cool", "gonna", "wanna",
            "super", "fun", "love", "check it out",
        ],
        "negative": [
            "therefore", "consequently", "heretofore",
            "utilize", "commence",
        ],
    },
    "authoritative": {
        "positive": [
            "must", "shall", "mandate", "require", "decree",
            "essential", "critical", "imperative",
        ],
        "negative": [
            "maybe", "perhaps", "might", "could possibly",
            "sort of", "kind of",
        ],
    },
    "enthusiastic": {
        "positive": [
            "amazing", "incredible", "fantastic", "love",
            "excited", "thrilled", "delighted",
            "wonderful", "tremendous", "outstanding",
        ],
        "negative": [
            "boring", "dull", "uninteresting", "mediocre",
        ],
    },
    "friendly": {
        "positive": [
            "help", "support", "guide", "together",
            "we", "us", "our", "let's", "team",
            "welcome", "happy", "glad",
        ],
        "negative": [
            "you must", "you have to", "failure", "wrong",
        ],
    },
    "minimalist": {
        "positive": [
            "simple", "clean", "clear", "streamlined",
            "focus", "essential", "core",
        ],
        "negative": [
            "comprehensive", "extensive", "complex", "sophisticated",
            "robust", "full-featured",
        ],
    },
}

# Conflicting tone pairs
_TONE_CONFLICTS: dict[str, set[str]] = {
    "professional": {"casual"},
    "casual": {"professional", "authoritative"},
    "authoritative": {"casual"},
    "enthusiastic": {"professional", "minimalist"},
    "friendly": {"authoritative"},
    "minimalist": {"enthusiastic"},
}


def _deterministic_tone_check(
    content: str,
    tone_guidelines: str,
) -> CheckResult:
    """Deterministic keyword-matching tone check.

    Parses tone keywords from *tone_guidelines* (looking for common
    brand personality labels) and checks content for conflicting or
    missing tone markers.
    """
    name = "tone_consistency"
    if not content.strip():
        return {"name": name, "passed": True, "detail": "empty content"}

    if not tone_guidelines:
        return {"name": name, "passed": True, "detail": "no tone guidelines provided"}

    guidelines_lower = tone_guidelines.lower()
    content_lower = content.lower()
    issues: list[str] = []

    # Detect target tone from guidelines text
    target_tones: list[str] = []
    for tone_name, _keywords in _TONE_KEYWORDS.items():
        if tone_name in guidelines_lower:
            target_tones.append(tone_name)

    if not target_tones:
        # No known tone identified — check for at least some positive indicators
        all_positive: list[str] = []
        for kw in _TONE_KEYWORDS.values():
            all_positive.extend(kw["positive"])
        found_positive = [kw for kw in all_positive if kw in content_lower]
        if not found_positive:
            return {
                "name": name,
                "passed": True,
                "detail": "no discernible tone violations detected",
            }
        return {"name": name, "passed": True, "detail": f"positive tone indicators found: {len(found_positive)}"}

    # Check for conflicting tone markers
    conflicting_tones: set[str] = set()
    for tone in target_tones:
        conflicting_tones |= _TONE_CONFLICTS.get(tone, set())

    for conflict in conflicting_tones:
        conflict_keywords = _TONE_KEYWORDS.get(conflict, {}).get("positive", [])
        found = [kw for kw in conflict_keywords if kw in content_lower]
        if found:
            issues.append(
                f"conflicting '{conflict}' tone markers found: "
                f"{', '.join(found[:3])}"
            )

    # Check target tone keywords are present
    for tone in target_tones:
        positive_kw = _TONE_KEYWORDS.get(tone, {}).get("positive", [])
        if positive_kw:
            present = [kw for kw in positive_kw if kw in content_lower]
            if not present:
                issues.append(
                    f"expected '{tone}' tone but no matching indicators found"
                )

    # Check for negative keywords
    for tone in target_tones:
        negative_kw = _TONE_KEYWORDS.get(tone, {}).get("negative", [])
        found_negative = [kw for kw in negative_kw if kw in content_lower]
        if found_negative:
            issues.append(
                f"'{tone}' tone markers that violate brand tone found: "
                f"{', '.join(found_negative[:3])}"
            )

    if not issues:
        tones_str = ", ".join(target_tones)
        return {
            "name": name,
            "passed": True,
            "detail": f"tone matches brand profile: '{tones_str}'",
        }

    return {"name": name, "passed": False, "detail": "; ".join(issues)}


def _build_tone_guidelines(brand_profile: dict[str, Any] | None) -> str:
    """Extract tone guidelines from a brand profile dict."""
    if not brand_profile:
        return ""

    parts: list[str] = []

    tone = brand_profile.get("tone_guidelines", "")
    if tone:
        parts.append(f"Tone guidelines: {tone}")

    personality = brand_profile.get("personality", "")
    if personality:
        parts.append(f"Brand personality: {personality}")

    audience = brand_profile.get("target_audience", "")
    if audience:
        parts.append(f"Target audience: {audience}")

    industry = brand_profile.get("industry", "")
    if industry:
        parts.append(f"Industry: {industry}")

    return " | ".join(parts)


# ---------------------------------------------------------------------------
# G6ToneCheckGate
# ---------------------------------------------------------------------------


class G6ToneCheckGate(BaseGate):
    """G6 Tone Check Gate — validates brand tone consistency.

    ``gate_context`` expected keys:
        - ``content``: str — text to evaluate for brand tone consistency
        - ``brand_profile`` (optional): dict with keys:
            - ``tone_guidelines``: str — textual brand tone guidelines
            - ``personality``: str — brand personality descriptors
            - ``target_audience``: str — audience description
            - ``industry``: str — brand industry
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing without running real detection.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error``.
    """

    _gate_name = "G6"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run brand tone consistency check and return structured result.

        When ``enable_llm`` is ``True`` (the default, configurable via
        ``gate_context["config"]``), attempts LLM-based evaluation first.
        On LLM failure, falls back to the deterministic keyword-matching
        check.  When ``_mock_results`` is present, always returns the
        deterministic path result overridden by mock values.
        """
        content: str = gate_context.get("content", "")
        brand_profile: dict[str, Any] | None = gate_context.get("brand_profile")
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")
        config: dict[str, Any] = gate_context.get("config", {})
        enable_llm: bool = config.get("enable_llm", True) if isinstance(config, dict) else True

        # Detect target platform for platform-scoped prompt overrides
        brand_platforms: list[str] = gate_context.get("brand_platforms", [])
        platform: str = brand_platforms[0] if brand_platforms else ""

        tone_guidelines: str = _build_tone_guidelines(brand_profile)

        if mock_results is not None:
            return self._build_result_from_mocks(tone_guidelines, mock_results)

        if enable_llm and content.strip() and tone_guidelines:
            llm_result = llm_check_with_fallback(
                text=content,
                check_type="tone_check",
                prompt_template_name="tone_check_g6",
                deterministic_fn=lambda text: cast(
                    LLMCheckResult,
                    self._run_deterministic(
                        text,
                        tone_guidelines,
                        None,
                    ),
                ),
                tone_guidelines=tone_guidelines,
                platform=platform,
            )

            if llm_result.get("method") == "llm":
                all_passed = llm_result["passed"]
                checks = self._build_llm_checks(llm_result)
                result = build_gate_result(
                    checks,
                    gate="G6",
                    expected_map=_EXPECTED_MAP,
                )
                result["method"] = "llm"
                result["tone_score"] = llm_result.get("tone_score", 1.0)
                result["brand_compliance"] = llm_result.get("brand_compliance", True)
                return result

            return cast(dict[str, Any], llm_result)

        return self._run_deterministic(content, tone_guidelines, mock_results)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_deterministic(
        self,
        content: str,
        tone_guidelines: str,
        mock_results: dict[str, dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Run the keyword-matching tone check (deterministic path)."""
        checks: list[CheckResult] = []

        if mock_results is not None and "tone_consistency" in mock_results:
            mock = mock_results["tone_consistency"]
            checks.append(
                {
                    "name": "tone_consistency",
                    "passed": bool(mock["passed"]),
                    "detail": str(mock.get("detail", "")),
                }
            )
        else:
            checks.append(_deterministic_tone_check(content, tone_guidelines))

        return build_gate_result(
            checks,
            gate="G6",
            expected_map=_EXPECTED_MAP,
        )

    def _build_result_from_mocks(
        self,
        tone_guidelines: str,
        mock_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Build gate result solely from mock overrides, skipping real checks."""
        # When mock results are provided for all checks, use them directly
        if "tone_consistency" in mock_results:
            return self._run_deterministic("", tone_guidelines, mock_results)

        # If no matching mock key, also run deterministic (it respects mocks)
        return self._run_deterministic("", tone_guidelines, mock_results)

    @staticmethod
    def _build_llm_checks(llm_result: LLMCheckResult) -> list[CheckResult]:
        """Convert LLM result into a checks list for standard format."""
        passed: bool = llm_result["passed"]
        issues: list[str] = llm_result.get("issues", [])
        detail = (
            "; ".join(issues) if issues else ("all tone checks passed" if passed else "tone issues found")
        )
        return [{"name": "tone_consistency", "passed": passed, "detail": detail}]

    # Expose as class methods for testing convenience
    @classmethod
    def extract_tone_guidelines(cls, brand_profile: dict[str, Any] | None) -> str:
        """Public wrapper for _build_tone_guidelines."""
        return _build_tone_guidelines(brand_profile)
