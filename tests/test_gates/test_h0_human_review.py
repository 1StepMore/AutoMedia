"""Tests for H0 Human Review Gate."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from automedia.gates.base import BaseGate, _registry
from automedia.gates.failure_modes import FAILURE_MODES
from automedia.gates.h0_human_review import H0HumanReviewGate
from automedia.pipelines.gate_engine import (
    PipelineProgress,
    _hitl_lock,
    _hitl_waiters,
)


# =========================================================================
# Unit tests: H0HumanReviewGate
# =========================================================================


class TestH0Gate:
    """Verify H0 gate behaviour in isolation."""

    def test_gate_is_registered(self) -> None:
        """H0 should be auto-registered in the GateRegistry."""
        assert "H0" in _registry

    def test_gate_name_and_mode(self) -> None:
        """H0 should have correct gate_name and failure_mode."""
        gate = _registry.get("H0")()
        assert gate.gate_name == "H0"
        assert gate.failure_mode == "stop"

    def test_returns_awaiting_hitl(self) -> None:
        """Without skip_review, gate should return awaiting_hitl status."""
        gate = _registry.get("H0")()
        result = gate.execute({"topic": "test"})
        assert result["passed"] is True
        assert result["gate"] == "H0"
        assert result["status"] == "awaiting_hitl"
        assert result["timeout_s"] == 86400
        assert "escalated_gates" in result

    def test_skip_review_bypasses(self) -> None:
        """With skip_review=True, gate should auto-pass as skipped."""
        gate = _registry.get("H0")()
        result = gate.execute({"skip_review": True, "topic": "test"})
        assert result["passed"] is True
        assert result["gate"] == "H0"
        assert result["status"] == "skipped"

    def test_escalated_gates_passed_through(self) -> None:
        """Escalated gates from auto-recovery should appear in result."""
        gate = _registry.get("H0")()
        escalated = [
            {"gate_name": "G0", "error": "quality fail", "regeneration_count": 2},
            {"gate_name": "V3", "error": "semantic mismatch", "regeneration_count": 2},
        ]
        result = gate.execute({
            "_escalated_gates": escalated,
            "topic": "test",
        })
        assert result["escalated_gates"] == escalated

    def test_custom_timeout(self) -> None:
        """hitl_timeout in gate_context should override default."""
        gate = _registry.get("H0")()
        result = gate.execute({"hitl_timeout": 3600, "topic": "test"})
        assert result["timeout_s"] == 3600


# =========================================================================
# Unit tests: PipelineProgress HITL methods
# =========================================================================


class TestPipelineProgressHITL:
    """Verify HITL methods on PipelineProgress."""

    def test_on_gate_awaiting_hitl_emits_event(self) -> None:
        """on_gate_awaiting_hitl should record an awaiting_hitl event."""
        progress = PipelineProgress(project_id="test-proj")
        progress.on_gate_awaiting_hitl("H0")
        data = progress.get_progress()
        assert data["current_gate"] == "H0"
        # Event should include the awaiting_hitl status
        events = data["events"]
        assert any(e["status"] == "awaiting_hitl" for e in events)

    def test_approve_hitl_in_process(self) -> None:
        """approve_hitl should signal the in-process event."""
        progress = PipelineProgress(project_id="test-proj")

        def _approve_later(p: PipelineProgress) -> None:
            p.approve_hitl()

        timer = threading.Timer(0.1, _approve_later, args=[progress])
        timer.start()
        result = progress.wait_for_hitl(project_dir="", timeout=10)
        timer.cancel()
        assert result is True

    def test_reject_hitl_in_process(self) -> None:
        """reject_hitl should signal rejection."""
        progress = PipelineProgress(project_id="test-proj")

        def _reject_later(p: PipelineProgress) -> None:
            p.reject_hitl()

        timer = threading.Timer(0.1, _reject_later, args=[progress])
        timer.start()
        result = progress.wait_for_hitl(project_dir="", timeout=10)
        timer.cancel()
        assert result is False

    def test_approve_hitl_writes_state_file(self, tmp_path: Any) -> None:
        """approve_hitl with project_dir should write .hitl_state.json."""
        progress = PipelineProgress(project_id="test-proj")
        progress.approve_hitl(project_dir=str(tmp_path))
        state_file = Path(tmp_path) / ".hitl_state.json"
        assert state_file.is_file()
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["decision"] == "approve"

    def test_reject_hitl_writes_state_file(self, tmp_path: Any) -> None:
        """reject_hitl with project_dir should write .hitl_state.json."""
        progress = PipelineProgress(project_id="test-proj")
        progress.reject_hitl(project_dir=str(tmp_path))
        state_file = Path(tmp_path) / ".hitl_state.json"
        assert state_file.is_file()
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["decision"] == "reject"

    def test_wait_for_hitl_file_based_approve(self, tmp_path: Any) -> None:
        """wait_for_hitl should detect .hitl_state.json approval."""
        progress = PipelineProgress(project_id="test-proj")
        state_file = Path(tmp_path) / ".hitl_state.json"

        def _write_approve() -> None:
            import time
            time.sleep(0.2)
            state_file.write_text(json.dumps({"decision": "approve"}), encoding="utf-8")

        timer = threading.Timer(0.05, _write_approve)
        timer.start()
        result = progress.wait_for_hitl(project_dir=str(tmp_path), timeout=10)
        timer.cancel()
        assert result is True

    def test_wait_for_hitl_timeout_auto_passes(self) -> None:
        """Timeout in wait_for_hitl should auto-approve."""
        progress = PipelineProgress(project_id="test-proj")
        # Use a tiny timeout — should expire and auto-pass
        result = progress.wait_for_hitl(project_dir="", timeout=0.01)
        assert result is True

    def test_hitl_waiters_registration(self) -> None:
        """_hitl_waiters should allow register/signal/unregister."""
        progress = PipelineProgress(project_id="reg-test")
        with _hitl_lock:
            _hitl_waiters["reg-test"] = progress
        try:
            with _hitl_lock:
                assert _hitl_waiters.get("reg-test") is progress
            looked_up: PipelineProgress | None
            with _hitl_lock:
                looked_up = _hitl_waiters.get("reg-test")
            assert looked_up is not None
            looked_up.approve_hitl()
        finally:
            with _hitl_lock:
                _hitl_waiters.pop("reg-test", None)
        with _hitl_lock:
            assert "reg-test" not in _hitl_waiters


# =========================================================================
# Integration tests: GateEngine + H0
# =========================================================================


class TestGateEngineH0:
    """Verify GateEngine handles H0 awaiting_hitl correctly."""

    def test_engine_creates_awaiting_hitl_event(self) -> None:
        """When H0 gate returns awaiting_hitl, the engine should wait."""
        from automedia.pipelines.gate_engine import GateEngine, GateProgressEvent

        gate = H0HumanReviewGate()
        engine = GateEngine(gates=[gate])
        progress = PipelineProgress(project_id="engine-test")

        # Auto-approve after a short delay
        def _auto_approve() -> None:
            import time
            time.sleep(0.2)
            progress.approve_hitl()

        timer = threading.Timer(0.05, _auto_approve)
        timer.start()
        success, results = engine.run(
            {"skip_review": False, "topic": "test"},
            progress=progress,
        )
        timer.cancel()

        # Should pass (auto-approved)
        assert success is True
        assert len(results) == 1
        assert results[0].get("_hitl_approved") is True

        # Progress events should include awaiting_hitl
        data = progress.get_progress()
        statuses = [e["status"] for e in data["events"]]
        assert "awaiting_hitl" in statuses
        assert "passed" in statuses


# =========================================================================
# Failure modes
# =========================================================================


class TestH0FailureMode:
    """Verify H0 entry exists in failure_modes.py."""

    def test_h0_in_failure_modes(self) -> None:
        """H0 should have a failure mode entry."""
        assert "H0" in FAILURE_MODES
        entry = FAILURE_MODES["H0"]
        assert isinstance(entry, dict)
        assert "description" in entry
        assert "common_causes" in entry
        assert "fixes" in entry
        assert "docstring_ref" in entry
