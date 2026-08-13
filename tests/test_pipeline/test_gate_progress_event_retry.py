"""Tests for GateProgressEvent retry metadata fields.

Scenarios
---------
1. GateProgressEvent can be created with attempt_number, retry_level, strategy_delta
2. Default values: attempt_number=1, retry_level=None, strategy_delta=None
3. All fields are stored and readable via __dict__
4. on_gate_start() with retry kwargs stores them in the event
5. on_gate_end() with retry kwargs stores them in the event
6. on_gate_awaiting_hitl() with retry kwargs stores them in the event
7. Events appear correctly in get_progress().events
8. strategy_delta can be a dict with nested structure
9. Different retry_level values are preserved (quality, tenacity, manual)
10. Multiple events preserve per-event retry metadata independently
"""

from __future__ import annotations

from automedia.pipelines.gate_engine import GateProgressEvent, PipelineProgress

# =====================================================================
# GateProgressEvent construction
# =====================================================================


class TestGateProgressEventConstruction:
    """Direct construction of GateProgressEvent with retry metadata."""

    def test_default_values(self) -> None:
        """Default retry metadata values are correct."""
        event = GateProgressEvent(gate_name="G0", status="running")
        assert event.attempt_number == 1
        assert event.retry_level is None
        assert event.strategy_delta is None

    def test_explicit_attempt_number(self) -> None:
        """attempt_number set explicitly is stored."""
        event = GateProgressEvent(gate_name="G0", status="running", attempt_number=3)
        assert event.attempt_number == 3

    def test_explicit_retry_level_quality(self) -> None:
        """retry_level='quality' is stored."""
        event = GateProgressEvent(gate_name="G0", status="running", retry_level="quality")
        assert event.retry_level == "quality"

    def test_explicit_retry_level_tenacity(self) -> None:
        """retry_level='tenacity' is stored."""
        event = GateProgressEvent(gate_name="G0", status="running", retry_level="tenacity")
        assert event.retry_level == "tenacity"

    def test_explicit_retry_level_manual(self) -> None:
        """retry_level='manual' is stored."""
        event = GateProgressEvent(gate_name="G0", status="running", retry_level="manual")
        assert event.retry_level == "manual"

    def test_strategy_delta_can_be_dict(self) -> None:
        """strategy_delta can be a flat dict."""
        delta = {"temperature": 0.7, "max_tokens": 2000}
        event = GateProgressEvent(gate_name="G0", status="passed", strategy_delta=delta)
        assert event.strategy_delta == delta

    def test_strategy_delta_nested_dict(self) -> None:
        """strategy_delta can be a nested dict."""
        delta = {"llm": {"temperature": 0.8, "model": "gpt-4"}, "prompt": "revised"}
        event = GateProgressEvent(gate_name="G0", status="failed", strategy_delta=delta)
        assert event.strategy_delta == delta
        assert event.strategy_delta["llm"]["temperature"] == 0.8

    def test_strategy_delta_none_by_default(self) -> None:
        """strategy_delta defaults to None."""
        event = GateProgressEvent(gate_name="G0", status="running")
        assert event.strategy_delta is None

    def test_all_retry_fields_together(self) -> None:
        """All three retry metadata fields can be set together."""
        delta = {"model": "deepseek-chat"}
        event = GateProgressEvent(
            gate_name="V3",
            status="running",
            attempt_number=2,
            retry_level="quality",
            strategy_delta=delta,
        )
        assert event.attempt_number == 2
        assert event.retry_level == "quality"
        assert event.strategy_delta == delta

    def test_events_for_all_statuses(self) -> None:
        """Retry metadata works for all event statuses."""
        for status in ("running", "passed", "failed", "skipped", "awaiting_hitl"):
            event = GateProgressEvent(
                gate_name="G0",
                status=status,  # type: ignore[arg-type]
                attempt_number=2,
                retry_level="tenacity",
                strategy_delta={"key": "val"},
            )
            assert event.status == status
            assert event.attempt_number == 2


# =====================================================================
# __dict__ serialisation
# =====================================================================


