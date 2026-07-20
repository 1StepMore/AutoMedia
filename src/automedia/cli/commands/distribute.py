"""``automedia distribute`` — run D-gates to prepare content for distribution platforms.

For each selected platform, runs the corresponding D-gate to rewrite the
project's base content into the platform-specific format and writes the
result under ``04_distribution/<platform>/`` in the project directory.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, cast

import typer

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
) -> None:
    """Run D-gates to prepare project content for platform-specific distribution.

    For each selected platform, runs the corresponding Distribution gate (D-gate)
    to rewrite the project's base content into the platform's required format and
    writes the result under ``04_distribution/<platform>/`` in the project
    directory.

    Use ``--platforms`` to select specific platforms or ``--all`` to target every
    available platform.  Add ``--dry-run`` to preview the plan without executing.
    """
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
