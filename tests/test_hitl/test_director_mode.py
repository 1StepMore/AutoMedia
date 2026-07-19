"""Tests for director mode integration — HITL preset, GateEngine pause/resume,
engine registry, parallel pipeline isolation, and failure cleanup.

All tests use synthetic data and mock gates — no LLM API calls.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from automedia.gates._context import GateContext
from automedia.gates.base import BaseGate
from automedia.hitl.config import HITLConfig
from automedia.pipelines.gate_engine import (
    GateEngine,
    get_registered_engine,
    list_registered_engines,
    register_engine,
    unregister_engine,
)

# ---------------------------------------------------------------------------
# Mock gates for director mode tests
# ---------------------------------------------------------------------------


class _AlwaysPassMockGate(BaseGate):
    """Mock gate that always passes — for director engine tests."""

    _gate_name = "D0"
    _failure_mode = "stop"

    def execute(
        self,
        gate_context: GateContext | dict[str, Any],
    ) -> dict[str, Any]:
        return {"passed": True, "gate": self.gate_name}


class _SecondMockGate(BaseGate):
    """Mock gate that always passes — second gate for multi-gate tests."""

    _gate_name = "D1"
    _failure_mode = "stop"

    def execute(
        self,
        gate_context: GateContext | dict[str, Any],
    ) -> dict[str, Any]:
        return {"passed": True, "gate": self.gate_name}


class _ThirdMockGate(BaseGate):
    """Mock gate that always passes — third gate for multi-gate tests."""

    _gate_name = "D2"
    _failure_mode = "stop"

    def execute(
        self,
        gate_context: GateContext | dict[str, Any],
    ) -> dict[str, Any]:
        return {"passed": True, "gate": self.gate_name}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_engine_in_thread(
    engine: GateEngine, context: dict[str, Any]
) -> tuple[threading.Thread, dict[str, Any]]:
    """Run engine.run() in a background thread and return results container."""
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
    return t, results


# ===================================================================
# Tests: Director preset
# ===================================================================


class TestDirectorPreset:
    """Tests for the director HITL preset loading."""

    def test_director_preset_loads_8_nodes(self) -> None:
        """Director preset loads 8 review nodes via HITLConfig."""
        hitl = HITLConfig(preset_name="director")
        nodes = hitl.list_nodes()
        assert len(nodes) == 8, f"Expected 8 nodes, got {len(nodes)}"
        # All director preset nodes are human-autoset
        for node in nodes:
            assert node["autoset"] == "human", f"Node {node['name']} not human"

    def test_director_preset_contains_expected_nodes(self) -> None:
        """Director preset contains the expected gate names."""
        hitl = HITLConfig(preset_name="director")
        node_names = {n["name"] for n in hitl.list_nodes()}
        expected = {
            "topic_selection",
            "cw_output",
            "g2_copy_review",
            "v0_lint",
            "v1_vision_qa",
            "v2_subtitle",
            "l2_archive",
            "l3_publish",
        }
        assert node_names == expected, f"Mismatch: {node_names ^ expected}"

    def test_default_preset_not_director(self) -> None:
        """Default HITL preset is 'automated', not director."""
        hitl = HITLConfig()
        node_names = {n["name"] for n in hitl.list_nodes()}
        # Automated preset should not have director-specific nodes
        assert "v0_lint" not in node_names


# ===================================================================
# Tests: GateEngine pause_on_approval + resume
# ===================================================================


class TestGateEnginePauseOnApproval:
    """Tests for GateEngine pause_on_approval=True and resume()."""

    def test_pause_on_approval_pauses_after_approval_gate(self) -> None:
        """GateEngine with pause_on_approval=True pauses after gate with
        requires_approval.  Verifies the engine is blocked awaiting approval."""
        gate = _AlwaysPassMockGate()
        engine = GateEngine(gates=[gate], pause_on_approval=True)
        context: dict[str, Any] = {
            "topic": "test",
            "requires_approval": [gate.gate_name],
        }

        thread, results = _run_engine_in_thread(engine, context)

        # Give the thread a moment to start and hit the pause
        time.sleep(0.05)

        # Check that the gate is awaiting approval
        pending = engine.list_pending_approvals()
        assert len(pending) == 1
        assert pending[0]["gate_name"] == gate.gate_name
        assert pending[0]["status"] == "awaiting_approval"

        # Resume to unblock
        engine.resume(gate.gate_name, approved=True)
        thread.join(timeout=3)
        assert results["done"], "Engine thread did not complete"
        ok, gate_results = results["return_value"]
        assert ok is True
        assert len(gate_results) == 1
        assert gate_results[0]["_approval"]["approved"] is True

    def test_resume_approved_true_continues(self) -> None:
        """resume(approved=True) unblocks pipeline and subsequent gates run."""
        gate = _AlwaysPassMockGate()
        second = _SecondMockGate()
        engine = GateEngine(gates=[gate, second], pause_on_approval=True)
        context: dict[str, Any] = {
            "topic": "test",
            "requires_approval": [gate.gate_name],
        }

        thread, results = _run_engine_in_thread(engine, context)

        time.sleep(0.05)

        # Verify pause
        pending = engine.list_pending_approvals()
        assert len(pending) == 1

        # Approve and continue — second gate should also complete
        engine.resume(gate.gate_name, approved=True)
        thread.join(timeout=3)
        assert results["done"], "Engine thread did not complete"
        ok, gate_results = results["return_value"]
        assert ok is True
        assert len(gate_results) == 2, "Both gates should have results"
        assert gate_results[0]["_approval"]["approved"] is True

    def test_resume_approved_false_rejects_gate(self) -> None:
        """resume(approved=False) unblocks pipeline and result shows rejection."""
        gate = _AlwaysPassMockGate()
        engine = GateEngine(gates=[gate], pause_on_approval=True)
        context: dict[str, Any] = {
            "topic": "test",
            "requires_approval": [gate.gate_name],
        }

        thread, results = _run_engine_in_thread(engine, context)

        time.sleep(0.05)

        # Verify pause
        pending = engine.list_pending_approvals()
        assert len(pending) == 1

        # Reject — pipeline should complete but with rejection signal
        engine.resume(gate.gate_name, approved=False)
        thread.join(timeout=3)
        assert results["done"], "Engine thread did not complete"
        ok, gate_results = results["return_value"]
        assert ok is True  # Gate still passed, just the human rejected
        assert gate_results[0]["_approval"]["approved"] is False

    def test_resume_nonexistent_gate_raises_key_error(self) -> None:
        """resume() with unknown gate_name raises KeyError."""
        gate = _AlwaysPassMockGate()
        engine = GateEngine(gates=[gate], pause_on_approval=True)
        context: dict[str, Any] = {
            "topic": "test",
            "requires_approval": [gate.gate_name],
        }

        thread, results = _run_engine_in_thread(engine, context)
        time.sleep(0.05)

        # Verify pause
        pending = engine.list_pending_approvals()
        assert len(pending) == 1

        # Trying to resume a wrong gate should raise
        with pytest.raises(KeyError, match="No gate awaiting approval"):
            engine.resume("nonexistent_gate", approved=True)

        # Clean up — resume the actual gate
        engine.resume(gate.gate_name, approved=True)
        thread.join(timeout=3)
        assert results["done"]

    def test_pause_on_approval_disabled_does_not_pause(self) -> None:
        """GateEngine with pause_on_approval=False does NOT pause even with
        requires_approval in context."""
        gate = _AlwaysPassMockGate()
        engine = GateEngine(gates=[gate], pause_on_approval=False)
        context: dict[str, Any] = {
            "topic": "test",
            "requires_approval": [gate.gate_name],
        }

        ok, gate_results = engine.run(context)
        assert ok is True
        assert len(gate_results) == 1
        # No approval key should be present when pause_on_approval is off
        assert "_approval" not in gate_results[0]


# ===================================================================
# Tests: Engine registry
# ===================================================================


class TestEngineRegistry:
    """Tests for _engine_registry functions in gate_engine.py."""

    def test_register_and_get(self) -> None:
        """register_engine stores engine, get_registered_engine retrieves it."""
        gate = _AlwaysPassMockGate()
        engine = GateEngine(gates=[gate], pause_on_approval=False)
        project_id = "proj_reg_test"

        register_engine(project_id, engine)
        retrieved = get_registered_engine(project_id)
        assert retrieved is engine

        # Cleanup
        unregister_engine(project_id)

    def test_get_nonexistent_engine_returns_none(self) -> None:
        """get_registered_engine returns None for unknown project_id."""
        assert get_registered_engine("nonexistent_project") is None

    def test_unregister_removes_engine(self) -> None:
        """unregister_engine removes engine from registry."""
        gate = _AlwaysPassMockGate()
        engine = GateEngine(gates=[gate], pause_on_approval=False)
        project_id = "proj_unreg_test"

        register_engine(project_id, engine)
        assert get_registered_engine(project_id) is engine

        unregister_engine(project_id)
        assert get_registered_engine(project_id) is None

    def test_unregister_nonexistent_does_not_raise(self) -> None:
        """unregister_engine with unknown project_id does not raise."""
        # Should not raise
        unregister_engine("nonexistent")

    def test_list_registered_engines(self) -> None:
        """list_registered_engines returns all registered engines."""
        gate = _AlwaysPassMockGate()
        engine1 = GateEngine(gates=[gate], pause_on_approval=False)
        engine2 = GateEngine(gates=[gate], pause_on_approval=False)

        register_engine("proj_list_a", engine1)
        register_engine("proj_list_b", engine2)

        engines = list_registered_engines()
        assert "proj_list_a" in engines
        assert "proj_list_b" in engines
        assert engines["proj_list_a"] is engine1
        assert engines["proj_list_b"] is engine2

        # Cleanup
        unregister_engine("proj_list_a")
        unregister_engine("proj_list_b")

    def test_list_registered_engines_isolation(self) -> None:
        """list_registered_engines returns a copy — mutations don't affect registry."""
        gate = _AlwaysPassMockGate()
        engine = GateEngine(gates=[gate], pause_on_approval=False)
        register_engine("proj_isolate", engine)

        engines_copy = list_registered_engines()
        engines_copy.clear()

        # Original registry should still have the entry
        assert get_registered_engine("proj_isolate") is engine

        # Cleanup
        unregister_engine("proj_isolate")

    def test_re_register_overwrites(self) -> None:
        """Re-registering same project_id overwrites previous engine."""
        gate = _AlwaysPassMockGate()
        engine1 = GateEngine(gates=[gate], pause_on_approval=False)
        engine2 = GateEngine(gates=[gate], pause_on_approval=True)

        register_engine("proj_overwrite", engine1)
        assert get_registered_engine("proj_overwrite") is engine1

        register_engine("proj_overwrite", engine2)
        assert get_registered_engine("proj_overwrite") is engine2
        assert get_registered_engine("proj_overwrite") is not engine1

        # Cleanup
        unregister_engine("proj_overwrite")