class TestDictSerialization:
    """GateProgressEvent fields appear in __dict__."""

    def test_default_fields_in_dict(self) -> None:
        """All default fields present in __dict__."""
        event = GateProgressEvent(gate_name="G0", status="running")
        d = event.__dict__
        assert d["gate_name"] == "G0"
        assert d["status"] == "running"
        assert d["attempt_number"] == 1
        assert d["retry_level"] is None
        assert d["strategy_delta"] is None

    def test_retry_fields_in_dict(self) -> None:
        """Retry metadata fields appear in __dict__."""
        event = GateProgressEvent(
            gate_name="G1",
            status="failed",
            attempt_number=2,
            retry_level="quality",
            strategy_delta={"temperature": 0.9},
        )
        d = event.__dict__
        assert d["attempt_number"] == 2
        assert d["retry_level"] == "quality"
        assert d["strategy_delta"] == {"temperature": 0.9}

    def test_dict_round_trip(self) -> None:
        """__dict__ can reconstruct a new event (dict-compat)."""
        event = GateProgressEvent(
            gate_name="G0",
            status="passed",
            duration_s=1.5,
            detail="ok",
            timestamp="2025-01-01T00:00:00",
            attempt_number=3,
            retry_level="tenacity",
            strategy_delta={"retry_delay": 2.0},
        )
        d = event.__dict__
        restored = GateProgressEvent(**d)
        assert restored.attempt_number == 3
        assert restored.retry_level == "tenacity"
        assert restored.strategy_delta == {"retry_delay": 2.0}


# =====================================================================
# on_gate_start with retry metadata
# =====================================================================


