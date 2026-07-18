"""``automedia history`` — query the pipeline history log.

Displays per-gate lifecycle events recorded by ``PipelineHistoryHook``
in a human-readable table (or machine-readable JSON with ``--json``).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import typer

from automedia.cli.commands.projects import _discover_projects
from automedia.cli.output import OutputMode, get_output_mode, output_json
from automedia.hooks.pipeline_history import _read_history


def _format_ts(unix_ts: float) -> str:
    """Format a Unix timestamp as a human-readable string."""
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def history_cmd(
    project_id: str = typer.Argument(
        ...,
        help="Project ID to query history for.",
    ),
    base_dir: str = typer.Option(
        ".",
        "--base-dir",
        "-d",
        help="Base directory to scan for projects.",
    ),
) -> None:
    """Show pipeline execution history for a project.

    Displays a table of Timestamp, Action, and Details columns from the
    per-project history database recorded by PipelineHistoryHook.
    """

    # Discover all projects to find the matching project dir
    try:
        projects = _discover_projects(base_dir)
    except Exception:
        projects = []

    match = [p for p in projects if p.get("project_id") == project_id]

    history_rows: list[dict] = []
    if match:
        project_dir = match[0]["_dir"]
        all_rows = _read_history(project_dir)
        # Filter rows that belong to this project_id (history DB may contain
        # multiple project_ids in shared scenarios)
        history_rows = [r for r in all_rows if r.get("project_id") == project_id]

    # --- JSON output ---
    if get_output_mode() == OutputMode.JSON:
        items = []
        for row in history_rows:
            items.append(
                {
                    "id": row.get("id"),
                    "project_id": row.get("project_id"),
                    "action": row.get("action"),
                    "timestamp": row.get("timestamp"),
                    "timestamp_iso": _format_ts(row["timestamp"]) if row.get("timestamp") else "",
                    "metadata": (
                        json.loads(row["metadata_json"])
                        if row.get("metadata_json")
                        else {}
                    ),
                }
            )
        output_json(
            {
                "status": "ok",
                "project_id": project_id,
                "count": len(items),
                "items": items,
            }
        )
        return

    # --- Text output ---
    if not history_rows:
        typer.echo("No history found")
        return

    # Table header
    typer.echo(f"{'Timestamp':<22} {'Action':<30} {'Details'}")
    typer.echo("-" * 80)

    for row in history_rows:
        ts = _format_ts(row["timestamp"]) if row.get("timestamp") else "?"
        action = row.get("action", "?")
        meta = {}
        if row.get("metadata_json"):
            try:
                meta = json.loads(row["metadata_json"])
            except (json.JSONDecodeError, TypeError):
                meta = {}
        # Build details string from metadata (exclude gate/project_id which
        # are implied by the action and project context)
        detail_parts = []
        for k, v in meta.items():
            if k in ("gate", "project_id"):
                continue
            detail_parts.append(f"{k}={v}")
        details = ", ".join(detail_parts) if detail_parts else ""

        typer.echo(f"{ts:<22} {action:<30} {details}")
