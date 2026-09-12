"""Standing negative-control / mutation family (gap Tr-09).

The harness's own accuracy was unproven: T-02/T-03/T-04 fixed three grader
bugs, but nothing established that a deliberately wrong artifact reliably goes
RED for every assertion type.  This module defines one negative control per
implemented expect key — all 9 graders in
:func:`automedia.validation.expects.evaluate_expect` — and mutates a known-good
artifact or call envelope at runtime:

* ``success`` — flip the envelope to ``success: false``
* ``data_has`` — truncate a required key from ``output.data``
* ``exit_code`` — flip a zero exit to non-zero
* ``stdout_has`` — corrupt the stdout marker
* ``stderr_has`` — empty the stderr marker
* ``artifact_exists`` — remove the artifact
* ``artifact_size_min`` — truncate the artifact below the minimum
* ``artifact_nonempty`` — empty the artifact
* ``gate_records_pass`` — flip a gate entry to failed

Each control is run through the REAL engine (not just the pure evaluator): the
positive form must be ``passed`` and the mutated form ``failed`` with its key
named.  ``test_assertion_is_load_bearing`` proves the assertion is what catches
the mutation (an empty expect lets the mutated input pass), and
``TestMultiAssertionIndependence`` proves removing a sibling assertion from a
multi-assertion positive step does not disable the matching control.

All inputs are synthetic (Red Line 4); the tool mutation is served by a
duck-typed dispatcher, so there is no network, LLM, or credential use.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import pytest

from automedia.validation.engine import make_adapters, run_validation_scenario_async
from automedia.validation.expects import evaluate_expect
from automedia.validation.schema import Expect, Scenario, Step

IMPLEMENTED_EXPECT_KEYS: tuple[str, ...] = (
    "success",
    "data_has",
    "exit_code",
    "stdout_has",
    "stderr_has",
    "artifact_exists",
    "artifact_size_min",
    "artifact_nonempty",
    "gate_records_pass",
)
"""The 9 graders ``evaluate_expect`` implements — one negative control each."""

_ARTIFACT_DIR = "controls"


@dataclass(frozen=True)
class Control:
    """One negative control: an expect key, its good baseline, its mutation."""

    key: str
    expect: dict[str, Any]
    good_output: dict[str, Any]
    mutated_output: dict[str, Any]
    artifact: str | None = None
    good_artifact: str | None = None
    mutated_artifact: str | None = None


def _artifact(key: str) -> str:
    return f"{_ARTIFACT_DIR}/{key}.txt"


CONTROLS: tuple[Control, ...] = (
    Control(
        "success",
        {"success": True},
        {"success": True},
        {"success": False, "error": "mutated failure"},
    ),
    Control(
        "data_has",
        {"data_has": ["alpha"]},
        {"success": True, "data": {"alpha": 1}},
        {"success": True, "data": {"beta": 1}},
    ),
    Control(
        "exit_code",
        {"exit_code": 0},
        {"success": True, "exit_code": 0},
        {"success": True, "exit_code": 2},
    ),
    Control(
        "stdout_has",
        {"stdout_has": ["good-marker"]},
        {"success": True, "stdout": "good-marker"},
        {"success": True, "stdout": "corrupted"},
    ),
    Control(
        "stderr_has",
        {"stderr_has": ["warn-marker"]},
        {"success": True, "stderr": "warn-marker"},
        {"success": True, "stderr": ""},
    ),
    Control(
        "artifact_exists",
        {},
        {},
        {},
        artifact=_artifact("artifact_exists"),
        good_artifact="present",
        mutated_artifact=None,
    ),
    Control(
        "artifact_size_min",
        {},
        {},
        {},
        artifact=_artifact("artifact_size_min"),
        good_artifact="12345",
        mutated_artifact="1234",
    ),
    Control(
        "artifact_nonempty",
        {},
        {},
        {},
        artifact=_artifact("artifact_nonempty"),
        good_artifact="x",
        mutated_artifact="",
    ),
    Control(
        "gate_records_pass",
        {},
        {},
        {},
        artifact=_artifact("gate_records_pass"),
        good_artifact=json.dumps({"gates": [{"name": "G0", "passed": True}]}),
        mutated_artifact=json.dumps({"gates": [{"name": "G0", "passed": False}]}),
    ),
)


class MutationServer:
    """Duck-typed dispatcher: ``negative_control_{key}`` returns good or mutated."""

    def __init__(self, controls: tuple[Control, ...]) -> None:
        self._by_tool = {f"negative_control_{control.key}": control for control in controls}

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> object:
        control = self._by_tool[name]
        return control.mutated_output if arguments.get("mutate") else control.good_output


def _materialize(cwd: Path, control: Control, *, mutated: bool) -> None:
    if control.artifact is None:
        return
    path = cwd / control.artifact
    path.parent.mkdir(parents=True, exist_ok=True)
    content = control.mutated_artifact if mutated else control.good_artifact
    if content is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(content, encoding="utf-8")


def _expect(control: Control, cwd: Path) -> dict[str, Any]:
    """The expect block for one control, resolving artifact paths against ``cwd``."""
    if control.artifact is None:
        return control.expect
    resolved = str(cwd / control.artifact)
    builders: dict[str, dict[str, Any]] = {
        "artifact_exists": {"artifact_exists": resolved},
        "artifact_size_min": {"artifact_exists": resolved, "artifact_size_min": 5},
        "artifact_nonempty": {"artifact_nonempty": resolved},
        "gate_records_pass": {"gate_records_pass": True},
    }
    return builders[control.key]


def _step(control: Control, *, mutated: bool, cwd: Path) -> Step:
    expect = _expect(control, cwd)
    if control.artifact is not None:
        return Step.from_dict(
            {
                "name": f"control {control.key}",
                "kind": "file",
                "check": f"the {control.key} grader must reject the mutated artifact",
                "standard": "founder-expectations.F01",
                "command": str(cwd / control.artifact),
                "expect": expect,
            }
        )
    return Step.from_dict(
        {
            "name": f"control {control.key}",
            "kind": "tool",
            "check": f"the {control.key} grader must reject the mutated envelope",
            "standard": "tool.contract",
            "tool": f"negative_control_{control.key}",
            "arguments": {"mutate": mutated},
            "expect": expect,
        }
    )


def _run(control: Control, *, mutated: bool, cwd: Path) -> dict[str, Any]:
    cwd.mkdir(parents=True, exist_ok=True)
    _materialize(cwd, control, mutated=mutated)
    scenario = Scenario(
        name=f"negative-control-{control.key}",
        description=f"negative control for expect.{control.key}",
        intent="prove the grader rejects a runtime-visible mutation (Tr-09)",
        steps=[_step(control, mutated=mutated, cwd=cwd)],
    )
    adapters = make_adapters(MutationServer(CONTROLS))
    return asyncio.run(run_validation_scenario_async(scenario, adapters, cwd=cwd))


class TestNegativeControlFamily:
    def test_one_control_per_implemented_key(self) -> None:
        assert {control.key for control in CONTROLS} == set(IMPLEMENTED_EXPECT_KEYS)
        assert len(CONTROLS) >= 9

    @pytest.mark.parametrize("control", CONTROLS, ids=lambda c: c.key)
    def test_known_good_baseline_passes(self, control: Control, tmp_path: Path) -> None:
        record = _run(control, mutated=False, cwd=tmp_path / "good")
        assert record["status"] == "passed", (
            f"{control.key}: the good baseline must pass, observed {record['status']!r}"
        )
        assert record["steps"][0]["failures"] == []

    @pytest.mark.parametrize("control", CONTROLS, ids=lambda c: c.key)
    def test_control_fails_on_runtime_mutation(self, control: Control, tmp_path: Path) -> None:
        record = _run(control, mutated=True, cwd=tmp_path / "mutated")
        assert record["status"] == "failed", (
            f"{control.key}: the mutation must go RED, observed {record['status']!r}"
        )
        (trace,) = record["steps"]
        assert trace["passed"] is False
        assert any(f"expect.{control.key}" in failure for failure in trace["failures"]), (
            f"{control.key}: the failure must name the key, observed {trace['failures']!r}"
        )

    @pytest.mark.parametrize("control", CONTROLS, ids=lambda c: c.key)
    def test_assertion_is_load_bearing(self, control: Control, tmp_path: Path) -> None:
        """Without the key assertion the mutated input passes (the assertion catches it).

        ``error_expected`` is set so the T-04 error-envelope default does not
        itself flag the mutated envelope; the only remaining signal is the key.
        """
        cwd = tmp_path / "bare"
        _materialize(cwd, control, mutated=True)
        result = evaluate_expect(
            Expect(error_expected=True),
            control.mutated_output,
            step=_step(control, mutated=True, cwd=cwd),
            cwd=cwd,
        )
        assert result.passed is True
        assert result.failures == []

    @pytest.mark.parametrize("control", CONTROLS, ids=lambda c: c.key)
    def test_key_assertion_detects_the_mutation(self, control: Control, tmp_path: Path) -> None:
        cwd = tmp_path / "direct"
        _materialize(cwd, control, mutated=True)
        result = evaluate_expect(
            Expect.from_dict(_expect(control, cwd)),
            control.mutated_output,
            step=_step(control, mutated=True, cwd=cwd),
            cwd=cwd,
        )
        assert result.passed is False
        assert any(f"expect.{control.key}" in failure for failure in result.failures)


class TestMultiAssertionIndependence:
    """Removing one assertion must not disable the matching control (Tr-09)."""

    _GOOD: ClassVar[dict[str, Any]] = {"success": True, "exit_code": 0, "stdout": "good-marker"}
    _MUTATED: ClassVar[dict[str, Any]] = {"success": True, "exit_code": 0, "stdout": "corrupted"}

    def test_positive_multi_assertion_step_passes(self) -> None:
        expect = Expect.from_dict({"success": True, "exit_code": 0, "stdout_has": ["good-marker"]})
        assert evaluate_expect(expect, self._GOOD).passed is True

    def test_removing_a_sibling_assertion_keeps_the_control_failing(self) -> None:
        # `success` is removed (the positive step is weakened); the stdout
        # control must still catch the mutation.
        weakened = Expect.from_dict({"exit_code": 0, "stdout_has": ["good-marker"]})
        assert evaluate_expect(weakened, self._GOOD).passed is True
        result = evaluate_expect(weakened, self._MUTATED)
        assert result.passed is False
        assert any("expect.stdout_has" in failure for failure in result.failures)

    def test_removing_the_matching_assertion_is_what_defeats_the_control(self) -> None:
        # The mutation is only caught while stdout_has is present.
        without_stdout = Expect.from_dict({"success": True, "exit_code": 0})
        assert evaluate_expect(without_stdout, self._MUTATED).passed is True
