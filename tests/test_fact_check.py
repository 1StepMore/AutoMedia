"""Tests for G0FactCheck gate — 5-step fact-check pipeline."""

from __future__ import annotations

from typing import Any

from automedia.gates.base import BaseGate, _registry
from automedia.gates.fact_check import _CHECK_NAMES, G0FactCheck
from automedia.gates.llm_helpers import G0CheckResult
from tests.mock_llm import (
    mock_llm_failure,
    mock_llm_response,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_context(
    *,
    topic: str = "Test Topic",
    content: str = "Some content from example.com about events on 2024-01-15.",
    source_data: dict[str, Any] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
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
    if config is not None:
        ctx["config"] = config
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

    def test_empty_source_data_skipped(self) -> None:
        """Empty source_data with enable_llm=False → gate returns skipped status."""
        ctx = _make_context(
            content="Any content.",
            source_data={},
            config={"enable_llm": False},
        )
        result = G0FactCheck().execute(ctx)
        assert result["passed"] is True
        assert result["gate"] == "G0"
        assert result["status"] == "skipped"
        assert "reason" in result

    def test_empty_source_data_skip_on_llm_failure(self) -> None:
        """Empty source_data + LLM failure → gate returns skipped status."""
        ctx = _make_context(
            content="Any content.",
            source_data={},
        )
        with mock_llm_failure():
            result = G0FactCheck().execute(ctx)
        assert result["passed"] is True
        assert result["gate"] == "G0"
        assert result["status"] == "skipped"
        assert "reason" in result


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
        """Empty gate_context doesn't crash — returns skipped."""
        ctx: dict[str, Any] = {"config": {"enable_llm": False}}
        result = G0FactCheck().execute(ctx)
        assert result["gate"] == "G0"
        assert result["passed"] is True
        assert result["status"] == "skipped"
        assert "reason" in result

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


# =========================================================================
# LLM integration tests
# =========================================================================


class TestG0LlmIntegration:
    """execute() respects enable_llm flag and mock_llm helpers."""

    # ------------------------------------------------------------------
    # LLM evaluation path
    # ------------------------------------------------------------------

    def test_llm_evaluation_returns_valid_result(self) -> None:
        """When LLM returns valid data, result.method='llm'."""
        data = G0CheckResult(passed=True, issues=[], confidence=1.0)
        ctx = _make_context(
            content="Alice and Bob attended the event.",
            source_data={
                "url": "",
                "published_date": "",
                "key_numbers": {},
                "entities": ["Alice", "Bob"],
                "quotes": [],
            },
        )
        with mock_llm_response(data):
            result = G0FactCheck().execute(ctx)

        assert result.get("method") == "llm"
        assert result["passed"] is True
        assert result["confidence"] == 1.0

    def test_llm_confidences_and_issues_propagate(self) -> None:
        """LLM result issues appear in check detail, confidence at top level."""
        data = G0CheckResult(
            passed=False,
            issues=["entity 'Charlie' not verified", "source mismatch"],
            confidence=0.3,
        )
        ctx = _make_context(
            content="Alice spoke at the event.",
            source_data={
                "url": "",
                "published_date": "",
                "key_numbers": {},
                "entities": ["Alice", "Bob"],
                "quotes": [],
            },
        )
        with mock_llm_response(data):
            result = G0FactCheck().execute(ctx)

        assert result.get("method") == "llm"
        assert result["passed"] is False
        assert result["confidence"] == 0.3
        for check in result["checks"]:
            assert "entity 'Charlie' not verified" in check["detail"]
            assert "source mismatch" in check["detail"]

    # ------------------------------------------------------------------
    # LLM failure → fallback path
    # ------------------------------------------------------------------

    def test_llm_failure_falls_back_to_deterministic(self) -> None:
        """When LLM fails, result.method='deterministic'."""
        ctx = _make_context(
            content="Alice and Bob attended the event.",
            source_data={
                "url": "",
                "published_date": "",
                "key_numbers": {},
                "entities": ["Alice", "Bob"],
                "quotes": [],
            },
        )
        with mock_llm_failure():
            result = G0FactCheck().execute(ctx)

        assert result.get("method") == "deterministic"

    def test_llm_failure_still_produces_valid_results(self) -> None:
        """After LLM fallback, deterministic logic still finds matching entities."""
        ctx = _make_context(
            content="Alice and Bob attended the event.",
            source_data={
                "url": "",
                "published_date": "",
                "key_numbers": {},
                "entities": ["Alice", "Bob"],
                "quotes": [],
            },
        )
        with mock_llm_failure():
            result = G0FactCheck().execute(ctx)

        assert result["passed"] is not None
        ent = next(c for c in result["checks"] if c["name"] == "entities")
        assert ent["passed"] is True  # Alice and Bob are in the content

    # ------------------------------------------------------------------
    # enable_llm=False flag
    # ------------------------------------------------------------------

    def test_enable_llm_false_uses_deterministic(self) -> None:
        """When enable_llm=False, result.method='deterministic'."""
        ctx = _make_context(
            content="Alice and Bob attended the event.",
            source_data={
                "url": "",
                "published_date": "",
                "key_numbers": {},
                "entities": ["Alice", "Bob"],
                "quotes": [],
            },
            config={"enable_llm": False},
        )
        result = G0FactCheck().execute(ctx)

        assert result.get("method") == "deterministic"
        # Deterministic logic still works
        ent = next(c for c in result["checks"] if c["name"] == "entities")
        assert ent["passed"] is True

    # ------------------------------------------------------------------
    # LLM plausibility check (empty source_data + enable_llm=True)
    # ------------------------------------------------------------------

    def test_llm_plausibility_check_passes(self) -> None:
        data = G0CheckResult(passed=True, issues=[], confidence=0.95)
        ctx = _make_context(
            content="The Earth revolves around the Sun.",
            source_data={},
            config={"enable_llm": True},
        )
        with mock_llm_response(data):
            result = G0FactCheck().execute(ctx)

        assert result["gate"] == "G0"
        assert result["passed"] is True
        assert result.get("method") == "llm"
        assert result.get("status") == "completed"
        assert len(result["checks"]) == 1
        assert result["checks"][0]["name"] == "plausibility_check"
        assert result["checks"][0]["passed"] is True
        assert result["confidence"] == 0.95

    def test_llm_plausibility_check_fails(self) -> None:
        data = G0CheckResult(
            passed=False,
            issues=["Claims 'Earth is flat' contradicts established scientific consensus"],
            confidence=0.3,
        )
        ctx = _make_context(
            content="The Earth is flat.",
            source_data={},
            config={"enable_llm": True},
        )
        with mock_llm_response(data):
            result = G0FactCheck().execute(ctx)

        assert result["gate"] == "G0"
        assert result["passed"] is False
        assert result.get("method") == "llm"
        assert result.get("status") == "completed"
        assert len(result["checks"]) == 1
        assert result["checks"][0]["name"] == "plausibility_check"
        assert result["checks"][0]["passed"] is False
        assert result["checks"][0]["detail"] == data.issues[0]
        assert result["confidence"] == 0.3

    def test_llm_plausibility_check_failure_falls_back_to_skipped(self) -> None:
        ctx = _make_context(
            content="Any content.",
            source_data={},
            config={"enable_llm": True},
        )
        with mock_llm_failure():
            result = G0FactCheck().execute(ctx)

        assert result["passed"] is True
        assert result["gate"] == "G0"
        assert result.get("status") == "skipped"
        assert "reason" in result

    def test_llm_plausibility_check_skipped_when_llm_disabled(self) -> None:
        ctx = _make_context(
            content="Any content.",
            source_data={},
            config={"enable_llm": False},
        )
        result = G0FactCheck().execute(ctx)

        assert result["passed"] is True
        assert result["gate"] == "G0"
        assert result.get("status") == "skipped"
        assert "reason" in result

    def test_enable_llm_false_skips_llm_even_when_mock_available(self) -> None:
        """When enable_llm=False, no LLM call is made."""
        data = G0CheckResult(passed=False, issues=["llm issue"])
        ctx = _make_context(
            content="Alice and Bob attended the event.",
            source_data={
                "url": "",
                "published_date": "",
                "key_numbers": {},
                "entities": ["Alice", "Bob"],
                "quotes": [],
            },
            config={"enable_llm": False},
        )
        with mock_llm_response(data) as mock:
            result = G0FactCheck().execute(ctx)

        # LLM should NOT have been called
        assert mock.call_count == 0
        assert result.get("method") == "deterministic"
