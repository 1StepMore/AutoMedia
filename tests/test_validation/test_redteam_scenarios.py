"""Red Team scenario family (gap T-20, plan todo 20).

The pyramid's Red Team layer had zero scenarios: no adversarial validation of
untrusted input.  This module is the real-library gate for the family — at
least three ordinary scenarios under ``scenarios/security/`` that:

* carry a benign control step that passes (a normal call behaves normally);
* carry an adversarial step whose safe outcome is asserted — a structured
  refusal (``expect.error_expected``) or a "did not execute / did not leak"
  marker printed by a real call;
* RUN through the real engine and reach ``passed``.

The scenarios are ordinary run records with no hard dependency on the
``security-research`` skill.  Tests read ``scenarios/`` and skip when
``AUTOMEDIA_VALIDATION_SCENARIOS_DIR`` points at a missing dir.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from automedia.mcp.server import create_server
from automedia.validation.engine import make_adapters, run_validation_scenario
from automedia.validation.loader import default_scenarios_dir, load_scenarios
from automedia.validation.schema import Scenario

REDTEAM_SCENARIOS: tuple[str, ...] = (
    "redteam-path-traversal-refused",
    "redteam-credential-exfiltration",
    "redteam-prompt-injection-topic",
)

# Markers printed by a real call whose safe outcome is "the attack did not
# land" (absence assertions the expect vocabulary cannot express directly).
SAFE_OUTCOME_MARKERS: tuple[str, ...] = (
    "SECRET_NOT_EXFILTRATED",
    "INJECTION_NOT_EXECUTED",
)


def _library_or_skip() -> list[Scenario]:
    override = os.environ.get("AUTOMEDIA_VALIDATION_SCENARIOS_DIR")
    if override and not Path(override).expanduser().is_dir():
        pytest.skip("AUTOMEDIA_VALIDATION_SCENARIOS_DIR points at a missing dir")
    return load_scenarios(default_scenarios_dir())


def _by_name() -> dict[str, Scenario]:
    return {scenario.name: scenario for scenario in _library_or_skip()}


def _stdout_markers(scenario: Scenario) -> set[str]:
    markers: set[str] = set()
    for step in scenario.steps:
        if step.expect.stdout_has:
            markers.update(step.expect.stdout_has)
    return markers


class TestRedTeamLibrary:
    def test_family_has_at_least_three_scenarios(self) -> None:
        by_name = _by_name()
        missing = [name for name in REDTEAM_SCENARIOS if name not in by_name]
        assert not missing, f"T-20 red-team scenarios missing from the library: {missing}"
        security = [s for s in _library_or_skip() if s.category == "security"]
        assert len(security) >= 3, f"red-team family has {len(security)} security scenarios (< 3)"

    @pytest.mark.parametrize("name", REDTEAM_SCENARIOS)
    def test_scenario_has_benign_and_adversarial_steps(self, name: str) -> None:
        scenario = _by_name()[name]
        assert scenario.category == "security"
        benign = any(
            step.expect.success is True or step.expect.exit_code == 0 for step in scenario.steps
        )
        structured_refusal = any(step.expect.error_expected is True for step in scenario.steps)
        safe_outcome = bool(_stdout_markers(scenario) & set(SAFE_OUTCOME_MARKERS))
        assert benign, f"{name}: no benign control step (success: true or exit_code: 0)"
        assert structured_refusal or safe_outcome, (
            f"{name}: no adversarial safe-outcome step (structured refusal or "
            f"one of {SAFE_OUTCOME_MARKERS})"
        )


class TestRedTeamRuns:
    """Benign input passes; the malicious input is safely handled."""

    @pytest.mark.parametrize("name", REDTEAM_SCENARIOS)
    def test_redteam_scenario_passes(
        self, name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        if shutil.which("automedia") is None:
            pytest.skip("the automedia CLI is not on PATH (install the package to run)")
        scenario = _by_name()[name]
        adapters = make_adapters(create_server())
        record: dict[str, Any] = run_validation_scenario(scenario, adapters, cwd=tmp_path)
        assert record["status"] == "passed", (
            f"{name}: expected passed, got {record['status']}; record={record!r}"
        )
