"""Gate engine — sequential pipeline executor with hook dispatch.

Runs an ordered list of :class:`BaseGate` instances, dispatches lifecycle
hooks, and respects each gate's ``failure_mode`` to decide whether to
STOP the pipeline or continue on failure.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict

import tenacity
from structlog import get_logger

from automedia.exceptions import GateError
from automedia.gates._context import GateContext
from automedia.gates.base import BaseGate
from automedia.hooks.protocol import GateHook

log = get_logger(__name__)

# Exception categorization for gate error handling.
_PERMANENT_EXCEPTIONS: tuple[type[Exception], ...] = (KeyError, ValueError, TypeError, GateError)
_TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (ConnectionError, TimeoutError)

# HITL (Human-in-the-Loop) coordination state.
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
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AssetInfo:
    """Metadata about a produced asset file."""

    type: str
    path: str
    platform: str = ""
    md5: str = ""


@dataclass
class GateLogEntry:
    """Log entry for a single gate execution."""

    gate_name: str
    status: Literal["passed", "failed", "error"]
    duration_s: float
    error: str | None = None


@dataclass
class PipelineResult:
    """Result of a full pipeline execution."""

    status: Literal["success", "failed", "partial"] = "success"
    project_id: str = ""
    project_dir: str = ""
    topic: str = ""
    brand: str = ""
    assets: list[AssetInfo] = field(default_factory=list)
    gates_log: list[GateLogEntry] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    total_duration_s: float = 0.0
    error: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


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


# ---------------------------------------------------------------------------
# Pipeline progress tracking (P0-04)
# ---------------------------------------------------------------------------


@dataclass
class GateProgressEvent:
    """Event emitted when a gate starts, passes, fails, or is skipped."""

    gate_name: str
    status: Literal["running", "passed", "failed", "skipped", "awaiting_hitl"]
    duration_s: float = 0.0
    detail: str = ""
    timestamp: str = ""


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
        self._hitl_event = threading.Event()
        self._hitl_decision: bool | None = None

    def set_gate_names(self, gate_names: list[str]) -> None:
        """Store the ordered list of all gate names for the pipeline.

        Also sets ``total_gates`` to the length of *gate_names*.

        Args:
            gate_names: Ordered list of gate names in execution order.
        """
        self._gate_names = list(gate_names)
        self.total_gates = len(gate_names)

    # -- Mutators (called by GateEngine.run) --------------------------------

    def on_gate_start(self, gate_name: str) -> None:
        """Record that *gate_name* has started execution."""
        with self._lock:
            self.current_gate = gate_name
            self._events.append(
                GateProgressEvent(
                    gate_name=gate_name,
                    status="running",
                    timestamp=datetime.now().isoformat(),
                )
            )

    def on_gate_end(
        self, gate_name: str, passed: bool, duration: float, detail: str = ""
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
            return {
                "project_id": self.project_id,
                "current_gate": self.current_gate,
                "gates_done": list(self._gates_done),
                "gates_remaining": gates_remaining,
                "total_gates": self.total_gates,
                "events": [e.__dict__ for e in self._events],
                "error": self.error,
            }

    def get_current_gate(self) -> str | None:
        """Return name of the currently-running gate, or *None*."""
        with self._lock:
            return self.current_gate

    # -- HITL (Human-in-the-Loop) lifecycle --------------------------------

    def on_gate_awaiting_hitl(self, gate_name: str, detail: str = "") -> None:
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
            state_file.write_text(
                json.dumps({"decision": "approve"}), encoding="utf-8"
            )
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
            state_file.write_text(
                json.dumps({"decision": "reject"}), encoding="utf-8"
            )
        else:
            self._hitl_decision = False
            self._hitl_event.set()

        with _hitl_lock:
            _hitl_waiters.pop(self.project_id, None)

    def wait_for_hitl(
        self, project_dir: str = "", timeout: float = 86400.0
    ) -> bool:
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
                        data = json.loads(
                            state_file.read_text(encoding="utf-8")
                        )
                        return data.get("decision") == "approve"
                    except (json.JSONDecodeError, OSError):
                        pass
                time.sleep(0.5)
            return True  # Timeout = auto-approve

        triggered = self._hitl_event.wait(timeout=timeout)

        if not triggered:
            return True  # Timeout = auto-approve

        return bool(self._hitl_decision)


# ---------------------------------------------------------------------------
# GateEngine
# ---------------------------------------------------------------------------


class GateEngine:
    """Sequential pipeline executor.

    Parameters
    ----------
    gates:
        Ordered list of :class:`BaseGate` instances to execute.
    hooks:
        Optional list of :class:`GateHook` observers notified at each
        lifecycle event.
    max_retries:
        Maximum retry attempts for gates with ``failure_mode="retry"``
        when a transient exception is raised.  Default: 3.
    retry_delay:
        Base delay in seconds for exponential backoff between retries.
        Actual delay = ``retry_delay * 2 ** (attempt - 1)``.  Default: 1.0.
    max_quality_retries:
        Maximum retry attempts for gates that return ``passed=False``
        with ``failure_mode="retry"`` (level 1 quality-feedback retry).
        The same gate is re-executed with the same content up to this
        many times.  Default: 3.  Set to 0 to disable quality retry.
    max_regenerations:
        Maximum content regeneration attempts when level 1 quality retries
        are exhausted for a gate with ``failure_mode="retry"``.  Each
        regeneration re-runs the CW (content writer) gate with failure
        feedback and executes all gates from CW onward.  Default: 2.
        Set to 0 to disable level 2 regeneration.
    """

    def __init__(
        self,
        gates: list[BaseGate],
        hooks: list[GateHook] | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        max_quality_retries: int = 3,
        max_regenerations: int = 2,
    ) -> None:
        """Initialize the gate engine with an ordered list of gates.

        Args:
            gates: Ordered list of BaseGate instances to execute sequentially.
            hooks: Optional lifecycle observers notified at each gate event.
            max_retries: Max retry attempts for gates with failure_mode="retry".
            retry_delay: Base delay in seconds for exponential backoff.
            max_quality_retries: Max quality retry attempts for gates that
                return ``passed=False`` with ``failure_mode='retry'``.
            max_regenerations: Max content regeneration attempts when level 1
                quality retries are exhausted.  Default: 2.
        """
        self._gates = list(gates)
        self._hooks: list[GateHook] = list(hooks) if hooks else []
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._max_quality_retries = max_quality_retries
        self._max_regenerations = max_regenerations

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _dispatch_before(self, gate_name: str, context: GateContext | dict[str, Any]) -> None:
        """Notify all registered hooks that *gate_name* is about to run."""
        log.debug("hooks.dispatch_before", gate_name=gate_name, hook_count=len(self._hooks))
        ctx = context.to_dict() if isinstance(context, GateContext) else context
        for hook in self._hooks:
            hook.before_gate(gate_name, ctx)

    def _dispatch_after(
        self, gate_name: str, context: GateContext | dict[str, Any], result: dict[str, Any]
    ) -> None:
        """Notify all registered hooks that *gate_name* completed successfully."""
        log.debug("hooks.dispatch_after", gate_name=gate_name, hook_count=len(self._hooks))
        ctx = context.to_dict() if isinstance(context, GateContext) else context
        for hook in self._hooks:
            hook.after_gate(gate_name, ctx, result)

    def _dispatch_failed(
        self, gate_name: str, context: GateContext | dict[str, Any], error: Exception
    ) -> None:
        """Notify all registered hooks that *gate_name* raised an exception."""
        log.debug(
            "hooks.dispatch_failed",
            gate_name=gate_name, error=str(error),
            hook_count=len(self._hooks),
        )
        ctx = context.to_dict() if isinstance(context, GateContext) else context
        for hook in self._hooks:
            hook.on_gate_failed(gate_name, ctx, error)

    # ------------------------------------------------------------------
    # Retry helper
    # ------------------------------------------------------------------

    def _execute_gate_with_retry(
        self,
        gate: BaseGate,
        gate_context: GateContext | dict[str, Any],
        fm: str,
        gate_name: str,
        progress: PipelineProgress | None = None,
    ) -> dict[str, Any]:
        """Execute *gate* with tenacity retry for transient exceptions.

        Only applies when ``fm == "retry"``.  Permanent and unknown
        exceptions are never retried — they propagate immediately.
        """
        if fm != "retry":
            return gate.execute(gate_context)

        _attempt_counter = {"n": 0}

        def _before_sleep(retry_state: tenacity.RetryCallState) -> None:
            """Log retry attempt info and update progress before sleeping."""
            _attempt_counter["n"] += 1
            attempt = _attempt_counter["n"]
            delay = float(retry_state.upcoming_sleep or 0)
            exc = retry_state.outcome.exception() if retry_state.outcome else None
            log.info(
                "gate.retry.attempt",
                gate_name=gate_name,
                attempt=attempt,
                max_retries=self._max_retries,
                delay_s=delay,
                error=str(exc) if exc else "",
            )
            if progress:
                progress.on_gate_end(gate_name, False, 0.0)
                progress.on_gate_start(gate_name)

        retryer = tenacity.Retrying(
            stop=tenacity.stop_after_attempt(self._max_retries),
            wait=tenacity.wait_exponential(multiplier=self._retry_delay),
            retry=tenacity.retry_if_exception_type(_TRANSIENT_EXCEPTIONS),
            before_sleep=_before_sleep,
            reraise=True,
        )
        result = retryer(gate.execute, gate_context)

        if _attempt_counter["n"] > 0:
            result.setdefault("retry_count", _attempt_counter["n"])
        return result

    # ------------------------------------------------------------------
    # Level 2: content regeneration (re-run from CW gate)
    # ------------------------------------------------------------------

    def _handle_level2_regeneration(
        self,
        gate_context: GateContext | dict[str, Any],
        failed_gate_name: str,
        failure_result: dict[str, Any],
        progress: PipelineProgress | None = None,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Level 2 recovery — regenerate content by re-running from CW.

        Increments ``gate_context["_regeneration_count"]`` and, when the
        count is below ``_max_regenerations``, re-runs all gates from the
        CW gate forward with ``gate_context["failure_feedback"]`` set so
        the content writer receives information about what failed.

        When the regeneration budget is exhausted, sets
        ``gate_context["_level2_exhausted"] = True`` for Task 20
        escalation.

        Returns
        -------
        tuple[bool, list[dict]]
            ``(all_ok, results_from_cw)`` where *results_from_cw* covers
            gates from CW through the end of the pipeline.
        """
        _local_max_regen = gate_context.get(
            "max_regenerations", self._max_regenerations
        )
        current = gate_context.get("_regeneration_count", 0)
        if current >= _local_max_regen:
            gate_context["_level2_exhausted"] = True

            # Populate _escalated_gates for H0 human escalation (Task 20)
            escalated: list[dict[str, Any]] = gate_context.setdefault(  # type: ignore[typeddict-unknown-key]  # _escalated_gates is not a key in GateContext TypedDict
                "_escalated_gates", []
            )
            escalated.append({
                "gate_name": failed_gate_name,
                "error": failure_result.get("error", "unknown"),
                "regeneration_count": current,
            })

            log.warning(
                "engine.level2.exhausted",
                regenerations_attempted=current,
                max_regenerations=_local_max_regen,
                failed_gate=failed_gate_name,
                escalated_gates=list(escalated),
            )
            return False, []

        new_count = current + 1
        gate_context["_regeneration_count"] = new_count

        feedback: dict[str, Any] = {
            "failed_gate": failed_gate_name,
            "error": failure_result.get("error", "unknown"),
            "regeneration_attempt": new_count,
            "max_regenerations": _local_max_regen,
        }
        gate_context["failure_feedback"] = feedback

        log.info(
            "engine.level2.regeneration",
            failed_gate=failed_gate_name,
            attempt=new_count,
            max_regenerations=_local_max_regen,
            error=feedback["error"],
        )

        # Locate the CW gate in the gate list
        cw_idx = -1
        for i, g in enumerate(self._gates):
            if g.gate_name == "CW":
                cw_idx = i
                break

        if cw_idx == -1:
            log.error(
                "engine.level2.no_cw_gate",
                hint="Cannot regenerate without a CW gate in the list",
            )
            return False, []

        # Clear content fields so CW regenerates fresh content
        gate_context["content"] = ""
        gate_context["draft"] = None

        # Build a sub-engine with gates from CW onward and re-run
        sub_gates = self._gates[cw_idx:]
        sub_engine = GateEngine(
            gates=sub_gates,
            hooks=self._hooks,
            max_retries=self._max_retries,
            retry_delay=self._retry_delay,
            max_quality_retries=self._max_quality_retries,
            max_regenerations=_local_max_regen,
        )
        sub_ok, sub_results = sub_engine._run(
            gate_context,
            early_stop=True,
            progress=progress,
        )

        return sub_ok, sub_results  # type: ignore[return-value]  # sub_engine._run() returns union; cannot narrow on early_stop param

    # ------------------------------------------------------------------
    # Private gate execution loop
    # ------------------------------------------------------------------

    def _run(
        self,
        gate_context: GateContext | dict[str, Any],
        *,
        early_stop: bool = True,
        progress: PipelineProgress | None = None,
    ) -> tuple[bool, list[dict[str, Any]]] | list[dict[str, Any]]:
        """Execute gates sequentially. Returns ``(all_ok, results)`` when
        *early_stop* is ``True``, or just *results* when ``False``."""
        results: list[dict[str, Any]] = []
        all_ok = True
        total_gates = len(self._gates)

        for gate_idx, gate in enumerate(self._gates, 1):
            gate_name = gate.gate_name
            gate_context["_gate_name"] = gate_name
            gate_context["_quality_retry_count"] = 0  # Reset per gate for quality retry tracking

            # Backward compatibility: accept "rewrite" → map to "retry"
            fm = gate.failure_mode
            if fm == "rewrite":
                warnings.warn(
                    f"failure_mode='rewrite' is deprecated for gate '{gate_name}', "
                    f"use failure_mode='retry' instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                fm = "retry"

            log.info(
                "gate.start",
                gate_name=gate_name, gate_idx=gate_idx,
                total_gates=total_gates,
                failure_mode=fm,
            )

            if progress:
                progress.on_gate_start(gate_name)

            self._dispatch_before(gate_name, gate_context)
            start = time.monotonic()

            try:
                result = self._execute_gate_with_retry(
                    gate, gate_context, fm, gate_name, progress,
                )
                duration = time.monotonic() - start
                result["duration_s"] = duration
                results.append(result)

                # HITL: when gate returns awaiting_hitl, pause for human review
                if result.get("status") == "awaiting_hitl" and progress:
                    timeout_s = result.get("timeout_s", 86400)
                    progress.on_gate_awaiting_hitl(gate_name)
                    hitl_ok = progress.wait_for_hitl(
                        project_dir="", timeout=timeout_s,
                    )
                    result["_hitl_approved"] = hitl_ok

                passed = result.get("passed", True)
                if progress:
                    progress.on_gate_end(
                        gate_name, passed, duration, detail=result.get("error", "")
                    )

                if passed:
                    all_ok = True
                    log.info("gate.passed", gate_name=gate_name, duration_s=duration)
                    self._dispatch_after(gate_name, gate_context, result)
                else:
                    all_ok = False
                    log.warning(
                        "gate.failed",
                        gate_name=gate_name, duration_s=duration,
                        failure_mode=fm,
                    )
                    if fm == "stop":
                        if early_stop:
                            return False, results
                        return results

                    # Level 1: quality-feedback retry
                    _local_max_quality = gate_context.get(
                        "max_quality_retries", self._max_quality_retries
                    )
                    _quality_attempt = 0
                    while _quality_attempt < _local_max_quality:
                        _quality_attempt += 1
                        gate_context["_quality_retry_count"] = _quality_attempt
                        _remaining = _local_max_quality - _quality_attempt

                        log.info(
                            "gate.quality_retry",
                            gate_name=gate_name,
                            attempt=_quality_attempt,
                            max_quality_retries=_local_max_quality,
                            remaining=_remaining,
                            failure_reason=result.get(
                                "error", "quality check failed"
                            ),
                        )

                        if progress:
                            progress.on_gate_end(gate_name, False, 0.0)
                            progress.on_gate_start(gate_name)

                        start = time.monotonic()
                        try:
                            result = self._execute_gate_with_retry(
                                gate, gate_context, fm, gate_name, progress,
                            )
                            duration = time.monotonic() - start
                            result["duration_s"] = duration
                            result["quality_retry_count"] = _quality_attempt
                            results[-1] = result

                            if (
                                result.get("status") == "awaiting_hitl"
                                and progress
                            ):
                                timeout_s = result.get("timeout_s", 86400)
                                progress.on_gate_awaiting_hitl(gate_name)
                                hitl_ok = progress.wait_for_hitl(
                                    project_dir="", timeout=timeout_s,
                                )
                                result["_hitl_approved"] = hitl_ok

                            passed = result.get("passed", True)
                            if progress:
                                progress.on_gate_end(
                                    gate_name, passed, duration, detail=result.get("error", "")
                                )

                            if passed:
                                all_ok = True
                                log.info(
                                    "gate.passed",
                                    gate_name=gate_name,
                                    duration_s=duration,
                                )
                                self._dispatch_after(
                                    gate_name, gate_context, result
                                )
                                break

                            log.warning(
                                "gate.quality_retry.attempt_failed",
                                gate_name=gate_name,
                                attempt=_quality_attempt,
                                remaining=_remaining,
                            )

                        except _PERMANENT_EXCEPTIONS as exc:
                            duration = time.monotonic() - start
                            all_ok = False
                            tb = traceback.format_exc()
                            log.error(
                                "gate.quality_retry.error.permanent",
                                gate_name=gate_name,
                                duration_s=duration,
                                error=str(exc),
                                attempt=_quality_attempt,
                                traceback=tb,
                            )
                            error_result = {
                                "passed": False,
                                "gate": gate_name,
                                "error": str(exc),
                                "duration_s": duration,
                                "quality_retry_count": _quality_attempt,
                            }
                            results[-1] = error_result
                            if progress:
                                progress.on_gate_end(
                                    gate_name, False, duration, detail=str(exc)
                                )
                            self._dispatch_failed(
                                gate_name, gate_context, exc
                            )
                            if early_stop:
                                return False, results
                            return results

                        except _TRANSIENT_EXCEPTIONS as exc:
                            duration = time.monotonic() - start
                            all_ok = False
                            tb = traceback.format_exc()
                            log.error(
                                "gate.quality_retry.error.transient",
                                gate_name=gate_name,
                                duration_s=duration,
                                error=str(exc),
                                attempt=_quality_attempt,
                                traceback=tb,
                            )
                            error_result = {
                                "passed": False,
                                "gate": gate_name,
                                "error": str(exc),
                                "duration_s": duration,
                                "retry_count": self._max_retries,
                                "retry_delay_s": self._retry_delay,
                                "quality_retry_count": _quality_attempt,
                            }
                            results[-1] = error_result
                            if progress:
                                progress.on_gate_end(
                                    gate_name, False, duration, detail=str(exc)
                                )
                            self._dispatch_failed(
                                gate_name, gate_context, exc
                            )
                            break

                        except Exception as exc:
                            # Unknown error during quality retry — log, record, and re-raise
                            duration = time.monotonic() - start
                            tb = traceback.format_exc()
                            log.error(
                                "gate.quality_retry.error.unknown",
                                gate_name=gate_name,
                                duration_s=duration,
                                error=str(exc),
                                attempt=_quality_attempt,
                                traceback=tb,
                            )
                            error_result = {
                                "passed": False,
                                "gate": gate_name,
                                "error": str(exc),
                                "duration_s": duration,
                                "quality_retry_count": _quality_attempt,
                            }
                            results[-1] = error_result
                            if progress:
                                progress.on_gate_end(
                                    gate_name, False, duration, detail=str(exc)
                                )
                            self._dispatch_failed(
                                gate_name, gate_context, exc
                            )
                            raise

                    if not passed:
                        all_ok = False
                        level2 = gate_context.get("_level2_handler")
                        if level2:
                            log.info(
                                "gate.quality_retry.level2",
                                gate_name=gate_name,
                                quality_retry_count=_quality_attempt,
                                handler=str(level2),
                            )
                            regen_ok, regen_results = level2(
                                gate_context=gate_context,
                                failed_gate_name=gate_name,
                                failure_result=result,
                                progress=progress,
                            )
                            if regen_results:
                                # Stitch regen results into full result list
                                cw_result_idx = None
                                for i_r, r in enumerate(results):
                                    if r.get("gate") == "CW":
                                        cw_result_idx = i_r
                                        break
                                if cw_result_idx is not None:
                                    results = (
                                        results[:cw_result_idx] + regen_results
                                    )
                                else:
                                    results = results + regen_results
                                all_ok = all(
                                    r.get("passed", True)
                                    for r in regen_results
                                )
                                # When level 2 is exhausted, check if H0
                                # approved the escalation — if so, the
                                # pipeline is successful despite earlier
                                # gate failures.
                                if gate_context.get("_level2_exhausted"):
                                    h0_result = next(
                                        (r for r in regen_results
                                         if r.get("gate") == "H0"),
                                        None,
                                    )
                                    if h0_result and h0_result.get("passed"):
                                        all_ok = True
                                if early_stop:
                                    return all_ok, results
                                return results
                        else:
                            log.info(
                                "gate.quality_retry.exhausted",
                                gate_name=gate_name,
                                quality_retry_count=_quality_attempt,
                                max_quality_retries=_local_max_quality,
                            )
                        self._dispatch_after(
                            gate_name, gate_context, result
                        )

            except _PERMANENT_EXCEPTIONS as exc:
                duration = time.monotonic() - start
                all_ok = False
                tb = traceback.format_exc()
                log.error(
                    "gate.error.permanent",
                    gate_name=gate_name, duration_s=duration,
                    error=str(exc), failure_mode=fm,
                    traceback=tb,
                )
                error_result = {
                    "passed": False,
                    "gate": gate_name,
                    "error": str(exc),
                    "duration_s": duration,
                }
                results.append(error_result)
                if progress:
                    progress.on_gate_end(gate_name, False, duration, detail=str(exc))
                self._dispatch_failed(gate_name, gate_context, exc)
                if early_stop:
                    return False, results
                return results

            except _TRANSIENT_EXCEPTIONS as exc:
                duration = time.monotonic() - start
                all_ok = False
                tb = traceback.format_exc()
                log.error(
                    "gate.error.transient",
                    gate_name=gate_name, duration_s=duration,
                    error=str(exc), failure_mode=fm,
                    traceback=tb,
                )
                error_result = {
                    "passed": False,
                    "gate": gate_name,
                    "error": str(exc),
                    "duration_s": duration,
                }
                if fm == "retry":
                    error_result["retry_count"] = self._max_retries
                    error_result["retry_delay_s"] = self._retry_delay
                results.append(error_result)
                if progress:
                    progress.on_gate_end(gate_name, False, duration, detail=str(exc))
                self._dispatch_failed(gate_name, gate_context, exc)
                if fm == "stop":
                    if early_stop:
                        return False, results
                    return results
                # failure_mode == "retry" → transient error, exhausted retries, continue

            except Exception as exc:
                # Unknown error during gate execution — log, record, stop pipeline
                duration = time.monotonic() - start
                all_ok = False
                tb = traceback.format_exc()
                log.error(
                    "gate.error.unknown",
                    gate_name=gate_name, duration_s=duration,
                    error=str(exc), failure_mode=fm,
                    traceback=tb,
                )
                error_result = {
                    "passed": False,
                    "gate": gate_name,
                    "error": str(exc),
                    "duration_s": duration,
                }
                results.append(error_result)
                if progress:
                    progress.on_gate_end(gate_name, False, duration, detail=str(exc))
                self._dispatch_failed(gate_name, gate_context, exc)
                if fm == "stop":
                    if early_stop:
                        return False, results
                    return results
                raise

        if early_stop:
            return all_ok, results
        return results

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        gate_context: GateContext | dict[str, Any],
        *,
        progress: PipelineProgress | None = None,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Execute all gates sequentially.

        Parameters
        ----------
        gate_context:
            Pipeline context passed from gate to gate.
        progress:
            Optional progress tracker.  When provided, ``GateProgressEvent``
            entries are emitted for each gate (start / end) so that agents
            polling via ``get_pipeline_progress`` can observe execution.

        Returns
        -------
        tuple[bool, list[dict]]
            ``(success, results)`` where *success* is ``True`` when
            every gate passed (or no ``failure_mode="stop"`` gate failed),
            and *results* is the list of per-gate result dicts.
        """
        # Wire level 2 handler when regeneration is enabled
        _local_max_regen = gate_context.get(  # type: ignore[typeddict-unknown-key]  # max_regenerations not a known key in GateContext TypedDict
            "max_regenerations", self._max_regenerations
        )
        if _local_max_regen > 0 and "_level2_handler" not in gate_context:  # type: ignore[operator]  # _local_max_regen is Any from TypedDict.get(); "in" not valid on TypedDict
            gate_context["_level2_handler"] = self._handle_level2_regeneration  # type: ignore[arg-type]  # dynamic key not defined in GateContext TypedDict
        return self._run(gate_context, early_stop=True, progress=progress)  # type: ignore[return-value]  # _run() return is union; cannot narrow on early_stop param

    def run_with_results(
        self,
        gate_context: GateContext | dict[str, Any],
        *,
        progress: PipelineProgress | None = None,
    ) -> list[dict[str, Any]]:
        """Execute all gates and return per-gate result dicts.

        Unlike :meth:`run`, this always returns the full result list
        regardless of early-stop.
        """
        return self._run(gate_context, early_stop=False, progress=progress)  # type: ignore[return-value]  # _run() return is union; cannot narrow on early_stop param


# Keep a backward-compatible alias so existing ``from ... import Pipeline``
# in __init__.py continues to work.
Pipeline = GateEngine
