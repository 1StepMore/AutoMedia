"""MCP resource handlers.

Three resource functions registered by :func:`automedia.mcp.server.create_server`.
Refactored from closures to module-level functions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from structlog import get_logger

from automedia.mcp._state import _lock, _pipeline_tracker
from automedia.mcp.tools import _discover_projects, _resolve_projects_dir

log = get_logger(__name__)


def list_projects_resource() -> str:
    """List all projects as a JSON array of summaries.

    Registered as ``automedia://projects``.
    """
    projects_dir = _resolve_projects_dir()
    projects = _discover_projects(projects_dir)
    data = [
        {
            "project_id": p["project_id"],
            "topic": p.get("topic", ""),
            "brand": p.get("brand", ""),
            "status": p.get("status", "unknown"),
            "created_at": p.get("created_at", ""),
        }
        for p in projects
    ]
    return json.dumps(data, indent=2, ensure_ascii=False)


def pipeline_status_resource(project_id: str) -> str:
    """Get pipeline status for a specific project by ID.

    Registered as ``automedia://pipeline/{project_id}``.
    """
    projects_dir = _resolve_projects_dir()
    projects = _discover_projects(projects_dir)
    match = [p for p in projects if p.get("project_id") == project_id]
    if not match:
        return json.dumps(
            {"status": "error", "error": f"Project {project_id!r} not found"},
            ensure_ascii=False,
        )
    proj = match[0]
    proj["project_dir"] = proj.pop("_dir", "")
    return json.dumps(proj, indent=2, ensure_ascii=False)


def topic_pool_resource() -> str:
    """List all topics in the pool as a JSON array.

    Registered as ``automedia://pool``.
    """
    pool_db_path = os.environ.get("AUTOMEDIA_POOL_DB", "")
    if not pool_db_path:
        pool_db_path = str(Path.cwd() / ".automedia" / "data" / "pool.db")
    db_file = Path(pool_db_path)
    if not db_file.exists():
        return json.dumps(
            {"status": "error", "error": "Pool database not found"},
            ensure_ascii=False,
        )
    try:
        from automedia.pool.db import PoolDB

        db = PoolDB(str(db_file))
        topics = db.list_topics()
        db.close()
        data = [
            {
                "id": t.get("id"),
                "title": t.get("title", ""),
                "category": t.get("category", ""),
                "status": t.get("status", ""),
                "score": t.get("score", 0.0),
            }
            for t in topics
        ]
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as exc:
        return json.dumps(
            {"status": "error", "error": str(exc)},
            ensure_ascii=False,
        )


def pipeline_metrics_resource(project_id: str) -> str:
    """Return live pipeline metrics for a running or completed pipeline.

    Registered as ``automedia://pipeline/{project_id}/metrics``.

    Returns gate-by-gate timing, status, and error information from
    the in-memory pipeline tracker.
    """
    with _lock:
        progress = _pipeline_tracker.get(project_id)

    if not progress:
        return json.dumps(
            {
                "status": "error",
                "error": (
                    f"No active pipeline found for project_id {project_id!r}. "
                    f"The pipeline may have already completed or the ID is invalid."
                ),
            },
            ensure_ascii=False,
        )

    progress_data = progress.get_progress()
    events = progress_data.get("events", [])

    gate_metrics: list[dict[str, Any]] = []
    for event in events:
        gate_metrics.append({
            "gate_name": event.get("gate", ""),
            "status": event.get("status", ""),
            "started_at": event.get("started_at"),
            "finished_at": event.get("finished_at"),
            "duration_s": event.get("duration_s"),
            "error": event.get("error"),
        })

    return json.dumps(
        {
            "project_id": project_id,
            "current_gate": progress_data.get("current_gate", ""),
            "gates_done": progress_data.get("gates_done", []),
            "gates_remaining": progress_data.get("gates_remaining", []),
            "total_gates": progress_data.get("total_gates", len(events)),
            "passed": sum(1 for e in events if e.get("status") == "passed"),
            "failed": sum(1 for e in events if e.get("status") == "failed"),
            "gate_metrics": gate_metrics,
            "error": progress_data.get("error"),
        },
        indent=2,
        ensure_ascii=False,
    )


def gate_info_resource(gate_name: str) -> str:
    """Return information about a specific pipeline gate.

    Registered as ``automedia://gate/{gate_name}/info``.

    Returns the gate's description, failure mode, common causes,
    and recommended fixes from the failure modes knowledge base.
    """
    from automedia.gates.failure_modes import FAILURE_MODES

    # Normalize gate name (case-insensitive lookup for convenience)
    lookup = gate_name.upper() if gate_name.upper() in FAILURE_MODES else gate_name
    info = FAILURE_MODES.get(lookup)

    if not info:
        available = sorted(FAILURE_MODES.keys())
        return json.dumps(
            {
                "status": "error",
                "error": f"Gate {gate_name!r} not found.",
                "available_gates": available,
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "gate_name": lookup,
            "description": info.get("description", ""),
            "common_causes": info.get("common_causes", []),
            "fixes": info.get("fixes", []),
            "docstring_ref": info.get("docstring_ref", ""),
        },
        indent=2,
        ensure_ascii=False,
    )
