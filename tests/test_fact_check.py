"""Tests for G0FactCheck gate — 5-step fact-check pipeline."""

from __future__ import annotations

from typing import Any

from automedia.gates.base import BaseGate, _registry
from automedia.gates.fact_check import _CHECK_NAMES, G0FactCheck

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_context(
    *,
    topic: str = "Test Topic",
    content: str = "Some content from example.com about events on 2024-01-15.",
    source_data: dict[str, Any] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a gate_context dict with sensible defaults."""
    ctx: dict[str, Any] = {
        "topic": topic,
        "content": content,
        "source_data": source_data
        if source_data is not None
        else {
            "url": "https://example.com/article",
            "published_date": "2024-06-01T00:00:00",
            "key_numbers": {"revenue": "42"},
            "entities": ["Alice", "Bob"],
            "quotes": ["important quote"],
        },
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


class TestG0FactCheckMetadata:
    """G0FactCheck has correct gate_name, failure_mode, and is registered."""

    def test_gate_name(self) -> None:
        gate = G0FactCheck()
        assert gate.gate_name == "G0"

    def test_failure_mode(self) -> None:
        gate = G0FactCheck()
        assert gate.failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(G0FactCheck, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "G0" in _registry
        assert _registry.get("G0") is G0FactCheck


# =========================================================================
# Mock-driven execute() tests
# =========================================================================


class TestG0MockDriven:
    """execute() respects _mock_results for deterministic testing."""

    def test_all_checks_pass(self) -> None:
        """All 5 mock checks pass → overall passed=True, confidence=1.0."""
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G0FactCheck().execute(ctx)

        assert result["passed"] is True
        assert result["gate"] == "G0"
        assert result["error"] is None
        assert result["confidence"] == 1.0
        assert len(result["checks"]) == 5

    def test_source_trace_failure_stops_gate(self) -> None:
        """source_trace failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("source_trace", "no source"))
        result = G0FactCheck().execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == "G0"
        failed = [c for c in result["checks"] if not c["passed"]]
        assert len(failed) == 1
        assert failed[0]["name"] == "source_trace"
        assert failed[0]["detail"] == "no source"

    def test_number_verification_failure(self) -> None:
        """number_verification failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("number_verification", "mismatch"))
        result = G0FactCheck().execute(ctx)

        assert result["passed"] is False
        failed_names = [c["name"] for c in result["checks"] if not c["passed"]]
        assert "number_verification" in failed_names

    def test_timeline_failure(self) -> None:
        """timeline failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("timeline", "future date"))
        result = G0FactCheck().execute(ctx)

        assert result["passed"] is False
        failed_names = [c["name"] for c in result["checks"] if not c["passed"]]
        assert "timeline" in failed_names

    def test_quotes_failure(self) -> None:
        """quotes failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("quotes", "missing quote"))
        result = G0FactCheck().execute(ctx)

        assert result["passed"] is False
        failed_names = [c["name"] for c in result["checks"] if not c["passed"]]
        assert "quotes" in failed_names

    def test_entities_failure(self) -> None:
        """entities failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("entities", "unknown entity"))
        result = G0FactCheck().execute(ctx)

        assert result["passed"] is False
        failed_names = [c["name"] for c in result["checks"] if not c["passed"]]
        assert "entities" in failed_names

    def test_all_checks_fail_low_confidence(self) -> None:
        """All 5 checks fail → confidence=0.0."""
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        ctx = _make_context(mock_results=fail_all)
        result = G0FactCheck().execute(ctx)

        assert result["passed"] is False
        assert result["confidence"] == 0.0

    def test_partial_pass_confidence(self) -> None:
        """3 of 5 pass → confidence=0.6."""
        mock = _all_pass_mock()
        mock["source_trace"] = {"passed": False, "detail": "x"}
        mock["timeline"] = {"passed": False, "detail": "y"}
        ctx = _make_context(mock_results=mock)
        result = G0FactCheck().execute(ctx)

        assert result["passed"] is False
        assert result["confidence"] == 0.6


# =========================================================================
# Real-logic tests (no mock)
# =========================================================================


