"""Gate engine — sequential pipeline executor with hook dispatch.

Runs an ordered list of :class:`BaseGate` instances, dispatches lifecycle
hooks, and respects each gate's ``failure_mode`` to decide whether to
STOP the pipeline or continue on failure.
"""

from __future__ import annotations

import threading
import time
import traceback
import warnings
from dataclasses import dataclass, field
from typing import Any, Literal

import tenacity
from structlog import get_logger

from automedia.exceptions import GateError
from automedia.gates._context import GateContext
from automedia.gates.base import BaseGate
from automedia.hooks.protocol import GateHook
from automedia.pipelines.gate_types import (
    GateErrorResult,
    GateProgressEvent,
    PipelineProgress,
    ProgressData,
    _hitl_lock,
    _hitl_waiters,
)

log = get_logger(__name__)

# Exception categorization for gate error handling.
_PERMANENT_EXCEPTIONS: tuple[type[Exception], ...] = (KeyError, ValueError, TypeError, GateError)
_TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (ConnectionError, TimeoutError)

# ``_hitl_lock`` and ``_hitl_waiters`` live in ``gate_types.py`` and are
# re-imported above for backward compatibility.

# Engine registry for MCP approve/reject tools (director mode).
# Maps ``project_id`` to ``GateEngine``.  Populated by ``run_full_pipeline``
# in ``runner.py`` and consumed by ``approve_gate`` / ``reject_gate`` /
# ``get_pending_approvals`` in ``tools.py``.
_engine_registry: dict[str, GateEngine] = {}
_engine_registry_lock = threading.Lock()


def get_registered_engine(project_id: str) -> GateEngine | None:
    with _engine_registry_lock:
        return _engine_registry.get(project_id)


def register_engine(project_id: str, engine: GateEngine) -> None:
    with _engine_registry_lock:
        _engine_registry[project_id] = engine


def unregister_engine(project_id: str) -> None:
    with _engine_registry_lock:
        _engine_registry.pop(project_id, None)


def list_registered_engines() -> dict[str, GateEngine]:
    with _engine_registry_lock:
        return dict(_engine_registry)


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
    workflow: str = ""
    """Name of the workflow used for this pipeline run, if any."""


