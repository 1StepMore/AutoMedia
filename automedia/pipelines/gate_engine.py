"""Gate engine — sequential pipeline executor with hook dispatch.

Runs an ordered list of :class:`BaseGate` instances, dispatches lifecycle
hooks, and respects each gate's ``failure_mode`` to decide whether to
STOP the pipeline or continue on failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from automedia.gates.base import BaseGate
from automedia.hooks.protocol import GateHook


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

    def _dispatch_before(self, gate_name: str, context: dict[str, Any]) -> None:
        for hook in self._hooks:
            hook.before_gate(gate_name, context)

    def _dispatch_after(
        self, gate_name: str, context: dict[str, Any], result: dict[str, Any]
    ) -> None:
        for hook in self._hooks:
            hook.after_gate(gate_name, context, result)

    def _dispatch_failed(
        self, gate_name: str, context: dict[str, Any], error: Exception
    ) -> None:
        for hook in self._hooks:
            hook.on_gate_failed(gate_name, context, error)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, gate_context: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
        """Execute all gates sequentially.

        Returns ``(success, results)`` where *success* is ``True`` when
        every gate passed (or no ``failure_mode="stop"`` gate failed), and
        *results* is the list of per-gate result dicts.
        """
        results: list[dict[str, Any]] = []
        all_ok = True

        for gate in self._gates:
            gate_name = gate.gate_name
            gate_context["_gate_name"] = gate_name

            self._dispatch_before(gate_name, gate_context)

            try:
                result = gate.execute(gate_context)
                results.append(result)

                passed = result.get("passed", True)
                if passed:
                    self._dispatch_after(gate_name, gate_context, result)
                else:
                    all_ok = False
                    if gate.failure_mode == "stop":
                        return False, results
                    # failure_mode == "rewrite" → continue
                    self._dispatch_after(gate_name, gate_context, result)

            except Exception as exc:
                all_ok = False
                error_result: dict[str, Any] = {
                    "passed": False,
                    "gate": gate_name,
                    "error": str(exc),
                }
                results.append(error_result)
                self._dispatch_failed(gate_name, gate_context, exc)
                if gate.failure_mode == "stop":
                    return False, results

        return all_ok, results

    def run_with_results(
        self, gate_context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Execute all gates and return per-gate result dicts.

        Unlike :meth:`run`, this always returns the full result list
        regardless of early-stop.
        """
        results: list[dict[str, Any]] = []

        for gate in self._gates:
            gate_name = gate.gate_name
            gate_context["_gate_name"] = gate_name

            self._dispatch_before(gate_name, gate_context)

            try:
                result = gate.execute(gate_context)
                results.append(result)

                passed = result.get("passed", True)
                if passed:
                    self._dispatch_after(gate_name, gate_context, result)
                else:
                    if gate.failure_mode == "stop":
                        return results
                    # failure_mode == "rewrite" → continue
                    self._dispatch_after(gate_name, gate_context, result)

            except Exception as exc:
                error_result: dict[str, Any] = {
                    "passed": False,
                    "gate": gate_name,
                    "error": str(exc),
                }
                results.append(error_result)
                self._dispatch_failed(gate_name, gate_context, exc)
                if gate.failure_mode == "stop":
                    return results

        return results


# Keep a backward-compatible alias so existing ``from ... import Pipeline``
# in __init__.py continues to work.
Pipeline = GateEngine
