"""``automedia archive`` — archive a project (Red Line 8 enforcement)."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from automedia.cli.output import output_error, output_text


def archive_cmd(
    project_id: str = typer.Argument(..., help="Project ID to archive."),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force archive even if status is not 'published'."
    ),
    base_dir: str = typer.Option(
        ".", "--base-dir", "-d", help="Base directory to scan for projects."
    ),
) -> None:
    """Archive a project.

    Red Line 8: if the project status is not ``published`` the command
    refuses to proceed unless ``--force`` is supplied.
    """
    # Locate project
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

    # Red Line 8: status must be published unless --force
    status = str(project_info.get("status", ""))
    if status != "published" and not force:
        output_error(
            f"Refused: project status is '{status}', not 'published'. "
            f"Use --force to override (Red Line 8)."
        )

    assert project_dir is not None  # output_error() raises SystemExit
    if project_dir.name.endswith("_archived"):
        output_error(
            f"Refused: project directory {project_dir.name!r} is already archived. "
            f"Double-archive would create nested _archived_archived. "
            f"Use 'archive' on the original (non-_archived) directory instead."
        )

    archive_dir = project_dir.parent / f"{project_dir.name}_archived"
    if archive_dir.exists():
        output_error(f"Archive target already exists: {archive_dir}")

    try:
        project_dir.rename(archive_dir)
    except OSError as exc:
        output_error(f"Archive failed: {exc}", code=0)
        raise typer.Exit(code=1) from exc

    output_text(
        f"Archived project {project_id} → {archive_dir}",
        data={"status": "ok", "project_id": project_id, "archive_dir": str(archive_dir)},
        green=True,
    )