# GateErrorResult, ProgressData, GateProgressEvent, and PipelineProgress
# are defined in gate_types.py and re-exported via the import above.


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
        pause_on_approval: bool = False,
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
            pause_on_approval: When ``True``, gates with ``requires_approval``
                in their context will pause after execution and wait for an
                external call to ``resume()``.  Default: ``False`` (backward
                compatible).
        """
        self._gates = list(gates)
        self._hooks: list[GateHook] = list(hooks) if hooks else []
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._max_quality_retries = max_quality_retries
        self._max_regenerations = max_regenerations
        self._pause_on_approval = pause_on_approval
        # Per-gate approval coordination (thread-safe via lock + Event).
        self._approval_events: dict[str, threading.Event] = {}
        self._approval_results: dict[str, dict[str, Any]] = {}
        self._approval_lock = threading.Lock()

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
            gate_name=gate_name,
            error=str(error),
            hook_count=len(self._hooks),
        )
        ctx = context.to_dict() if isinstance(context, GateContext) else context
        for hook in self._hooks:
            hook.on_gate_failed(gate_name, ctx, error)

    def _gate_requires_approval(self, gate_name: str, gate_context: dict[str, Any]) -> bool:
        """Check whether *gate_name* needs approval before continuing.

        Returns ``True`` only when ``pause_on_approval`` is enabled AND
        the gate context indicates this gate requires approval.
        ``requires_approval`` can be a boolean (applies to all gates) or
        a sequence of gate names (applies only to named gates).
        """
        if not self._pause_on_approval:
            return False
        ra = gate_context.get("requires_approval", False)
        if isinstance(ra, (list, tuple, set)):
            return gate_name in ra
        return bool(ra)

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
                progress.on_gate_end(
                    gate_name,
                    False,
                    0.0,
                    attempt_number=_attempt_counter["n"],
                    retry_level="tenacity",
                )
                progress.on_gate_start(
                    gate_name,
                    attempt_number=_attempt_counter["n"] + 1,
                    retry_level="tenacity",
                )

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
        _local_max_regen = gate_context.get("max_regenerations", self._max_regenerations)
        current = gate_context.get("_regeneration_count", 0)
        if current >= _local_max_regen:
            gate_context["_level2_exhausted"] = True

            # Populate _escalated_gates for H0 human escalation (Task 20)
            escalated: list[dict[str, Any]] = gate_context.setdefault(  # type: ignore[typeddict-unknown-key]  # _escalated_gates is not a key in GateContext TypedDict
                "_escalated_gates", []
            )
            escalated.append(
                {
                    "gate_name": failed_gate_name,
                    "error": failure_result.get("error", "unknown"),
                    "regeneration_count": current,
                }
            )

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

        _gate_loop_idx = 0
        while _gate_loop_idx < len(self._gates):
            gate = self._gates[_gate_loop_idx]
            gate_idx = _gate_loop_idx + 1
            gate_name = gate.gate_name
            gate_context["_gate_name"] = gate_name
            gate_context["_quality_retry_count"] = 0  # Reset per gate for quality retry tracking

            # NEW: Check cancellation
            if progress and progress.is_cancelled():
                log.warning("gate_engine.cancelled", gate_name=gate_name)
                break

            # NEW: Check skip flag
            if progress and progress.consume_skip_gate() == gate_name:
                log.info("gate_engine.skipped", gate_name=gate_name)
                if progress:
                    progress.on_gate_end(gate_name, True, 0.0, detail="skipped via MCP")
                _gate_loop_idx += 1
                continue

            # NEW: Wait if paused (between gates, not during a gate)
            if progress and not progress.wait_if_paused():
                break  # cancelled during pause

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
                gate_name=gate_name,
                gate_idx=gate_idx,
                total_gates=total_gates,
                failure_mode=fm,
            )

            if progress:
                progress.on_gate_start(gate_name)

            self._dispatch_before(gate_name, gate_context)
            start = time.monotonic()

            try:
                result = self._execute_gate_with_retry(
                    gate,
                    gate_context,
                    fm,
                    gate_name,
                    progress,
                )
                duration = time.monotonic() - start
                result["duration_s"] = duration
                results.append(result)

                # HITL: when gate returns awaiting_hitl, pause for human review
                if result.get("status") == "awaiting_hitl" and progress:
                    timeout_s = result.get("timeout_s", 86400)
                    progress.on_gate_awaiting_hitl(gate_name)
                    hitl_ok = progress.wait_for_hitl(
                        project_dir="",
                        timeout=timeout_s,
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
                        gate_name=gate_name,
                        duration_s=duration,
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
                            failure_reason=result.get("error", "quality check failed"),
                        )

                        if progress:
                            progress.on_gate_end(
                                gate_name,
                                False,
                                0.0,
                                attempt_number=_quality_attempt,
                                retry_level="quality",
                            )
                            progress.on_gate_start(
                                gate_name,
                                attempt_number=_quality_attempt + 1,
                                retry_level="quality",
                            )

                        start = time.monotonic()
                        try:
                            result = self._execute_gate_with_retry(
                                gate,
                                gate_context,
                                fm,
                                gate_name,
                                progress,
                            )
                            duration = time.monotonic() - start
                            result["duration_s"] = duration
                            result["quality_retry_count"] = _quality_attempt
                            results[-1] = result

                            if result.get("status") == "awaiting_hitl" and progress:
                                timeout_s = result.get("timeout_s", 86400)
                                progress.on_gate_awaiting_hitl(gate_name)
                                hitl_ok = progress.wait_for_hitl(
                                    project_dir="",
                                    timeout=timeout_s,
                                )
                                result["_hitl_approved"] = hitl_ok

                            passed = result.get("passed", True)
                            if progress:
                                progress.on_gate_end(
                                    gate_name,
                                    passed,
                                    duration,
                                    detail=result.get("error", ""),
                                    attempt_number=_quality_attempt,
                                    retry_level="quality",
                                )

                            if passed:
                                all_ok = True
                                log.info(
                                    "gate.passed",
                                    gate_name=gate_name,
                                    duration_s=duration,
                                )
                                self._dispatch_after(gate_name, gate_context, result)
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
                                    gate_name,
                                    False,
                                    duration,
                                    detail=str(exc),
                                    attempt_number=_quality_attempt,
                                    retry_level="quality",
                                )
                            self._dispatch_failed(gate_name, gate_context, exc)
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
                                    gate_name,
                                    False,
                                    duration,
                                    detail=str(exc),
                                    attempt_number=_quality_attempt,
                                    retry_level="quality",
                                )
                            self._dispatch_failed(gate_name, gate_context, exc)
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
                                    gate_name,
                                    False,
                                    duration,
                                    detail=str(exc),
                                    attempt_number=_quality_attempt,
                                    retry_level="quality",
                                )
                            self._dispatch_failed(gate_name, gate_context, exc)
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
                                    results = results[:cw_result_idx] + regen_results
                                else:
                                    results = results + regen_results
                                all_ok = all(r.get("passed", True) for r in regen_results)
                                # When level 2 is exhausted, check if H0
                                # approved the escalation — if so, the
                                # pipeline is successful despite earlier
                                # gate failures.
                                if gate_context.get("_level2_exhausted"):
                                    h0_result = next(
                                        (r for r in regen_results if r.get("gate") == "H0"),
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
                        self._dispatch_after(gate_name, gate_context, result)

            except _PERMANENT_EXCEPTIONS as exc:
                duration = time.monotonic() - start
                all_ok = False
                tb = traceback.format_exc()
                log.error(
                    "gate.error.permanent",
                    gate_name=gate_name,
                    duration_s=duration,
                    error=str(exc),
                    failure_mode=fm,
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
                    gate_name=gate_name,
                    duration_s=duration,
                    error=str(exc),
                    failure_mode=fm,
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
                    gate_name=gate_name,
                    duration_s=duration,
                    error=str(exc),
                    failure_mode=fm,
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

            # NEW: Check retry flag after gate completes
            if progress:
                retry_target = progress.consume_retry_gate()
                if retry_target == gate_name:
                    log.info("gate_engine.retry", gate_name=gate_name)
                    continue  # _gate_loop_idx unchanged — re-runs same gate

            # NEW: Pause on approval — block until resume() is called
            if self._gate_requires_approval(gate_name, gate_context):
                _approval_evt = threading.Event()
                with self._approval_lock:
                    self._approval_events[gate_name] = _approval_evt
                if progress:
                    progress.on_gate_awaiting_hitl(gate_name, detail="awaiting_approval")
                log.info(
                    "gate_engine.pause_on_approval",
                    gate_name=gate_name,
                    message="Waiting for resume() — gate requires approval",
                )
                _approval_evt.wait()
                with self._approval_lock:
                    _approval = self._approval_results.pop(gate_name, {"approved": True})
                    self._approval_events.pop(gate_name, None)
                result["_approval"] = _approval
                log.info(
                    "gate_engine.resumed",
                    gate_name=gate_name,
                    approved=_approval.get("approved"),
                )

            _gate_loop_idx += 1

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
        try:
            result = self._run(gate_context, early_stop=True, progress=progress)  # type: ignore[return-value]  # _run() return is union; cannot narrow on early_stop param
        finally:
            if progress:
                progress.mark_finished()
        return result  # type: ignore[return-value]  # _run() return is union; cannot narrow on early_stop param

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
        try:
            result = self._run(gate_context, early_stop=False, progress=progress)  # type: ignore[return-value]  # _run() return is union; cannot narrow on early_stop param
        finally:
            if progress:
                progress.mark_finished()
        return result  # type: ignore[return-value]  # _run() return is union; cannot narrow on early_stop param

    # ------------------------------------------------------------------
    # Approval pause / resume (director mode)
    # ------------------------------------------------------------------

    def resume(
        self,
        gate_name: str,
        approved: bool = True,
        modifications: dict[str, Any] | None = None,
    ) -> None:
        """Resume a gate paused for approval.

        Unblocks the execution loop when ``pause_on_approval`` is enabled
        and a gate with ``requires_approval`` in its context is waiting.

        Args:
            gate_name: Name of the gate to resume.
            approved: Whether the gate output is approved.
            modifications: Optional modifications to apply to the gate
                result before continuing.

        Raises:
            KeyError: If no gate named *gate_name* is currently awaiting
                approval.
        """
        with self._approval_lock:
            evt = self._approval_events.get(gate_name)
            if evt is None:
                raise KeyError(
                    f"No gate awaiting approval: {gate_name!r}. "
                    f"Active waiters: {set(self._approval_events.keys())}"
                )
            self._approval_results[gate_name] = {
                "approved": approved,
                "modifications": modifications or {},
            }
            evt.set()
        log.info(
            "gate_engine.resume.called",
            gate_name=gate_name,
            approved=approved,
        )

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        """Return metadata for every gate currently awaiting approval.

        Returns
        -------
        list[dict]
            Each entry has ``gate_name`` and ``status`` keys.
            Empty list when no gates are paused for approval.
        """
        with self._approval_lock:
            return [
                {"gate_name": gate_name, "status": "awaiting_approval"}
                for gate_name in self._approval_events
            ]


# Keep a backward-compatible alias so existing ``from ... import Pipeline``
# in __init__.py continues to work.
Pipeline = GateEngine
