"""Tests for GateEngine retry logic on transient exceptions."""

from __future__ import annotations

from typing import Any

import pytest
from structlog.testing import capture_logs

from automedia.gates.h0_human_review import H0HumanReviewGate
from automedia.pipelines.gate_engine import (
    GateEngine,
    PipelineProgress,
)


class _FakeGate:
    """Lightweight gate stub that bypasses BaseGate's auto-registration."""

    def __init__(
        self,
        name: str,
        mode: str,
        execute_fn: Any,
    ) -> None:
        self._name = name
        self._mode = mode
        self._execute_fn = execute_fn

    @property
    def gate_name(self) -> str:
        return self._name

    @property
    def failure_mode(self) -> str:
        return self._mode

    def execute(self, ctx: dict[str, Any]) -> dict[str, Any]:
        return self._execute_fn(ctx)


# ---------------------------------------------------------------------------
# (a) Flaky gate fails 2 times transient, succeeds on 3rd
# ---------------------------------------------------------------------------


def test_retry_succeeds_after_transient_failures() -> None:
    call_count = {"n": 0}

    def _flaky_execute(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise ConnectionError("transient failure")
        return {"passed": True, "gate": "G0"}

    gate = _FakeGate("G0", "retry", _flaky_execute)
    engine = GateEngine([gate], max_retries=3, retry_delay=0.01)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    ok, results = engine.run({"topic": "test"})

    assert ok is True
    assert len(results) == 1
    assert results[0]["passed"] is True
    assert results[0].get("retry_count") == 2
    assert call_count["n"] == 3


# ---------------------------------------------------------------------------
# (b) Flaky gate always fails transient — exhausts retries
# ---------------------------------------------------------------------------


def test_retry_exhausted_on_persistent_transient() -> None:
    call_count = {"n": 0}

    def _always_fail(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        raise TimeoutError("always times out")

    gate = _FakeGate("G0", "retry", _always_fail)
    engine = GateEngine([gate], max_retries=3, retry_delay=0.01)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    ok, results = engine.run({"topic": "test"})

    assert ok is False
    assert len(results) == 1
    assert results[0]["passed"] is False
    assert results[0]["retry_count"] == 3
    assert results[0]["retry_delay_s"] == 0.01
    assert call_count["n"] == 3


# ---------------------------------------------------------------------------
# (c) Permanent error — no retry, immediate failure
# ---------------------------------------------------------------------------


def test_permanent_error_no_retry() -> None:
    call_count = {"n": 0}

    def _key_error(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        raise KeyError("missing key")

    gate = _FakeGate("G0", "retry", _key_error)
    engine = GateEngine([gate], max_retries=3, retry_delay=0.01)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    ok, results = engine.run({"topic": "test"})

    assert ok is False
    assert len(results) == 1
    assert results[0]["passed"] is False
    assert "retry_count" not in results[0]
    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# (d) failure_mode="stop" with transient error — no retry
# ---------------------------------------------------------------------------


def test_stop_mode_no_retry_on_transient() -> None:
    call_count = {"n": 0}

    def _conn_error(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        raise ConnectionError("connection lost")

    gate = _FakeGate("G0", "stop", _conn_error)
    engine = GateEngine([gate], max_retries=3, retry_delay=0.01)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    ok, results = engine.run({"topic": "test"})

    assert ok is False
    assert len(results) == 1
    assert results[0]["passed"] is False
    assert "retry_count" not in results[0]
    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# (e) Log output contains retry attempt messages
# ---------------------------------------------------------------------------


def test_retry_logging_contains_attempt_messages() -> None:
    call_count = {"n": 0}

    def _flaky_execute(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise ConnectionError("transient")
        return {"passed": True, "gate": "G0"}

    gate = _FakeGate("G0", "retry", _flaky_execute)
    engine = GateEngine([gate], max_retries=3, retry_delay=0.01)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    with capture_logs() as cap:
        engine.run({"topic": "test"})

    retry_events = [
        e for e in cap if e.get("log_level") == "info" and "retry" in e.get("event", "")
    ]
    assert len(retry_events) == 2

    first = retry_events[0]
    assert first["attempt"] == 1
    assert first["max_retries"] == 3
    assert first["gate_name"] == "G0"


# ---------------------------------------------------------------------------
# Progress events emitted for each retry attempt
# ---------------------------------------------------------------------------


def test_retry_emits_progress_events() -> None:
    call_count = {"n": 0}

    def _flaky_execute(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise ConnectionError("transient")
        return {"passed": True, "gate": "G0"}

    gate = _FakeGate("G0", "retry", _flaky_execute)
    engine = GateEngine([gate], max_retries=3, retry_delay=0.01)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    progress = PipelineProgress(project_id="test-proj")

    engine.run({"topic": "test"}, progress=progress)

    events = progress.get_progress()["events"]
    running_events = [e for e in events if e["status"] == "running"]
    failed_events = [e for e in events if e["status"] == "failed"]
    passed_events = [e for e in events if e["status"] == "passed"]

    assert len(running_events) == 3
    assert len(failed_events) == 2
    assert len(passed_events) == 1


# ---------------------------------------------------------------------------
# Unknown exception with retry mode — no retry, re-raises
# ---------------------------------------------------------------------------


def test_unknown_exception_no_retry_reraises() -> None:
    call_count = {"n": 0}

    def _runtime_error(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        raise RuntimeError("unexpected")

    gate = _FakeGate("G0", "retry", _runtime_error)
    engine = GateEngine([gate], max_retries=3, retry_delay=0.01)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    with pytest.raises(RuntimeError, match="unexpected"):
        engine.run({"topic": "test"})

    assert call_count["n"] == 1


# =========================================================================
# Level 1: Quality-feedback retry
# =========================================================================


# ---------------------------------------------------------------------------
# (a) Gate fails quality check 2 times, passes on 3rd
# ---------------------------------------------------------------------------


def test_quality_retry_succeeds_after_failures() -> None:
    call_count: dict[str, int] = {"n": 0}

    def _quality_flaky(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        if call_count["n"] < 3:
            return {"passed": False, "gate": "G0", "error": "quality fail"}
        return {"passed": True, "gate": "G0"}

    gate = _FakeGate("G0", "retry", _quality_flaky)
    engine = GateEngine([gate], max_quality_retries=3)

    ok, results = engine.run({"topic": "test"})

    assert ok is True
    assert len(results) == 1
    assert results[0]["passed"] is True
    assert results[0].get("quality_retry_count") == 2
    assert call_count["n"] == 3


# ---------------------------------------------------------------------------
# (b) Quality retry exhausted — gate always fails
# ---------------------------------------------------------------------------


def test_quality_retry_exhausted() -> None:
    call_count: dict[str, int] = {"n": 0}

    def _always_fail(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        return {"passed": False, "gate": "G0", "error": "always fails"}

    gate = _FakeGate("G0", "retry", _always_fail)
    engine = GateEngine([gate], max_quality_retries=3)

    ok, results = engine.run({"topic": "test"})

    assert ok is False
    assert len(results) == 1
    assert results[0]["passed"] is False
    assert results[0].get("quality_retry_count") == 3
    assert call_count["n"] == 4


# ---------------------------------------------------------------------------
# (c) failure_mode='stop' — no quality retry
# ---------------------------------------------------------------------------


def test_quality_retry_stop_mode_no_retry() -> None:
    call_count: dict[str, int] = {"n": 0}

    def _fail_stop(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        return {"passed": False, "gate": "G0", "error": "fatal"}

    gate = _FakeGate("G0", "stop", _fail_stop)
    engine = GateEngine([gate], max_quality_retries=3)

    ok, results = engine.run({"topic": "test"})

    assert ok is False
    assert len(results) == 1
    assert "quality_retry_count" not in results[0]
    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# (d) max_quality_retries=0 — no quality retry
# ---------------------------------------------------------------------------


def test_quality_retry_disabled_when_zero() -> None:
    call_count: dict[str, int] = {"n": 0}

    def _fail_quality(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        return {"passed": False, "gate": "G0", "error": "quality fail"}

    gate = _FakeGate("G0", "retry", _fail_quality)
    engine = GateEngine([gate], max_quality_retries=0)

    ok, results = engine.run({"topic": "test"})

    assert ok is False
    assert len(results) == 1
    assert results[0]["passed"] is False
    assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# (e) Quality retry emits progress events
# ---------------------------------------------------------------------------


def test_quality_retry_emits_progress_events() -> None:
    call_count: dict[str, int] = {"n": 0}

    def _quality_flaky(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        if call_count["n"] < 3:
            return {"passed": False, "gate": "G0", "error": "quality fail"}
        return {"passed": True, "gate": "G0"}

    gate = _FakeGate("G0", "retry", _quality_flaky)
    engine = GateEngine([gate], max_quality_retries=3)
    progress = PipelineProgress(project_id="test-proj")

    engine.run({"topic": "test"}, progress=progress)

    events = progress.get_progress()["events"]
    running_events = [e for e in events if e["status"] == "running"]
    failed_events = [e for e in events if e["status"] == "failed"]
    passed_events = [e for e in events if e["status"] == "passed"]

    # Events: start → end(False) → end(False,0) → start → end(False) → end(False,0) → start → end(True)
    assert len(running_events) == 3
    assert len(failed_events) == 4
    assert len(passed_events) == 1


# ---------------------------------------------------------------------------
# (f) Quality retry logging contains attempt info
# ---------------------------------------------------------------------------


def test_quality_retry_logging() -> None:
    call_count: dict[str, int] = {"n": 0}

    def _quality_flaky(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        if call_count["n"] < 3:
            return {"passed": False, "gate": "G0", "error": "quality fail"}
        return {"passed": True, "gate": "G0"}

    gate = _FakeGate("G0", "retry", _quality_flaky)
    engine = GateEngine([gate], max_quality_retries=3)

    with capture_logs() as cap:
        engine.run({"topic": "test"})

    quality_retry_events = [e for e in cap if e.get("event") == "gate.quality_retry"]
    assert len(quality_retry_events) == 2

    first = quality_retry_events[0]
    assert first["attempt"] == 1
    assert first["remaining"] == 2
    assert first["max_quality_retries"] == 3
    assert first["gate_name"] == "G0"
    assert first["failure_reason"] == "quality fail"

    second = quality_retry_events[1]
    assert second["attempt"] == 2
    assert second["remaining"] == 1


# ---------------------------------------------------------------------------
# (g) Quality retry exhausted continues to next gate
# ---------------------------------------------------------------------------


def test_quality_retry_exhausted_continues_pipeline() -> None:
    call_count: dict[str, int] = {"n": 0}

    def _always_fail(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        return {"passed": False, "gate": "G0", "error": "always fails"}

    gate_a = _FakeGate("G0", "retry", _always_fail)
    gate_b = _FakeGate("G1", "stop", lambda ctx: {"passed": True, "gate": "G1"})
    engine = GateEngine([gate_a, gate_b], max_quality_retries=2)

    ok, results = engine.run({"topic": "test"})

    assert ok is True
    assert len(results) == 2
    assert results[0]["passed"] is False
    assert results[0].get("quality_retry_count") == 2
    assert results[1]["passed"] is True
    assert results[1]["gate"] == "G1"
    assert call_count["n"] == 3


# ---------------------------------------------------------------------------
# (h) Quality retry with level 2 handler — delegates
# ---------------------------------------------------------------------------


def test_quality_retry_delegates_to_level2_handler() -> None:
    call_count: dict[str, int] = {"n": 0}
    level2_called: dict[str, bool] = {"called": False}

    def _always_fail(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        return {"passed": False, "gate": "G0", "error": "always fails"}

    def _level2_handler(
        **kwargs: Any,
    ) -> tuple[bool, list[dict[str, Any]]]:
        level2_called["called"] = True
        return False, []

    gate = _FakeGate("G0", "retry", _always_fail)
    # Include CW so level 2 handler does not crash looking for it
    cw_gate = _FakeGate("CW", "stop", lambda ctx: {"passed": True, "gate": "CW"})
    engine = GateEngine([cw_gate, gate], max_quality_retries=2, max_regenerations=0)

    ctx: dict[str, Any] = {"topic": "test", "_level2_handler": _level2_handler}
    ok, results = engine.run(ctx)

    assert ok is False
    assert call_count["n"] == 3
    assert level2_called["called"] is True


# ---------------------------------------------------------------------------
# (i) Quality retry count in gate_context
# ---------------------------------------------------------------------------


def test_quality_retry_tracks_count_in_context() -> None:
    call_count: dict[str, int] = {"n": 0}
    captured_counts: list[int] = []

    def _tracking_execute(ctx: dict[str, Any]) -> dict[str, Any]:
        call_count["n"] += 1
        captured_counts.append(ctx.get("_quality_retry_count", -1))
        if call_count["n"] < 3:
            return {"passed": False, "gate": "G0", "error": "fail"}
        return {"passed": True, "gate": "G0"}

    gate = _FakeGate("G0", "retry", _tracking_execute)
    engine = GateEngine([gate], max_quality_retries=3)

    engine.run({"topic": "test"})

    assert captured_counts == [0, 1, 2]
    assert call_count["n"] == 3


# =========================================================================
# Level 2: content regeneration
# =========================================================================

# ---------------------------------------------------------------------------
# (j) Regeneration triggers after quality retries exhausted
# ---------------------------------------------------------------------------


def test_level2_regeneration_triggers_after_quality_exhausted() -> None:
    """Level 2 regeneration re-runs CW after level 1 quality retries exhausted.

    CW is re-executed once for the regeneration pass, and the downstream
    gate (which initially failed) passes on the second attempt.
    """
    cw_count: dict[str, int] = {"n": 0}
    g0_count: dict[str, int] = {"n": 0}

    def _cw(ctx: dict[str, Any]) -> dict[str, Any]:
        cw_count["n"] += 1
        ctx["content"] = f"regenerated content v{cw_count['n']}"
        return {"passed": True, "gate": "CW"}

    def _g0(ctx: dict[str, Any]) -> dict[str, Any]:
        g0_count["n"] += 1
        if g0_count["n"] <= 1:
            return {"passed": False, "gate": "G0", "error": "quality fail"}
        return {"passed": True, "gate": "G0"}

    cw_gate = _FakeGate("CW", "stop", _cw)
    g0_gate = _FakeGate("G0", "retry", _g0)
    engine = GateEngine(
        [cw_gate, g0_gate],
        max_quality_retries=0,
        max_regenerations=2,
    )

    ok, results = engine.run({"topic": "test"})

    assert ok is True
    # CW: initial + 1 regeneration
    assert cw_count["n"] == 2
    # G0: initial (fail) + regeneration pass
    assert g0_count["n"] == 2
    assert len(results) == 2
    assert results[0]["passed"] is True
    assert results[0]["gate"] == "CW"
    assert results[1]["passed"] is True
    assert results[1]["gate"] == "G0"


# ---------------------------------------------------------------------------
# (k) Regeneration count tracks across multiple regenerations
# ---------------------------------------------------------------------------


def test_level2_regeneration_count_tracked_in_context() -> None:
    """_regeneration_count increments across multiple regeneration passes."""
    cw_count: dict[str, int] = {"n": 0}

    def _cw_always_pass(ctx: dict[str, Any]) -> dict[str, Any]:
        cw_count["n"] += 1
        ctx["content"] = f"v{cw_count['n']}"
        return {"passed": True, "gate": "CW"}

    def _g0_always_fail(ctx: dict[str, Any]) -> dict[str, Any]:
        return {"passed": False, "gate": "G0", "error": "still bad"}

    cw_gate = _FakeGate("CW", "stop", _cw_always_pass)
    g0_gate = _FakeGate("G0", "retry", _g0_always_fail)
    engine = GateEngine(
        [cw_gate, g0_gate],
        max_quality_retries=0,
        max_regenerations=2,
    )

    ctx: dict[str, Any] = {"topic": "test"}
    ok, results = engine.run(ctx)

    assert ok is False
    # CW: initial + 2 regenerations = 3
    assert cw_count["n"] == 3
    # After 2 regenerations exhausted
    assert ctx.get("_regeneration_count") == 2
    # failure_feedback should contain info about the last failure
    fb = ctx.get("failure_feedback")
    assert fb is not None
    assert fb["failed_gate"] == "G0"
    assert fb["error"] == "still bad"


# ---------------------------------------------------------------------------
# (l) Max regenerations exhausted sets _level2_exhausted flag
# ---------------------------------------------------------------------------


def test_level2_max_regenerations_sets_exhausted_flag() -> None:
    """After max_regenerations attempts, _level2_exhausted is True."""
    cw_gate = _FakeGate(
        "CW",
        "stop",
        lambda ctx: {"passed": True, "gate": "CW"},
    )
    g0_gate = _FakeGate(
        "G0",
        "retry",
        lambda ctx: {"passed": False, "gate": "G0", "error": "fails always"},
    )
    engine = GateEngine(
        [cw_gate, g0_gate],
        max_quality_retries=0,
        max_regenerations=2,
    )

    ctx: dict[str, Any] = {"topic": "test"}
    ok, results = engine.run(ctx)

    assert ok is False
    assert ctx.get("_level2_exhausted") is True
    assert ctx.get("_regeneration_count") == 2
    assert len(results) >= 1
    # Final result should still show the failure
    assert results[-1]["passed"] is False


# ---------------------------------------------------------------------------
# (m) Regeneration re-runs all gates from CW onward (not just failed gate)
# ---------------------------------------------------------------------------


def test_level2_regeneration_runs_all_gates_from_cw() -> None:
    """All gates from CW are re-run during regeneration, not just the failed one."""
    gate_calls: dict[str, int] = {"CW": 0, "G0": 0, "G1": 0}

    def _cw(ctx: dict[str, Any]) -> dict[str, Any]:
        gate_calls["CW"] += 1
        ctx["content"] = f"v{gate_calls['CW']}"
        return {"passed": True, "gate": "CW"}

    def _g0(ctx: dict[str, Any]) -> dict[str, Any]:
        gate_calls["G0"] += 1
        # Always fail — triggers regeneration
        return {"passed": False, "gate": "G0", "error": "bad g0"}

    def _g1(ctx: dict[str, Any]) -> dict[str, Any]:
        gate_calls["G1"] += 1
        return {"passed": True, "gate": "G1"}

    cw = _FakeGate("CW", "stop", _cw)
    g0 = _FakeGate("G0", "retry", _g0)
    g1 = _FakeGate("G1", "stop", _g1)

    engine = GateEngine(
        [cw, g0, g1],
        max_quality_retries=0,
        max_regenerations=1,
    )

    ctx: dict[str, Any] = {"topic": "test"}
    ok, results = engine.run(ctx)

    assert ok is False
    # CW: initial + 1 regeneration = 2
    assert gate_calls["CW"] == 2
    # G0: initial + regeneration = 2
    assert gate_calls["G0"] == 2
    # G1: runs once in the regeneration sub-engine (exhausted before outer)
    assert gate_calls["G1"] == 1
    assert len(results) >= 2
    assert results[-1]["gate"] == "G1"


# =========================================================================
# Level 3: Human escalation via H0 (Task 20)
# =========================================================================


# ---------------------------------------------------------------------------
# (n) Level 2 exhaustion populates _escalated_gates
# ---------------------------------------------------------------------------


def test_level2_exhaustion_populates_escalated_gates() -> None:
    """When level 2 regeneration budget exhausted, _escalated_gates
    is populated with the failed gate name, error, and regen count."""
    cw_gate = _FakeGate(
        "CW",
        "stop",
        lambda ctx: {"passed": True, "gate": "CW"},
    )
    g0_gate = _FakeGate(
        "G0",
        "retry",
        lambda ctx: {"passed": False, "gate": "G0", "error": "persistent failure"},
    )

    engine = GateEngine(
        [cw_gate, g0_gate],
        max_quality_retries=0,
        max_regenerations=2,
    )

    ctx: dict[str, Any] = {"topic": "test"}
    ok, results = engine.run(ctx)

    assert ok is False
    assert ctx.get("_level2_exhausted") is True
    assert ctx.get("_regeneration_count") == 2

    escalated = ctx.get("_escalated_gates", [])
    assert len(escalated) == 1
    entry = escalated[0]
    assert entry["gate_name"] == "G0"
    assert entry["error"] == "persistent failure"
    assert entry["regeneration_count"] == 2


# ---------------------------------------------------------------------------
# (o) Level 2 escalation flows to H0 gate
# ---------------------------------------------------------------------------


def test_level2_escalation_flows_to_h0_gate() -> None:
    """Full 3-level chain: quality failure → level 1 retries → level 2
    regeneration → level 2 exhausted → H0 gate receives escalated info.

    This simulates a real pipeline where CW writes, G0 fails persistently
    through all recovery levels, and H0 catches the escalation.
    """
    import threading

    g0_call_count: dict[str, int] = {"n": 0}

    def _cw(ctx: dict[str, Any]) -> dict[str, Any]:
        ctx["content"] = "test content"
        return {"passed": True, "gate": "CW"}

    def _g0_always_fail(ctx: dict[str, Any]) -> dict[str, Any]:
        g0_call_count["n"] += 1
        return {"passed": False, "gate": "G0", "error": "always bad"}

    cw_gate = _FakeGate("CW", "stop", _cw)
    g0_gate = _FakeGate("G0", "retry", _g0_always_fail)
    h0_gate = H0HumanReviewGate()

    engine = GateEngine(
        [cw_gate, g0_gate, h0_gate],
        max_quality_retries=1,  # Allow 1 level 1 retry per gate pass
        max_regenerations=2,  # Allow 2 regeneration attempts
    )
    progress = PipelineProgress(project_id="escalation-test")

    # Auto-approve HITL after a short delay
    def _auto_approve() -> None:
        import time

        time.sleep(0.2)
        progress.approve_hitl()

    timer = threading.Timer(0.05, _auto_approve)
    timer.start()
    ok, results = engine.run(
        {"topic": "test", "skip_review": False},
        progress=progress,
    )
    timer.cancel()

    # After exhausting 2 regenerations, G0 still fails, but the pipeline
    # continues to H0 which auto-passes via HITL approve → overall success
    assert ok is True

    # H0 result should contain escalated_gates with G0 failure info
    h0_result = next(r for r in results if r.get("gate") == "H0")
    assert h0_result["status"] == "awaiting_hitl"
    assert h0_result["_hitl_approved"] is True

    escalated: list[dict[str, Any]] | None = h0_result.get("escalated_gates")
    assert escalated is not None, "H0 result should contain escalated_gates"
    assert len(escalated) >= 1

    entry = escalated[0]
    assert entry["gate_name"] == "G0"
    assert "error" in entry
    assert "regeneration_count" in entry

    # Verify the regen count matches max
    assert entry["regeneration_count"] == 2