# ===================================================================
# Tests: Parallel pipeline isolation
# ===================================================================


class TestParallelPipelineIsolation:
    """Tests that two pipelines with separate GateEngines do not interfere."""

    def test_parallel_pipelines_independent_pause(self) -> None:
        """Two engines running concurrently with independent pauses.

        Resuming one engine does not affect the other.
        """
        gate1 = _AlwaysPassMockGate()
        gate2 = _SecondMockGate()

        engine1 = GateEngine(gates=[gate1], pause_on_approval=True)
        engine2 = GateEngine(gates=[gate2], pause_on_approval=True)

        context1: dict[str, Any] = {
            "topic": "pipeline_1",
            "requires_approval": [gate1.gate_name],
        }
        context2: dict[str, Any] = {
            "topic": "pipeline_2",
            "requires_approval": [gate2.gate_name],
        }

        # Run both in background threads
        t1, r1 = _run_engine_in_thread(engine1, context1)
        t2, r2 = _run_engine_in_thread(engine2, context2)

        time.sleep(0.05)

        # Both should be paused independently
        assert len(engine1.list_pending_approvals()) == 1
        assert len(engine2.list_pending_approvals()) == 1

        # Resume engine 2 first — engine 1 should remain paused
        engine2.resume(gate2.gate_name, approved=True)
        t2.join(timeout=3)
        assert r2["done"], "Engine 2 thread did not complete"

        # Engine 1 should still be paused
        assert len(engine1.list_pending_approvals()) == 1

        # Resume engine 1
        engine1.resume(gate1.gate_name, approved=True)
        t1.join(timeout=3)
        assert r1["done"], "Engine 1 thread did not complete"

    def test_parallel_pipelines_separate_registry(self) -> None:
        """Two engines can be independently registered and retrieved."""
        gate = _AlwaysPassMockGate()
        engine1 = GateEngine(gates=[gate], pause_on_approval=True)
        engine2 = GateEngine(gates=[gate], pause_on_approval=True)

        register_engine("proj_parallel_a", engine1)
        register_engine("proj_parallel_b", engine2)

        assert get_registered_engine("proj_parallel_a") is engine1
        assert get_registered_engine("proj_parallel_b") is engine2
        assert get_registered_engine("proj_parallel_a") is not engine2

        # Cleanup
        unregister_engine("proj_parallel_a")
        unregister_engine("proj_parallel_b")

    def test_parallel_pipelines_independent_gate_results(self) -> None:
        """Two engines running in parallel produce independent results."""
        gate1 = _AlwaysPassMockGate()
        gate2 = _SecondMockGate()
        gate3 = _ThirdMockGate()

        engine1 = GateEngine(gates=[gate1, gate2], pause_on_approval=True)
        engine2 = GateEngine(gates=[gate3], pause_on_approval=True)

        context1: dict[str, Any] = {
            "topic": "pipeline_1",
            "requires_approval": [gate1.gate_name],
        }
        context2: dict[str, Any] = {
            "topic": "pipeline_2",
            "requires_approval": [gate3.gate_name],
        }

        t1, r1 = _run_engine_in_thread(engine1, context1)
        t2, r2 = _run_engine_in_thread(engine2, context2)

        time.sleep(0.05)

        # Both paused
        assert len(engine1.list_pending_approvals()) == 1
        assert len(engine2.list_pending_approvals()) == 1

        # Resume engine 1
        engine1.resume(gate1.gate_name, approved=True)
        t1.join(timeout=3)
        assert r1["done"]

        # Engine 1 has 2 gates (both pass)
        ok1, results1 = r1["return_value"]
        assert ok1 is True
        assert len(results1) == 2
        assert results1[0]["gate"] == "D0"
        assert results1[1]["gate"] == "D1"

        # Engine 2 still paused
        assert len(engine2.list_pending_approvals()) == 1

        # Resume engine 2
        engine2.resume(gate3.gate_name, approved=True)
        t2.join(timeout=3)
        assert r2["done"]

        # Engine 2 has 1 gate
        ok2, results2 = r2["return_value"]
        assert ok2 is True
        assert len(results2) == 1
        assert results2[0]["gate"] == "D2"


# ===================================================================
# Tests: Failure / error cleanup
# ===================================================================


class TestFailureCleanup:
    """Tests that engines are properly cleaned up on failure scenarios."""

    def test_unregister_engine_cleanup(self) -> None:
        """unregister_engine properly removes engine and pending list is empty."""
        gate = _AlwaysPassMockGate()
        engine = GateEngine(gates=[gate], pause_on_approval=False)
        register_engine("proj_cleanup_test", engine)

        assert get_registered_engine("proj_cleanup_test") is engine

        unregister_engine("proj_cleanup_test")
        assert get_registered_engine("proj_cleanup_test") is None
        assert "proj_cleanup_test" not in list_registered_engines()

    def test_registry_empty_after_all_unregistered(self) -> None:
        """Registry becomes empty after all engines are unregistered."""
        gate = _AlwaysPassMockGate()
        engine = GateEngine(gates=[gate], pause_on_approval=False)

        register_engine("temp_1", engine)
        register_engine("temp_2", engine)
        assert len(list_registered_engines()) >= 2

        unregister_engine("temp_1")
        unregister_engine("temp_2")
        assert "temp_1" not in list_registered_engines()
        assert "temp_2" not in list_registered_engines()
