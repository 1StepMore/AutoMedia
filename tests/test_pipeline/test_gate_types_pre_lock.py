"""Pre-lock tests for gate data types — capture exact behavior before extraction.

These tests verify the structure, defaults, and behavior of:
- GateErrorResult (TypedDict)
- ProgressData (TypedDict)
- GateProgressEvent (dataclass)
- PipelineProgress (class)

All imports come from ``gate_engine`` (pre-extraction source).
After extraction to ``gate_types.py``, the same tests must pass when
importing from ``gate_types`` or via the backward-compat ``gate_engine``
re-exports.
"""

from __future__ import annotations

from typing import Any

from automedia.pipelines.gate_engine import (
    GateErrorResult,
    GateProgressEvent,
    PipelineProgress,
    ProgressData,
)


# =====================================================================
# GateErrorResult TypedDict
# =====================================================================

class TestGateErrorResult:
    """GateErrorResult is a TypedDict(total=False) with optional keys.

    Always-required keys (implicitly via usage convention):
    - passed: bool
    - gate: str
    - error: str
    - duration_s: float

    Optional keys (set for retry exhaustion):
    - retry_count: int
    - retry_delay_s: float
    """

    def test_minimal_fields(self) -> None:
        """Create GateErrorResult with only required fields."""
        result: GateErrorResult = {
            "passed": False,
            "gate": "G0",
            "error": "fact check failed",
            "duration_s": 1.23,
        }
        assert result["passed"] is False
        assert result["gate"] == "G0"
        assert result["error"] == "fact check failed"
        assert result["duration_s"] == 1.23

    def test_with_retry_fields(self) -> None:
        """Create GateErrorResult with retry metadata."""
        result: GateErrorResult = {
            "passed": False,
            "gate": "V0",
            "error": "transient error after 3 retries",
            "duration_s": 5.67,
            "retry_count": 3,
            "retry_delay_s": 2.0,
        }
        assert result["retry_count"] == 3
        assert result["retry_delay_s"] == 2.0

    def test_all_fields_optional_by_typeddict(self) -> None:
        """Because total=False, missing optional fields is valid."""
        result: GateErrorResult = {
            "passed": True,
            "gate": "G1",
            "error": "",
            "duration_s": 0.5,
        }
        # Accessing missing optional key raises KeyError
        import pytest
        with pytest.raises(KeyError):
            _ = result["retry_count"]  # type: ignore[typeddict-item]

    def test_passed_true_ok(self) -> None:
        """GateErrorResult can represent a successful gate error (edge case)."""
        result: GateErrorResult = {
            "passed": True,
            "gate": "no-op",
            "error": "",
            "duration_s": 0.0,
        }
        assert result["passed"] is True


# =====================================================================
# ProgressData TypedDict
# =====================================================================

class TestProgressData:
    """ProgressData is a TypedDict(total=False) for get_progress() snapshots.

    Keys:
        project_id: str
        current_gate: str | None
        gates_done: list[str]
        gates_remaining: list[str]
        total_gates: int
        events: list[dict[str, Any]]
        error: str | None
        is_running: bool
        is_failed: bool
        elapsed_s: float
    """

    def test_typeddict_structure(self) -> None:
        """ProgressData accepts all fields."""
        data: ProgressData = {
            "project_id": "proj-123",
            "current_gate": "G0",
            "gates_done": [],
            "gates_remaining": ["G0", "G1"],
            "total_gates": 2,
            "events": [],
            "error": None,
            "is_running": True,
            "is_failed": False,
            "elapsed_s": 12.345,
        }
        assert data["project_id"] == "proj-123"
        assert data["current_gate"] == "G0"
        assert data["total_gates"] == 2
        assert data["is_running"] is True
        assert data["is_failed"] is False
        assert data["elapsed_s"] == 12.345

    def test_current_gate_can_be_none(self) -> None:
        """When no gate is running, current_gate is None."""
        data: ProgressData = {
            "project_id": "proj-123",
            "current_gate": None,
            "gates_done": ["G0"],
            "gates_remaining": ["G1"],
            "total_gates": 2,
            "events": [],
            "error": None,
            "is_running": False,
            "is_failed": False,
            "elapsed_s": 0.0,
        }
        assert data["current_gate"] is None

    def test_error_field_is_optional(self) -> None:
        """error can be None or a string."""
        no_error: ProgressData = {
            "project_id": "p",
            "current_gate": None,
            "gates_done": [],
            "gates_remaining": [],
            "total_gates": 0,
            "events": [],
            "error": None,
            "is_running": False,
            "is_failed": False,
            "elapsed_s": 0.0,
        }
        assert no_error["error"] is None

        with_error: ProgressData = {
            "project_id": "p",
            "current_gate": None,
            "gates_done": [],
            "gates_remaining": [],
            "total_gates": 0,
            "events": [],
            "error": "something broke",
            "is_running": False,
            "is_failed": True,
            "elapsed_s": 0.0,
        }
        assert with_error["error"] == "something broke"


