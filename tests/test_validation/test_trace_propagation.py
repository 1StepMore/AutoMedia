"""Trace-propagation assertion (gap Tr-01): the ``trace_id`` expect key.

Tr-01: no scenario asserted traceability, even though a correlation id exists
in code (``automedia.core.logging.bind_correlation_id``,
``automedia.pipelines.runner``).  The ``trace_id`` expect key grades a produced
record for a trace/correlation identifier:

* ``trace_id: true``  — a non-empty ``trace_id``/``correlation_id`` field must
  appear in the output;
* ``trace_id: "<id>"`` — that literal must appear among the output's trace ids
  or any nested string (stdout JSON included);
* ``trace_id: false`` — the inverse (no trace id present).

The committed ``trace-propagation-assertion`` scenario is the expected RED for
the product: the tool binds a correlation id but does not propagate it into
the MCP output.  The tests below prove the key in both directions with an
injected dispatcher, and assert the committed scenario is load-bearing.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from automedia.validation.engine import make_adapters, run_validation_scenario_async
from automedia.validation.expects import evaluate_expect
from automedia.validation.loader import default_scenarios_dir, load_scenarios
from automedia.validation.schema import Expect, Scenario, SchemaError

SCENARIO = "trace-propagation-assertion"


def _expect(**fields: object) -> Expect:
    return Expect.from_dict(fields)


class TestTraceIdBool:
    def test_true_passes_on_trace_id_field(self) -> None:
        output = {"success": True, "trace_id": "abc123"}
        result = evaluate_expect(_expect(trace_id=True), output)
        assert result.passed is True
        assert result.failures == []

    def test_true_passes_on_correlation_id_field(self) -> None:
        output = {"success": True, "data": {"correlation_id": "corr-1"}}
        assert evaluate_expect(_expect(trace_id=True), output).passed is True

    def test_true_fails_when_absent(self) -> None:
        result = evaluate_expect(_expect(trace_id=True), {"success": True})
        assert result.passed is False
        assert any("expect.trace_id" in f for f in result.failures)

    def test_true_fails_on_empty_trace_id(self) -> None:
        result = evaluate_expect(_expect(trace_id=True), {"success": True, "trace_id": ""})
        assert result.passed is False

    def test_false_passes_when_absent(self) -> None:
        assert evaluate_expect(_expect(trace_id=False), {"success": True}).passed is True

    def test_false_fails_when_present(self) -> None:
        result = evaluate_expect(_expect(trace_id=False), {"success": True, "trace_id": "x"})
        assert result.passed is False
        assert any("expect.trace_id" in f for f in result.failures)


class TestTraceIdLiteral:
    def test_literal_matches_trace_id(self) -> None:
        output = {"success": True, "trace_id": "run-42"}
        assert evaluate_expect(_expect(trace_id="run-42"), output).passed is True

    def test_literal_matches_nested_string(self) -> None:
        output = {"success": True, "stdout": '{"correlation_id": "run-42"}'}
        assert evaluate_expect(_expect(trace_id="run-42"), output).passed is True

    def test_literal_missing_fails(self) -> None:
        output = {"success": True, "trace_id": "run-99"}
        result = evaluate_expect(_expect(trace_id="run-42"), output)
        assert result.passed is False
        assert any("expect.trace_id" in f for f in result.failures)


class TestSchema:
    @pytest.mark.parametrize("value", [True, False, "abc"])
    def test_bool_and_str_accepted(self, value: object) -> None:
        assert _expect(trace_id=value).trace_id == value

    @pytest.mark.parametrize("value", [1, 0, 1.5, ["x"]])
    def test_other_types_rejected(self, value: object) -> None:
        with pytest.raises(SchemaError, match="trace_id"):
            _expect(trace_id=value)


class _TraceServer:
    """Duck-typed dispatcher: returns the product record with/without a trace id."""

    def __init__(self, *, traced: bool) -> None:
        self._traced = traced

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> object:
        output: dict[str, Any] = {"success": True, "note": "pattern_a_raw_data"}
        if self._traced:
            output["trace_id"] = "product-trace-0001"
        return output


def _load_scenario() -> Scenario:
    library = load_scenarios(default_scenarios_dir())
    by_name = {scenario.name: scenario for scenario in library}
    assert SCENARIO in by_name, f"{SCENARIO} missing from the committed library"
    return by_name[SCENARIO]


def _run(*, traced: bool, tmp_path: Path) -> dict[str, Any]:
    scenario = _load_scenario()
    adapters = make_adapters(_TraceServer(traced=traced))
    return asyncio.run(run_validation_scenario_async(scenario, adapters, cwd=tmp_path))


class TestCommittedScenario:
    def test_scenario_declares_trace_id_expectation(self) -> None:
        scenario = _load_scenario()
        assert scenario.steps[0].expect.trace_id is True

    def test_traced_product_output_passes(self, tmp_path: Path) -> None:
        record = _run(traced=True, tmp_path=tmp_path)
        assert record["status"] == "passed"
        assert record["steps"][0]["failures"] == []

    def test_untraced_product_output_is_the_recorded_defect(self, tmp_path: Path) -> None:
        record = _run(traced=False, tmp_path=tmp_path)
        assert record["status"] == "failed"
        assert any("expect.trace_id" in f for f in record["steps"][0]["failures"])
