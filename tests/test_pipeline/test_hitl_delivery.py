"""HITL approval delivery — issue #105 regression coverage.

Before this change the H0 pause could only be resolved from inside the process
that was running the pipeline (the in-memory ``_hitl_waiters`` registry), the
file-backed branch of ``wait_for_hitl`` was unreachable because the engine
passed ``project_dir=""``, and a timed-out pause auto-approved after a hardcoded
24 hours.  These tests pin the delivered behaviour:

* a decision written to ``.hitl_state.json`` by *another* process is honoured;
* the engine actually passes the project dir (the wiring that made the file
  branch dead code);
* a timeout no longer silently approves, and the default budget is one hour
  rather than 24;
* a stale decision file cannot leak into a later run.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from automedia.gates.h0_human_review import H0HumanReviewGate
from automedia.pipelines.gate_engine import GateEngine
from automedia.pipelines.gate_types import PipelineProgress

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _write_decision(project_dir: Path, decision: str) -> None:
    (project_dir / ".hitl_state.json").write_text(
        json.dumps({"decision": decision}), encoding="utf-8"
    )


class _AwaitingGate:
    """Stub gate that always pauses for review, like H0 does.

    Duck-typed rather than a ``BaseGate`` subclass on purpose: subclassing
    auto-registers in the global ``GateRegistry`` singleton, which would both
    trip the RL6 gate-naming red line and leak state into other test files
    (the failure mode behind issue #28).  ``GateEngine`` only ever touches
    ``gate_name``, ``execute`` and ``failure_mode``.
    """

    gate_name = "STUB"
    failure_mode = "stop"

    def __init__(self, on_timeout: str | None = None) -> None:
        self._on_timeout = on_timeout

    def execute(self, gate_context: Any) -> dict[str, Any]:
        result: dict[str, Any] = {
            "passed": True,
            "gate": self.gate_name,
            "status": "awaiting_hitl",
            "timeout_s": 10.0,
        }
        if self._on_timeout is not None:
            result["on_timeout"] = self._on_timeout
        return result


# -- the pause budget and the timeout outcome (H0) ---------------------------


def test_h0_default_timeout_is_one_hour_not_24h() -> None:
    """Given no configuration, H0 pauses for 1h — not the old hardcoded 24h."""
    result = H0HumanReviewGate().execute({"skip_review": False, "hitl_config": {}})
    assert result["timeout_s"] == 3600


def test_h0_timeout_outcome_defaults_to_reject() -> None:
    """A timed-out pause must not silently approve by default."""
    result = H0HumanReviewGate().execute({"skip_review": False, "hitl_config": {}})
    assert result["on_timeout"] == "reject"


def test_h0_timeout_outcome_honours_config() -> None:
    """An operator can restore fail-open explicitly."""
    result = H0HumanReviewGate().execute(
        {"skip_review": False, "hitl_config": {"on_timeout": "approve"}}
    )
    assert result["on_timeout"] == "approve"


def test_h0_explicit_gate_context_timeout_wins() -> None:
    """The pre-existing ``hitl_timeout`` override still takes precedence."""
    result = H0HumanReviewGate().execute(
        {"skip_review": False, "hitl_timeout": 90, "hitl_config": {"timeout_s": 3600}}
    )
    assert result["timeout_s"] == 90


# -- cross-process delivery through .hitl_state.json -------------------------


def test_wait_for_hitl_honours_delivered_approve(tmp_path: Path) -> None:
    """Given a decision file written by another process, the wait approves."""
    progress = PipelineProgress(project_id="p1")
    threading.Timer(0.2, lambda: _write_decision(tmp_path, "approve")).start()
    start = time.monotonic()
    assert progress.wait_for_hitl(project_dir=str(tmp_path), timeout=5.0) is True
    assert time.monotonic() - start < 2.0, "returned by timeout, not by delivery"


def test_wait_for_hitl_honours_delivered_reject(tmp_path: Path) -> None:
    """Given a decision file saying reject, the wait rejects."""
    progress = PipelineProgress(project_id="p2")
    threading.Timer(0.2, lambda: _write_decision(tmp_path, "reject")).start()
    start = time.monotonic()
    assert progress.wait_for_hitl(project_dir=str(tmp_path), timeout=5.0) is False
    assert time.monotonic() - start < 2.0, "returned by timeout, not by delivery"


def test_wait_for_hitl_consumes_the_decision_file(tmp_path: Path) -> None:
    """The decision file is single-use so it cannot re-decide a later pause."""
    progress = PipelineProgress(project_id="p3")
    _write_decision(tmp_path, "approve")
    assert progress.wait_for_hitl(project_dir=str(tmp_path), timeout=5.0) is True
    assert not (tmp_path / ".hitl_state.json").exists()


def test_wait_for_hitl_in_process_decision_wins(tmp_path: Path) -> None:
    """The in-memory path (MCP review_decision) must keep working unchanged."""
    progress = PipelineProgress(project_id="p4")
    progress.on_gate_awaiting_hitl("H0")
    progress.approve_hitl()
    assert progress.wait_for_hitl(project_dir=str(tmp_path), timeout=5.0) is True


def test_a_delivered_decision_is_not_wiped_by_registering_the_pause(tmp_path: Path) -> None:
    """A decision may land before the engine registers the pause.

    Regression guard: resetting the tracker when a gate *begins* awaiting review
    turned such a decision into a timeout, which under the old fail-open default
    silently auto-approved a human rejection.  It shipped as a broken
    ``test_h0_reject_in_quality_retry_path_halts``.
    """
    progress = PipelineProgress(project_id="p5a")
    progress.reject_hitl()
    progress.on_gate_awaiting_hitl("H0")
    start = time.monotonic()
    assert progress.wait_for_hitl(project_dir=str(tmp_path), timeout=5.0) is False
    assert time.monotonic() - start < 2.0, "pre-delivered decision was discarded"


def test_a_decision_stays_sticky_across_quality_retries(tmp_path: Path) -> None:
    """A decision must survive a re-wait, not be consumed by the first one.

    The quality-retry loop re-executes a gate that returned ``awaiting_hitl`` and
    waits again.  If the first wait consumed the answer, the re-wait would block
    for the full budget and then fall through to the timeout policy — which
    turned a human *rejection* into an approval and let the pipeline publish.
    This is the invariant ``test_h0_reject_in_quality_retry_path_halts`` relies
    on at the engine level.
    """
    progress = PipelineProgress(project_id="p5")
    progress.on_gate_awaiting_hitl("H0")
    progress.reject_hitl()

    assert progress.wait_for_hitl(project_dir=str(tmp_path), timeout=5.0) is False

    progress.on_gate_awaiting_hitl("H0")
    start = time.monotonic()
    assert progress.wait_for_hitl(project_dir=str(tmp_path), timeout=5.0) is False
    assert time.monotonic() - start < 2.0, "re-wait blocked instead of reusing the decision"


# -- the timeout outcome is honoured by the wait -----------------------------


def test_wait_for_hitl_timeout_rejects_when_configured() -> None:
    """Given no decision and on_timeout=reject, the wait rejects."""
    progress = PipelineProgress(project_id="p6")
    assert progress.wait_for_hitl(timeout=0.3, on_timeout="reject") is False


def test_wait_for_hitl_timeout_approves_when_configured() -> None:
    """The legacy fail-open behaviour stays available on request."""
    progress = PipelineProgress(project_id="p7")
    assert progress.wait_for_hitl(timeout=0.3, on_timeout="approve") is True


# -- the engine actually wires the project dir through -----------------------


def test_engine_delivers_an_external_approval_to_a_paused_gate(tmp_path: Path) -> None:
    """The engine must pass a real project_dir, or the file branch is dead code.

    The elapsed assertion is load-bearing: with the old ``project_dir=""`` the
    engine ignored the delivered file, waited out the stub's 10s budget and
    auto-approved, so a bare "did it pass?" check would go green on exactly the
    silent-trap behaviour this issue is about.
    """
    engine = GateEngine(gates=[_AwaitingGate()])
    progress = PipelineProgress(project_id="p8")
    context: dict[str, Any] = {"project_dir": str(tmp_path), "topic": "t", "brand": "b"}
    threading.Timer(0.3, lambda: _write_decision(tmp_path, "approve")).start()

    start = time.monotonic()
    ok, results = engine.run(context, progress=progress)
    elapsed = time.monotonic() - start

    assert ok is True
    assert results[0]["_hitl_approved"] is True
    assert elapsed < 5.0, "gate auto-approved on timeout instead of consuming the decision"


def test_engine_delivers_an_external_rejection_to_a_paused_gate(tmp_path: Path) -> None:
    """A delivered rejection must halt the pipeline, exactly like an in-process one."""
    engine = GateEngine(gates=[_AwaitingGate()])
    progress = PipelineProgress(project_id="p9")
    context: dict[str, Any] = {"project_dir": str(tmp_path), "topic": "t", "brand": "b"}
    threading.Timer(0.3, lambda: _write_decision(tmp_path, "reject")).start()

    start = time.monotonic()
    ok, results = engine.run(context, progress=progress)
    elapsed = time.monotonic() - start

    assert ok is False
    assert results[0]["_hitl_approved"] is False
    assert elapsed < 5.0, "gate timed out instead of consuming the decision"


def test_engine_applies_on_timeout_from_the_gate_result(tmp_path: Path) -> None:
    """With no decision delivered, the gate's on_timeout decides the outcome."""
    engine = GateEngine(gates=[_AwaitingGate(on_timeout="reject")])
    progress = PipelineProgress(project_id="p10")
    context: dict[str, Any] = {"project_dir": str(tmp_path), "topic": "t", "brand": "b"}

    ok, results = engine.run(context, progress=progress)

    assert ok is False
    assert results[0]["_hitl_approved"] is False


# -- stale decision hygiene -------------------------------------------------


def test_stale_decision_file_is_cleared_at_run_start(tmp_path: Path) -> None:
    """A leftover decision must not auto-approve the next run."""
    from automedia.pipelines.runner import clear_stale_hitl_state

    _write_decision(tmp_path, "approve")
    clear_stale_hitl_state(str(tmp_path))
    assert not (tmp_path / ".hitl_state.json").exists()


def test_clear_stale_hitl_state_is_safe_when_absent(tmp_path: Path) -> None:
    """Clearing a directory with no decision file is a no-op, not an error."""
    from automedia.pipelines.runner import clear_stale_hitl_state

    clear_stale_hitl_state(str(tmp_path))


def test_clear_stale_hitl_state_rejects_a_non_directory(tmp_path: Path) -> None:
    """A bad project dir must not crash the run before it starts."""
    from automedia.pipelines.runner import clear_stale_hitl_state

    target = tmp_path / "not-a-dir"
    target.write_text("x", encoding="utf-8")
    clear_stale_hitl_state(str(target))
    assert target.exists()
