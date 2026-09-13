"""Rollback behavioural coverage (gap R-05).

``automedia rollback`` had only a ``--help`` surface probe.  The committed
``rollback-behavior`` scenario advances a synthetic project to ``published``
with recorded pipeline history, runs the real rollback CLI (confirming the
interactive prompt), and asserts the archive is intact, the status is
reverted to ``draft``, and no orphan directory is left behind.

Synthetic fixtures only (Red Line 4): the temp project tree lives under
``/tmp/automedia``; no production data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from automedia.mcp.server import create_server
from automedia.validation.engine import make_adapters, run_validation_scenario
from automedia.validation.loader import load_scenarios
from automedia.validation.schema import Scenario

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMITTED = "rollback-behavior"


def _run(scenario: Scenario) -> dict[str, Any]:
    return run_validation_scenario(scenario, make_adapters(create_server()), cwd=_REPO_ROOT)


def _committed(name: str) -> Scenario:
    for scenario in load_scenarios():
        if scenario.name == name:
            return scenario
    raise AssertionError(f"committed scenario {name!r} not found in the library")


class TestCommittedRollbackBehaviorScenario:
    def test_scenario_invokes_rollback_and_asserts_archive(self) -> None:
        scenario = _committed(_COMMITTED)
        assert scenario.user_level == "L3"
        commands = [step.command or "" for step in scenario.steps]
        assert any("automedia rollback" in command for command in commands), commands
        assert any("projroll_archived" in command for command in commands), commands
        collected = [a.path for step in scenario.steps for a in step.collect_artifacts]
        assert any(path.endswith("00_project_info.json") for path in collected), collected

    def test_committed_scenario_passes_and_reverts(self) -> None:
        record = _run(_committed(_COMMITTED))
        assert record["status"] == "passed", record
        assert record["summary"]["failed"] == 0
        rolled_back = [
            step for step in record["steps"] if step["name"] == "rollback reverts the project"
        ]
        assert rolled_back, "rollback step missing from the run record"
        assert rolled_back[0]["passed"] is True
