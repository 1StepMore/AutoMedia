"""Gate engine — sequential pipeline executor with hook dispatch.

Runs an ordered list of :class:`BaseGate` instances, dispatches lifecycle
hooks, and respects each gate's ``failure_mode`` to decide whether to
STOP the pipeline or continue on failure.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from structlog import get_logger

from automedia.gates._context import GateContext
from automedia.gates.base import BaseGate
from automedia.hooks.protocol import GateHook

log = get_logger(__name__)

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

    status: Literal["success", "failed", "partial", "rl9_violation"] = "success"
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


# ---------------------------------------------------------------------------
# Pipeline progress tracking (P0-04)
# ---------------------------------------------------------------------------


@dataclass
class GateProgressEvent:
    """Event emitted when a gate starts, passes, fails, or is skipped."""

    gate_name: str
    status: Literal["running", "passed", "failed", "skipped"]
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
        self.project_id = project_id
        self.current_gate: str | None = None
        self._events: list[GateProgressEvent] = []
        self.error: str | None = None
        self._lock = threading.Lock()

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

    def on_gate_end(self, gate_name: str, passed: bool, duration: float) -> None:
        """Record that *gate_name* completed with *passed*/duration."""
        with self._lock:
            self.current_gate = None
            status: Literal["passed", "failed"] = "passed" if passed else "failed"
            self._events.append(
                GateProgressEvent(
                    gate_name=gate_name,
                    status=status,
                    duration_s=duration,
                    timestamp=datetime.now().isoformat(),
                )
            )

    # -- Accessors (called by MCP get_pipeline_progress) --------------------

    def get_progress(self) -> dict[str, Any]:
        """Return current progress as a JSON-compatible dict."""
        with self._lock:
            return {
                "project_id": self.project_id,
                "current_gate": self.current_gate,
                "events": [e.__dict__ for e in self._events],
                "error": self.error,
            }

    def get_current_gate(self) -> str | None:
        """Return name of the currently-running gate, or *None*."""
        with self._lock:
            return self.current_gate


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
    """

    def __init__(
        self,
        gates: list[BaseGate],
        hooks: list[GateHook] | None = None,
    ) -> None:
        self._gates = list(gates)
        self._hooks: list[GateHook] = list(hooks) if hooks else []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _dispatch_before(self, gate_name: str, context: GateContext | dict[str, Any]) -> None:
        log.debug("hooks.dispatch_before", gate_name=gate_name, hook_count=len(self._hooks))
        ctx = context.to_dict() if isinstance(context, GateContext) else context
        for hook in self._hooks:
            hook.before_gate(gate_name, ctx)

    def _dispatch_after(
        self, gate_name: str, context: GateContext | dict[str, Any], result: dict[str, Any]
    ) -> None:
        log.debug("hooks.dispatch_after", gate_name=gate_name, hook_count=len(self._hooks))
        ctx = context.to_dict() if isinstance(context, GateContext) else context
        for hook in self._hooks:
            hook.after_gate(gate_name, ctx, result)

    def _dispatch_failed(
        self, gate_name: str, context: GateContext | dict[str, Any], error: Exception
    ) -> None:
        log.debug(
            "hooks.dispatch_failed",
            gate_name=gate_name, error=str(error),
            hook_count=len(self._hooks),
        )
        ctx = context.to_dict() if isinstance(context, GateContext) else context
        for hook in self._hooks:
            hook.on_gate_failed(gate_name, ctx, error)

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
            log.info(
                "gate.start",
                gate_name=gate_name, gate_idx=gate_idx,
                total_gates=total_gates,
                failure_mode=gate.failure_mode,
            )

            if progress:
                progress.on_gate_start(gate_name)

            self._dispatch_before(gate_name, gate_context)
            start = time.monotonic()

            try:
                result = gate.execute(gate_context)
                results.append(result)
                duration = time.monotonic() - start

                passed = result.get("passed", True)
                if progress:
                    progress.on_gate_end(gate_name, passed, duration)

                if passed:
                    log.info("gate.passed", gate_name=gate_name, duration_s=duration)
                    self._dispatch_after(gate_name, gate_context, result)
                else:
                    all_ok = False
                    log.warning(
                        "gate.failed",
                        gate_name=gate_name, duration_s=duration,
                        failure_mode=gate.failure_mode,
                    )
                    if gate.failure_mode == "stop":
                        if early_stop:
                            return False, results
                        return results
                    # failure_mode == "rewrite" → continue
                    self._dispatch_after(gate_name, gate_context, result)

            except Exception as exc:
                duration = time.monotonic() - start
                all_ok = False
                log.error(
                    "gate.error",
                    gate_name=gate_name, duration_s=duration,
                    error=str(exc), failure_mode=gate.failure_mode,
                )
                error_result: dict[str, Any] = {
                    "passed": False,
                    "gate": gate_name,
                    "error": str(exc),
                }
                results.append(error_result)
                if progress:
                    progress.on_gate_end(gate_name, False, duration)
                self._dispatch_failed(gate_name, gate_context, exc)
                if gate.failure_mode == "stop":
                    if early_stop:
                        return False, results
                    return results

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
        return self._run(gate_context, early_stop=True, progress=progress)  # type: return-value

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
        return self._run(gate_context, early_stop=False, progress=progress)  # type: return-value


# Keep a backward-compatible alias so existing ``from ... import Pipeline``
# in __init__.py continues to work.
Pipeline = GateEngine
