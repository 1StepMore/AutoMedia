"""Tests for G2CopyReview gate — 5-round structural copy quality review."""

from __future__ import annotations

from typing import Any

from automedia.gates.base import BaseGate, _registry
from automedia.gates.copy_review import (
    _CHECK_NAMES,
    G2CopyReview,
    _check_clarity,
    _check_evidence,
    _check_so_what,
    _check_specificity,
    _check_tone,
    _rewrite_content,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_CLEAN_CONTENT = (
    "Our team reduced onboarding time by 40% over six months. "
    "New hires reach full productivity in two weeks instead of five. "
    "For example, the Berlin office cut ramp-up from 35 days to 14. "
    "This leads to faster project delivery and lower training costs."
)


def _make_context(
    *,
    content: str = _CLEAN_CONTENT,
    brand_profile: dict[str, Any] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a gate_context dict with sensible defaults."""
    ctx: dict[str, Any] = {"content": content}
    if brand_profile is not None:
        ctx["brand_profile"] = brand_profile
    if mock_results is not None:
        ctx["_mock_results"] = mock_results
    return ctx


def _all_pass_mock() -> dict[str, dict[str, Any]]:
    """Return mock results where every check passes."""
    return {name: {"passed": True, "detail": "ok"} for name in _CHECK_NAMES}


def _fail_check(name: str, detail: str = "failed") -> dict[str, dict[str, Any]]:
    """Return mock results where *name* fails and the rest pass."""
    results = _all_pass_mock()
    results[name] = {"passed": False, "detail": detail}
    return results


# =========================================================================
# Gate metadata & registration
# =========================================================================


class TestG2CopyReviewMetadata:
    """G2CopyReview has correct gate_name, failure_mode, and is registered."""

    def test_gate_name(self) -> None:
        gate = G2CopyReview()
        assert gate.gate_name == "G2"

    def test_failure_mode_is_rewrite(self) -> None:
        gate = G2CopyReview()
        assert gate.failure_mode == "retry"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(G2CopyReview, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "G2" in _registry
        assert _registry.get("G2") is G2CopyReview


# =========================================================================
# Mock-driven execute() tests
# =========================================================================


class TestG2MockDriven:
    """execute() respects _mock_results for deterministic testing."""

    def test_all_checks_pass(self) -> None:
        """All 5 mock checks pass → overall passed=True."""
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G2CopyReview().execute(ctx)

        assert result["passed"] is True
        assert result["gate"] == "G2"
        assert result["error"] is None
        assert result["modified_content"] is None
        assert len(result["checks"]) == 5

    def test_single_check_failure(self) -> None:
        """Any single check failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("clarity"))
        result = G2CopyReview().execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == "G2"
        failed = [c for c in result["checks"] if not c["passed"]]
        assert len(failed) == 1
        assert failed[0]["name"] == "clarity"

    def test_modified_content_present_on_failure(self) -> None:
        """When mock check fails and content exists → modified_content is set."""
        ctx = _make_context(
            content="Some text here.",
            mock_results=_fail_check("tone"),
        )
        result = G2CopyReview().execute(ctx)

        assert result["passed"] is False
        assert result["modified_content"] is not None
        assert isinstance(result["modified_content"], str)

    def test_all_checks_fail(self) -> None:
        """All 5 checks fail → overall passed=False."""
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        ctx = _make_context(mock_results=fail_all)
        result = G2CopyReview().execute(ctx)

        assert result["passed"] is False
        assert len(result["checks"]) == 5
        assert all(not c["passed"] for c in result["checks"])

    def test_mock_detail_propagated(self) -> None:
        """Mock detail strings appear verbatim in result."""
        mock = _all_pass_mock()
        mock["so_what"] = {"passed": False, "detail": "custom detail xyz"}
        ctx = _make_context(mock_results=mock)
        result = G2CopyReview().execute(ctx)

        sw = next(c for c in result["checks"] if c["name"] == "so_what")
        assert sw["detail"] == "custom detail xyz"


# =========================================================================
# Real-logic tests — one per review round
# =========================================================================


class TestG2RealClarity:
    """Real detection of clarity issues."""

    def test_jargon_detected(self) -> None:
        result = _check_clarity("We leverage synergy to deliver scalable solutions.")
        assert result["passed"] is False
        assert "jargon" in result["detail"]

    def test_vague_words_detected(self) -> None:
        result = _check_clarity("It was really very quite good actually.")
        assert result["passed"] is False
        assert "vague" in result["detail"]

    def test_long_sentence_detected(self) -> None:
        long = " ".join(["word"] * 40) + "."
        result = _check_clarity(long)
        assert result["passed"] is False
        assert "35 words" in result["detail"]

    def test_clean_content_passes(self) -> None:
        result = _check_clarity(_CLEAN_CONTENT)
        assert result["passed"] is True


class TestG2RealTone:
    """Real detection of tone mismatches."""

    def test_professional_conflicts_with_casual(self) -> None:
        ctx_content = "Hey, this is awesome and cool stuff!"
        result = _check_tone(ctx_content, {"tone": "professional"})
        assert result["passed"] is False
        assert "conflicting" in result["detail"]

    def test_matching_tone_passes(self) -> None:
        ctx_content = "Therefore, the established process has proven effective."
        result = _check_tone(ctx_content, {"tone": "professional"})
        assert result["passed"] is True

    def test_no_brand_profile_passes(self) -> None:
        result = _check_tone("Some content.", None)
        assert result["passed"] is True

    def test_no_tone_key_passes(self) -> None:
        result = _check_tone("Some content.", {"language": "en"})
        assert result["passed"] is True


class TestG2RealSoWhat:
    """Real detection of 'So what?' value gaps."""

    def test_value_indicators_pass(self) -> None:
        content = "This reduces costs by 30% and improves efficiency for your team."
        result = _check_so_what(content)
        assert result["passed"] is True

    def test_question_answer_pattern_passes(self) -> None:
        content = "Why does this matter? Because it saves you hours of manual work each week."
        result = _check_so_what(content)
        assert result["passed"] is True

    def test_no_value_fails(self) -> None:
        content = "We launched a new product last quarter. The team worked hard on it."
        result = _check_so_what(content)
        assert result["passed"] is False
        assert "why should" in result["detail"].lower()


class TestG2RealEvidence:
    """Real detection of unsupported claims."""

    def test_claim_with_data_passes(self) -> None:
        content = (
            "Studies show this is the best approach. Data from 2024 confirms a 25% improvement."
        )
        result = _check_evidence(content)
        assert result["passed"] is True

    def test_claim_without_data_fails(self) -> None:
        content = "This is the best product available. It is well-known for quality."
        result = _check_evidence(content)
        assert result["passed"] is False
        assert "no supporting data" in result["detail"]

    def test_no_claims_passes(self) -> None:
        content = "We launched the product on Monday. The team celebrated."
        result = _check_evidence(content)
        assert result["passed"] is True


class TestG2RealSpecificity:
    """Real detection of abstract vs concrete language."""

    def test_abstract_without_concrete_fails(self) -> None:
        content = "Our innovative, game-changing, revolutionary solution transforms your business."
        result = _check_specificity(content)
        assert result["passed"] is False
        assert "abstract" in result["detail"]

    def test_abstract_with_concrete_passes(self) -> None:
        content = (
            "Our innovative approach cut costs by 40% in 3 months,"
            " for example in the Berlin office."
        )
        result = _check_specificity(content)
        assert result["passed"] is True

    def test_no_abstract_passes(self) -> None:
        content = "The team finished on time. Results were strong."
        result = _check_specificity(content)
        assert result["passed"] is True


# =========================================================================
# Rewrite / modification tests
# =========================================================================


class TestG2Rewrite:
    """_rewrite_content produces cleaner output."""

    def test_replaces_leverage_with_use(self) -> None:
        result = _rewrite_content("We leverage modern tools.")
        assert "leverage" not in result.lower()
        assert "use" in result.lower()

    def test_replaces_synergy_with_teamwork(self) -> None:
        result = _rewrite_content("The synergy between teams was strong.")
        assert "synergy" not in result.lower()
        assert "teamwork" in result.lower()

    def test_softens_innovative(self) -> None:
        result = _rewrite_content("Our innovative platform delivers results.")
        assert "innovative" not in result.lower()
        assert "new" in result.lower()

    def test_removes_vague_words(self) -> None:
        result = _rewrite_content("It was really very good.")
        assert "really" not in result.lower()
        assert "very" not in result.lower()

    def test_softens_game_changing(self) -> None:
        result = _rewrite_content("This game-changing tool helps teams.")
        assert "game-changing" not in result.lower()
        assert "significant" in result.lower()


# =========================================================================
# Result structure
# =========================================================================


class TestG2ResultStructure:
    """Returned dict always has the expected keys and types."""

    def test_result_has_all_required_keys(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G2CopyReview().execute(ctx)

        assert "passed" in result
        assert "gate" in result
        assert "checks" in result
        assert "modified_content" in result
        assert "error" in result

    def test_checks_have_correct_structure(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G2CopyReview().execute(ctx)

        for check in result["checks"]:
            assert "name" in check
            assert "passed" in check
            assert "detail" in check
            assert isinstance(check["passed"], bool)
            assert isinstance(check["detail"], str)

    def test_all_five_checks_present(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G2CopyReview().execute(ctx)

        check_names = [c["name"] for c in result["checks"]]
        assert check_names == _CHECK_NAMES


# =========================================================================
# Edge cases
# =========================================================================


class TestG2EdgeCases:
    """Edge-case handling."""

    def test_missing_context_keys(self) -> None:
        """Empty gate_context doesn't crash — uses defaults."""
        result = G2CopyReview().execute({})
        assert result["gate"] == "G2"
        assert isinstance(result["checks"], list)
        assert len(result["checks"]) == 5

    def test_empty_content_all_pass(self) -> None:
        """Empty content → all checks pass (nothing to detect)."""
        result = G2CopyReview().execute({"content": ""})
        assert result["passed"] is True
        assert result["modified_content"] is None

    def test_clean_content_all_pass(self) -> None:
        """Clean, well-written content passes all 5 checks."""
        ctx = _make_context(content=_CLEAN_CONTENT)
        result = G2CopyReview().execute(ctx)
        assert result["passed"] is True
        assert result["modified_content"] is None

    def test_modified_content_none_when_all_pass(self) -> None:
        """When all checks pass, modified_content is None."""
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G2CopyReview().execute(ctx)
        assert result["modified_content"] is None

    def test_red_line_gate_failure_returns_failed_status(self) -> None:
        """Red Line: gate failure is detectable via passed=False."""
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        ctx = _make_context(mock_results=fail_all)
        result = G2CopyReview().execute(ctx)
        assert result["passed"] is False
        assert result["gate"] == "G2"

    def test_all_5_rounds_covered(self) -> None:
        """Red Line 4: all 5 review rounds are present as checks."""
        assert len(_CHECK_NAMES) == 5
        expected = {"clarity", "tone", "so_what", "evidence", "specificity"}
        assert set(_CHECK_NAMES) == expected