# =====================================================================
# GateProgressEvent dataclass
# =====================================================================

class TestGateProgressEvent:
    """GateProgressEvent dataclass with retry metadata fields."""

    def test_minimal_construction(self) -> None:
        """Create with just gate_name and status."""
        event = GateProgressEvent(gate_name="G0", status="running")
        assert event.gate_name == "G0"
        assert event.status == "running"
        assert event.duration_s == 0.0
        assert event.detail == ""
        assert event.timestamp == ""
        assert event.attempt_number == 1
        assert event.retry_level is None
        assert event.strategy_delta is None

    def test_full_construction(self) -> None:
        """Create with all fields."""
        event = GateProgressEvent(
            gate_name="V0",
            status="passed",
            duration_s=3.14,
            detail="ok",
            timestamp="2026-01-01T00:00:00",
            attempt_number=2,
            retry_level="quality",
            strategy_delta={"temperature": 0.7},
        )
        assert event.gate_name == "V0"
        assert event.status == "passed"
        assert event.duration_s == 3.14
        assert event.attempt_number == 2
        assert event.retry_level == "quality"
        assert event.strategy_delta == {"temperature": 0.7}

    def test_status_literals(self) -> None:
        """Status must be one of the allowed literal values."""
        GateProgressEvent(gate_name="g", status="running")
        GateProgressEvent(gate_name="g", status="passed")
        GateProgressEvent(gate_name="g", status="failed")
        GateProgressEvent(gate_name="g", status="skipped")
        GateProgressEvent(gate_name="g", status="awaiting_hitl")

    def test_dict_representation(self) -> None:
        """__dict__ returns all fields for JSON serialization."""
        event = GateProgressEvent(
            gate_name="G0",
            status="running",
            attempt_number=1,
        )
        d = event.__dict__
        assert isinstance(d, dict)
        assert d["gate_name"] == "G0"
        assert d["status"] == "running"
        assert d["attempt_number"] == 1

    def test_default_retry_level_none(self) -> None:
        """retry_level defaults to None (no retry metadata)."""
        event = GateProgressEvent(gate_name="g", status="passed")
        assert event.retry_level is None

    def test_default_attempt_number_one(self) -> None:
        """attempt_number defaults to 1 (first attempt)."""
        event = GateProgressEvent(gate_name="g", status="passed")
        assert event.attempt_number == 1

    def test_strategy_delta_default_none(self) -> None:
        """strategy_delta defaults to None."""
        event = GateProgressEvent(gate_name="g", status="passed")
        assert event.strategy_delta is None

    def test_strategy_delta_nested_dict(self) -> None:
        """strategy_delta can hold nested structures."""
        event = GateProgressEvent(
            gate_name="g",
            status="running",
            strategy_delta={"llm": {"temperature": 0.5, "max_tokens": 2000}},
        )
        assert event.strategy_delta["llm"]["temperature"] == 0.5  # type: ignore[index]


# =====================================================================
# PipelineProgress class — construction and default state
# =====================================================================

class TestPipelineProgressConstruction:
    """PipelineProgress default state after __init__."""

    def test_default_project_id(self) -> None:
        """Default project_id is empty string."""
        progress = PipelineProgress()
        assert progress.project_id == ""

    def test_custom_project_id(self) -> None:
        """project_id can be set via constructor."""
        progress = PipelineProgress(project_id="my-project")
        assert progress.project_id == "my-project"

    def test_initial_state(self) -> None:
        """Initial state: no current gate, no error, zero total."""
        progress = PipelineProgress()
        assert progress.current_gate is None
        assert progress.error is None
        assert progress.total_gates == 0

    def test_initial_not_cancelled(self) -> None:
        """Fresh PipelineProgress is not cancelled."""
        progress = PipelineProgress()
        assert progress.is_cancelled() is False

    def test_initial_not_paused(self) -> None:
        """Fresh PipelineProgress is not paused."""
        progress = PipelineProgress()
        assert progress.is_paused() is False


