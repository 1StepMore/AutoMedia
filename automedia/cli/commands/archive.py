"""``automedia archive`` — archive a project (Red Line 8 enforcement)."""

from __future__ import annotations

import json
from pathlib import Path

import typer


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
        typer.secho(f"Project {project_id!r} not found.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Red Line 8: status must be published unless --force
    status = str(project_info.get("status", ""))
    if status != "published" and not force:
        typer.secho(
            f"Refused: project status is '{status}', not 'published'. "
            f"Use --force to override (Red Line 8).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    # Perform archive — rename directory with _archived suffix
    archive_dir = project_dir.parent / f"{project_dir.name}_archived"
    if archive_dir.exists():
        typer.secho(f"Archive target already exists: {archive_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    try:
        project_dir.rename(archive_dir)
    except OSError as exc:
        typer.secho(f"Archive failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(
        f"Archived project {project_id} → {archive_dir}",
        fg=typer.colors.GREEN,
    )
