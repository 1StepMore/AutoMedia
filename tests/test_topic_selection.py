"""Tests for TopicSelectionGate — pre-gate topic quality filtering."""

from __future__ import annotations

from typing import Any

from automedia.gates.base import BaseGate, _registry
from automedia.gates.topic_selection import _CHECK_NAMES, TopicSelectionGate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_context(
    *,
    topic: str = "AI advances in medical diagnosis",
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a gate_context dict with sensible defaults."""
    ctx: dict[str, Any] = {
        "topic": topic,
    }
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


class TestTopicSelectionMetadata:
    """TopicSelectionGate has correct gate_name, failure_mode, and is registered."""

    def test_gate_name(self) -> None:
        gate = TopicSelectionGate()
        assert gate.gate_name == "pre-gate"

    def test_failure_mode(self) -> None:
        gate = TopicSelectionGate()
        assert gate.failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(TopicSelectionGate, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "pre-gate" in _registry
        assert _registry.get("pre-gate") is TopicSelectionGate


# =========================================================================
# Mock-driven execute() tests
# =========================================================================


class TestTopicSelectionMockDriven:
    """execute() respects _mock_results for deterministic testing."""

    def test_all_checks_pass(self) -> None:
        """All mock checks pass → overall passed=True."""
        ctx = _make_context(mock_results=_all_pass_mock())
        result = TopicSelectionGate().execute(ctx)

        assert result["passed"] is True
        assert result["gate"] == "pre-gate"
        assert result["error"] is None
        assert len(result["checks"]) == 6

    def test_single_check_failure(self) -> None:
        """One check fails → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("topic_not_finance", "finance topic"))
        result = TopicSelectionGate().execute(ctx)

        assert result["passed"] is False
        failed = [c for c in result["checks"] if not c["passed"]]
        assert len(failed) == 1
        assert failed[0]["name"] == "topic_not_finance"

    def test_all_checks_fail(self) -> None:
        """All 6 checks fail → overall passed=False."""
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        ctx = _make_context(mock_results=fail_all)
        result = TopicSelectionGate().execute(ctx)

        assert result["passed"] is False
        assert all(not c["passed"] for c in result["checks"])


# =========================================================================
# Real-logic tests — forbidden categories
# =========================================================================


class TestTopicSelectionForbidden:
    """Topics matching forbidden categories are intercepted."""

    def test_clean_topic_passes(self) -> None:
        """A topic with no forbidden patterns passes."""
        ctx = _make_context(topic="How AI is improving crop yields in agriculture")
        result = TopicSelectionGate().execute(ctx)
        assert result["passed"] is True

    def test_charity_topic_blocked(self) -> None:
        """公益 topic is blocked."""
        ctx = _make_context(topic="公益科普：如何预防流感")
        result = TopicSelectionGate().execute(ctx)
        assert result["passed"] is False
        charity = next(c for c in result["checks"] if c["name"] == "topic_not_charity")
        assert charity["passed"] is False

    def test_government_tool_topic_blocked(self) -> None:
        """政府 tool topic is blocked."""
        ctx = _make_context(topic="政府数字化转型工具推荐")
        result = TopicSelectionGate().execute(ctx)
        assert result["passed"] is False
        gov = next(c for c in result["checks"] if c["name"] == "topic_not_gov_tool")
        assert gov["passed"] is False

    def test_investment_topic_blocked(self) -> None:
        """投资 topic is blocked."""
        ctx = _make_context(topic="2026年最佳投资策略分析")
        result = TopicSelectionGate().execute(ctx)
        assert result["passed"] is False
        inv = next(c for c in result["checks"] if c["name"] == "topic_not_investment")
        assert inv["passed"] is False

    def test_finance_topic_blocked(self) -> None:
        """金融 topic is blocked."""
        ctx = _make_context(topic="金融科技行业趋势报告")
        result = TopicSelectionGate().execute(ctx)
        assert result["passed"] is False
        fin = next(c for c in result["checks"] if c["name"] == "topic_not_finance")
        assert fin["passed"] is False

    def test_entertainment_topic_blocked(self) -> None:
        """娱乐 topic is blocked."""
        ctx = _make_context(topic="娱乐圈最新八卦新闻")
        result = TopicSelectionGate().execute(ctx)
        assert result["passed"] is False
        ent = next(c for c in result["checks"] if c["name"] == "topic_not_entertainment")
        assert ent["passed"] is False

    def test_concert_event_blocked(self) -> None:
        """Bug 1 fix: 演唱会 (concert) is blocked as entertainment."""
        ctx = _make_context(topic="演唱会现场精彩回顾")
        result = TopicSelectionGate().execute(ctx)
        assert result["passed"] is False, f"got passed={result['passed']}"
        ent = next(c for c in result["checks"] if c["name"] == "topic_not_entertainment")
        assert ent["passed"] is False, f"entertainment check passed: {ent}"

    def test_sports_event_blocked(self) -> None:
        """Bug 1: 体育 (sports) is blocked as entertainment."""
        ctx = _make_context(topic="足球比赛精彩瞬间")
        result = TopicSelectionGate().execute(ctx)
        assert result["passed"] is False, f"got passed={result['passed']}"

    def test_english_charity_blocked(self) -> None:
        """English charity keyword is blocked."""
        ctx = _make_context(topic="Top 10 charity organizations to donate to")
        result = TopicSelectionGate().execute(ctx)
        assert result["passed"] is False
        charity = next(c for c in result["checks"] if c["name"] == "topic_not_charity")
        assert charity["passed"] is False

    def test_english_finance_blocked(self) -> None:
        """English finance keyword is blocked."""
        ctx = _make_context(topic="Best financial planning tools for 2026")
        result = TopicSelectionGate().execute(ctx)
        assert result["passed"] is False
        fin = next(c for c in result["checks"] if c["name"] == "topic_not_finance")
        assert fin["passed"] is False

    def test_case_insensitive_matching(self) -> None:
        """Matching is case-insensitive."""
        ctx = _make_context(topic="INVESTMENT banking trends")
        result = TopicSelectionGate().execute(ctx)
        assert result["passed"] is False
        inv = next(c for c in result["checks"] if c["name"] == "topic_not_investment")
        assert inv["passed"] is False


