"""``automedia rollback`` — archive a project and revert status to draft."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import cast

import typer

from automedia.cli.output import output_error, output_text
from automedia.hooks.pipeline_history import _open_db
from automedia.pipelines.rollback_types import (
    is_eligible_for_rollback,
    update_project_status,
)


def rollback_cmd(
    project_id: str = typer.Argument(..., help="Project ID to roll back."),
    base_dir: str = typer.Option(
        ".", "--base-dir", "-d", help="Base directory to scan for projects."
    ),
) -> None:
    """Roll back a project: archive it and revert status to draft.

    The project directory is renamed to ``{name}_archived``, its status is
    set to ``\"draft\"``, and a ``ROLLED_BACK`` entry is appended to the
    project's pipeline history database.
    """
    # ------------------------------------------------------------------
    # 1. Locate project
    # ------------------------------------------------------------------
    base = Path(base_dir)
    info_files = list(base.glob("*/00_project_info.json"))
    project_dir: Path | None = None
    project_info: dict[str, object] = {}

    for info_file in info_files:
        try:
            with open(info_file, encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("project_id") == project_id:
                project_dir = info_file.parent
                project_info = data
                break
        except (json.JSONDecodeError, OSError):
            continue

    if project_dir is None:
        output_error(f"Project {project_id!r} not found.")

    project_dir = cast(Path, project_dir)

    # ------------------------------------------------------------------
    # 2. Pre-checks
    # ------------------------------------------------------------------

    # Already archived?
    if project_dir.name.endswith("_archived"):
        output_error(
            f"Refused: project directory {project_dir.name!r} is already archived."
        )

    # Has pipeline history (must have run at least once)?
    if not is_eligible_for_rollback(str(project_dir)):
        output_error(
            f"Project {project_id!r} has no pipeline history "
            "and cannot be rolled back."
        )

    # ------------------------------------------------------------------
    # 3. User confirmation
    # ------------------------------------------------------------------
    status = str(project_info.get("status", ""))
    if not typer.confirm(
        f"Roll back project {project_id!r} (status: {status!r})? Continue?",
        default=False,
    ):
        output_text(
            "Rollback cancelled.",
            data={"status": "cancelled", "project_id": project_id},
        )
        raise typer.Exit()

    # ------------------------------------------------------------------
    # 4. Write ROLLED_BACK to history  (before archiving changes the path)
    # ------------------------------------------------------------------
    try:
        conn = _open_db(str(project_dir))
        try:
            conn.execute(
                "INSERT INTO pipeline_history "
                "(project_id, action, timestamp, metadata_json) "
                "VALUES (?, ?, ?, ?)",
                (
                    project_id,
                    "rolled_back",
                    time.time(),
                    json.dumps({"project_id": project_id}, ensure_ascii=False),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except (OSError, sqlite3.Error) as exc:
        output_error(f"Failed to write rollback history: {exc}")

    # ------------------------------------------------------------------
    # 5. Archive (rename directory)
    # ------------------------------------------------------------------
    archive_dir = project_dir.parent / f"{project_dir.name}_archived"
    if archive_dir.exists():
        output_error(f"Archive target already exists: {archive_dir}")

    try:
        project_dir.rename(archive_dir)
    except OSError as exc:
        output_error(f"Archive failed: {exc}", code=0)
        raise typer.Exit(code=1) from exc

    # ------------------------------------------------------------------
    # 6. Revert status to draft in the (now archived) info file
    # ------------------------------------------------------------------
    if not update_project_status(str(archive_dir), "draft"):
        output_error("Failed to update project status after archiving.", code=0)
        raise typer.Exit(code=1)

    # ------------------------------------------------------------------
    # 7. Done
    # ------------------------------------------------------------------
    output_text(
        f"Rolled back project {project_id} → {archive_dir} (status: draft)",
        data={
            "status": "ok",
            "project_id": project_id,
            "archive_dir": str(archive_dir),
        },
        green=True,
    )
