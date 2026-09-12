"""Rerun-stability / order-isolation gate (gap R-11).

Two consecutive suite runs over the same library must produce identical
per-scenario statuses; a deliberately order-dependent fixture (its verdict
depends on state left by the previous run) must be detected as a failure.
All fixtures are synthetic (Red Line 4) — no network, no LLM, no credentials.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from automedia.validation.stability import (
    RerunInstabilityError,
    StabilityReport,
    compare_statuses,
    scenario_statuses,
    verify_rerun_stability_async,
)

_STANDARDS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "synth"
    / "standards"
    / "standards_fixture.md"
)
_STANDARD = "founder-expectations.F01"

_STABLE_SCENARIO = f"""\
name: {{name}}
description: Deterministic scenario for the rerun-stability gate.
intent: Prove identical libraries yield identical statuses across runs.
category: baseline
requires_env: []
steps:
  - name: echo a marker
    kind: cli
    check: the command exits 0 and prints its marker
    standard: {_STANDARD}
    command: python3 -c "print('{{marker}}')"
    timeout_seconds: 30
    expect:
      exit_code: 0
      stdout_has: ["{{marker}}"]
"""


def _library(tmp_path: Path, files: dict[str, str]) -> Path:
    lib = tmp_path / "scenarios"
    lib.mkdir()
    shutil.copy2(_STANDARDS_FIXTURE, lib / "STANDARDS.md")
    for filename, content in files.items():
        (lib / filename).write_text(content, encoding="utf-8")
    return lib


def _stable_library(tmp_path: Path) -> Path:
    return _library(
        tmp_path,
        {
            "a.yaml": _STABLE_SCENARIO.format(name="stable-a", marker="alpha"),
            "b.yaml": _STABLE_SCENARIO.format(name="stable-b", marker="beta"),
        },
    )


def _order_dependent_library(tmp_path: Path) -> Path:
    marker = tmp_path / "state" / "seen.marker"
    script = tmp_path / "flip.py"
    script.write_text(
        "import pathlib, sys\n"
        "p = pathlib.Path(sys.argv[1])\n"
        "seen = p.exists()\n"
        "p.parent.mkdir(parents=True, exist_ok=True)\n"
        "p.touch()\n"
        "sys.exit(0 if not seen else 1)\n",
        encoding="utf-8",
    )
    scenario = f"""\
name: order-dependent
description: A fixture whose verdict flips on the second run (leftover state).
intent: Prove the rerun-stability gate detects an order-dependent fixture.
category: baseline
requires_env: []
steps:
  - name: pass only when the marker is absent
    kind: cli
    check: the command passes on a clean state and fails once state is left behind
    standard: {_STANDARD}
    command: python3 {script} {marker}
    timeout_seconds: 30
    expect:
      exit_code: 0
"""
    return _library(tmp_path, {"flaky.yaml": scenario})


class TestCompareStatuses:
    def test_identical_maps_have_no_differences(self) -> None:
        assert compare_statuses({"a": "passed"}, {"a": "passed"}) == {}

    def test_status_change_is_a_difference(self) -> None:
        assert compare_statuses({"a": "passed"}, {"a": "failed"}) == {
            "a": {"first": "passed", "second": "failed"}
        }

    def test_scenario_present_in_one_run_is_a_difference(self) -> None:
        assert compare_statuses({"a": "passed"}, {}) == {"a": {"first": "passed", "second": None}}

    def test_scenario_statuses_extracts_name_status(self) -> None:
        record = {
            "scenarios": [
                {"scenario": "a", "status": "passed"},
                {"scenario": "b", "status": "unconfigured"},
            ]
        }
        assert scenario_statuses(record) == {"a": "passed", "b": "unconfigured"}


class TestStableLibrary:
    def test_two_consecutive_runs_are_identical(self, tmp_path: Path) -> None:
        lib = _stable_library(tmp_path)
        report = asyncio.run(verify_rerun_stability_async(None, lib, runs_root=tmp_path / "runs"))
        assert report.stable is True
        assert report.differences == {}
        assert report.statuses == {"stable-a": "passed", "stable-b": "passed"}
        assert len(report.runs) == 2
        assert all(run_dir for run_dir in report.run_dirs)
        report.require_stable()

    def test_report_requires_two_runs(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="at least two runs"):
            StabilityReport(({"a": "passed"},))
        with pytest.raises(ValueError, match="at least two runs"):
            asyncio.run(
                verify_rerun_stability_async(
                    None, None, runs_root=tmp_path / "never-written", runs=1
                )
            )


class TestOrderDependentFixture:
    def test_order_dependent_fixture_is_detected(self, tmp_path: Path) -> None:
        lib = _order_dependent_library(tmp_path)
        report = asyncio.run(verify_rerun_stability_async(None, lib, runs_root=tmp_path / "runs"))
        assert report.stable is False
        assert "order-dependent" in report.differences
        assert report.differences["order-dependent"] == {
            "first": "passed",
            "second": "failed",
        }
        with pytest.raises(RerunInstabilityError, match="order-dependent"):
            report.require_stable()
