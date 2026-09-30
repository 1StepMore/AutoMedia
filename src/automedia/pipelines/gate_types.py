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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict

from structlog import get_logger

from automedia.hitl.constants import HITL_DEFAULT_TIMEOUT_S

log = get_logger(__name__)

_HITL_DEFAULT_TIMEOUT_S_FLOAT: float = float(HITL_DEFAULT_TIMEOUT_S)

_HITL_POLL_INTERVAL_S: float = 0.2
"""How often a pause re-checks for a delivered decision file.

Short enough that an operator does not notice the lag after running
``automedia hitl approve``, long enough that a multi-hour wait is not a busy
loop.
"""

# ---------------------------------------------------------------------------
# HITL (Human-in-the-Loop) coordination state.
# ---------------------------------------------------------------------------

_hitl_lock = threading.Lock()
"""Lock protecting ``_hitl_waiters``."""

_hitl_waiters: dict[str, Any] = {}
"""Maps ``project_id`` to the :class:`PipelineProgress` awaiting a decision.

Registered by ``on_gate_awaiting_hitl`` and consumed by the MCP
``review_decision`` tool, which resolves a pause made by a pipeline this
process is running.  Entries are removed on decision, so the registry only ever
holds currently-paused pipelines.  It is process-local: a decision for a
pipeline started by another process must arrive through ``.hitl_state.json``
(see :meth:`PipelineProgress.wait_for_hitl`).
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
    token_usage: dict[str, Any] | None
    estimated_cost_usd: float | None


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
        self.token_usage: dict[str, Any] | None = None
        self.estimated_cost_usd: float | None = None

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
                "token_usage": self.token_usage,
                "estimated_cost_usd": self.estimated_cost_usd,
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

    def _in_memory_decision(self) -> bool | None:
        """Return the in-process decision, or ``None`` while still undecided.

        The decision is deliberately NOT cleared once read.  The quality-retry
        loop re-executes a gate that returned ``awaiting_hitl`` and waits again;
        that re-wait must keep seeing the same answer, otherwise the retry burns
        its whole timeout and then falls through to the timeout policy — which
        silently turned a human rejection into an approval.
        """
        with _hitl_lock:
            return self._hitl_decision

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
            with _hitl_lock:
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
            with _hitl_lock:
                self._hitl_decision = False
                self._hitl_event.set()

        with _hitl_lock:
            _hitl_waiters.pop(self.project_id, None)

    def poll_hitl_decision(self, project_dir: str = "") -> bool | None:
        """Return a delivered HITL decision without blocking, else ``None``.

        Non-blocking counterpart of :meth:`wait_for_hitl`, used when the caller
        does not want to wait (``GateEngine(wait_for_hitl=False)``).  Both
        delivery channels are checked once: the in-memory decision first (how
        the MCP ``review_decision`` tool resolves a same-process pause), then
        the durable ``project_dir/.hitl_state.json`` file (how a separate
        ``automedia hitl approve`` process delivers).  The file is single-use,
        exactly as :meth:`wait_for_hitl` consumes it.

        Returns
        -------
        bool | None
            ``True`` to approve, ``False`` to reject, ``None`` when no
            decision has been delivered yet.
        """
        decided = self._in_memory_decision()
        if decided is not None:
            return decided
        if not project_dir:
            return None
        return self._consume_hitl_state_file(Path(project_dir) / ".hitl_state.json")

    @staticmethod
    def _consume_hitl_state_file(state_file: Path) -> bool | None:
        """Read and delete a delivered decision, or ``None`` if not ready yet.

        The file is single-use on purpose: a decision left on disk would be
        re-read by the next pause and silently approve it.  A partially written
        or absent file yields ``None`` so the caller keeps polling.
        """
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        decision = data.get("decision") if isinstance(data, dict) else None
        if decision not in ("approve", "reject"):
            return None
        try:
            state_file.unlink(missing_ok=True)
        except OSError:
            log.debug("hitl.state_file_unlink_failed", path=str(state_file))
        return decision == "approve"

    def wait_for_hitl(
        self,
        project_dir: str = "",
        timeout: float = _HITL_DEFAULT_TIMEOUT_S_FLOAT,
        on_timeout: str = "approve",
    ) -> bool:
        """Block the calling thread until a HITL decision arrives or *timeout*.

        Both channels are honoured at once: the in-memory event (set by
        ``approve_hitl`` / ``reject_hitl``, which is how the MCP
        ``review_decision`` tool resolves a pause in the same process) and the
        durable ``project_dir/.hitl_state.json`` file (how a *separate*
        ``automedia hitl approve`` process delivers a decision).  Whichever
        arrives first wins; a decision already recorded is returned immediately.

        Parameters
        ----------
        project_dir:
            When given, also poll ``.hitl_state.json`` in this directory.
        timeout:
            Seconds to wait before applying *on_timeout*.
        on_timeout:
            ``"approve"`` fails open, ``"reject"`` fails closed.  Anything else
            is treated as ``"reject"`` — an unrecognised policy must never
            silently ship unreviewed content.

        Returns
        -------
        bool
            ``True`` for approve, ``False`` for reject.
        """
        timeout_approves = on_timeout == "approve"
        state_file = Path(project_dir) / ".hitl_state.json" if project_dir else None

        decided = self._in_memory_decision()
        if decided is not None:
            return decided

        deadline = time.monotonic() + timeout

        if state_file is None:
            if self._hitl_event.wait(timeout=max(0.0, deadline - time.monotonic())):
                decided = self._in_memory_decision()
                return timeout_approves if decided is None else decided
            return timeout_approves

        while True:
            decided = self._in_memory_decision()
            if decided is not None:
                return decided
            delivered = self._consume_hitl_state_file(state_file)
            if delivered is not None:
                return delivered
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return timeout_approves
            if self._hitl_event.wait(timeout=min(_HITL_POLL_INTERVAL_S, remaining)):
                decided = self._in_memory_decision()
                if decided is not None:
                    return decided

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


def consume_hitl_decision_file(project_dir: str) -> bool | None:
    """Read and consume a delivered ``.hitl_state.json`` decision, else ``None``.

    Module-level equivalent of :meth:`PipelineProgress.poll_hitl_decision` for
    callers that hold no ``PipelineProgress`` (e.g. a non-TTY run that still
    wants to honour a decision already written by another process).  The file is
    single-use, exactly as :meth:`PipelineProgress.wait_for_hitl` consumes it.
    """
    if not project_dir:
        return None
    return PipelineProgress._consume_hitl_state_file(Path(project_dir) / ".hitl_state.json")