# =====================================================================
# PipelineProgress — gate lifecycle methods
# =====================================================================

class TestPipelineProgressLifecycle:
    """PipelineProgress on_gate_start / on_gate_end behavior."""

    def test_on_gate_start_sets_current_gate(self) -> None:
        """After on_gate_start, current_gate is set."""
        progress = PipelineProgress()
        progress.on_gate_start("G0")
        assert progress.current_gate == "G0"

    def test_on_gate_end_clears_current_gate(self) -> None:
        """After on_gate_end, current_gate is None."""
        progress = PipelineProgress()
        progress.on_gate_start("G0")
        progress.on_gate_end("G0", True, 1.0)
        assert progress.current_gate is None

    def test_on_gate_end_tracks_done(self) -> None:
        """Completed gates appear in _gates_done (accessed via get_progress)."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0", "G1"])
        progress.on_gate_start("G0")
        progress.on_gate_end("G0", True, 1.0)
        data = progress.get_progress()
        assert "G0" in data["gates_done"]

    def test_on_gate_end_duplicate_not_duplicated(self) -> None:
        """Same gate completed multiple times (retry) only recorded once."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0"])
        progress.on_gate_start("G0")
        progress.on_gate_end("G0", True, 1.0)
        progress.on_gate_start("G0")
        progress.on_gate_end("G0", False, 2.0)
        data = progress.get_progress()
        assert data["gates_done"] == ["G0"]  # Only once

    def test_events_list_populated(self) -> None:
        """Events are appended on start and end."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0"])
        progress.on_gate_start("G0")
        progress.on_gate_end("G0", True, 1.0)
        data = progress.get_progress()
        assert len(data["events"]) == 2
        assert data["events"][0]["status"] == "running"
        assert data["events"][1]["status"] == "passed"

    def test_mark_finished(self) -> None:
        """mark_finished clears current_gate and marks not running."""
        progress = PipelineProgress(project_id="p")
        progress.on_gate_start("G0")
        progress.mark_finished()
        assert progress.current_gate is None
        data = progress.get_progress()
        assert data["is_running"] is False


# =====================================================================
# PipelineProgress — set_gate_names and progress query
# =====================================================================

class TestPipelineProgressGates:
    """PipelineProgress.set_gate_names() and get_progress()."""

    def test_set_gate_names_sets_total(self) -> None:
        """set_gate_names sets total_gates to list length."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0", "G1", "G2"])
        assert progress.total_gates == 3

    def test_gates_remaining_initially_full(self) -> None:
        """Before any gates run, gates_remaining == all gate names."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0", "G1"])
        data = progress.get_progress()
        assert data["gates_remaining"] == ["G0", "G1"]

    def test_gates_remaining_after_one_done(self) -> None:
        """After one gate passes, gates_remaining drops by one."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0", "G1", "G2"])
        progress.on_gate_start("G0")
        progress.on_gate_end("G0", True, 1.0)
        data = progress.get_progress()
        assert data["gates_remaining"] == ["G1", "G2"]

    def test_gates_done_and_remaining_in_sync(self) -> None:
        """gates_done + gates_remaining == all gates."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0", "G1", "G2", "G3"])
        for g in ["G0", "G1"]:
            progress.on_gate_start(g)
            progress.on_gate_end(g, True, 0.5)
        data = progress.get_progress()
        assert len(data["gates_done"]) + len(data["gates_remaining"]) == 4

    def test_elapsed_s_increases(self) -> None:
        """elapsed_s is positive after gates start."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0"])
        progress.on_gate_start("G0")
        data = progress.get_progress()
        assert data["elapsed_s"] >= 0.0


# =====================================================================
# PipelineProgress — cancel / pause / resume / retry / skip
# =====================================================================

