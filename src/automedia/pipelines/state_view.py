"""Read-only per-gate pipeline state aggregation (graph-engineering-rollout Wave 3, Todo 10).

Aggregates the current state of every gate in a pipeline mode from two
existing state sources — ``history.db`` (written by
:class:`~automedia.hooks.pipeline_history.PipelineHistoryHook`) and
``pipeline_md5.json`` (written by
:func:`~automedia.hooks.md5_tracker.record_md5`) — plus the static
``AUTO_GATE_DAG`` for track metadata.

This module is READ-ONLY (Metis G3/G8): it performs NO new state writes.
It is best-effort: no run-boundary segmentation — the latest history row
per gate (highest ``id``) wins.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from automedia.hooks.md5_tracker import get_pipeline_md5
from automedia.hooks.pipeline_history import _read_history
from automedia.pipelines.dag import AUTO_GATE_DAG
from automedia.pipelines.runner import _MODE_MAP

GateStatus = Literal["passed", "failed", "pending"]


@dataclass
class GateState:
    """Per-gate aggregated state for one project.

    Attributes
    ----------
    gate:
        Gate name (e.g. ``"G0"``, ``"V1"``).
    status:
        ``"passed"`` / ``"failed"`` / ``"pending"`` — derived from the
        latest history row for the gate (see module docstring).
    track:
        Static track from ``AUTO_GATE_DAG[gate].track``.
    md5:
        Recorded asset digest from ``pipeline_md5.json`` if the gate
        produced an asset, else ``None``.
    recorded_at:
        ISO timestamp of that md5 record, else ``None``.
    """

    gate: str
    status: GateStatus
    track: str
    md5: str | None = None
    recorded_at: str | None = None


def _read_project_id(project_dir: str) -> str:
    """Return the ``project_id`` from ``00_project_info.json``, or ``""``.

    Mirrors the read pattern in ``runner._find_auto_resume_point``: a
    missing or unparsable info file yields an empty id, which callers
    treat as "no history for this project".
    """
    info_path = Path(project_dir) / "00_project_info.json"
    if not info_path.is_file():
        return ""
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
        return str(info.get("project_id", ""))
    except (OSError, ValueError):
        return ""


def _status_for_gate(gate: str, rows: list[dict[str, object]]) -> GateStatus:
    """Derive the status of *gate* from history rows (ordered by id ASC).

    The LAST relevant row wins (latest-row-wins).  ``completed`` rows are
    classified via their ``passed`` metadata (defaulting to true, matching
    ``PipelineHistoryHook.after_gate``); a ``failed`` action row is always
    a failure.  Rows for other gates are ignored.
    """
    status: GateStatus = "pending"
    prefix = f"{gate}:"
    for row in rows:
        action = str(row.get("action", ""))
        if not action.startswith(prefix):
            continue
        suffix = action[len(prefix) :]
        if suffix == "completed":
            try:
                meta = json.loads(str(row.get("metadata_json") or "{}"))
            except ValueError:
                meta = {}
            status = "passed" if meta.get("passed") is not False else "failed"
        elif suffix == "failed":
            status = "failed"
    return status


def aggregate_pipeline_state(project_dir: str, mode: str = "auto") -> list[GateState]:
    """Aggregate per-gate state for *project_dir* under pipeline *mode*.

    For each gate in ``_MODE_MAP[mode]`` (in that exact order) the latest
    history row determines the status, and ``pipeline_md5.json`` supplies
    the asset ``md5``/``recorded_at`` when the gate produced an asset.

    Read-only and best-effort: a missing info file, history database, or
    md5 file simply yields pending rows (never raises, never writes).
    """
    gate_names = _MODE_MAP.get(mode, [])
    if not gate_names:
        return []

    rows: list[dict[str, object]] = []
    project_id = _read_project_id(project_dir)
    if project_id:
        rows = [
            row
            for row in _read_history(project_dir)
            if row.get("project_id") == project_id
        ]

    gates_md5: dict[str, dict[str, object]] = {}
    md5_data = get_pipeline_md5(project_dir)
    if isinstance(md5_data, dict):
        gates_raw = md5_data.get("gates")
        if isinstance(gates_raw, dict):
            gates_md5 = gates_raw

    result: list[GateState] = []
    for gate in gate_names:
        node = AUTO_GATE_DAG.get(gate)
        track = node.track if node is not None else "qa"
        record = gates_md5.get(gate)
        if isinstance(record, dict):
            md5_value = record.get("md5")
            recorded_at = record.get("recorded_at")
        else:
            md5_value = None
            recorded_at = None
        result.append(
            GateState(
                gate=gate,
                status=_status_for_gate(gate, rows),
                track=track,
                md5=str(md5_value) if md5_value is not None else None,
                recorded_at=str(recorded_at) if recorded_at is not None else None,
            )
        )
    return result
