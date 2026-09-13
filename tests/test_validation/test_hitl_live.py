"""Live HITL approve/reject validation (gap R-03).

The live H0 path was untested: ``review_decision`` was covered only by a
NOT_FOUND boundary probe, ``get_pending_approvals`` only by an empty queue,
and ``approve_gate``/``reject_gate`` only by the dormant engine-registry
double.  This module proves the LIVE path end to end:

* the ``hitl_pause`` fixture starts a REAL :class:`GateEngine` with an
  :class:`H0HumanReviewGate` in a daemon thread, registered in
  ``_hitl_waiters`` under a fixed id, so the real ``review_decision`` tool
  resolves it (the same in-process pause path a ``run_pipeline`` daemon
  thread uses);
* approve resumes the engine to completion (``engine.run`` returns ok True,
  the gate records ``_hitl_approved: True``);
* reject halts it (ok False, gate failed, ``_hitl_approved: False``);
* the fixture tears the paused waiter and the engine registration back out.

The H0 gate is LLM-free, so the path is deterministic without a provider
(``AUTOMEDIA_FAKE_LLM`` is not required — a real run would be strictly
weaker evidence).  Synthetic fixtures only (Red Line 4).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from automedia.mcp.server import create_server
from automedia.mcp.tools.review import review_decision
from automedia.pipelines.gate_types import _hitl_lock, _hitl_waiters
from automedia.validation.engine import make_adapters, run_validation_scenario
from automedia.validation.fixtures import (
    HITL_MARKER_PATH,
    HITL_PIPELINE_ID,
    apply_fixtures,
)
from automedia.validation.loader import load_scenarios
from automedia.validation.schema import FIXTURES, Scenario

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APPROVE = "hitl-approve-resume"
_REJECT = "hitl-reject-halt"
_PENDING = "get-pending-approvals-paused"


def _run(scenario: Scenario, run_root: Path | None = None) -> dict[str, Any]:
    return run_validation_scenario(
        scenario, make_adapters(create_server()), run_root=run_root, cwd=_REPO_ROOT
    )


def _committed(name: str) -> Scenario:
    for scenario in load_scenarios():
        if scenario.name == name:
            return scenario
    raise AssertionError(f"committed scenario {name!r} not found in the library")


def _wait_for_marker(timeout: float = 5.0) -> dict[str, Any]:
    """Poll until the marker holds parseable, non-empty JSON or the deadline passes.

    The writer may expose the file before its content is durable (and a
    global path can be re-created by an overlapping run), so mere existence
    is not enough: keep polling on empty/partial content and only fail once
    the deadline passes, reporting the path, the last byte count and the last
    parse error so the CI failure is diagnosable without another round trip.
    """
    marker = Path(HITL_MARKER_PATH)
    deadline = time.monotonic() + timeout
    last_size: int | None = None
    last_error: str | None = None
    while time.monotonic() < deadline:
        if marker.is_file():
            raw = marker.read_text(encoding="utf-8")
            last_size = len(raw.encode("utf-8"))
            if raw.strip():
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                else:
                    if isinstance(parsed, dict) and parsed:
                        return parsed
                    last_error = "marker JSON parsed to an empty object"
        time.sleep(0.05)
    raise AssertionError(
        f"live HITL marker {marker} never held parseable, non-empty JSON within "
        f"{timeout:g}s: last_observed_bytes={last_size!r}, last_parse_error={last_error!r}"
    )


class TestFixtureRegistration:
    def test_hitl_pause_fixture_is_registered(self) -> None:
        assert "hitl_pause" in FIXTURES


class TestLiveHITLFixture:
    def test_seeds_a_paused_h0_and_tears_it_down(self) -> None:
        with apply_fixtures(["hitl_pause"]), _hitl_lock:
            assert _hitl_waiters.get(HITL_PIPELINE_ID) is not None
        with _hitl_lock:
            assert _hitl_waiters.get(HITL_PIPELINE_ID) is None

    def test_approve_resumes_to_completion(self) -> None:
        with apply_fixtures(["hitl_pause"]):
            result = review_decision(project_id=HITL_PIPELINE_ID, gate_name="H0", action="approve")
            assert result["success"] is True
            assert result["approved"] is True
            marker = _wait_for_marker()
        assert marker["ok"] is True
        assert marker["approved"] is True

    def test_reject_stays_halted(self) -> None:
        with apply_fixtures(["hitl_pause"]):
            result = review_decision(
                project_id=HITL_PIPELINE_ID,
                gate_name="H0",
                action="reject",
                reason="off-brand",
            )
            assert result["success"] is True
            assert result["rejected"] is True
            marker = _wait_for_marker()
        assert marker["ok"] is False
        assert marker["approved"] is False


class TestCommittedHITLScenarios:
    def test_approve_scenario_reaches_review_decision(self) -> None:
        scenario = _committed(_APPROVE)
        assert scenario.user_level == "L3"
        assert scenario.fixtures == ["hitl_pause"]
        tools = [step.tool for step in scenario.steps if step.kind == "tool"]
        assert "review_decision" in tools
        assert scenario.steps[0].arguments["action"] == "approve"
        collected = [a.path for step in scenario.steps for a in step.collect_artifacts]
        assert HITL_MARKER_PATH in collected, collected

    def test_reject_scenario_reaches_review_decision(self) -> None:
        scenario = _committed(_REJECT)
        assert scenario.fixtures == ["hitl_pause"]
        assert scenario.steps[0].arguments["action"] == "reject"

    def test_approve_scenario_passes(self, tmp_path: Path) -> None:
        record = _run(_committed(_APPROVE), run_root=tmp_path)
        assert record["status"] == "passed", record
        assert record["steps"][0]["output"]["approved"] is True

    def test_reject_scenario_passes(self, tmp_path: Path) -> None:
        record = _run(_committed(_REJECT), run_root=tmp_path)
        assert record["status"] == "passed", record
        assert record["steps"][0]["output"]["rejected"] is True

    def test_pending_approvals_scenario_surfaces_a_paused_gate(self) -> None:
        record = _run(_committed(_PENDING))
        assert record["status"] == "passed", record
        output = record["steps"][0]["output"]
        assert output["success"] is True
        assert "pending_approvals" in output
        assert "count" in output
