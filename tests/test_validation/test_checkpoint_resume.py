"""Checkpoint/resume validation (gap R-02).

Long-running pipeline recovery was unproven: no scenario exercised a
persisted checkpoint surviving an interruption and being read back without
restarting.  This module pins the committed ``pipeline-checkpoint-resume``
scenario (real surfaces: ``pause_pipeline``/``resume_pipeline`` on the
seeded in-process tracker, plus ``automedia pipeline state`` reading the
persisted ``history.db``/``pipeline_md5.json`` checkpoint) AND proves the
runtime checkpoint is preserved across a pause/resume cycle: the seeded
``PipelineProgress`` records G0 as completed, and pause -> resume must not
reset ``gates_done`` or restart the gate list.

Synthetic fixtures only (Red Line 4): the temp project trees live under
``/tmp/automedia`` and the engine seeds in-process state through the
existing ``pipeline_control`` fixture seam.  No LLM, no network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from automedia.mcp.server import create_server
from automedia.validation.engine import make_adapters, run_validation_scenario
from automedia.validation.loader import load_scenarios
from automedia.validation.schema import Scenario

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMITTED = "pipeline-checkpoint-resume"


def _run(scenario: Scenario, run_root: Path | None = None) -> dict[str, Any]:
    return run_validation_scenario(
        scenario, make_adapters(create_server()), run_root=run_root, cwd=_REPO_ROOT
    )


def _committed(name: str) -> Scenario:
    for scenario in load_scenarios():
        if scenario.name == name:
            return scenario
    raise AssertionError(f"committed scenario {name!r} not found in the library")


def _resume_scenario() -> Scenario:
    """The pause -> interrupt -> resume cycle against the seeded tracker."""
    return Scenario.from_dict(
        {
            "name": "runtime-checkpoint-resume",
            "description": "Checkpoint preservation across pause and resume.",
            "intent": "Prove pause -> resume preserves the runtime gate checkpoint.",
            "user_level": "L0",
            "requires_env": [],
            "fixtures": ["pipeline_control"],
            "steps": [
                {
                    "name": "checkpoint before the interrupt",
                    "kind": "tool",
                    "check": "the seeded pipeline reports its gate checkpoint",
                    "standard": "tool.contract",
                    "tool": "get_pipeline_progress",
                    "arguments": {"project_id": "valctrlpipeline1"},
                    "expect": {"success": True, "output_has": ["gates_done", "total_gates"]},
                },
                {
                    "name": "pause interrupts the pipeline",
                    "kind": "tool",
                    "check": "pause_pipeline signals the pause",
                    "standard": "tool.contract",
                    "tool": "pause_pipeline",
                    "arguments": {"project_id": "valctrlpipeline1"},
                    "expect": {"success": True},
                },
                {
                    "name": "resume continues the pipeline",
                    "kind": "tool",
                    "check": "resume_pipeline lifts the pause",
                    "standard": "tool.contract",
                    "tool": "resume_pipeline",
                    "arguments": {"project_id": "valctrlpipeline1"},
                    "expect": {"success": True},
                },
                {
                    "name": "checkpoint preserved after resume",
                    "kind": "tool",
                    "check": "the same gate checkpoint survives the cycle",
                    "standard": "tool.contract",
                    "tool": "get_pipeline_progress",
                    "arguments": {"project_id": "valctrlpipeline1"},
                    "expect": {"success": True, "output_has": ["gates_done", "total_gates"]},
                },
            ],
        }
    )


class TestCommittedCheckpointResumeScenario:
    def test_scenario_declares_pause_resume_and_checkpoint_artifact(self) -> None:
        scenario = _committed(_COMMITTED)
        assert scenario.user_level == "L1"
        tools = [step.tool for step in scenario.steps if step.kind == "tool"]
        assert "pause_pipeline" in tools
        assert "resume_pipeline" in tools
        assert scenario.fixtures == ["pipeline_control"]
        collected = [a.path for step in scenario.steps for a in step.collect_artifacts]
        assert any(path.endswith("pipeline_md5.json") for path in collected), collected

    def test_committed_scenario_passes_with_checkpoint_artifact(self, tmp_path: Path) -> None:
        record = _run(_committed(_COMMITTED), run_root=tmp_path)
        assert record["status"] == "passed", record
        assert record["summary"]["failed"] == 0
        checkpoint_steps = [step for step in record["steps"] if step.get("artifacts")]
        assert checkpoint_steps, "no checkpoint artifact was collected"
        (entry,) = checkpoint_steps[0]["artifacts"]
        assert entry["ok"] is True
        assert str(entry["path"]).endswith("pipeline_md5.json")


class TestRuntimeCheckpointPreserved:
    def test_gates_done_survive_pause_and_resume(self) -> None:
        """No restart: the completed-gate checkpoint is identical after resume."""
        record = _run(_resume_scenario())
        assert record["status"] == "passed", record

        before = record["steps"][0]["output"]
        after = record["steps"][3]["output"]
        assert before["gates_done"] == ["G0"]
        assert after["gates_done"] == ["G0"], (
            "resume restarted the pipeline: gates_done changed "
            f"{before['gates_done']} -> {after['gates_done']}"
        )
        assert before["total_gates"] == after["total_gates"] == 3
        assert before["gates_remaining"] == after["gates_remaining"]

    def test_pause_and_resume_reach_the_control_surfaces(self) -> None:
        record = _run(_resume_scenario())
        assert record["steps"][1]["output"]["paused"] is True
        assert record["steps"][2]["output"]["resumed"] is True
