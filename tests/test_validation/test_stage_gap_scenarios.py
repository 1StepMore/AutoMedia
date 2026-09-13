"""Stage-gap scenarios (gap T-11, plan todo 18 / T-18).

The register found named stage gaps that the library never drove end to end:
``cron run`` execution, asset ingest + non-empty search, the ORF format
conversion happy path, multi-tenant pool selection, and feature-tier gate
filtering.  This module is the real-library gate for those five scenarios:

* each named scenario loads from the committed library with the expected
  ``user_level`` (L0 for the unconfigured deterministic capabilities, L4 for
  the multi-tenant / feature-tier operator capabilities);
* each scenario RUNS through the real engine against the live FastMCP server
  and reaches ``passed``.

The tests read ``scenarios/`` (skip when ``AUTOMEDIA_VALIDATION_SCENARIOS_DIR``
points at a missing dir, mirroring ``test_library_smoke``).  The ORF scenario
is skipped when the optional ``orf`` package is absent (its declared
``requires_env`` marker cannot be honestly satisfied there), matching the
existing ``format-output-contract`` convention.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from automedia.mcp.server import create_server
from automedia.validation.engine import make_adapters, run_validation_scenario
from automedia.validation.loader import default_scenarios_dir, load_scenarios
from automedia.validation.schema import Scenario

# Scenario name -> the user_level its persona stage requires.
STAGE_GAP_SCENARIOS: dict[str, str] = {
    "cron-run-execution": "L0",
    "asset-ingest-nonempty-search": "L0",
    "orf-format-output-happy": "L0",
    "select-topic-multi-tenant": "L4",
    "feature-tier-gate-filter": "L4",
}

_ORF_FLAG = "AUTOMEDIA_VALIDATION_EXPECT_ORF"


def _library_or_skip() -> list[Scenario]:
    override = os.environ.get("AUTOMEDIA_VALIDATION_SCENARIOS_DIR")
    if override and not Path(override).expanduser().is_dir():
        pytest.skip("AUTOMEDIA_VALIDATION_SCENARIOS_DIR points at a missing dir")
    return load_scenarios(default_scenarios_dir())


def _by_name() -> dict[str, Scenario]:
    return {scenario.name: scenario for scenario in _library_or_skip()}


class TestStageGapLibrary:
    def test_every_capability_has_a_scenario(self) -> None:
        by_name = _by_name()
        missing = [name for name in STAGE_GAP_SCENARIOS if name not in by_name]
        assert not missing, f"T-11 stage-gap scenarios missing from the library: {missing}"

    @pytest.mark.parametrize("name,level", sorted(STAGE_GAP_SCENARIOS.items()))
    def test_scenario_declares_the_expected_user_level(self, name: str, level: str) -> None:
        scenario = _by_name()[name]
        assert scenario.user_level == level, (
            f"{name}: expected user_level {level}, got {scenario.user_level}"
        )
        assert scenario.steps, f"{name}: scenario has no primary steps"


class TestStageGapRuns:
    """Each capability reaches a passed step in a real engine run."""

    @staticmethod
    def _run(name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
        if shutil.which("automedia") is None:
            pytest.skip("the automedia CLI is not on PATH (install the package to run)")
        if name == "orf-format-output-happy":
            pytest.importorskip("orf")
            monkeypatch.setenv(_ORF_FLAG, "1")
        scenario = _by_name()[name]
        adapters = make_adapters(create_server())
        return run_validation_scenario(scenario, adapters, cwd=tmp_path)

    @pytest.mark.parametrize("name", sorted(STAGE_GAP_SCENARIOS))
    def test_stage_gap_scenario_passes(
        self, name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record = self._run(name, tmp_path, monkeypatch)
        status = record["status"]
        assert status == "passed", f"{name}: expected passed, got {status}; record={record!r}"