class TestPipelineProgressControl:
    """PipelineProgress cancel/pause/resume/retry/skip methods."""

    def test_cancel_sets_flag(self) -> None:
        """cancel() marks pipeline as cancelled."""
        progress = PipelineProgress()
        progress.cancel()
        assert progress.is_cancelled() is True

    def test_cancel_unblocks_pause(self) -> None:
        """cancel() also sets the pause event so a paused pipeline can stop."""
        progress = PipelineProgress()
        progress.pause()
        assert progress.is_paused() is True
        progress.cancel()
        assert progress.is_paused() is False  # pause event was set
        assert progress.is_cancelled() is True

    def test_pause_and_resume(self) -> None:
        """pause() blocks, resume() unblocks."""
        progress = PipelineProgress()
        assert progress.is_paused() is False
        progress.pause()
        assert progress.is_paused() is True
        progress.resume()
        assert progress.is_paused() is False

    def test_wait_if_paused_returns_true_when_not_paused(self) -> None:
        """wait_if_paused returns True immediately when not paused."""
        progress = PipelineProgress()
        assert progress.wait_if_paused() is True

    def test_wait_if_paused_returns_false_if_cancelled_during_pause(self) -> None:
        """wait_if_paused returns False when cancelled during pause."""
        progress = PipelineProgress()
        progress.pause()
        progress.cancel()
        assert progress.wait_if_paused() is False

    def test_mark_and_consume_retry_gate(self) -> None:
        """mark_retry_gate / consume_retry_gate round-trip."""
        progress = PipelineProgress()
        progress.mark_retry_gate("G0")
        assert progress.consume_retry_gate() == "G0"
        assert progress.consume_retry_gate() is None  # cleared

    def test_mark_and_consume_skip_gate(self) -> None:
        """mark_skip_gate / consume_skip_gate round-trip."""
        progress = PipelineProgress()
        progress.mark_skip_gate("V3")
        assert progress.consume_skip_gate() == "V3"
        assert progress.consume_skip_gate() is None  # cleared


# =====================================================================
# PipelineProgress — HITL methods
# =====================================================================

class TestPipelineProgressHITL:
    """PipelineProgress HITL (Human-in-the-Loop) methods."""

    def test_on_gate_awaiting_hitl_sets_current_gate(self) -> None:
        """on_gate_awaiting_hitl sets current_gate."""
        progress = PipelineProgress(project_id="test-proj")
        progress.on_gate_awaiting_hitl("H0", detail="Needs review")
        assert progress.current_gate == "H0"

    def test_on_gate_awaiting_hitl_creates_event(self) -> None:
        """on_gate_awaiting_hitl adds an awaiting_hitl event."""
        progress = PipelineProgress(project_id="test-proj")
        progress.on_gate_awaiting_hitl("H0")
        data = progress.get_progress()
        assert any(e["status"] == "awaiting_hitl" for e in data["events"])

    def test_approve_hitl_signals_event(self) -> None:
        """approve_hitl triggers decision in wait_for_hitl."""
        progress = PipelineProgress(project_id="test-approve")
        progress.on_gate_awaiting_hitl("H0")
        progress.approve_hitl()
        result = progress.wait_for_hitl(timeout=5.0)
        assert result is True

    def test_reject_hitl_signals_event(self) -> None:
        """reject_hitl triggers decision in wait_for_hitl."""
        progress = PipelineProgress(project_id="test-reject")
        progress.on_gate_awaiting_hitl("H0")
        progress.reject_hitl()
        result = progress.wait_for_hitl(timeout=5.0)
        assert result is False

    def test_hitl_timeout_auto_approves(self) -> None:
        """wait_for_hitl timeout returns True (auto-approve)."""
        progress = PipelineProgress(project_id="test-timeout")
        progress.on_gate_awaiting_hitl("H0")
        result = progress.wait_for_hitl(timeout=0.01)
        assert result is True  # Timeout = auto-approve


# =====================================================================
# Backward compatibility: import from gate_engine still works
# =====================================================================

class TestBackwardCompatImports:
    """Verifies that importing from gate_engine still works."""

    def test_import_gate_error_result_from_gate_engine(self) -> None:
        """from automedia.pipelines.gate_engine import GateErrorResult works."""
        from automedia.pipelines.gate_engine import GateErrorResult as GER
        assert GER is GateErrorResult

    def test_import_progress_data_from_gate_engine(self) -> None:
        """from automedia.pipelines.gate_engine import ProgressData works."""
        from automedia.pipelines.gate_engine import ProgressData as PD
        assert PD is ProgressData

    def test_import_gate_progress_event_from_gate_engine(self) -> None:
        """from automedia.pipelines.gate_engine import GateProgressEvent works."""
        from automedia.pipelines.gate_engine import GateProgressEvent as GPE
        assert GPE is GateProgressEvent

    def test_import_pipeline_progress_from_gate_engine(self) -> None:
        """from automedia.pipelines.gate_engine import PipelineProgress works."""
        from automedia.pipelines.gate_engine import PipelineProgress as PP
        assert PP is PipelineProgress
