"""``automedia distribute`` — run D-gates to prepare content for distribution platforms.

For each selected platform, runs the corresponding D-gate to rewrite the
project's base content into the platform-specific format and writes the
result under ``04_distribution/<platform>/`` in the project directory.

Cron integration
----------------
Use ``--cron`` to schedule a distribution for later execution.  The entry
is stored in ``cron/jobs.yaml`` under ``pipeline_schedules`` and is executed
by the ``automedia cron run run-distribute`` command.

Use ``--cron-list`` to view scheduled distributions and ``--cron-remove``
to delete one.
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any, cast

import typer
import yaml

from automedia.cli.output import OutputMode, get_output_mode, output_error, output_text

# ---------------------------------------------------------------------------
# Platform → D-gate mapping
# ---------------------------------------------------------------------------

_PLATFORM_GATES: dict[str, str] = {
    "wechat": "D1Gate",
    "twitter": "D2Gate",
    "zhihu": "D3ZhihuRewrite",
    "xiaohongshu": "D4Gate",
    "bilibili": "D5BilibiliRewrite",
    "youtube": "D6YouTubeGate",
    "tiktok": "D7Gate",
}

_PLATFORM_MODULES: dict[str, str] = {
    "wechat": "automedia.gates.distribution.d1_wechat",
    "twitter": "automedia.gates.distribution.d2_twitter",
    "zhihu": "automedia.gates.distribution.d3_zhihu",
    "xiaohongshu": "automedia.gates.distribution.d4_xiaohongshu",
    "bilibili": "automedia.gates.distribution.d5_bilibili",
    "youtube": "automedia.gates.distribution.d6_youtube",
    "tiktok": "automedia.gates.distribution.d7_tiktok",
}

ALL_PLATFORMS: list[str] = sorted(_PLATFORM_GATES.keys())

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _discover_project(base_dir: str, project_id: str) -> tuple[Path, dict[str, Any]] | None:
    """Find a project by ID under *base_dir* and return ``(project_dir, info)``."""
    base = Path(base_dir)
    for info_file in base.glob("*/00_project_info.json"):
        try:
            with open(info_file, encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("project_id") == project_id:
                return info_file.parent, data
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _load_project_content(project_dir: Path) -> tuple[str, str | None]:
    """Load content from the project's ``01_content/drafts/`` directory.

    Returns
    -------
    tuple[str, str | None]
        ``(content, title)`` — *title* is inferred from the first ``# `` heading
        and may be ``None``.
    """
    drafts_dir = project_dir / "01_content" / "drafts"
    if not drafts_dir.is_dir():
        return "", None

    md_files = sorted(drafts_dir.glob("*.md"))
    if not md_files:
        return "", None

    content = md_files[0].read_text(encoding="utf-8")

    # Try to infer title from first markdown H1 heading
    title: str | None = None
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# ") or stripped.startswith("#\t"):
            title = stripped.lstrip("# \t")
            break

    return content, title


def _import_gate_class(platform: str):
    """Lazy-import the D-gate class for *platform*."""
    module_path = _PLATFORM_MODULES[platform]
    mod = importlib.import_module(module_path)
    class_name = _PLATFORM_GATES[platform]
    return getattr(mod, class_name)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def distribute_cmd(
    project_id: str = typer.Argument(..., help="Project ID to distribute."),
    platforms: str | None = typer.Option(
        None,
        "--platforms",
        help="Comma-separated list of target platforms (e.g. wechat,twitter).",
    ),
    all_platforms: bool = typer.Option(
        False,
        "--all",
        help="Distribute to all available platforms.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print distribution plan without executing gates.",
    ),
    base_dir: str = typer.Option(
        ".",
        "--base-dir",
        "-d",
        help="Base directory to scan for projects.",
    ),
    # ------------------------------------------------------------------
    # Cron scheduling options
    # ------------------------------------------------------------------
    cron: str | None = typer.Option(
        None,
        "--cron",
        help="Cron expression for scheduled distribution (e.g. '0 8 * * *').",
    ),
    cron_list: bool = typer.Option(
        False,
        "--cron-list",
        help="List scheduled distributions.",
    ),
    cron_remove: str | None = typer.Option(
        None,
        "--cron-remove",
        help="Name of scheduled distribution to remove (use --cron-list to see names).",
    ),
) -> None:
    """Run D-gates to prepare project content for platform-specific distribution.

    For each selected platform, runs the corresponding Distribution gate (D-gate)
    to rewrite the project's base content into the platform's required format and
    writes the result under ``04_distribution/<platform>/`` in the project
    directory.

    Use ``--platforms`` to select specific platforms or ``--all`` to target every
    available platform.  Add ``--dry-run`` to preview the plan without executing.

    Use ``--cron`` to schedule the distribution.  Use ``--cron-list`` to view
    scheduled distributions and ``--cron-remove`` to delete one.
    """
    # ------------------------------------------------------------------
    # Resolve the jobs.yaml path (reuse MCP helper logic)
    # ------------------------------------------------------------------
    _jobs_yaml_path: Path | None = None

    def _get_jobs_yaml() -> Path:
        """Locate ``cron/jobs.yaml`` under the automedia package."""
        nonlocal _jobs_yaml_path
        if _jobs_yaml_path is None:
            import automedia as _am_pkg
            _jobs_yaml_path = (
                Path(_am_pkg.__file__).resolve().parent / "cron" / "jobs.yaml"
            )
        return _jobs_yaml_path

    def _read_schedules() -> list[dict[str, Any]]:
        """Read ``pipeline_schedules`` from ``cron/jobs.yaml``."""
        path = _get_jobs_yaml()
        if not path.is_file():
            return []
        try:
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                return []
            return data.get("pipeline_schedules", []) or []
        except Exception:
            return []

    def _write_schedules(schedules: list[dict[str, Any]]) -> None:
        """Write ``pipeline_schedules`` back to ``cron/jobs.yaml``."""
        path = _get_jobs_yaml()
        if path.is_file():
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        else:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data["pipeline_schedules"] = schedules
        with open(path, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, default_flow_style=False, allow_unicode=True)

    # ------------------------------------------------------------------
    # Handle --cron-list: show scheduled distributions
    # ------------------------------------------------------------------
    if cron_list:
        all_schedules = _read_schedules()
        project_schedules = [
            s for s in all_schedules
            if s.get("name", "").startswith(f"distribute-{project_id}")
        ]

        if get_output_mode() == OutputMode.JSON:
            output_text(
                None,
                data={
                    "status": "ok",
                    "project_id": project_id,
                    "schedules": project_schedules,
                    "count": len(project_schedules),
                },
            )
            return

        if not project_schedules:
            typer.echo(f"No scheduled distributions found for project {project_id!r}.")
            return

        typer.echo(f"Scheduled distributions for project {project_id!r}:")
        typer.echo("-" * 60)
        for s in project_schedules:
            name = s.get("name", "?")
            expression = s.get("expression", s.get("schedule", "?"))
            platforms_str = s.get("platforms", s.get("platform", ""))
            typer.echo(f"  Name       : {name}")
            typer.echo(f"  Schedule   : {expression}")
            typer.echo(f"  Platforms  : {platforms_str}")
            typer.echo()
        return

    # ------------------------------------------------------------------
    # Handle --cron-remove: delete a scheduled distribution
    # ------------------------------------------------------------------
    if cron_remove:
        all_schedules = _read_schedules()
        before = len(all_schedules)
        remaining = [s for s in all_schedules if s.get("name") != cron_remove]

        if len(remaining) == before:
            output_error(
                f"Scheduled distribution {cron_remove!r} not found. "
                "Use --cron-list to see available names."
            )

        _write_schedules(remaining)

        if get_output_mode() == OutputMode.JSON:
            output_text(
                None,
                data={
                    "status": "ok",
                    "removed": cron_remove,
                    "project_id": project_id,
                },
            )
            return

        typer.secho(
            f"Removed scheduled distribution {cron_remove!r}.",
            fg=typer.colors.GREEN,
        )
        return

    # ------------------------------------------------------------------
    # Handle --cron: schedule a distribution
    # ------------------------------------------------------------------
    if cron:
        # Validate cron expression (5 fields)
        if not re.match(r"^(\S+\s+){4}\S+$", cron.strip()):
            output_error(
                f"Invalid cron expression {cron!r}: must have exactly 5 fields "
                "(min hour day month weekday)."
            )

        # Resolve platform list
        if all_platforms:
            platform_list = ALL_PLATFORMS
        elif platforms:
            platform_list = [p.strip() for p in platforms.split(",") if p.strip()]
            invalid = [p for p in platform_list if p not in _PLATFORM_GATES]
            if invalid:
                output_error(
                    f"Unknown platform(s): {', '.join(invalid)}. "
                    f"Valid platforms: {', '.join(ALL_PLATFORMS)}"
                )
        else:
            platform_list = ALL_PLATFORMS

        platforms_str = ",".join(platform_list)
        name = f"distribute-{project_id}"

        # Read existing schedules, check for duplicate name
        schedules = _read_schedules()
        if any(s.get("name") == name for s in schedules):
            output_error(
                f"A scheduled distribution named {name!r} already exists. "
                "Use --cron-remove to remove it first."
            )

        # Build the CLI command that will be executed by the cron runner
        command = f"automedia distribute {project_id} --platforms {platforms_str}"

        entry: dict[str, Any] = {
            "name": name,
            "expression": cron,
            "command": command,
            "project_id": project_id,
            "platforms": platforms_str,
        }
        schedules.append(entry)
        _write_schedules(schedules)

        if get_output_mode() == OutputMode.JSON:
            output_text(
                None,
                data={
                    "status": "ok",
                    "name": name,
                    "command": command,
                    "expression": cron,
                    "project_id": project_id,
                    "platforms": platforms_str,
                },
            )
            return

        typer.secho(
            f"Scheduled distribution: {name}",
            fg=typer.colors.GREEN,
        )
        typer.echo(f"  Expression : {cron}")
        typer.echo(f"  Command    : {command}")
        typer.echo()
        typer.echo(
            "The schedule will be executed by the cron system when "
            "'automedia cron run run-distribute' is triggered."
        )
        return

    # ------------------------------------------------------------------
    # Validate platform selection
    # ------------------------------------------------------------------
    if all_platforms and platforms:
        output_error("Cannot combine --all with --platforms.")
    if not all_platforms and not platforms:
        output_error("Either --platforms or --all is required.")

    if all_platforms:
        selected: list[str] = ALL_PLATFORMS
        platforms_list: str = ", ".join(ALL_PLATFORMS)
    else:
        platforms_list = cast(str, platforms)
        selected = [p.strip() for p in platforms_list.split(",") if p.strip()]
        invalid = [p for p in selected if p not in _PLATFORM_GATES]
        if invalid:
            output_error(
                f"Unknown platform(s): {', '.join(invalid)}. "
                f"Valid platforms: {', '.join(ALL_PLATFORMS)}"
            )

    # ------------------------------------------------------------------
    # Locate project
    # ------------------------------------------------------------------
    found = _discover_project(base_dir, project_id)
    if found is None:
        output_error(f"Project {project_id!r} not found in {base_dir}.")

    project_dir, project_info = cast(tuple[Path, dict[str, Any]], found)
    brand = project_info.get("brand", "")
    topic = project_info.get("topic", "")

    # ------------------------------------------------------------------
    # Load content
    # ------------------------------------------------------------------
    content, title = _load_project_content(project_dir)
    if not content.strip():
        output_error(f"No content found in {project_dir / '01_content' / 'drafts'}.")

    # ------------------------------------------------------------------
    # Dry-run mode — print plan and exit
    # ------------------------------------------------------------------
    if dry_run:
        if get_output_mode() == OutputMode.JSON:
            output_text(
                None,
                data={
                    "status": "dry_run",
                    "project_id": project_id,
                    "project_dir": str(project_dir),
                    "brand": brand,
                    "topic": topic,
                    "title": title or "",
                    "platforms": selected,
                    "content_length": len(content),
                },
            )
            return

        typer.echo(f"Distribution plan for project {project_id!r}")
        typer.echo(f"  Topic      : {topic}")
        typer.echo(f"  Brand      : {brand}")
        typer.echo(f"  Project dir: {project_dir}")
        if title:
            typer.echo(f"  Title      : {title}")
        typer.echo(f"  Content    : {len(content)} characters")
        typer.echo(f"  Platforms  : {', '.join(selected)}")
        typer.echo()
        typer.echo("  Dry-run — no gates executed.")
        return

    # ------------------------------------------------------------------
    # Execute D-gates for each selected platform
    # ------------------------------------------------------------------
    results: list[dict[str, Any]] = []
    failed: int = 0

    for platform in selected:
        gate_class = _import_gate_class(platform)
        gate = gate_class()

        gate_context: dict[str, Any] = {
            "content": content,
            "project_dir": str(project_dir),
            "brand": brand,
            "title": title or "",
        }

        try:
            result = gate.execute(gate_context)
            passed = result.get("passed", False)
            output_path = result.get("output_path", "")

            results.append(
                {
                    "platform": platform,
                    "gate": gate.gate_name,
                    "passed": passed,
                    "output_path": output_path,
                    "error": result.get("error"),
                }
            )

            if not passed:
                failed += 1
                typer.secho(
                    f"  {gate.gate_name} ({platform}) ❌ — {result.get('error', 'unknown error')}",
                    fg=typer.colors.RED,
                )
            else:
                typer.secho(
                    f"  {gate.gate_name} ({platform}) ✅ — {output_path}",
                    fg=typer.colors.GREEN,
                )

        except Exception as exc:
            failed += 1
            results.append(
                {
                    "platform": platform,
                    "gate": getattr(gate_class, "_gate_name", "?"),
                    "passed": False,
                    "output_path": "",
                    "error": str(exc),
                }
            )
            typer.secho(
                f"  {platform} ❌ — {exc}",
                fg=typer.colors.RED,
            )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total = len(selected)
    passed_count = total - failed

    if output_text(
        None,
        data={
            "status": "ok" if failed == 0 else "partial",
            "project_id": project_id,
            "project_dir": str(project_dir),
            "platforms": results,
            "passed": passed_count,
            "failed": failed,
            "total": total,
        },
    ):
        if failed:
            raise typer.Exit(code=1)
        return

    typer.echo()
    colour = typer.colors.GREEN if failed == 0 else typer.colors.YELLOW
    typer.secho(
        f"Distribution complete — {passed_count}/{total} passed, {failed} failed",
        fg=colour,
        bold=True,
    )

    if failed:
        raise typer.Exit(code=1)
