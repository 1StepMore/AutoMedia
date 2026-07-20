"""Tests for G6 Tone Check Gate — brand tone consistency validation.

Covers ``G6ToneCheckGate.execute()`` with:
- Mock-driven execution (deterministic, no LLM)
- Deterministic keyword-matching path (``enable_llm=False``)
- Edge cases (empty context, whitespace-only content)
- Gate metadata and registry registration
"""

from __future__ import annotations

from typing import Any

from automedia.gates.base import BaseGate, _registry
from automedia.gates.g6_tone_check import G6ToneCheckGate

# =========================================================================
# Helpers
# =========================================================================


def _make_context(
    *,
    content: str = "",
    brand_profile: dict[str, Any] | None = None,
    mock_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a gate_context dict with sensible defaults.

    Sets ``enable_llm=False`` to force deterministic keyword-matching
    path for all non-mocked tests.
    """
    ctx: dict[str, Any] = {
        "content": content,
        "config": {"enable_llm": False},
    }
    if brand_profile is not None:
        ctx["brand_profile"] = brand_profile
    if mock_results is not None:
        ctx["_mock_results"] = mock_results
    return ctx


PROFESSIONAL_PROFILE: dict[str, Any] = {
    "tone_guidelines": "professional",
    "personality": "authoritative and data-driven",
}


# =========================================================================
# Gate metadata & registration
# =========================================================================


class TestG6Metadata:
    """G6ToneCheckGate has correct gate metadata and is auto-registered."""

    def test_gate_name(self) -> None:
        gate = G6ToneCheckGate()
        assert gate.gate_name == "G6"

    def test_failure_mode(self) -> None:
        gate = G6ToneCheckGate()
        assert gate.failure_mode == "retry"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(G6ToneCheckGate, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "G6" in _registry
        assert _registry.get("G6") is G6ToneCheckGate


# =========================================================================
# Mock-driven execution
# =========================================================================


class TestExecuteWithMockResults:
    """G6ToneCheckGate.execute() with _mock_results overrides."""

    def test_matching_tone_passes(self) -> None:
        """Mock result with passed=True returns passed gate result."""
        ctx = _make_context(
            content="This content matches the brand tone perfectly.",
            mock_results={
                "tone_consistency": {
                    "passed": True,
                    "detail": "tone matches brand profile: 'professional'",
                }
            },
        )
        result = G6ToneCheckGate().execute(ctx)
        assert result["passed"] is True
        assert result["gate"] == "G6"
        assert result["checks"][0]["passed"] is True
        assert "tone matches brand profile" in result["checks"][0]["detail"]

    def test_tone_violation_fails(self) -> None:
        """Mock result with passed=False returns failure with violations."""
        ctx = _make_context(
            content="This content has blatant tone violations.",
            mock_results={
                "tone_consistency": {
                    "passed": False,
                    "detail": "conflicting 'casual' tone markers found: hey, awesome",
                }
            },
        )
        result = G6ToneCheckGate().execute(ctx)
        assert result["passed"] is False
        assert result["gate"] == "G6"
        assert result["checks"][0]["passed"] is False
        assert "conflicting" in result["checks"][0]["detail"]

    def test_mock_overrides_empty_content(self) -> None:
        """Mock results take precedence even when content is empty."""
        ctx = _make_context(
            content="",
            mock_results={
                "tone_consistency": {
                    "passed": False,
                    "detail": "tone violation detected by mock",
                }
            },
        )
        result = G6ToneCheckGate().execute(ctx)
        assert result["passed"] is False
        assert result["checks"][0]["passed"] is False
        assert "tone violation" in result["checks"][0]["detail"]


# =========================================================================
# Deterministic path (enable_llm=False)
# =========================================================================


class TestDeterministicPath:
    """Deterministic keyword-matching path with enable_llm=False."""

    def test_professional_tone_match(self) -> None:
        """Content with professional + authoritative keywords passes tone check."""
        ctx = _make_context(
            content=(
                "Our research and analysis of data suggests that "
                "this established approach is proven to work. "
                "It is essential and critical that we mandate "
                "these standards."
            ),
            brand_profile=PROFESSIONAL_PROFILE,
        )
        result = G6ToneCheckGate().execute(ctx)
        assert result["passed"] is True
        assert result["checks"][0]["name"] == "tone_consistency"
        assert "tone matches brand profile" in result["checks"][0]["detail"]

    def test_tone_conflict_detected(self) -> None:
        """Content mixing professional and casual tones fails."""
        ctx = _make_context(
            content="Based on our research, hey check it out this awesome data!",
            brand_profile=PROFESSIONAL_PROFILE,
        )
        result = G6ToneCheckGate().execute(ctx)
        assert result["passed"] is False
        assert result["checks"][0]["passed"] is False
        detail = result["checks"][0]["detail"]
        # Should report either conflicting tone markers or negative violations
        assert "conflicting" in detail or "violate" in detail

    def test_empty_content_handled_gracefully(self) -> None:
        """Empty content returns passed=True with 'empty content' detail."""
        ctx = _make_context(
            content="",
            brand_profile=PROFESSIONAL_PROFILE,
        )
        result = G6ToneCheckGate().execute(ctx)
        assert result["passed"] is True
        assert result["checks"][0]["detail"] == "empty content"

    def test_missing_brand_profile_handled_gracefully(self) -> None:
        """No brand_profile handled without crash (returns passed=True with
        descriptive detail about missing guidelines)."""
        ctx = _make_context(
            content="Content with positive tone indicators.",
            # brand_profile intentionally omitted
        )
        result = G6ToneCheckGate().execute(ctx)
        assert result["passed"] is True
        assert "no tone guidelines" in result["checks"][0]["detail"].lower() or \
            "positive tone indicators" in result["checks"][0]["detail"]

    def test_empty_brand_profile_handled(self) -> None:
        """Brand profile with empty tone_guidelines is handled without crash."""
        ctx = _make_context(
            content="Some content.",
            brand_profile={},
        )
        result = G6ToneCheckGate().execute(ctx)
        assert result["passed"] is True
        assert "no tone guidelines" in result["checks"][0]["detail"].lower() or \
            "no discernible tone" in result["checks"][0]["detail"].lower()


# =========================================================================
# Edge cases
# =========================================================================


class TestEdgeCases:
    """Edge-case handling for G6 gate."""

    def test_empty_context_does_not_crash(self) -> None:
        """Empty gate_context dict does not raise."""
        result = G6ToneCheckGate().execute({})
        assert isinstance(result, dict)
        assert "passed" in result
        assert "gate" in result
        assert "checks" in result

    def test_whitespace_only_content(self) -> None:
        """Whitespace-only content is treated like empty content."""
        ctx = _make_context(
            content="   \n  \t  ",
            brand_profile={"tone_guidelines": "professional"},
        )
        result = G6ToneCheckGate().execute(ctx)
        assert result["passed"] is True
        assert result["checks"][0]["detail"] == "empty content"

    def test_extract_tone_guidelines(self) -> None:
        """extract_tone_guidelines class method builds correct string."""
        profile = {
            "tone_guidelines": "professional",
            "personality": "data-driven",
            "target_audience": "executives",
            "industry": "tech",
        }
        guidelines = G6ToneCheckGate.extract_tone_guidelines(profile)
        assert "tone guidelines: professional" in guidelines.lower()
        assert "personality: data-driven" in guidelines.lower()
        assert "audience: executives" in guidelines.lower()
        assert "industry: tech" in guidelines.lower()

    def test_extract_tone_guidelines_none(self) -> None:
        """extract_tone_guidelines returns empty string for None."""
        assert G6ToneCheckGate.extract_tone_guidelines(None) == ""

    def test_extract_tone_guidelines_empty(self) -> None:
        """extract_tone_guidelines returns empty string for empty dict."""
        assert G6ToneCheckGate.extract_tone_guidelines({}) == ""
