"""Tests for MCP director mode tools — ``approve_gate``, ``reject_gate``,
``get_pending_approvals``.

All tests use synthetic data and mock engines — no LLM API calls.
"""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.gates._context import GateContext
from automedia.gates.base import BaseGate
from automedia.mcp.tools import approve_gate, get_pending_approvals, reject_gate
from automedia.pipelines.gate_engine import (
    GateEngine,
    PipelineProgress,
    get_registered_engine,
    register_engine,
    unregister_engine,
)

# ---------------------------------------------------------------------------
# Mock gate
# ---------------------------------------------------------------------------


class _MockDirectorGate(BaseGate):
    """Mock gate that always passes — for director MCP tool tests."""

    _gate_name = "D5"
    _failure_mode = "stop"

    def execute(
        self,
        gate_context: GateContext | dict[str, Any],
    ) -> dict[str, Any]:
        return {"passed": True, "gate": self.gate_name}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_paused_engine(
    gate_name: str = "D5",
) -> tuple[GateEngine, threading.Thread, dict[str, Any]]:
    """Create a GateEngine paused on approval and return (engine, thread, results).

    Starts the engine in a background thread and waits for it to hit the
    approval pause.  Caller must resume() and join the thread to clean up.
    """
    gate = _MockDirectorGate()
    engine = GateEngine(gates=[gate], pause_on_approval=True)
    context: dict[str, Any] = {
        "topic": "test_director_mcp",
        "requires_approval": [gate_name],
    }

    results: dict[str, Any] = {"done": False, "return_value": None, "error": None}

    def _run() -> None:
        try:
            results["return_value"] = engine.run(context)
        except Exception as exc:  # noqa: BLE001 — catch all for thread safety
            results["error"] = exc
        finally:
            results["done"] = True

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    time.sleep(0.05)

    return engine, t, results


# ===================================================================
# Tests: approve_gate
# ===================================================================


class TestApproveGate:
    """Tests for approve_gate MCP tool."""

    def test_approve_gate_with_valid_project(self) -> None:
        """approve_gate returns approved=True for a valid project_id and gate_name."""
        engine, thread, results = _build_paused_engine()
        register_engine("proj_approve_valid", engine)

        try:
            result = approve_gate(
                project_id="proj_approve_valid",
                gate_name="D5",
            )

            assert result["success"] is True
            assert result["approved"] is True
            assert result["project_id"] == "proj_approve_valid"
            assert result["gate_name"] == "D5"

            thread.join(timeout=3)
            assert results["done"]
        finally:
            unregister_engine("proj_approve_valid")

        # Verify the gate result shows approval
        ok, gate_results = results["return_value"]
        assert ok is True
        assert gate_results[0]["_approval"]["approved"] is True

    def test_approve_gate_unknown_project_returns_error(self) -> None:
        """approve_gate returns error for unknown project_id."""
        result = approve_gate(project_id="nonexistent", gate_name="D5")

        assert result["success"] is False
        assert "error" in result
        assert result["error"]["code"] == "NOT_FOUND"

    def test_approve_gate_unknown_gate_returns_error(self) -> None:
        """approve_gate returns error when gate_name is not awaiting approval."""
        engine, thread, results = _build_paused_engine()
        register_engine("proj_wrong_gate", engine)

        try:
            result = approve_gate(
                project_id="proj_wrong_gate",
                gate_name="nonexistent_gate",
            )

            assert result["success"] is False
            assert result["error"]["code"] == "INVALID_PARAM"

            # Clean up the paused engine
            engine.resume("D5", approved=True)
            thread.join(timeout=3)
        finally:
            unregister_engine("proj_wrong_gate")


# ===================================================================
# Tests: reject_gate
# ===================================================================


