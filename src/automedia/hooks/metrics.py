"""Metrics hook — records per-gate execution metrics to production_metrics.json."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from typing import Any

from structlog import get_logger

from automedia.hooks.protocol import GateObserver

log = get_logger(__name__)

METRICS_FILENAME = "production_metrics.json"


def _metrics_path(project_dir: str) -> str:
    """Return absolute path to production_metrics.json under *project_dir*."""
    return os.path.join(project_dir, METRICS_FILENAME)


class MetricsHook(GateObserver):
    """Records per-gate execution metrics and writes them to
    ``{project_dir}/production_metrics.json``.

    Each gate invocation is tracked with its start time, duration,
    pass/fail status, and optional error message.  The metrics file is
    updated after every ``after_gate`` or ``on_gate_failed`` call.
    """

    def __init__(self) -> None:
        """Initialize the metrics hook with empty state."""
        self._start_times: dict[str, float] = {}
        self._gates: list[dict[str, Any]] = []
        self._project_dir: str | None = None
        self._project_id: str | None = None

    # ------------------------------------------------------------------
    # GateObserver overrides
    # ------------------------------------------------------------------

    def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
        """Record the start time for *gate_name*."""
        self._start_times[gate_name] = time.monotonic()
        # Capture project metadata from context (first call wins)
        if self._project_dir is None:
            self._project_dir = context.get("project_dir")
        if self._project_id is None:
            self._project_id = context.get("project_id")

    def after_gate(self, gate_name: str, context: dict[str, Any], result: dict[str, Any]) -> None:
        """Compute duration, record gate status, and persist metrics."""
        duration = self._compute_duration(gate_name)
        passed = result.get("passed", True)
        entry: dict[str, Any] = {
            "gate": gate_name,
            "status": "passed" if passed else "failed",
            "duration_s": round(duration, 4),
            "error": result.get("error"),
        }
        self._gates.append(entry)
        self._write_metrics()

    def on_gate_failed(self, gate_name: str, context: dict[str, Any], error: Exception) -> None:
        """Record a gate that raised an exception."""
        duration = self._compute_duration(gate_name)
        entry: dict[str, Any] = {
            "gate": gate_name,
            "status": "error",
            "duration_s": round(duration, 4),
            "error": str(error),
        }
        self._gates.append(entry)
        self._write_metrics()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_duration(self, gate_name: str) -> float:
        """Return elapsed seconds since ``before_gate`` for *gate_name*."""
        start = self._start_times.pop(gate_name, None)
        if start is None:
            return 0.0
        return time.monotonic() - start

    def _build_payload(self) -> dict[str, Any]:
        """Build the JSON-serialisable metrics payload."""
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "project_id": self._project_id or "",
            "gates": list(self._gates),
        }

    def _write_metrics(self) -> None:
        """Persist current metrics to ``production_metrics.json``.

        Write errors are logged and silently skipped — the hook must never
        raise or interfere with pipeline execution.
        """
        project_dir = self._project_dir
        if project_dir is None:
            log.warning("MetricsHook: project_dir not set; skipping write")
            return

        path = _metrics_path(project_dir)
        try:
            payload = self._build_payload()
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
        except OSError:
            log.exception("MetricsHook: failed to write %s", path)
