"""Gate data types — TypedDicts and dataclasses used by the gate engine.

Extracted from ``gate_engine.py`` for cleaner separation.  All original
definitions are preserved verbatim — no behavior changes.

``gate_engine.py`` re-exports these so ``from automedia.pipelines.gate_engine
import ...`` continues to work.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict

# ---------------------------------------------------------------------------
# HITL (Human-in-the-Loop) coordination state.
# ---------------------------------------------------------------------------

_hitl_lock = threading.Lock()
"""Lock protecting ``_hitl_waiters``."""

_hitl_waiters: dict[str, Any] = {}
"""Maps ``gate_name`` to a dict with ``event``, ``status``, and ``detail``.

Structure::

    {
        gate_name: {
            "event": threading.Event(),
            "status": "awaiting" | "approved" | "rejected",
            "detail": str,
        }
    }
"""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class GateErrorResult(TypedDict, total=False):
    """Structured error result produced when a gate raises an exception.

    ``passed``, ``gate``, ``error``, and ``duration_s`` are always
    present.  ``retry_count`` and ``retry_delay_s`` are set when
    transient exceptions exhaust their retry budget.
    """

    passed: bool
    gate: str
    error: str
    duration_s: float
    retry_count: int
    retry_delay_s: float


class ProgressData(TypedDict, total=False):
    """Snapshot of pipeline progress returned by ``get_progress()``."""

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


@dataclass
class GateProgressEvent:
    """Event emitted when a gate starts, passes, fails, or is skipped."""

    gate_name: str
    status: Literal["running", "passed", "failed", "skipped", "awaiting_hitl"]
    duration_s: float = 0.0
    detail: str = ""
    timestamp: str = ""
    # Retry metadata (see GateEngine retry logic)
    attempt_number: int = 1
    retry_level: str | None = None  # "quality" | "tenacity" | "manual" | None
    strategy_delta: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Pipeline progress tracking (P0-04)
# ---------------------------------------------------------------------------


class PipelineProgress:
    """Thread-safe observable progress tracker for pipeline execution.

    Agents can poll progress via ``get_progress()`` while the pipeline
    runs in a background thread.  All mutations are protected by a
    ``threading.Lock`` so the MCP query thread never sees torn state.
    """

    def __init__(self, project_id: str = "") -> None:
        """Initialize the progress tracker.

        Args:
            project_id: Optional project identifier for tracking context.
        """
        self.project_id = project_id
        self.current_gate: str | None = None
        self._events: list[GateProgressEvent] = []
        self.error: str | None = None
        self.total_gates: int = 0
        self._gates_done: list[str] = []
        self._gate_names: list[str] = []
        self._lock = threading.Lock()
        self._started_at: float | None = None
        self._finished: bool = False
        self._hitl_event = threading.Event()
        self._hitl_decision: bool | None = None
        self._cancelled: bool = False
        self._paused_event: threading.Event = threading.Event()
        self._paused_event.set()  # Not paused by default
        self._retry_gate: str | None = None
        self._skip_gate: str | None = None

    def set_gate_names(self, gate_names: list[str]) -> None:
        """Store the ordered list of all gate names for the pipeline.

        Also sets ``total_gates`` to the length of *gate_names*.

        Args:
            gate_names: Ordered list of gate names in execution order.
        """
        self._gate_names = list(gate_names)
        self.total_gates = len(gate_names)

    # -- Mutators (called by GateEngine.run) --------------------------------

    def on_gate_start(
        self,
        gate_name: str,
        attempt_number: int = 1,
        retry_level: str | None = None,
        strategy_delta: dict[str, Any] | None = None,
    ) -> None:
        """Record that *gate_name* has started execution."""
        with self._lock:
            if self._started_at is None:
                self._started_at = time.time()
            self.current_gate = gate_name
            self._events.append(
                GateProgressEvent(
                    gate_name=gate_name,
                    status="running",
                    timestamp=datetime.now().isoformat(),
                    attempt_number=attempt_number,
                    retry_level=retry_level,
                    strategy_delta=strategy_delta,
                )
            )

    def on_gate_end(
        self,
        gate_name: str,
        passed: bool,
        duration: float,
        detail: str = "",
        attempt_number: int = 1,
        retry_level: str | None = None,
        strategy_delta: dict[str, Any] | None = None,
    ) -> None:
        """Record that *gate_name* completed with *passed*/duration."""
        with self._lock:
            self.current_gate = None
            status: Literal["passed", "failed"] = "passed" if passed else "failed"
            self._events.append(
                GateProgressEvent(
                    gate_name=gate_name,
                    status=status,
                    duration_s=duration,
                    detail=detail,
                    timestamp=datetime.now().isoformat(),
                    attempt_number=attempt_number,
                    retry_level=retry_level,
                    strategy_delta=strategy_delta,
                )
            )
            # Track unique completed gates (retry may call on_gate_end
            # multiple times for the same gate — only record once).
            if gate_name not in self._gates_done:
                self._gates_done.append(gate_name)

    # -- Accessors (called by MCP get_pipeline_progress) --------------------

    def get_progress(self) -> ProgressData:
        """Return current progress as a JSON-compatible dict."""
        with self._lock:
            gates_remaining = self._gate_names[len(self._gates_done) :]
            elapsed = (time.time() - self._started_at) if self._started_at else 0.0
            return {
                "project_id": self.project_id,
                "current_gate": self.current_gate,
                "gates_done": list(self._gates_done),
                "gates_remaining": gates_remaining,
                "total_gates": self.total_gates,
                "events": [e.__dict__ for e in self._events],
                "error": self.error,
                "is_running": self._started_at is not None and not self._finished,
                "is_failed": self.error is not None,
                "elapsed_s": round(elapsed, 3),
            }

    def get_current_gate(self) -> str | None:
        """Return name of the currently-running gate, or *None*."""
        with self._lock:
            return self.current_gate

    def mark_finished(self) -> None:
        """Mark the pipeline as finished (no longer running).

        Sets ``_finished`` to ``True`` and clears ``current_gate``.
        Safe to call multiple times.
        """
        with self._lock:
            self._finished = True
            self.current_gate = None

    # -- HITL (Human-in-the-Loop) lifecycle --------------------------------

    def on_gate_awaiting_hitl(
        self,
        gate_name: str,
        detail: str = "",
        attempt_number: int = 1,
        retry_level: str | None = None,
        strategy_delta: dict[str, Any] | None = None,
    ) -> None:
        """Record that *gate_name* is awaiting human review.

        Sets ``current_gate`` to *gate_name* and adds an event with
        status ``"awaiting_hitl"``.  Registers this instance in
        ``_hitl_waiters`` so external callers can signal it.
        """
        with self._lock:
            self.current_gate = gate_name
            self._events.append(
                GateProgressEvent(
                    gate_name=gate_name,
                    status="awaiting_hitl",
                    detail=detail,
                    timestamp=datetime.now().isoformat(),
                    attempt_number=attempt_number,
                    retry_level=retry_level,
                    strategy_delta=strategy_delta,
                )
            )
        with _hitl_lock:
            _hitl_waiters[self.project_id] = self

    def approve_hitl(self, project_dir: str = "") -> None:
        """Approve an awaiting HITL gate.

        *In-memory mode* (no *project_dir*): signals the internal event.
        *File mode* (*project_dir* given): writes ``.hitl_state.json``.

        Removes this instance from ``_hitl_waiters``.
        """
        if project_dir:
            state_file = Path(project_dir) / ".hitl_state.json"
            state_file.write_text(json.dumps({"decision": "approve"}), encoding="utf-8")
        else:
            self._hitl_decision = True
            self._hitl_event.set()

        with _hitl_lock:
            _hitl_waiters.pop(self.project_id, None)

    def reject_hitl(self, project_dir: str = "") -> None:
        """Reject an awaiting HITL gate.

        *In-memory mode* (no *project_dir*): signals the internal event.
        *File mode* (*project_dir* given): writes ``.hitl_state.json``.

        Removes this instance from ``_hitl_waiters``.
        """
        if project_dir:
            state_file = Path(project_dir) / ".hitl_state.json"
            state_file.write_text(json.dumps({"decision": "reject"}), encoding="utf-8")
        else:
            self._hitl_decision = False
            self._hitl_event.set()

        with _hitl_lock:
            _hitl_waiters.pop(self.project_id, None)

    def wait_for_hitl(self, project_dir: str = "", timeout: float = 86400.0) -> bool:
        """Block the calling thread until HITL decision or *timeout*.

        *In-memory mode* (no *project_dir*): waits on an internal
        :class:`threading.Event` signalled by ``approve_hitl()`` /
        ``reject_hitl()``.

        *File mode* (*project_dir* given): polls
        ``project_dir/.hitl_state.json`` for a decision.

        On timeout the gate auto-approves (returns ``True``).

        Returns
        -------
        bool
            ``True`` for approve, ``False`` for reject.
        """
        if project_dir:
            state_file = Path(project_dir) / ".hitl_state.json"
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if state_file.is_file():
                    try:
                        data = json.loads(state_file.read_text(encoding="utf-8"))
                        return data.get("decision") == "approve"
                    except (json.JSONDecodeError, OSError):
                        pass
                time.sleep(0.5)
            return True  # Timeout = auto-approve

        triggered = self._hitl_event.wait(timeout=timeout)

        if not triggered:
            return True  # Timeout = auto-approve

        return bool(self._hitl_decision)

    # -- Cancel / Pause / Retry / Skip control ------------------------------

    def cancel(self) -> None:
        """Signal pipeline to stop at next gate boundary."""
        with self._lock:
            self._cancelled = True
            self._paused_event.set()  # Unblock if paused

    def pause(self) -> None:
        """Pause pipeline after current gate completes."""
        with self._lock:
            self._paused_event.clear()

    def resume(self) -> None:
        """Resume a paused pipeline."""
        with self._lock:
            self._paused_event.set()

    def is_cancelled(self) -> bool:
        """Check whether cancellation has been requested."""
        with self._lock:
            return self._cancelled

    def is_paused(self) -> bool:
        """Check whether pipeline is currently paused."""
        with self._lock:
            return not self._paused_event.is_set()

    def wait_if_paused(self) -> bool:
        """Block while paused. Returns False if cancelled during wait."""
        self._paused_event.wait()
        return not self.is_cancelled()

    def mark_retry_gate(self, gate_name: str) -> None:
        """Mark a gate for retry on next cycle."""
        with self._lock:
            self._retry_gate = gate_name

    def mark_skip_gate(self, gate_name: str) -> None:
        """Mark a gate to be skipped on next cycle."""
        with self._lock:
            self._skip_gate = gate_name

    def consume_retry_gate(self) -> str | None:
        """Atomically read and clear the retry-gate flag."""
        with self._lock:
            val = self._retry_gate
            self._retry_gate = None
            return val

    def consume_skip_gate(self) -> str | None:
        """Atomically read and clear the skip-gate flag."""
        with self._lock:
            val = self._skip_gate
            self._skip_gate = None
            return val