class TestRejectGate:
    """Tests for reject_gate MCP tool."""

    def test_reject_gate_with_valid_project(self) -> None:
        """reject_gate returns rejected=True for a valid project_id and gate_name."""
        engine, thread, results = _build_paused_engine()
        register_engine("proj_reject_valid", engine)

        try:
            result = reject_gate(
                project_id="proj_reject_valid",
                gate_name="D5",
                reason="Content needs revision",
            )

            assert result["success"] is True
            assert result["rejected"] is True
            assert result["project_id"] == "proj_reject_valid"
            assert result["gate_name"] == "D5"

            thread.join(timeout=3)
            assert results["done"]
        finally:
            unregister_engine("proj_reject_valid")

        # Verify the gate result shows rejection
        ok, gate_results = results["return_value"]
        assert ok is True
        assert gate_results[0]["_approval"]["approved"] is False
        assert gate_results[0]["_approval"]["modifications"]["reason"] == "Content needs revision"

    def test_reject_gate_unknown_project_returns_error(self) -> None:
        """reject_gate returns error for unknown project_id."""
        result = reject_gate(project_id="nonexistent", gate_name="D5")

        assert result["success"] is False
        assert result["error"]["code"] == "NOT_FOUND"

    def test_reject_gate_unknown_gate_returns_error(self) -> None:
        """reject_gate returns error when gate_name is not awaiting approval."""
        engine, thread, results = _build_paused_engine()
        register_engine("proj_reject_wrong", engine)

        try:
            result = reject_gate(
                project_id="proj_reject_wrong",
                gate_name="wrong_gate_name",
            )

            assert result["success"] is False
            assert result["error"]["code"] == "INVALID_PARAM"

            # Clean up the paused engine
            engine.resume("D5", approved=True)
            thread.join(timeout=3)
        finally:
            unregister_engine("proj_reject_wrong")


# ===================================================================
# Tests: get_pending_approvals
# ===================================================================


class TestGetPendingApprovals:
    """Tests for get_pending_approvals MCP tool."""

    def test_get_pending_approvals_with_project_filter(self) -> None:
        """get_pending_approvals returns pending gates for a specific project."""
        engine, thread, results = _build_paused_engine()
        register_engine("proj_pending_filter", engine)

        try:
            result = get_pending_approvals(project_id="proj_pending_filter")

            assert result["success"] is True
            assert result["count"] == 1
            assert len(result["pending_approvals"]) == 1
            assert result["pending_approvals"][0]["project_id"] == "proj_pending_filter"
            assert result["pending_approvals"][0]["gate_name"] == "D5"
            assert result["pending_approvals"][0]["status"] == "awaiting_approval"

            # Clean up
            engine.resume("D5", approved=True)
            thread.join(timeout=3)
        finally:
            unregister_engine("proj_pending_filter")

    def test_get_pending_approvals_no_project_filter(self) -> None:
        """get_pending_approvals without project_id returns all pending gates."""
        engine1, t1, r1 = _build_paused_engine("D5")
        engine2, t2, r2 = _build_paused_engine("D5")
        register_engine("proj_all_1", engine1)
        register_engine("proj_all_2", engine2)

        try:
            result = get_pending_approvals()

            assert result["success"] is True
            assert result["count"] == 2
            assert len(result["pending_approvals"]) == 2

            project_ids = {p["project_id"] for p in result["pending_approvals"]}
            assert project_ids == {"proj_all_1", "proj_all_2"}

            # Clean up
            engine1.resume("D5", approved=True)
            engine2.resume("D5", approved=True)
            t1.join(timeout=3)
            t2.join(timeout=3)
        finally:
            unregister_engine("proj_all_1")
            unregister_engine("proj_all_2")

    def test_get_pending_approvals_empty_when_no_pipelines(self) -> None:
        """get_pending_approvals returns empty list when no engines are registered."""
        result = get_pending_approvals()
        assert result["success"] is True
        assert result["count"] == 0
        assert result["pending_approvals"] == []

    def test_get_pending_approvals_unknown_project_returns_empty(self) -> None:
        """get_pending_approvals for unknown project_id returns empty list."""
        result = get_pending_approvals(project_id="nonexistent")
        assert result["success"] is True
        assert result["count"] == 0
        assert result["pending_approvals"] == []