class TestOnGateStartRetryMetadata:
    """PipelineProgress.on_gate_start() stores retry metadata."""

    def test_on_gate_start_defaults(self) -> None:
        """on_gate_start without retry args uses defaults."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0", "G1"])
        progress.on_gate_start("G0")
        p = progress.get_progress()
        events = p["events"]
        assert len(events) == 1
        assert events[0]["status"] == "running"
        assert events[0]["attempt_number"] == 1
        assert events[0]["retry_level"] is None
        assert events[0]["strategy_delta"] is None

    def test_on_gate_start_with_retry_level(self) -> None:
        """on_gate_start with retry_level='quality' stores it."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0"])
        progress.on_gate_start("G0", attempt_number=2, retry_level="quality")
        p = progress.get_progress()
        event = p["events"][0]
        assert event["attempt_number"] == 2
        assert event["retry_level"] == "quality"

    def test_on_gate_start_with_strategy_delta(self) -> None:
        """on_gate_start with strategy_delta stores it."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0"])
        delta = {"max_retries": 5, "delay": 2.0}
        progress.on_gate_start("G0", attempt_number=3, retry_level="tenacity", strategy_delta=delta)
        p = progress.get_progress()
        event = p["events"][0]
        assert event["attempt_number"] == 3
        assert event["retry_level"] == "tenacity"
        assert event["strategy_delta"] == delta


# =====================================================================
# on_gate_end with retry metadata
# =====================================================================


class TestOnGateEndRetryMetadata:
    """PipelineProgress.on_gate_end() stores retry metadata."""

    def test_on_gate_end_defaults(self) -> None:
        """on_gate_end without retry args uses defaults."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0", "G1"])
        progress.on_gate_start("G0")
        progress.on_gate_end("G0", True, 1.0)
        p = progress.get_progress()
        events = [e for e in p["events"] if e["status"] != "running"]
        assert len(events) == 1
        assert events[0]["attempt_number"] == 1
        assert events[0]["retry_level"] is None

    def test_on_gate_end_with_retry_level_quality(self) -> None:
        """on_gate_end with retry_level='quality' stores it."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0"])
        progress.on_gate_start("G0")
        progress.on_gate_end("G0", False, 1.5, attempt_number=1, retry_level="quality")
        p = progress.get_progress()
        event = p["events"][-1]
        assert event["attempt_number"] == 1
        assert event["retry_level"] == "quality"

    def test_on_gate_end_with_retry_level_tenacity(self) -> None:
        """on_gate_end with retry_level='tenacity' stores it."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0"])
        progress.on_gate_start("G0")
        progress.on_gate_end("G0", False, 0.0, attempt_number=2, retry_level="tenacity")
        p = progress.get_progress()
        event = p["events"][-1]
        assert event["attempt_number"] == 2
        assert event["retry_level"] == "tenacity"

    def test_on_gate_end_with_strategy_delta(self) -> None:
        """on_gate_end with strategy_delta stores it."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0"])
        progress.on_gate_start("G0")
        delta = {"prompt": "revised-v2"}
        progress.on_gate_end(
            "G0", True, 2.0, attempt_number=3, retry_level="quality", strategy_delta=delta
        )
        p = progress.get_progress()
        event = p["events"][-1]
        assert event["attempt_number"] == 3
        assert event["retry_level"] == "quality"
        assert event["strategy_delta"] == delta


# =====================================================================
# on_gate_awaiting_hitl with retry metadata
# =====================================================================


class TestOnGateAwaitingHITLRetryMetadata:
    """PipelineProgress.on_gate_awaiting_hitl() stores retry metadata."""

    def test_on_gate_awaiting_hitl_defaults(self) -> None:
        """on_gate_awaiting_hitl without retry args uses defaults."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0"])
        progress.on_gate_awaiting_hitl("G0")
        p = progress.get_progress()
        event = p["events"][0]
        assert event["status"] == "awaiting_hitl"
        assert event["attempt_number"] == 1
        assert event["retry_level"] is None

    def test_on_gate_awaiting_hitl_with_retry_metadata(self) -> None:
        """on_gate_awaiting_hitl with retry metadata stores it."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0"])
        delta = {"timeout": 600}
        progress.on_gate_awaiting_hitl(
            "G0",
            detail="human review needed",
            attempt_number=2,
            retry_level="quality",
            strategy_delta=delta,
        )
        p = progress.get_progress()
        event = p["events"][0]
        assert event["attempt_number"] == 2
        assert event["retry_level"] == "quality"
        assert event["strategy_delta"] == delta
        assert event["detail"] == "human review needed"


# =====================================================================
# Events in get_progress() — combined scenarios
# =====================================================================


class TestEventsInGetProgress:
    """Multiple events with retry metadata appear correctly."""

    def test_retry_cycle_events(self) -> None:
        """A full retry cycle: initial → quality retry → pass."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0", "G1"])

        # First attempt — fails
        progress.on_gate_start("G0", attempt_number=1)
        progress.on_gate_end("G0", False, 1.0, attempt_number=1, retry_level="quality")

        # Quality retry — fails
        progress.on_gate_start("G0", attempt_number=2, retry_level="quality")
        progress.on_gate_end("G0", False, 0.8, attempt_number=2, retry_level="quality")

        # Final attempt — passes
        progress.on_gate_start("G0", attempt_number=3, retry_level="quality")
        progress.on_gate_end("G0", True, 1.2, attempt_number=3, retry_level="quality")

        # Next gate
        progress.on_gate_start("G1")
        progress.on_gate_end("G1", True, 0.5)

        p = progress.get_progress()
        events = p["events"]

        assert len(events) == 8  # 3 start + 3 end for G0, 1 start + 1 end for G1

        # Check retry metadata for G0 end events
        g0_end_events = [e for e in events if e["gate_name"] == "G0" and e["status"] != "running"]
        assert len(g0_end_events) == 3
        assert g0_end_events[0]["attempt_number"] == 1
        assert g0_end_events[0]["retry_level"] == "quality"
        assert g0_end_events[1]["attempt_number"] == 2
        assert g0_end_events[1]["retry_level"] == "quality"
        assert g0_end_events[2]["attempt_number"] == 3
        assert g0_end_events[2]["retry_level"] == "quality"

        # G1 should have defaults
        g1_events = [e for e in events if e["gate_name"] == "G1"]
        for ev in g1_events:
            assert ev["attempt_number"] == 1
            assert ev["retry_level"] is None

    def test_tenacity_retry_events(self) -> None:
        """Events from tenacity retry have retry_level='tenacity'."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0"])

        # Simulate: initial → tenacity before_sleep (end old, start new) → final pass
        progress.on_gate_start("G0")
        progress.on_gate_end("G0", False, 0.5, attempt_number=1, retry_level="tenacity")
        progress.on_gate_start("G0", attempt_number=2, retry_level="tenacity")
        progress.on_gate_end("G0", True, 1.0, attempt_number=2, retry_level="tenacity")

        p = progress.get_progress()
        events = p["events"]

        # First end event
        assert events[1]["attempt_number"] == 1
        assert events[1]["retry_level"] == "tenacity"
        # Second start event
        assert events[2]["attempt_number"] == 2
        assert events[2]["retry_level"] == "tenacity"
        # Second end event
        assert events[3]["attempt_number"] == 2
        assert events[3]["retry_level"] == "tenacity"

    def test_mixed_retry_levels(self) -> None:
        """Different retry levels appear independently in events."""
        progress = PipelineProgress()
        progress.set_gate_names(["G0"])

        progress.on_gate_start("G0")
        # Quality retry attempt
        progress.on_gate_end("G0", False, 0.5, attempt_number=1, retry_level="quality")
        progress.on_gate_start("G0", attempt_number=2, retry_level="quality")
        # Tenacity retry within quality retry
        progress.on_gate_end("G0", False, 0.2, attempt_number=1, retry_level="tenacity")
        progress.on_gate_start("G0", attempt_number=2, retry_level="tenacity")
        # Final pass
        progress.on_gate_end("G0", True, 1.0, attempt_number=2, retry_level="tenacity")

        p = progress.get_progress()
        events = p["events"]

        retry_levels = [(e["attempt_number"], e["retry_level"]) for e in events[1:]]
        assert (1, "quality") in retry_levels
        assert (1, "tenacity") in retry_levels
        assert (2, "tenacity") in retry_levels