# =========================================================================
# Real-logic tests — length validation
# =========================================================================


class TestTopicSelectionLength:
    """Topic length validation."""

    def test_topic_too_short_fails(self) -> None:
        """Topic shorter than 5 chars fails."""
        ctx = _make_context(topic="Hi")
        result = TopicSelectionGate().execute(ctx)
        tl = next(c for c in result["checks"] if c["name"] == "topic_length_valid")
        assert tl["passed"] is False
        assert "too short" in tl["detail"]

    def test_topic_too_long_fails(self) -> None:
        """Topic longer than 500 chars fails."""
        ctx = _make_context(topic="A" * 501)
        result = TopicSelectionGate().execute(ctx)
        tl = next(c for c in result["checks"] if c["name"] == "topic_length_valid")
        assert tl["passed"] is False
        assert "too long" in tl["detail"]

    def test_topic_empty_fails(self) -> None:
        """Empty topic fails."""
        ctx = _make_context(topic="")
        result = TopicSelectionGate().execute(ctx)
        assert result["passed"] is False

    def test_topic_just_right_length_passes(self) -> None:
        """Topic with valid length passes."""
        ctx = _make_context(topic="Quantum computing applications in drug discovery")
        result = TopicSelectionGate().execute(ctx)
        tl = next(c for c in result["checks"] if c["name"] == "topic_length_valid")
        assert tl["passed"] is True


# =========================================================================
# Result structure
# =========================================================================


class TestTopicSelectionResultStructure:
    """Returned dict always has the expected keys and types."""

    def test_result_has_all_required_keys(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = TopicSelectionGate().execute(ctx)

        assert "passed" in result
        assert "gate" in result
        assert "checks" in result
        assert "error" in result

    def test_checks_have_correct_structure(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = TopicSelectionGate().execute(ctx)

        for check in result["checks"]:
            assert "name" in check
            assert "passed" in check
            assert "detail" in check
            assert isinstance(check["passed"], bool)
            assert isinstance(check["detail"], str)

    def test_all_six_checks_present(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = TopicSelectionGate().execute(ctx)

        check_names = [c["name"] for c in result["checks"]]
        assert check_names == _CHECK_NAMES


# =========================================================================
# Edge cases
# =========================================================================


class TestTopicSelectionEdgeCases:
    """Edge-case handling."""

    def test_empty_context_does_not_crash(self) -> None:
        """Empty gate_context doesn't crash."""
        result = TopicSelectionGate().execute({})
        assert result["gate"] == "pre-gate"
        assert isinstance(result["checks"], list)
        assert result["passed"] is False  # Empty topic fails

    def test_non_string_topic(self) -> None:
        """Non-string topic is treated as empty."""
        ctx = _make_context(topic=12345)  # type: ignore[arg-type]
        result = TopicSelectionGate().execute(ctx)
        assert result["passed"] is False

    def test_mixed_english_chinese_blocked(self) -> None:
        """Mixed language with forbidden phrase is blocked."""
        ctx = _make_context(topic="政府 AI policy recommendations for 2026")
        result = TopicSelectionGate().execute(ctx)
        assert result["passed"] is False
        gov = next(c for c in result["checks"] if c["name"] == "topic_not_gov_tool")
        assert gov["passed"] is False

    def test_mock_detail_propagated(self) -> None:
        """Mock detail strings appear verbatim."""
        mock = _all_pass_mock()
        mock["topic_not_entertainment"] = {"passed": False, "detail": "custom entertainment block"}
        ctx = _make_context(mock_results=mock)
        result = TopicSelectionGate().execute(ctx)
        ent = next(c for c in result["checks"] if c["name"] == "topic_not_entertainment")
        assert ent["detail"] == "custom entertainment block"