class TestG0RealLogic:
    """execute() without _mock_results runs actual check functions."""

    def test_source_trace_finds_domain(self) -> None:
        """Content mentioning the source domain passes source_trace."""
        ctx = _make_context(
            content="According to example.com, the event happened.",
            source_data={
                "url": "https://example.com/article",
                "published_date": "",
                "key_numbers": {},
                "entities": [],
                "quotes": [],
            },
        )
        result = G0FactCheck().execute(ctx)
        trace = next(c for c in result["checks"] if c["name"] == "source_trace")
        assert trace["passed"] is True

    def test_source_trace_missing_domain(self) -> None:
        """Content without source domain fails source_trace."""
        ctx = _make_context(
            content="Some content without any domain reference.",
            source_data={
                "url": "https://trusted-source.org/article",
                "published_date": "",
                "key_numbers": {},
                "entities": [],
                "quotes": [],
            },
        )
        result = G0FactCheck().execute(ctx)
        trace = next(c for c in result["checks"] if c["name"] == "source_trace")
        assert trace["passed"] is False

    def test_number_verification_passes(self) -> None:
        """Numbers in content matching source_data pass."""
        ctx = _make_context(
            content="Revenue was 42 million this year.",
            source_data={
                "url": "",
                "published_date": "",
                "key_numbers": {"revenue": "42"},
                "entities": [],
                "quotes": [],
            },
        )
        result = G0FactCheck().execute(ctx)
        num = next(c for c in result["checks"] if c["name"] == "number_verification")
        assert num["passed"] is True

    def test_number_verification_fails_on_mismatch(self) -> None:
        """Numbers in content NOT matching source_data fail."""
        ctx = _make_context(
            content="Revenue was 99 million this year.",
            source_data={
                "url": "",
                "published_date": "",
                "key_numbers": {"revenue": "42"},
                "entities": [],
                "quotes": [],
            },
        )
        result = G0FactCheck().execute(ctx)
        num = next(c for c in result["checks"] if c["name"] == "number_verification")
        assert num["passed"] is False

    def test_timeline_future_date_fails(self) -> None:
        """Dates after published_date fail timeline check."""
        ctx = _make_context(
            content="Event on 2025-12-31 was significant.",
            source_data={
                "url": "",
                "published_date": "2024-01-01T00:00:00",
                "key_numbers": {},
                "entities": [],
                "quotes": [],
            },
        )
        result = G0FactCheck().execute(ctx)
        tl = next(c for c in result["checks"] if c["name"] == "timeline")
        assert tl["passed"] is False

    def test_timeline_no_future_date_passes(self) -> None:
        """All dates before published_date pass timeline check."""
        ctx = _make_context(
            content="Event on 2023-06-15 was significant.",
            source_data={
                "url": "",
                "published_date": "2024-01-01T00:00:00",
                "key_numbers": {},
                "entities": [],
                "quotes": [],
            },
        )
        result = G0FactCheck().execute(ctx)
        tl = next(c for c in result["checks"] if c["name"] == "timeline")
        assert tl["passed"] is True

    def test_quotes_missing_fails(self) -> None:
        """Quotes not found in content fail."""
        ctx = _make_context(
            content="No matching text here.",
            source_data={
                "url": "",
                "published_date": "",
                "key_numbers": {},
                "entities": [],
                "quotes": ["exact quote from source"],
            },
        )
        result = G0FactCheck().execute(ctx)
        qt = next(c for c in result["checks"] if c["name"] == "quotes")
        assert qt["passed"] is False

    def test_entities_found_passes(self) -> None:
        """All entities present in content pass."""
        ctx = _make_context(
            content="Alice met Bob at the conference.",
            source_data={
                "url": "",
                "published_date": "",
                "key_numbers": {},
                "entities": ["Alice", "Bob"],
                "quotes": [],
            },
        )
        result = G0FactCheck().execute(ctx)
        ent = next(c for c in result["checks"] if c["name"] == "entities")
        assert ent["passed"] is True

    def test_entities_missing_fails(self) -> None:
        """Entities not found in content fail."""
        ctx = _make_context(
            content="Charlie spoke at the event.",
            source_data={
                "url": "",
                "published_date": "",
                "key_numbers": {},
                "entities": ["Alice", "Bob"],
                "quotes": [],
            },
        )
        result = G0FactCheck().execute(ctx)
        ent = next(c for c in result["checks"] if c["name"] == "entities")
        assert ent["passed"] is False

    def test_empty_source_data_all_pass(self) -> None:
        """Empty source_data → all checks pass (nothing to verify)."""
        ctx = _make_context(
            content="Any content.",
            source_data={},
        )
        result = G0FactCheck().execute(ctx)
        assert result["passed"] is True
        assert result["confidence"] == 1.0


# =========================================================================
# Result structure
# =========================================================================


class TestG0ResultStructure:
    """Returned dict always has the expected keys and types."""

    def test_result_has_all_required_keys(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G0FactCheck().execute(ctx)

        assert "passed" in result
        assert "gate" in result
        assert "checks" in result
        assert "error" in result
        assert "confidence" in result

    def test_checks_have_correct_structure(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G0FactCheck().execute(ctx)

        for check in result["checks"]:
            assert "name" in check
            assert "passed" in check
            assert "detail" in check
            assert isinstance(check["passed"], bool)
            assert isinstance(check["detail"], str)

    def test_all_five_checks_present(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G0FactCheck().execute(ctx)

        check_names = [c["name"] for c in result["checks"]]
        assert check_names == _CHECK_NAMES


# =========================================================================
# Edge cases
# =========================================================================


class TestG0EdgeCases:
    """Edge-case handling."""

    def test_missing_context_keys(self) -> None:
        """Empty gate_context doesn't crash — uses defaults."""
        result = G0FactCheck().execute({})
        assert result["gate"] == "G0"
        assert isinstance(result["checks"], list)

    def test_red_line_gate_failure_returns_failed_status(self) -> None:
        """Red Line 1: gate failure is detectable via passed=False."""
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        ctx = _make_context(mock_results=fail_all)
        result = G0FactCheck().execute(ctx)
        assert result["passed"] is False
        # Caller checks passed flag to determine pipeline stop
        assert result["gate"] == "G0"

    def test_mock_result_detail_propagated(self) -> None:
        """Mock detail strings appear verbatim in result."""
        mock = _all_pass_mock()
        mock["timeline"] = {"passed": False, "detail": "custom error 123"}
        ctx = _make_context(mock_results=mock)
        result = G0FactCheck().execute(ctx)
        tl = next(c for c in result["checks"] if c["name"] == "timeline")
        assert tl["detail"] == "custom error 123"
