"""Tests for V0Lint gate — HyperFrames lint check."""

from __future__ import annotations

from typing import Any

from automedia.gates._result import build_gate_result
from automedia.gates.base import BaseGate, _registry
from automedia.gates.lint import _CHECK_NAMES, V0Lint


def _make_context(
    *,
    lint_result: dict[str, Any] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "lint_result": lint_result
        if lint_result is not None
        else {
            "errors": 0,
            "warnings": 2,
            "syntax_ok": True,
        },
    }
    if mock_results is not None:
        ctx["_mock_results"] = mock_results
    return ctx


def _all_pass_mock() -> dict[str, dict[str, Any]]:
    return {name: {"passed": True, "detail": "ok"} for name in _CHECK_NAMES}


def _fail_check(name: str, detail: str = "failed") -> dict[str, dict[str, Any]]:
    results = _all_pass_mock()
    results[name] = {"passed": False, "detail": detail}
    return results


class TestV0Metadata:
    def test_gate_name(self) -> None:
        assert V0Lint().gate_name == "V0"

    def test_failure_mode(self) -> None:
        assert V0Lint().failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(V0Lint, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "V0" in _registry
        assert _registry.get("V0") is V0Lint


class TestV0MockDriven:
    def test_all_checks_pass(self) -> None:
        result = V0Lint().execute(_make_context(mock_results=_all_pass_mock()))
        assert result["passed"] is True
        assert result["gate"] == "V0"
        assert result["error"] is None
        assert len(result["checks"]) == 3

    def test_lint_errors_failure(self) -> None:
        result = V0Lint().execute(
            _make_context(mock_results=_fail_check("lint_errors", "5 errors"))
        )
        assert result["passed"] is False
        assert any(c["name"] == "lint_errors" and not c["passed"] for c in result["checks"])

    def test_lint_warnings_failure(self) -> None:
        result = V0Lint().execute(
            _make_context(mock_results=_fail_check("lint_warnings", "too many"))
        )
        assert result["passed"] is False
        assert any(c["name"] == "lint_warnings" and not c["passed"] for c in result["checks"])

    def test_syntax_valid_failure(self) -> None:
        result = V0Lint().execute(
            _make_context(mock_results=_fail_check("syntax_valid", "bad syntax"))
        )
        assert result["passed"] is False
        assert any(c["name"] == "syntax_valid" and not c["passed"] for c in result["checks"])

    def test_all_checks_fail(self) -> None:
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        result = V0Lint().execute(_make_context(mock_results=fail_all))
        assert result["passed"] is False

    def test_partial_failure(self) -> None:
        mock = _all_pass_mock()
        mock["lint_errors"] = {"passed": False, "detail": "x"}
        result = V0Lint().execute(_make_context(mock_results=mock))
        assert result["passed"] is False


class TestV0RealLogic:
    def test_zero_errors_passes(self) -> None:
        result = V0Lint().execute(
            _make_context(lint_result={"errors": 0, "warnings": 0, "syntax_ok": True})
        )
        chk = next(c for c in result["checks"] if c["name"] == "lint_errors")
        assert chk["passed"] is True

    def test_nonzero_errors_fails(self) -> None:
        result = V0Lint().execute(
            _make_context(lint_result={"errors": 3, "warnings": 0, "syntax_ok": True})
        )
        chk = next(c for c in result["checks"] if c["name"] == "lint_errors")
        assert chk["passed"] is False

    def test_warnings_within_tolerance(self) -> None:
        result = V0Lint().execute(
            _make_context(lint_result={"errors": 0, "warnings": 10, "syntax_ok": True})
        )
        chk = next(c for c in result["checks"] if c["name"] == "lint_warnings")
        assert chk["passed"] is True

    def test_warnings_exceed_tolerance(self) -> None:
        result = V0Lint().execute(
            _make_context(lint_result={"errors": 0, "warnings": 15, "syntax_ok": True})
        )
        chk = next(c for c in result["checks"] if c["name"] == "lint_warnings")
        assert chk["passed"] is False

    def test_syntax_ok_passes(self) -> None:
        result = V0Lint().execute(
            _make_context(lint_result={"errors": 0, "warnings": 0, "syntax_ok": True})
        )
        chk = next(c for c in result["checks"] if c["name"] == "syntax_valid")
        assert chk["passed"] is True

    def test_syntax_bad_fails(self) -> None:
        result = V0Lint().execute(
            _make_context(lint_result={"errors": 0, "warnings": 0, "syntax_ok": False})
        )
        chk = next(c for c in result["checks"] if c["name"] == "syntax_valid")
        assert chk["passed"] is False


class TestV0ResultStructure:
    def test_result_has_all_required_keys(self) -> None:
        result = V0Lint().execute(_make_context(mock_results=_all_pass_mock()))
        for key in ("passed", "gate", "checks", "error"):
            assert key in result

    def test_checks_have_correct_structure(self) -> None:
        result = V0Lint().execute(_make_context(mock_results=_all_pass_mock()))
        for check in result["checks"]:
            assert "name" in check
            assert "passed" in check
            assert "detail" in check
            assert isinstance(check["passed"], bool)

    def test_all_three_checks_present(self) -> None:
        result = V0Lint().execute(_make_context(mock_results=_all_pass_mock()))
        assert [c["name"] for c in result["checks"]] == _CHECK_NAMES

    def test_build_result_with_error(self) -> None:
        result = build_gate_result(
            [{"name": "x", "passed": False, "detail": "fail"}],
            gate="V0",
            error="oops",
        )
        assert result["passed"] is False
        assert result["error"] == "oops"

    def test_missing_context_keys(self) -> None:
        result = V0Lint().execute({})
        assert result["gate"] == "V0"
        assert len(result["checks"]) == 3

    def test_mock_detail_propagated(self) -> None:
        mock = _all_pass_mock()
        mock["lint_errors"] = {"passed": False, "detail": "custom 789"}
        result = V0Lint().execute(_make_context(mock_results=mock))
        ck = next(c for c in result["checks"] if c["name"] == "lint_errors")
        assert ck["detail"] == "custom 789"
