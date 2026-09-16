"""``automedia archive`` — archive a project (Red Line 8 enforcement)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import typer

from automedia.cli.output import output_error, output_text


def build_l2_archive_context(
    project_info: dict[str, Any],
    project_dir: Path,
    archive_dir: Path,
    *,
    force: bool,
) -> dict[str, Any]:
    """Derive the L2 archive-validation context from real project data.

    ``platform`` is resolved from the brand profile keyed by the project's
    ``brand`` field — ``00_project_info.json`` stores ``brand``, not
    ``platforms`` — and falls back to the literal ``"unspecified"`` when the
    brand declares no platforms.
    """
    from automedia.manifests.brand_profile_schema import load_brand_profiles

    brand = str(project_info.get("brand", ""))
    profile = load_brand_profiles().get(brand)
    platforms = ", ".join(profile.platforms) if profile and profile.platforms else "unspecified"

    return {
        "archive_status": str(project_info.get("status", "")),
        "force": force,
        "archive_path": str(archive_dir),
        "output_dir": str(project_dir),
        "archive_metadata": {
            "title": str(project_info.get("topic", "")),
            "platform": platforms,
            "created_at": str(project_info.get("created_at", "")),
        },
    }


def run_l2_archive_gate(context: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """Execute L2 on *context* and return ``(passed, failure_mode, result)``."""
    from automedia.gates.archive_validation import L2ArchiveValidation

    gate = L2ArchiveValidation()
    result = gate.execute(context)
    return bool(result.get("passed", False)), gate.failure_mode, result


def archive_cmd(
    project_id: str = typer.Argument(..., metavar="project_id", help="Project ID to archive."),
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

    project_dir = cast(Path, project_dir)
    if project_dir.name.endswith("_archived"):
        output_error(
            f"Refused: project directory {project_dir.name!r} is already archived. "
            f"Double-archive would create nested _archived_archived. "
            f"Use 'archive' on the original (non-_archived) directory instead."
        )

    archive_dir = project_dir.parent / f"{project_dir.name}_archived"
    if archive_dir.exists():
        output_error(f"Archive target already exists: {archive_dir}")

    # L2 archive validation: runs after the Red Line 8 eligibility check and
    # before the rename. ``force=True`` short-circuits so L2 is never invoked.
    if not force:
        l2_passed, l2_failure_mode, _l2_result = run_l2_archive_gate(
            build_l2_archive_context(project_info, project_dir, archive_dir, force=force)
        )
        if not l2_passed and l2_failure_mode == "stop":
            output_error(
                "Refused: L2 archive validation failed. "
                "Resolve the archive integrity issues or use --force (Red Line 8)."
            )

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
