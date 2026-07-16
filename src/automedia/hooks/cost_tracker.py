"""Cost tracker hook — records LLM token usage per gate to cost_log.jsonl.

Uses the thread-local :class:`~automedia.core.llm_client._UsageTracker` to
compute per-gate token consumption deltas.  Each delta is appended to
``cost_log.jsonl`` in the project directory as a JSON line.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from structlog import get_logger

from automedia.core.llm_client import get_usage_delta, get_usage_summary
from automedia.hooks.protocol import GateObserver

log = get_logger(__name__)

COST_LOG_FILENAME = "cost_log.jsonl"


class CostTracker(GateObserver):
    """Tracks LLM token usage across pipeline gates.

    Records per-gate LLM token consumption to ``{project_dir}/cost_log.jsonl``.
    Uses :class:`GateObserver` as base — only overrides the hook methods
    relevant to cost tracking.

    Thread safety: delegates to the module-level ``_UsageTracker`` in
    ``automedia.core.llm_client`` which stores per-thread state via
    :class:`threading.local`.

    Parameters
    ----------
    project_dir:
        Absolute path to the pipeline project directory where
        ``cost_log.jsonl`` will be written.
    """

    def __init__(self, project_dir: str) -> None:
        self._project_dir = project_dir
        self._snapshot: dict[str, Any] = get_usage_summary()

    def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
        """Take a usage snapshot before the gate runs."""
        self._snapshot = get_usage_summary()

    def after_gate(self, gate_name: str, context: dict[str, Any], result: dict[str, Any]) -> None:
        """Compute usage delta and write to JSONL on success."""
        self._flush(gate_name)

    def on_gate_failed(self, gate_name: str, context: dict[str, Any], error: Exception) -> None:
        """Compute usage delta and write to JSONL on failure."""
        self._flush(gate_name, error=str(error))

    def _flush(self, gate_name: str, error: str = "") -> None:
        """Compute token delta since last snapshot and write ``cost_log.jsonl``.

        Skips writing when no new LLM calls were made (delta is empty).
        """
        delta = get_usage_delta(self._snapshot)
        if not delta["calls"]:
            return

        log_file = Path(self._project_dir) / COST_LOG_FILENAME
        log_file.parent.mkdir(parents=True, exist_ok=True)

        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "gate": gate_name,
            "calls": delta["calls"],
            "prompt_tokens": delta["prompt_tokens"],
            "completion_tokens": delta["completion_tokens"],
            "total_tokens": delta["total_tokens"],
        }
        if error:
            entry["error"] = error

        with open(os.fspath(log_file), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
