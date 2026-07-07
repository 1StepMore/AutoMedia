"""AutoMedia MCP Server — stdio transport with 8 tools.

Provides an MCP-compliant server exposing AutoMedia pipeline operations
as LLM-callable tools.  All file-system operations are gated behind a
path allowlist loaded from ``mcp_allowlist.yaml``.

Usage::

    # Install with the ``mcp`` extra
    pip install -e ".[mcp]"

    # Run the server (stdio transport)
    python3 -m automedia.mcp.server

    # Or show help
    python3 -m automedia.mcp.server --help
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Allowlist helpers
# ---------------------------------------------------------------------------

_ALLOWLIST_FILE = Path(__file__).parent / "mcp_allowlist.yaml"

# Cache the resolved allowlist directories so we don't re-read YAML on every
# tool call.  Populated by ``_load_allowlist()`` on first access.
_cached_allowlist: list[str] | None = None


def _load_allowlist(*, allowlist_path: Path | None = None) -> list[str]:
    """Load and cache allowed directories from the YAML config.

    Parameters
    ----------
    allowlist_path:
        Override path to the allowlist YAML file.  When *None* the
        default ``mcp_allowlist.yaml`` next to this module is used.

    Returns
    -------
    list[str]
        Resolved absolute directory paths.
    """
    global _cached_allowlist
    path = allowlist_path if allowlist_path is not None else _ALLOWLIST_FILE
    if not path.exists():
        _cached_allowlist = []
        return []
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    raw: list[str] = data.get("allowed_directories", []) or []
    resolved = [os.path.realpath(d) for d in raw]
    _cached_allowlist = resolved
    return resolved


def _reset_allowlist_cache() -> None:
    """Reset the cached allowlist.  Used in tests."""
    global _cached_allowlist
    _cached_allowlist = None


def check_path_allowed(path: str, *, allowlist: list[str] | None = None) -> bool:
    """Return *True* if *path* falls under an allowed directory.

    When the allowlist is empty **all paths are allowed** (permissive
    default — the operator must explicitly configure restrictions).

    Parameters
    ----------
    path:
        File or directory path to validate (need not exist).
    allowlist:
        Override list of resolved directory paths.  When *None* the
        cached allowlist from the YAML file is used.
    """
    if allowlist is None:
        allowlist = _cached_allowlist if _cached_allowlist is not None else _load_allowlist()
    if not allowlist:
        return True  # empty allowlist → permissive
    real = os.path.realpath(path)
    return any(real.startswith(d) for d in allowlist)


def _require_allowed(path: str, *, tool_name: str = "") -> None:
    """Raise ``ValueError`` if *path* is not in the allowlist."""
    if not check_path_allowed(path):
        prefix = f"[{tool_name}] " if tool_name else ""
        raise ValueError(
            f"{prefix}Path {path!r} is not within any allowed directory. "
            f"Configure allowed_directories in mcp_allowlist.yaml."
        )


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _discover_projects(base_dir: str) -> list[dict[str, Any]]:
    """Scan *base_dir* for project info JSON files and return their contents."""
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


def _project_assets(project_dir: str) -> list[dict[str, Any]]:
    """Walk *project_dir* and return a list of asset metadata dicts."""
    assets: list[dict[str, Any]] = []
    root = Path(project_dir)
    if not root.is_dir():
        return assets
    for fpath in sorted(root.rglob("*")):
        if fpath.is_file() and fpath.name != "00_project_info.json":
            rel = fpath.relative_to(root)
            assets.append({
                "path": str(fpath),
                "relative_path": str(rel),
                "name": fpath.name,
                "size_bytes": fpath.stat().st_size,
            })
    return assets


def _pipeline_result_to_dict(result: Any) -> dict[str, Any]:
    """Convert a :class:`PipelineResult` dataclass to a plain dict."""
    from dataclasses import asdict

    try:
        return asdict(result)
    except Exception:
        # Fallback: manual extraction
        return {
            "status": getattr(result, "status", "unknown"),
            "project_id": getattr(result, "project_id", ""),
            "project_dir": getattr(result, "project_dir", ""),
            "topic": getattr(result, "topic", ""),
            "brand": getattr(result, "brand", ""),
            "error": getattr(result, "error", None),
        }


# ---------------------------------------------------------------------------
# Tool handler functions (module-level for testability)
# ---------------------------------------------------------------------------

def select_topic(
    category: str = "",
    tenant_id: str = "default",
    pool_db_path: str = "",
) -> dict[str, Any]:
    """Select the highest-scored pending topic from the pool.

    Parameters
    ----------
    category:
        Optional category filter (e.g. ``"tech"``, ``"finance"``).
    tenant_id:
        Tenant / namespace identifier.
    pool_db_path:
        Explicit path to the topic pool SQLite database.  When
        empty the default location is used.

    Returns
    -------
    dict
        ``{"selected": {...}, "remaining_count": int}`` or
        ``{"selected": null, "error": str}``.
    """
    try:
        from automedia.pool.db import PoolDB

        if pool_db_path:
            _require_allowed(pool_db_path, tool_name="select_topic")
            db = PoolDB(pool_db_path)
        else:
            db = PoolDB(":memory:")

        topics = db.list_topics(status="pending")
        if category:
            topics = [t for t in topics if t.get("category") == category]
        if tenant_id and tenant_id != "default":
            topics = [t for t in topics if t.get("tenant_id") == tenant_id]

        if not topics:
            return {"selected": None, "remaining_count": 0, "error": "No pending topics found"}

        # Sort by score descending
        topics.sort(key=lambda t: t.get("score", 0.0), reverse=True)
        chosen = topics[0]
        db.mark_selected(chosen["id"])
        db.close()
        return {"selected": chosen, "remaining_count": len(topics) - 1}

    except Exception as exc:
        return {"selected": None, "error": str(exc)}


def run_pipeline(
    topic: str,
    brand: str,
    mode: str = "auto",
    tenant_id: str = "default",
    resume_from: str = "",
) -> dict[str, Any]:
    """Execute the full AutoMedia production pipeline.

    Parameters
    ----------
    topic:
        Content topic / subject.
    brand:
        Brand identifier.
    mode:
        Pipeline mode — ``"auto"``, ``"text_only"``, ``"video_only"``,
        or ``"qa_only"``.
    tenant_id:
        Tenant / namespace identifier.
    resume_from:
        Gate name to resume from (skip preceding gates).  Empty
        runs from the beginning.

    Returns
    -------
    dict
        PipelineResult serialised as a JSON-compatible dict.
    """
    try:
        from automedia.pipelines.runner import run_full_pipeline

        result = run_full_pipeline(
            topic=topic,
            brand=brand,
            mode=mode,
            tenant_id=tenant_id,
            resume_from=resume_from or None,
        )
        return _pipeline_result_to_dict(result)

    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


def get_pipeline_status(
    project_id: str,
    base_dir: str = ".",
) -> dict[str, Any]:
    """Return the current status / progress of a pipeline run.

    Looks up the project by *project_id* and returns its metadata
    together with the sub-directory listing as a proxy for progress.

    Parameters
    ----------
    project_id:
        The 12-char hex project identifier.
    base_dir:
        Base directory to scan for projects.

    Returns
    -------
    dict
        ``{"project": {...}, "subdirs": [...]}`` or error.
    """
    try:
        _require_allowed(base_dir, tool_name="get_pipeline_status")
        projects = _discover_projects(base_dir)
        match = [p for p in projects if p.get("project_id") == project_id]
        if not match:
            return {"error": f"Project {project_id!r} not found"}
        proj = match[0]
        proj_dir = proj.get("_dir", "")
        subdirs = []
        if proj_dir and Path(proj_dir).is_dir():
            subdirs = sorted(
                str(p.relative_to(proj_dir))
                for p in Path(proj_dir).iterdir()
                if p.is_dir()
            )
        return {"project": proj, "subdirs": subdirs}

    except Exception as exc:
        return {"error": str(exc)}


def list_projects(
    base_dir: str = ".",
    status: str = "",
) -> dict[str, Any]:
    """List all projects found under *base_dir*.

    Parameters
    ----------
    base_dir:
        Root directory to scan for ``00_project_info.json`` files.
    status:
        Optional status filter (e.g. ``"published"``).

    Returns
    -------
    dict
        ``{"projects": [...]}``.
    """
    try:
        _require_allowed(base_dir, tool_name="list_projects")
        projects = _discover_projects(base_dir)
        if status:
            projects = [p for p in projects if p.get("status", "") == status]
        return {"projects": projects, "count": len(projects)}

    except Exception as exc:
        return {"projects": [], "error": str(exc)}


def get_project_assets(
    project_dir: str,
) -> dict[str, Any]:
    """Return the list of asset files inside a project directory.

    Parameters
    ----------
    project_dir:
        Absolute path to the project root.

    Returns
    -------
    dict
        ``{"assets": [...], "count": int}``.
    """
    try:
        _require_allowed(project_dir, tool_name="get_project_assets")
        assets = _project_assets(project_dir)
        return {"assets": assets, "count": len(assets)}

    except Exception as exc:
        return {"assets": [], "error": str(exc)}


def archive_project(
    project_id: str,
    base_dir: str = ".",
    force: bool = False,
) -> dict[str, Any]:
    """Archive a project (Red Line 8 enforcement).

    Refuses to archive unless the project status is ``"published"``
    or *force* is ``True``.

    Parameters
    ----------
    project_id:
        The 12-char hex project identifier.
    base_dir:
        Base directory to scan for projects.
    force:
        Force archive even if status is not ``"published"``.

    Returns
    -------
    dict
        ``{"archived": True, "archive_dir": str}`` or error.
    """
    try:
        _require_allowed(base_dir, tool_name="archive_project")

        # Red Line 8: refuse without force when status ≠ published
        projects = _discover_projects(base_dir)
        match = [p for p in projects if p.get("project_id") == project_id]
        if not match:
            return {"archived": False, "error": f"Project {project_id!r} not found"}

        proj = match[0]
        status_val = str(proj.get("status", ""))
        if status_val != "published" and not force:
            return {
                "archived": False,
                "error": (
                    f"Refused: project status is '{status_val}', not 'published'. "
                    f"Set force=True to override (Red Line 8)."
                ),
            }

        project_dir = Path(proj["_dir"])
        archive_dir = project_dir.parent / f"{project_dir.name}_archived"
        if archive_dir.exists():
            return {"archived": False, "error": f"Archive target already exists: {archive_dir}"}

        project_dir.rename(archive_dir)
        return {"archived": True, "archive_dir": str(archive_dir)}

    except Exception as exc:
        return {"archived": False, "error": str(exc)}


def list_topic_pool(
    status: str = "",
    category: str = "",
    pool_db_path: str = "",
) -> dict[str, Any]:
    """List topics in the pool, optionally filtered by status or category.

    Parameters
    ----------
    status:
        Filter by topic status (e.g. ``"pending"``, ``"selected"``).
    category:
        Filter by category.
    pool_db_path:
        Explicit path to the topic pool SQLite database.

    Returns
    -------
    dict
        ``{"topics": [...], "count": int}``.
    """
    try:
        from automedia.pool.db import PoolDB

        if pool_db_path:
            _require_allowed(pool_db_path, tool_name="list_topic_pool")
            db = PoolDB(pool_db_path)
        else:
            db = PoolDB(":memory:")

        topics = db.list_topics(status=status or None)
        if category:
            topics = [t for t in topics if t.get("category") == category]
        db.close()
        return {"topics": topics, "count": len(topics)}

    except Exception as exc:
        return {"topics": [], "error": str(exc)}


def register_omni_adapter(
    platform_name: str,
    adapter_class: str = "",
) -> dict[str, Any]:
    """Register an Omni adapter (stub).

    This is a placeholder that records the intent to register an
    adapter.  Full implementation requires the adapter class to be
    importable at runtime.

    Parameters
    ----------
    platform_name:
        Platform identifier (e.g. ``"wechat"``, ``"weibo"``).
    adapter_class:
        Dotted Python path to the adapter class (optional stub).

    Returns
    -------
    dict
        ``{"registered": True, "platform": str}`` or stub notice.
    """
    try:
        from automedia.adapters.registry import AdapterRegistry

        if adapter_class:
            # Attempt dynamic import
            module_path, _, class_name = adapter_class.rpartition(".")
            if not module_path:
                return {"registered": False, "error": f"Invalid adapter_class: {adapter_class!r}"}
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            AdapterRegistry.register(cls)
            return {"registered": True, "platform": platform_name, "class": adapter_class}

        # Stub mode — just acknowledge
        return {
            "registered": False,
            "platform": platform_name,
            "stub": True,
            "message": (
                f"Stub: adapter for {platform_name!r} acknowledged. "
                f"Provide adapter_class to fully register."
            ),
        }

    except Exception as exc:
        return {"registered": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# MCP Server construction
# ---------------------------------------------------------------------------

def create_server() -> Any:
    """Create and configure the FastMCP server instance.

    Returns
    -------
    FastMCP
        A fully configured server with all 8 tools registered.
    """
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        name="AutoMedia",
        instructions=(
            "AutoMedia automated media production pipeline. "
            "Use these tools to manage topic pools, run production pipelines, "
            "and inspect project assets."
        ),
    )

    # Register all 8 tools
    mcp.tool(
        description=(
            "Select the highest-scored pending topic from the pool. "
            "Returns the selected topic and remaining count."
        ),
    )(select_topic)

    mcp.tool(
        description=(
            "Execute the full AutoMedia production pipeline. "
            "Returns PipelineResult as JSON."
        ),
    )(run_pipeline)

    mcp.tool(
        description=(
            "Return the current status / progress of a pipeline run "
            "by project ID."
        ),
    )(get_pipeline_status)

    mcp.tool(
        description=(
            "List all projects found under a base directory, "
            "optionally filtered by status."
        ),
    )(list_projects)

    mcp.tool(
        description=(
            "Return the list of asset files inside a project directory."
        ),
    )(get_project_assets)

    mcp.tool(
        description=(
            "Archive a project. Red Line 8: refuses unless status is "
            "'published' or force=True."
        ),
    )(archive_project)

    mcp.tool(
        description=(
            "List topics in the pool, optionally filtered by "
            "status or category."
        ),
    )(list_topic_pool)

    mcp.tool(
        description=(
            "Register an Omni adapter (stub). Provide platform_name "
            "and optional adapter_class dotted path."
        ),
    )(register_omni_adapter)

    return mcp


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the AutoMedia MCP server (stdio transport)."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python3 -m automedia.mcp.server",
        description="AutoMedia MCP Server — stdio transport with 8 tools.",
    )
    parser.add_argument(
        "--show-tools",
        action="store_true",
        help="List registered tool names and exit.",
    )
    args = parser.parse_args()

    server = create_server()

    if args.show_tools:
        # FastMCP stores tools internally; print names for quick inspection
        print("Registered MCP tools:")
        for name in sorted(server._tool_manager._tools.keys()):
            print(f"  - {name}")
        return

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
