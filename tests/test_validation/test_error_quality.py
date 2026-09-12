"""Error-quality assertions (gaps R-07, R-08): ``error_code_has`` /
``recovery_has`` expect keys + the forced-LLM-failure fixed-outcome scenario.

R-08: error quality (codes + recovery instructions) was never evaluated by an
assertion.  The two new keys grade a structured error envelope: the resolved
``error.code`` must be non-empty and contain every declared substring, and the
resolved recovery/resolution string must be non-empty and contain every
declared substring.

R-07: the committed ``llm-unavailable-error-quality`` scenario asserts ONE
fixed outcome — ``success: false`` carrying a code + a recovery string, with
NO fallback-success branch.  The tests below run that exact scenario through
the REAL engine with an injected dispatcher that forces the LLM error (and
variants that omit the recovery string or return a fallback success), proving
the scenario is load-bearing in both directions.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from automedia.mcp.mcp_error import MCPErrorCode, error_response
from automedia.validation.engine import make_adapters, run_validation_scenario_async
from automedia.validation.expects import evaluate_expect
from automedia.validation.loader import default_scenarios_dir, load_scenarios
from automedia.validation.schema import Expect, Scenario, SchemaError

SCENARIO = "llm-unavailable-error-quality"
FLAG = "AUTOMEDIA_VALIDATION_EXPECT_LLM_UNAVAILABLE"


def _error_expect(**fields: object) -> Expect:
    fields.setdefault("error_expected", True)
    return Expect.from_dict(fields)


GOOD_ERROR: dict[str, Any] = error_response(
    MCPErrorCode.LLM_ERROR, "Brand strategy generation failed: provider unreachable"
)
"""The real tool's LLM-unavailable envelope (error.code=LLM_ERROR + resolution)."""


class TestErrorCodeHas:
    def test_passes_on_nonempty_code_with_substring(self) -> None:
        result = evaluate_expect(_error_expect(error_code_has=["LLM_ERROR"]), GOOD_ERROR)
        assert result.passed is True
        assert result.failures == []

    def test_empty_list_asserts_only_nonempty(self) -> None:
        result = evaluate_expect(_error_expect(error_code_has=[]), GOOD_ERROR)
        assert result.passed is True

    def test_missing_code_fails(self) -> None:
        result = evaluate_expect(
            _error_expect(error_code_has=["LLM_ERROR"]),
            {"success": False, "error": {"message": "x"}},
        )
        assert result.passed is False
        assert any("expect.error_code_has" in f for f in result.failures)

    def test_wrong_code_fails(self) -> None:
        result = evaluate_expect(_error_expect(error_code_has=["NOT_FOUND"]), GOOD_ERROR)
        assert result.passed is False
        assert any("expect.error_code_has" in f for f in result.failures)

    def test_code_nested_under_data_found(self) -> None:
        output = {"success": False, "data": GOOD_ERROR}
        assert evaluate_expect(_error_expect(error_code_has=["LLM_ERROR"]), output).passed is True


class TestRecoveryHas:
    def test_passes_on_resolution_with_substring(self) -> None:
        result = evaluate_expect(_error_expect(recovery_has=["AUTOMEDIA_LLM_API_KEY"]), GOOD_ERROR)
        assert result.passed is True
        assert result.failures == []

    def test_missing_recovery_fails(self) -> None:
        stripped = {"success": False, "error": {"code": "LLM_ERROR", "message": "x"}}
        result = evaluate_expect(_error_expect(recovery_has=["AUTOMEDIA_LLM_API_KEY"]), stripped)
        assert result.passed is False
        assert any("expect.recovery_has" in f for f in result.failures)

    def test_recovery_without_substring_fails(self) -> None:
        result = evaluate_expect(_error_expect(recovery_has=["retry with a valid key"]), GOOD_ERROR)
        assert result.passed is False
        assert any("expect.recovery_has" in f for f in result.failures)


class TestSchema:
    def test_keys_are_lists_of_strings(self) -> None:
        expect = _error_expect(error_code_has=["A"], recovery_has=["B"])
        assert expect.error_code_has == ["A"]
        assert expect.recovery_has == ["B"]

    def test_string_value_rejected(self) -> None:
        with pytest.raises(SchemaError, match="error_code_has"):
            _error_expect(error_code_has="LLM_ERROR")
        with pytest.raises(SchemaError, match="recovery_has"):
            _error_expect(recovery_has="retry")

    def test_non_string_element_rejected(self) -> None:
        with pytest.raises(SchemaError, match="error_code_has"):
            _error_expect(error_code_has=[1])


class _ForcedLLMServer:
    """Duck-typed dispatcher: forces one fixed outcome per ``mode``."""

    def __init__(self, mode: str) -> None:
        self._mode = mode

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> object:
        if self._mode == "coded":
            return error_response(MCPErrorCode.LLM_ERROR, "forced: provider unreachable")
        if self._mode == "no_recovery":
            return {"success": False, "error": {"code": "LLM_ERROR", "message": "forced"}}
        return {"success": True, "brand_positioning": "fallback success"}


def _load_scenario() -> Scenario:
    library = load_scenarios(default_scenarios_dir())
    by_name = {scenario.name: scenario for scenario in library}
    assert SCENARIO in by_name, f"{SCENARIO} missing from the committed library"
    return by_name[SCENARIO]


def _run(mode: str, tmp_path: Path) -> dict[str, Any]:
    scenario = _load_scenario()
    adapters = make_adapters(_ForcedLLMServer(mode))
    return asyncio.run(run_validation_scenario_async(scenario, adapters, cwd=tmp_path))


class TestForcedLlmFailureScenario:
    def test_committed_scenario_declares_code_and_recovery(self) -> None:
        scenario = _load_scenario()
        assert scenario.requires_env == [FLAG]
        expect = scenario.steps[0].expect
        assert expect.error_code_has == ["LLM_ERROR"]
        assert expect.recovery_has == ["AUTOMEDIA_LLM_API_KEY"]
        assert expect.success is False
        assert expect.error_expected is True

    def test_forced_llm_failure_passes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(FLAG, "1")
        record = _run("coded", tmp_path)
        assert record["status"] == "passed"
        assert record["steps"][0]["failures"] == []

    def test_missing_recovery_string_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(FLAG, "1")
        record = _run("no_recovery", tmp_path)
        assert record["status"] == "failed"
        assert any("expect.recovery_has" in f for f in record["steps"][0]["failures"])

    def test_fallback_success_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(FLAG, "1")
        record = _run("fallback_success", tmp_path)
        assert record["status"] == "failed"
        assert any("expect.success" in f for f in record["steps"][0]["failures"])
