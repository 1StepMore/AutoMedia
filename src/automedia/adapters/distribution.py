"""Shared distribution logic — used by both CLI and MCP tools.

Provides :func:`distribute_to_platforms` which discovers a project by ID
and delegates to :class:`~automedia.adapters.publish_engine.PublishEngine`
for multi-platform publishing.
"""

from __future__ import annotations

from typing import Any

from structlog import get_logger

from automedia.adapters.publish_engine import PublishEngine

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_default_projects_dir: str | None = None


def _resolve_projects_dir(override: str | None = None) -> str:
    """Resolve the projects directory.

    Checks *override* first, then falls back to the default logic
    (``AUTOMEDIA_PROJECTS_DIR`` env var or ``.automedia/output/projects``).
    """
    if override:
        return override
    global _default_projects_dir
    if _default_projects_dir is None:
        env_dir = __import__("os").environ.get("AUTOMEDIA_PROJECTS_DIR", "")
        if env_dir:
            _default_projects_dir = str(__import__("pathlib").Path(env_dir).resolve())
        else:
            _default_projects_dir = str(
                __import__("pathlib").Path.cwd() / ".automedia" / "output" / "projects"
            )
    return _default_projects_dir


def _discover_projects(base_dir: str) -> list[dict[str, Any]]:
    """Scan *base_dir* for project info JSON files and return their contents."""
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    projects: list[dict[str, Any]] = []
    base = Path(base_dir)
    for info_file in sorted(base.glob("*/00_project_info.json")):
        try:
            with open(info_file, encoding="utf-8") as fh:
                data = json.load(fh)
            data["_dir"] = str(info_file.parent)
            projects.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return projects


def distribute_to_platforms(
    project_id: str,
    platforms: list[str] | None = None,
    all_platforms: bool = False,
    dry_run: bool = False,
    base_dir: str | None = None,
) -> dict[str, Any]:
    """Distribute (publish) a project's content to one or more platforms.

    Parameters
    ----------
    project_id:
        The 12-char hex project identifier.
    platforms:
        Specific list of platform names to target (e.g. ``["wechat", "zhihu"]``).
        When ``None`` and *all_platforms* is ``False``, this is an error.
    all_platforms:
        When ``True``, distribute to every registered (enabled, non-manual)
        platform regardless of *platforms*.
    dry_run:
        When ``True``, validate pre-conditions for each platform without
        actually publishing.  Returns the same result shape with
        ``"dry_run": True`` on each platform entry.
    base_dir:
        Root directory containing project directories.  When ``None``
        the default projects directory is used.

    Returns
    -------
    dict
        ``{"platforms": {platform: str, ...}, "summary": str, "dry_run": bool}``
        where each platform value is one of ``"success"``, ``"failed"``,
        ``"skipped"``, ``"would_succeed"``, ``"would_fail"``, or
        ``"not_found"``.
    """
    # --- Discover project -------------------------------------------------
    projects_dir = _resolve_projects_dir(base_dir)
    projects = _discover_projects(projects_dir)
    match = [p for p in projects if p.get("project_id") == project_id]
    if not match:
        return {
            "platforms": {},
            "summary": f"Project {project_id!r} not found",
            "dry_run": dry_run,
            "error": f"Project {project_id!r} not found in {projects_dir}",
        }

    proj = match[0]
    artifact_dir = proj.get("_dir", "")

    # --- Resolve target platforms -----------------------------------------
    from automedia.adapters.registry import AdapterRegistry  # noqa: PLC0415

    registered = AdapterRegistry.list()

    target_platforms: list[str] = []
    if all_platforms:
        target_platforms = list(registered)
    elif platforms:
        # Validate that requested platforms are registered
        unknown = [p for p in platforms if p not in registered]
        if unknown:
            return {
                "platforms": {},
                "summary": f"Unknown platforms: {', '.join(unknown)}",
                "dry_run": dry_run,
                "error": {
                    "unknown_platforms": unknown,
                    "registered": registered,
                },
            }
        target_platforms = list(platforms)
    else:
        # No platforms specified and all_platforms is False
        return {
            "platforms": {},
            "summary": "No platforms specified. Provide a platform list or set all=True.",
            "dry_run": dry_run,
            "error": "No target platforms",
        }

    if not artifact_dir:
        return {
            "platforms": {},
            "summary": "Project artifact directory not found",
            "dry_run": dry_run,
            "error": "Project has no artifact directory",
        }

    # --- Dry run: validate without publishing ------------------------------
    if dry_run:
        results: dict[str, str] = {}
        for platform_name in target_platforms:
            try:
                adapter_cls = AdapterRegistry.get(platform_name)
                adapter = adapter_cls()
                valid = adapter.validate(artifact_dir)
                results[platform_name] = "would_succeed" if valid else "would_fail"
            except Exception as exc:
                log.warning(
                    "distribution.dry_run.error",
                    platform=platform_name,
                    error=str(exc),
                )
                results[platform_name] = "would_fail"

        success_count = sum(
            1 for v in results.values() if v == "would_succeed"
        )
        total = len(results)
        return {
            "platforms": results,
            "summary": f"{success_count}/{total} platforms would succeed",
            "dry_run": True,
        }

    # --- Actual publish via PublishEngine ----------------------------------
    engine = PublishEngine()
    try:
        raw_results = engine.publish_all(
            artifact_dir=artifact_dir,
            project=proj,
            automation=None,
        )
    except Exception as exc:
        log.error("distribution.publish_all.error", error=str(exc))
        return {
            "platforms": {p: "failed" for p in target_platforms},
            "summary": f"0/{len(target_platforms)} platforms succeeded — engine error: {exc}",
            "dry_run": False,
            "error": str(exc),
        }

    # Map PublishEngine results to the expected return format
    platform_results: dict[str, str] = {}
    for platform_name in target_platforms:
        raw = raw_results.get(platform_name, {})
        status = raw.get("status", "")
        if status == "ok":
            platform_results[platform_name] = "success"
        elif status == "skipped":
            platform_results[platform_name] = "skipped"
        elif status == "draft_created":
            platform_results[platform_name] = "success"
        else:
            platform_results[platform_name] = "failed"

    success_count = sum(1 for v in platform_results.values() if v == "success")
    total = len(platform_results)
    return {
        "platforms": platform_results,
        "summary": f"{success_count}/{total} platforms succeeded",
        "dry_run": False,
    }
