"""Tests for G1Humanizer gate — 9-category AI writing pattern detection."""

from __future__ import annotations

from typing import Any

from automedia.gates.base import BaseGate, _registry
from automedia.gates.humanizer import (
    _CHECK_NAMES,
    G1Humanizer,
    _check_absolute_assertions,
    _check_filler_connectors,
    _check_hollow_intros,
    _check_long_conjunctions,
    _check_overacademic_vocabulary,
    _check_overused_adverbs,
    _check_repetitive_structures,
    _check_template_conclusions,
    _check_vague_subjects,
    _rewrite_content,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_CLEAN_CONTENT = (
    "The team finished the project ahead of schedule. "
    "Each member contributed unique skills to the effort. "
    "Results exceeded expectations across all metrics."
)


def _make_context(
    *,
    content: str = _CLEAN_CONTENT,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a gate_context dict with sensible defaults."""
    ctx: dict[str, Any] = {"content": content}
    if mock_results is not None:
        ctx["_mock_results"] = mock_results
    return ctx


def _all_pass_mock() -> dict[str, dict[str, Any]]:
    """Return mock results where every check passes."""
    return {name: {"passed": True, "detail": "ok"} for name in _CHECK_NAMES}


def _fail_check(name: str, detail: str = "detected") -> dict[str, dict[str, Any]]:
    """Return mock results where *name* fails and the rest pass."""
    results = _all_pass_mock()
    results[name] = {"passed": False, "detail": detail}
    return results


# =========================================================================
# Gate metadata & registration
# =========================================================================


class TestG1HumanizerMetadata:
    """G1Humanizer has correct gate_name, failure_mode, and is registered."""

    def test_gate_name(self) -> None:
        gate = G1Humanizer()
        assert gate.gate_name == "G1"

    def test_failure_mode_is_rewrite(self) -> None:
        gate = G1Humanizer()
        assert gate.failure_mode == "retry"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(G1Humanizer, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "G1" in _registry
        assert _registry.get("G1") is G1Humanizer


# =========================================================================
# Mock-driven execute() tests
# =========================================================================


class TestG1MockDriven:
    """execute() respects _mock_results for deterministic testing."""

    def test_all_checks_pass(self) -> None:
        """All 9 mock checks pass → overall passed=True."""
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G1Humanizer().execute(ctx)

        assert result["passed"] is True
        assert result["gate"] == "G1"
        assert result["error"] is None
        assert result["modified_content"] is None
        assert len(result["checks"]) == 9

    def test_single_check_failure(self) -> None:
        """Any single check failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("overused_adverbs"))
        result = G1Humanizer().execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == "G1"
        failed = [c for c in result["checks"] if not c["passed"]]
        assert len(failed) == 1
        assert failed[0]["name"] == "overused_adverbs"

    def test_modified_content_present_on_failure(self) -> None:
        """When mock check fails and content exists → modified_content is set."""
        ctx = _make_context(
            content="Some text here.",
            mock_results=_fail_check("overused_adverbs"),
        )
        result = G1Humanizer().execute(ctx)

        assert result["passed"] is False
        assert result["modified_content"] is not None
        assert isinstance(result["modified_content"], str)

    def test_all_checks_fail(self) -> None:
        """All 9 checks fail → overall passed=False."""
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        ctx = _make_context(mock_results=fail_all)
        result = G1Humanizer().execute(ctx)

        assert result["passed"] is False
        assert len(result["checks"]) == 9
        assert all(not c["passed"] for c in result["checks"])

    def test_mock_detail_propagated(self) -> None:
        """Mock detail strings appear verbatim in result."""
        mock = _all_pass_mock()
        mock["hollow_intros"] = {"passed": False, "detail": "custom detail xyz"}
        ctx = _make_context(mock_results=mock)
        result = G1Humanizer().execute(ctx)

        hi = next(c for c in result["checks"] if c["name"] == "hollow_intros")
        assert hi["detail"] == "custom detail xyz"


# =========================================================================
# Real-logic tests — one per pattern category
# =========================================================================


class TestG1RealOverusedAdverbs:
    """Real detection of overused adverbs."""

    def test_detects_importantly(self) -> None:
        result = _check_overused_adverbs("Importantly, the data shows growth.")
        assert result["passed"] is False
        assert "importantly" in result["detail"]

    def test_clean_text_passes(self) -> None:
        result = _check_overused_adverbs("The data shows clear growth trends.")
        assert result["passed"] is True


class TestG1RealHollowIntros:
    """Real detection of hollow introductory phrases."""

    def test_detects_in_todays_world(self) -> None:
        result = _check_hollow_intros("In today's world, technology is everywhere.")
        assert result["passed"] is False

    def test_detects_its_worth_noting(self) -> None:
        result = _check_hollow_intros("It's worth noting that rates have changed.")
        assert result["passed"] is False

    def test_clean_text_passes(self) -> None:
        result = _check_hollow_intros("Technology is everywhere now.")
        assert result["passed"] is True


class TestG1RealVagueSubjects:
    """Real detection of vague subject constructions."""

    def test_detects_we_must(self) -> None:
        result = _check_vague_subjects("We must address climate change.")
        assert result["passed"] is False

    def test_detects_we_need_to(self) -> None:
        result = _check_vague_subjects("We need to improve efficiency.")
        assert result["passed"] is False

    def test_clean_text_passes(self) -> None:
        result = _check_vague_subjects("The team improved efficiency by 20%.")
        assert result["passed"] is True


class TestG1RealFillerConnectors:
    """Real detection of filler connectors at sentence starts."""

    def test_detects_furthermore(self) -> None:
        result = _check_filler_connectors("Furthermore, the results were strong.")
        assert result["passed"] is False

    def test_detects_moreover(self) -> None:
        result = _check_filler_connectors("Moreover, revenue increased.")
        assert result["passed"] is False

    def test_detects_additionally(self) -> None:
        result = _check_filler_connectors("Additionally, costs dropped.")
        assert result["passed"] is False

    def test_mid_sentence_usage_passes(self) -> None:
        """'Furthermore' mid-sentence is not a sentence-start filler."""
        result = _check_filler_connectors("The plan was furthermore refined by the team.")
        assert result["passed"] is True


class TestG1RealLongConjunctions:
    """Real detection of long conjunction chains."""

    def test_detects_triple_and(self) -> None:
        result = _check_long_conjunctions(
            "We offer design and development and testing and deployment."
        )
        assert result["passed"] is False

    def test_single_conjunction_passes(self) -> None:
        result = _check_long_conjunctions("We offer design and development services.")
        assert result["passed"] is True


class TestG1RealTemplateConclusions:
    """Real detection of template-style conclusions."""

    def test_detects_in_conclusion(self) -> None:
        result = _check_template_conclusions("In conclusion, the project was a success.")
        assert result["passed"] is False

    def test_detects_to_sum_up(self) -> None:
        result = _check_template_conclusions("To sum up, we achieved our goals.")
        assert result["passed"] is False

    def test_clean_text_passes(self) -> None:
        result = _check_template_conclusions("The project delivered strong results.")
        assert result["passed"] is True


class TestG1RealOveracademicVocabulary:
    """Real detection of over-academic vocabulary."""

    def test_detects_utilize(self) -> None:
        result = _check_overacademic_vocabulary("We utilize modern tools.")
        assert result["passed"] is False
        assert "utilize" in result["detail"]

    def test_detects_leverage(self) -> None:
        result = _check_overacademic_vocabulary("We leverage AI capabilities.")
        assert result["passed"] is False
        assert "leverage" in result["detail"]

    def test_clean_text_passes(self) -> None:
        result = _check_overacademic_vocabulary("We use modern tools.")
        assert result["passed"] is True


class TestG1RealAbsoluteAssertions:
    """Real detection of absolute assertions."""

    def test_detects_always(self) -> None:
        result = _check_absolute_assertions("This always works perfectly.")
        assert result["passed"] is False

    def test_detects_never(self) -> None:
        result = _check_absolute_assertions("This never fails under pressure.")
        assert result["passed"] is False

    def test_detects_everyone_knows(self) -> None:
        result = _check_absolute_assertions("Everyone knows that exercise is good.")
        assert result["passed"] is False

    def test_clean_text_passes(self) -> None:
        result = _check_absolute_assertions("This usually works well.")
        assert result["passed"] is True


class TestG1RealRepetitiveStructures:
    """Real detection of repetitive sentence-opening structures."""

    def test_detects_triple_repetition(self) -> None:
        text = "The system works. The system scales. The system adapts. Other things change."
        result = _check_repetitive_structures(text)
        assert result["passed"] is False
        assert "the" in result["detail"]

    def test_varied_openings_pass(self) -> None:
        text = "The system works. Revenue grew. Teams adapted well."
        result = _check_repetitive_structures(text)
        assert result["passed"] is True

    def test_too_few_sentences_pass(self) -> None:
        result = _check_repetitive_structures("Short text.")
        assert result["passed"] is True


# =========================================================================
# Rewrite / modification tests
# =========================================================================


class TestG1Rewrite:
    """_rewrite_content produces cleaner output."""

    def test_replaces_utilize_with_use(self) -> None:
        result = _rewrite_content("We utilize modern tools.")
        assert "utilize" not in result.lower()
        assert "use" in result.lower()

    def test_replaces_leverage_with_use(self) -> None:
        result = _rewrite_content("We leverage AI capabilities.")
        assert "leverage" not in result.lower()
        assert "use" in result.lower()

    def test_softens_always(self) -> None:
        result = _rewrite_content("This always delivers results.")
        assert "always" not in result.lower()
        assert "often" in result.lower()

    def test_softens_never(self) -> None:
        result = _rewrite_content("This never fails.")
        assert "never" not in result.lower()
        assert "rarely" in result.lower()

    def test_removes_furthermore(self) -> None:
        result = _rewrite_content("Furthermore, the data confirms this.")
        assert "furthermore" not in result.lower()

    def test_removes_hollow_intro(self) -> None:
        result = _rewrite_content("In today's world, technology matters.")
        assert "in today" not in result.lower()

    def test_removes_template_conclusion(self) -> None:
        result = _rewrite_content("In conclusion, we succeeded.")
        assert "in conclusion" not in result.lower()


# =========================================================================
# Result structure
# =========================================================================


class TestG1ResultStructure:
    """Returned dict always has the expected keys and types."""

    def test_result_has_all_required_keys(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G1Humanizer().execute(ctx)

        assert "passed" in result
        assert "gate" in result
        assert "checks" in result
        assert "modified_content" in result
        assert "error" in result

    def test_checks_have_correct_structure(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G1Humanizer().execute(ctx)

        for check in result["checks"]:
            assert "name" in check
            assert "passed" in check
            assert "detail" in check
            assert isinstance(check["passed"], bool)
            assert isinstance(check["detail"], str)

    def test_all_nine_checks_present(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G1Humanizer().execute(ctx)

        check_names = [c["name"] for c in result["checks"]]
        assert check_names == _CHECK_NAMES


# =========================================================================
# Edge cases
# =========================================================================


class TestG1EdgeCases:
    """Edge-case handling."""

    def test_missing_context_keys(self) -> None:
        """Empty gate_context doesn't crash — uses defaults."""
        result = G1Humanizer().execute({})
        assert result["gate"] == "G1"
        assert isinstance(result["checks"], list)
        assert len(result["checks"]) == 9

    def test_empty_content_all_pass(self) -> None:
        """Empty content → all checks pass (nothing to detect)."""
        result = G1Humanizer().execute({"content": ""})
        assert result["passed"] is True
        assert result["modified_content"] is None

    def test_clean_content_all_pass(self) -> None:
        """Clean, human-written content passes all 9 checks."""
        ctx = _make_context(content=_CLEAN_CONTENT)
        result = G1Humanizer().execute(ctx)
        assert result["passed"] is True
        assert result["modified_content"] is None

    def test_modified_content_none_when_all_pass(self) -> None:
        """When all checks pass, modified_content is None."""
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G1Humanizer().execute(ctx)
        assert result["modified_content"] is None

    def test_all_9_pattern_categories_covered(self) -> None:
        """Red Line 4: all 9 pattern categories are present as checks."""
        assert len(_CHECK_NAMES) == 9
        expected = {
            "overused_adverbs",
            "hollow_intros",
            "vague_subjects",
            "filler_connectors",
            "long_conjunctions",
            "template_conclusions",
            "overacademic_vocabulary",
            "absolute_assertions",
            "repetitive_structures",
        }
        assert set(_CHECK_NAMES) == expected
