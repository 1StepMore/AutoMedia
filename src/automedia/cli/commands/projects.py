"""``automedia projects`` — list and inspect media projects."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from automedia.cli.output import OutputMode, get_output_mode, output_error_json, output_json

app = typer.Typer(name="projects", help="List and inspect media projects.")

_PROJECT_GLOB = "*/00_project_info.json"

_ASSET_SUBDIRS = (
    "01_content",
    "02_images",
    "03_video",
    "04_subtitle",
    "05_review",
    "06_publish",
)


def _discover_projects(base_dir: str) -> list[dict[str, str]]:
    """Scan *base_dir* for project info JSON files and return their contents."""
    projects: list[dict[str, str]] = []
    base = Path(base_dir)
    for info_file in sorted(base.glob(_PROJECT_GLOB)):
        try:
            with open(info_file, encoding="utf-8") as fh:
                data = json.load(fh)
            data["_dir"] = str(info_file.parent)
            projects.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return projects


# ---------------------------------------------------------------------------
# projects list
# ---------------------------------------------------------------------------


@app.command("list")
def projects_list(
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by project status."),
    base_dir: str = typer.Option(
        ".", "--base-dir", "-d", help="Base directory to scan for projects."
    ),
) -> None:
    """List projects found under the base directory."""
    is_json = get_output_mode() == OutputMode.JSON
    try:
        projects = _discover_projects(base_dir)
    except Exception as exc:
        if is_json:
            output_error_json(f"Error scanning projects: {exc}")
        else:
            typer.secho(f"Error scanning projects: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if status:
        projects = [p for p in projects if p.get("status", "") == status]

    if is_json:
        # Strip internal _dir key from output
        items = [{k: v for k, v in p.items() if k != "_dir"} for p in projects]
        output_json({"status": "ok", "items": items, "count": len(items)})
        return

    if not projects:
        typer.echo("No projects found.")
        return

    typer.echo(f"{'Project ID':<16} {'Brand':<12} {'Topic'}")
    typer.echo("-" * 60)
    for p in projects:
        typer.echo(
            f"{p.get('project_id', '?'):<16} {p.get('brand', '?'):<12} {p.get('topic', '?')}"
        )


# ---------------------------------------------------------------------------
# projects get
# ---------------------------------------------------------------------------


@app.command("get")
def projects_get(
    project_id: str = typer.Argument(..., help="Project ID to inspect."),
    base_dir: str = typer.Option(
        ".", "--base-dir", "-d", help="Base directory to scan for projects."
    ),
) -> None:
    """Show details for a single project."""
    is_json = get_output_mode() == OutputMode.JSON
    try:
        projects = _discover_projects(base_dir)
    except Exception as exc:
        if is_json:
            output_error_json(f"Error scanning projects: {exc}")
        else:
            typer.secho(f"Error scanning projects: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    match = [p for p in projects if p.get("project_id") == project_id]
    if not match:
        msg = f"Project {project_id!r} not found."
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    proj = match[0]
    if is_json:
        output_json({k: v for k, v in proj.items() if k != "_dir"})
    else:
        typer.echo(json.dumps(proj, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# projects get-assets
# ---------------------------------------------------------------------------


def _collect_assets(project_dir: Path) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []
    for subdir_name in _ASSET_SUBDIRS:
        subdir = project_dir / subdir_name
        if not subdir.is_dir():
            continue
        for fpath in sorted(subdir.rglob("*")):
            if fpath.is_file():
                assets.append(
                    {
                        "path": str(fpath),
                        "name": fpath.name,
                        "subdir": subdir_name,
                        "size": str(fpath.stat().st_size),
                    }
                )
    return assets


@app.command("get-assets")
def projects_get_assets(
    project_id: str = typer.Argument(..., help="Project ID to list assets for."),
    base_dir: str = typer.Option(
        ".", "--base-dir", "-d", help="Base directory to scan for projects."
    ),
) -> None:
    """Return a JSON list of asset files for a project."""
    is_json = get_output_mode() == OutputMode.JSON
    try:
        projects = _discover_projects(base_dir)
    except Exception as exc:
        if is_json:
            output_error_json(f"Error scanning projects: {exc}")
        else:
            typer.secho(f"Error scanning projects: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    match = [p for p in projects if p.get("project_id") == project_id]
    if not match:
        msg = f"Project {project_id!r} not found."
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    proj = match[0]
    project_dir = Path(proj["_dir"])
    assets = _collect_assets(project_dir)
    if is_json:
        output_json({"status": "ok", "items": assets, "count": len(assets)})
    else:
        typer.echo(json.dumps(assets, indent=2, ensure_ascii=False))
