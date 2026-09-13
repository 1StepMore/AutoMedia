"""Positive-path fixture seam for the control/approval MCP tools (T-05).

The seven control/approval tools act on runtime state created under a random
``run_pipeline`` project id a static scenario cannot address.  A scenario may
declare ``fixtures:`` so the real engine seeds the same in-process state and
the REAL tool is called through the REAL MCP dispatcher.  These tests prove
the seam end to end (real server, real tool code) plus the schema and the
teardown contract.  Synthetic fixtures only (Red Line 4).
"""

from __future__ import annotations

from typing import Any

import pytest

from automedia.mcp._state import _pipeline_tracker
from automedia.mcp.server import create_server
from automedia.pipelines.gate_engine import get_registered_engine
from automedia.validation.engine import make_adapters, run_validation_scenario
from automedia.validation.schema import Scenario, SchemaError

STANDARD = "tool.contract"


def _scenario(
    name: str,
    tool: str,
    arguments: dict[str, Any],
    fixtures: list[str],
    *,
    expect: dict[str, Any] | None = None,
) -> Scenario:
    return Scenario.from_dict(
        {
            "name": name,
            "description": "synthetic control fixture scenario",
            "intent": "prove the fixture seam seeds state the tool acts on",
            "user_level": "L0",
            "requires_env": [],
            "fixtures": fixtures,
            "steps": [
                {
                    "name": f"call {tool}",
                    "kind": "tool",
                    "check": "the tool reaches its success branch",
                    "standard": STANDARD,
                    "tool": tool,
                    "arguments": arguments,
                    "expect": expect or {"success": True},
                }
            ],
        }
    )


def _run(scenario: Scenario) -> dict[str, Any]:
    return run_validation_scenario(scenario, make_adapters(create_server()))


class TestFixtureSchema:
    def test_fixtures_field_accepts_known_names(self) -> None:
        scenario = _scenario(
            "fx-known", "pause_pipeline", {"project_id": "x"}, ["pipeline_control"]
        )
        assert scenario.fixtures == ["pipeline_control"]

    def test_unknown_fixture_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="unknown fixture"):
            _scenario("fx-bad", "pause_pipeline", {"project_id": "x"}, ["not_a_fixture"])

    def test_fixtures_default_empty(self) -> None:
        scenario = Scenario.from_dict(
            {
                "name": "fx-default",
                "description": "no fixtures",
                "intent": "default is empty",
                "user_level": "L0",
                "steps": [
                    {
                        "name": "s",
                        "kind": "tool",
                        "check": "c",
                        "standard": STANDARD,
                        "tool": "health_check",
                        "arguments": {},
                        "expect": {"success": True},
                    }
                ],
            }
        )
        assert scenario.fixtures == []


class TestPipelineControlFixture:
    def test_pause_pipeline_reaches_success(self) -> None:
        record = _run(
            _scenario(
                "fx-pause",
                "pause_pipeline",
                {"project_id": "valctrlpipeline1"},
                ["pipeline_control"],
            )
        )
        assert record["status"] == "passed", record
        assert record["steps"][0]["output"]["paused"] is True

    def test_retry_gate_reaches_success(self) -> None:
        record = _run(
            _scenario(
                "fx-retry",
                "retry_gate",
                {"project_id": "valctrlpipeline1", "gate_name": "G0"},
                ["pipeline_control"],
            )
        )
        assert record["status"] == "passed", record
        assert record["steps"][0]["output"]["retrying"] is True

    def test_state_is_torn_down_after_the_scenario(self) -> None:
        _run(
            _scenario(
                "fx-teardown",
                "cancel_pipeline",
                {"project_id": "valctrlpipeline1"},
                ["pipeline_control"],
            )
        )
        assert "valctrlpipeline1" not in _pipeline_tracker

    def test_without_the_fixture_the_tool_errors(self) -> None:
        scenario = _scenario(
            "fx-nofixture",
            "pause_pipeline",
            {"project_id": "valctrlpipeline1"},
            [],
            expect={"success": False, "error_expected": True},
        )
        record = _run(scenario)
        assert record["status"] == "passed", record
        assert record["steps"][0]["output"]["success"] is False


class TestPausedEngineFixture:
    def test_approve_gate_reaches_success(self) -> None:
        record = _run(
            _scenario(
                "fx-approve",
                "approve_gate",
                {"project_id": "valctrlengine1", "gate_name": "H0"},
                ["paused_engine"],
            )
        )
        assert record["status"] == "passed", record
        assert record["steps"][0]["output"]["approved"] is True

    def test_reject_gate_reaches_success(self) -> None:
        record = _run(
            _scenario(
                "fx-reject",
                "reject_gate",
                {"project_id": "valctrlengine1", "gate_name": "H0", "reason": "no"},
                ["paused_engine"],
            )
        )
        assert record["status"] == "passed", record
        assert record["steps"][0]["output"]["rejected"] is True

    def test_engine_is_unregistered_after_the_scenario(self) -> None:
        _run(
            _scenario(
                "fx-engine-teardown",
                "approve_gate",
                {"project_id": "valctrlengine1", "gate_name": "H0"},
                ["paused_engine"],
            )
        )
        assert get_registered_engine("valctrlengine1") is None
