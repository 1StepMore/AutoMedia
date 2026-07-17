"""MCP tool handler functions (module-level for testability).

All 14 tool handlers plus the helper utilities they depend on.
Imported and registered by :func:`automedia.mcp.server.create_server`.
"""

from __future__ import annotations

import importlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import yaml
from structlog import get_logger

from automedia.core.logging import bind_correlation_id
from automedia.mcp._state import (
    _SERVER_START,
    _lock,
    _pipeline_tracker,
)
from automedia.mcp.allowlist import (
    _ALLOWED_OUTPUT_FORMATS,
)
from automedia.pipelines.gate_engine import PipelineProgress, PipelineResult, ProgressData
from automedia.pipelines.runner import VALID_MODES

# Track registered tool count (set dynamically by server.py after registration)
_tools_count: int = 0


def set_tools_count(count: int) -> None:
    """Set the registered tool count (called from server.py after registration)."""
    global _tools_count
    _tools_count = count


def _require_allowed(path: str, *, tool_name: str = "") -> None:
    """Delegate to the server module's ``_require_allowed`` at call time.

    This indirection ensures that ``@patch("automedia.mcp.server._require_allowed")``
    in tests correctly intercepts calls from tool functions.
    """
    from automedia.mcp import server as _srv

    _srv._require_allowed(path, tool_name=tool_name)

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _resolve_projects_dir() -> str:
    """Resolve the projects directory from env or config defaults.

    Checks ``AUTOMEDIA_PROJECTS_DIR`` first, then falls back to
    ``.automedia/output/projects`` relative to the current working directory.

    Returns
    -------
    str
        Absolute path to the projects directory.
    """
    env_dir = os.environ.get("AUTOMEDIA_PROJECTS_DIR", "")
    if env_dir:
        return str(Path(env_dir).resolve())
    return str(Path.cwd() / ".automedia" / "output" / "projects")


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
            assets.append(
                {
                    "path": str(fpath),
                    "relative_path": str(rel),
                    "name": fpath.name,
                    "size_bytes": fpath.stat().st_size,
                }
            )
    return assets


def _pipeline_result_to_dict(result: PipelineResult) -> dict[str, Any]:
    """Convert a :class:`PipelineResult` dataclass to a plain dict."""
    from dataclasses import asdict

    try:
        return asdict(result)
    except TypeError:
        # Fallback: manual extraction (non-dataclass result)
        return {
            "status": getattr(result, "status", "unknown"),
            "project_id": getattr(result, "project_id", ""),
            "project_dir": getattr(result, "project_dir", ""),
            "topic": getattr(result, "topic", ""),
            "brand": getattr(result, "brand", ""),
            "error": getattr(result, "error", None),
        }


# ---------------------------------------------------------------------------
# Tool handler functions
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
        # MCP boundary: catch-all to return error dict for any pool/DB failure
        return {"selected": None, "error": str(exc)}


def _fetch_tavily_trending(category: str) -> str:
    api_key = os.environ.get("AUTOMEDIA_TAVILY_API_KEY", "")
    if not api_key:
        return ""

    try:
        import httpx
    except ImportError:
        return ""

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": category,
                    "search_depth": "advanced",
                    "max_results": 8,
                    "include_domains": [],
                    "exclude_domains": [],
                },
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
    except Exception:
        return ""

    results = data.get("results", [])
    if not results:
        return ""

    lines: list[str] = []
    for item in results[:8]:
        title = (item.get("title") or "").strip()
        content = (item.get("content") or "")[:200]
        if title:
            lines.append(f"- {title}")
            if content:
                lines.append(f"  {content}")
    return "\n".join(lines) if lines else ""


def research_topics(
    category: str,
    count: int = 5,
    trending_data: str = "",
    pattern: str = "b",
) -> dict[str, Any]:
    """Research trending or high-potential topics within a category using LLM.

    Uses the ``topic_research`` prompt template and the
    :class:`TopicResearchOutput` Pydantic model to produce a structured
    list of topic suggestions with angles, confidence scores, and format
    recommendations.  The result is ready to feed into the topic pool.

    When ``AUTOMEDIA_TAVILY_API_KEY`` is configured, the function first
    fetches real-time trending signals from the Tavily Search API and
    passes them as ``trending_data`` to the LLM, providing up-to-date
    context beyond the LLM's training data cutoff.

    Parameters
    ----------
    category:
        Content category to research (e.g. ``"AI Tools"``, ``"Finance"``).
    count:
        Number of topics to generate (default 5).
    trending_data:
        Optional context — trending signals, audience data, or keywords
        to steer the LLM toward relevant topics.  When Tavily is
        configured, real-time data is merged into this field.
    pattern:
        When ``"a"``, return raw input data without calling the LLM.
        When ``"b"`` (default), use the LLM as usual.

    Returns
    -------
    dict
        ``{"topics": [...], "category": str, "total_found": int}``
        or an error dict on failure.
    """
    if pattern == "a":
        return {"topics": [], "category": category, "total_found": 0, "note": "pattern_a_raw_data"}
    try:
        from automedia.core.llm_client import llm_complete_structured_safe
        from automedia.decision.pydantic import TopicResearchOutput
        from automedia.prompts import load_prompt

        if not trending_data:
            tavily_data = _fetch_tavily_trending(category)
            if tavily_data:
                trending_data = (
                    f"Real-time search results for \"{category}\":\n"
                    f"{tavily_data}"
                )

        prompt = load_prompt(
            "topic_research",
            category=category,
            count=count,
            trending_data=trending_data,
        )
        result = llm_complete_structured_safe(
            prompt,
            response_format=TopicResearchOutput,
        )
        return result.model_dump()
    except Exception as exc:
        # MCP boundary: catch-all for LLM/prompt/template errors
        return {"topics": [], "category": category, "total_found": 0, "error": str(exc)}


def run_pipeline(
    topic: str,
    brand: str,
    mode: str = "auto",
    # DEPRECATED — kept for backward compatibility, scheduled for removal
    decision_mode: str = "build",
    tenant_id: str = "default",
    resume_from: str = "",
    source_path: str = "",
    source_url: str = "",
) -> dict[str, Any]:
    """Execute the full AutoMedia production pipeline in a background thread.

    Launches the pipeline asynchronously and returns immediately with a
    ``project_id`` that can be used with ``get_pipeline_progress`` to
    poll execution status.

    Parameters
    ----------
    topic:
        Content topic / subject.
    brand:
        Brand identifier.
    mode:
        Pipeline mode — ``"auto"``, ``"text_only"``,
        ``"text_with_cover"``, ``"video_only"``, ``"qa_only"``,
        ``"image-carousel"``, ``"social-thread"``, or
        ``"short-video"``.
    tenant_id:
        Tenant / namespace identifier.
    resume_from:
        Gate name to resume from (skip preceding gates).  Empty
        runs from the beginning.
    source_path:
        Path to a source document (``.md``, ``.txt``, or ``.pdf``).
        Content is loaded and injected into the pipeline gate context
        for downstream gates to process.
    source_url:
        URL to fetch source content from.  Content is loaded and
        injected into the pipeline gate context.

    Returns
    -------
    dict
        ``{"project_id": str, "status": "started"}`` on success, or
        ``{"status": "failed", "error": str}`` on immediate failure.
    """
    # Pre-validate mode to fail fast
    # Uses VALID_MODES shared constant from runner.py (single source of truth)
    if mode not in VALID_MODES:
        return {
            "status": "failed",
            "error": f"Unknown pipeline mode {mode!r}. Choose from: {list(VALID_MODES)}",
        }

    # Validate source_path against allowlist
    # If the path is not allowed, log a warning and fall back gracefully
    # rather than failing the pipeline start.
    if source_path:
        try:
            _require_allowed(source_path, tool_name="run_pipeline")
        except Exception as exc:
            # Allowlist check failed — fall back gracefully rather than failing startup
            log.warning("run_pipeline: source_path %s not in allowlist: %s", source_path, exc)
            source_path = ""

    project_id = str(uuid.uuid4())[:12]
    progress = PipelineProgress(project_id=project_id)
    with _lock:
        _pipeline_tracker[project_id] = progress

    def _run() -> None:
        """Background thread — wraps pipeline execution in try/except."""
        try:
            from automedia.pipelines.runner import run_full_pipeline

            # Bind correlation_id for distributed tracing in this thread
            bind_correlation_id()

            result = run_full_pipeline(
                topic=topic,
                brand=brand,
                mode=mode,
                decision_mode=decision_mode,
                tenant_id=tenant_id,
                resume_from=resume_from or None,
                source_path=source_path,
                source_url=source_url,
            )
            progress.project_id = result.project_id
        except Exception as exc:
            # Background thread catch-all — pipeline errors stored in progress
            progress.error = str(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"project_id": project_id, "status": "started"}


def batch_run(
    topics: list[str],
    brand: str,
    mode: str = "auto",
) -> dict[str, Any]:
    """Execute pipelines for multiple topics sequentially.

    Iterates over *topics* and calls :func:`run_full_pipeline` for each
    one.  A single topic failure does **not** stop the batch — errors
    are collected and all remaining topics are processed.  Returns
    per-topic results with a summary.

    Parameters
    ----------
    topics:
        List of content topics / subjects.
    brand:
        Brand identifier.
    mode:
        Pipeline mode — ``"auto"``, ``"text_only"``,
        ``"text_with_cover"``, ``"video_only"``, ``"qa_only"``,
        ``"image-carousel"``, ``"social-thread"``, or
        ``"short-video"``.

    Returns
    -------
    dict
        ``{"results": [...], "total": int, "passed": int, "failed": int}``
        where each result entry is ``{"topic": str, "status": str,
        "project_id": str, "error": str | None}``.
    """
    from automedia.pipelines.runner import run_full_pipeline

    results: list[dict[str, Any]] = []

    for topic in topics:
        try:
            bind_correlation_id()
            pipeline_result = run_full_pipeline(
                topic=topic,
                brand=brand,
                mode=mode,
            )
            results.append({
                "topic": topic,
                "status": pipeline_result.status,
                "project_id": pipeline_result.project_id,
                "error": pipeline_result.error,
            })
        except Exception as exc:
            # MCP boundary: per-topic catch-all so one failure doesn't stop the batch
            results.append({
                "topic": topic,
                "status": "failed",
                "project_id": "",
                "error": str(exc),
            })

    passed = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - passed
    return {
        "results": results,
        "total": len(results),
        "passed": passed,
        "failed": failed,
    }


def get_pipeline_progress(project_id: str) -> ProgressData:
    """Get current progress of a running pipeline by project_id.

    Poll this after ``run_pipeline`` to observe gate execution in real
    time.  Returns the current gate, a list of gate progress events
    (start / passed / failed), and any error captured from the background
    thread.

    Parameters
    ----------
    project_id:
        The project id returned by ``run_pipeline``.

    Returns
    -------
    dict
        ``{"project_id", "current_gate", "gates_done", "gates_remaining",
        "total_gates", "events", "error"}`` or
        ``{"error": "not found"}``.
    """
    with _lock:
        progress = _pipeline_tracker.get(project_id)
    if not progress:
        return {"error": f"No active pipeline found for project_id {project_id!r}"}
    return progress.get_progress()


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
                str(p.relative_to(proj_dir)) for p in Path(proj_dir).iterdir() if p.is_dir()
            )
        return {"project": proj, "subdirs": subdirs}

    except Exception as exc:
        # MCP boundary: catch-all for file/allowlist errors
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
        # MCP boundary: catch-all for file-scan/allowlist errors
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
        # MCP boundary: catch-all for file-scan/allowlist errors
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
        # MCP boundary: catch-all for file/allowlist/rename errors
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
        # MCP boundary: catch-all for PoolDB errors
        return {"topics": [], "error": str(exc)}


def pool_add_topic(
    title: str,
    category: str = "",
    pool_db_path: str = "",
) -> dict[str, Any]:
    """Add a topic to the topic pool.

    Parameters
    ----------
    title:
        Title of the topic to add.
    category:
        Optional category for the topic.
    pool_db_path:
        Explicit path to the topic pool SQLite database.

    Returns
    -------
    dict
        ``{"id": int, "title": str, "category": str, "status": "pending"}``
        or an error dict on failure.
    """
    try:
        from automedia.pool.db import PoolDB

        if pool_db_path:
            _require_allowed(pool_db_path, tool_name="pool_add_topic")
            db = PoolDB(pool_db_path)
        else:
            db = PoolDB(":memory:")

        topic_id = db.add_topic(data={"title": title, "category": category})
        db.close()
        return {
            "id": topic_id,
            "title": title,
            "category": category,
            "status": "pending",
        }
    except Exception as exc:
        # MCP boundary: catch-all for PoolDB errors
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Cron schedule management helpers
# ---------------------------------------------------------------------------


def _get_jobs_yaml_path() -> Path:
    """Resolve the path to ``cron/jobs.yaml`` in the automedia package."""
    import automedia as _am_pkg

    pkg_root = Path(_am_pkg.__file__).resolve().parent
    return pkg_root / "cron" / "jobs.yaml"


def _read_pipeline_schedules() -> list[dict[str, Any]]:
    """Read ``pipeline_schedules`` from ``cron/jobs.yaml``."""
    path = _get_jobs_yaml_path()
    if not path.is_file():
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            return []
        return data.get("pipeline_schedules", []) or []
    except Exception:
        # YAML parse errors are non-fatal — return empty schedule list
        return []


def _write_pipeline_schedules(schedules: list[dict[str, Any]]) -> None:
    """Write ``pipeline_schedules`` back to ``cron/jobs.yaml``, preserving existing keys."""
    path = _get_jobs_yaml_path()
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


def add_cron_schedule(
    name: str,
    expression: str,
    brand: str = "",
    category: str = "",
    count: int = 1,
) -> dict[str, Any]:
    """Add a cron schedule entry to ``cron/jobs.yaml``.

    Parameters
    ----------
    name:
        Unique name for the schedule entry.
    expression:
        Cron expression with 5 fields (min hour day month weekday).
    brand:
        Brand name to use when running the pipeline.
    category:
        Topic category filter.
    count:
        Number of topics to process (default 1).

    Returns
    -------
    dict
        ``{"added": True, "name": str}`` or ``{"error": str}``.
    """
    import re

    if not re.match(r"^(\S+\s+){4}\S+$", expression.strip()):
        return {
            "error": f"Invalid cron expression {expression!r}: must have exactly 5 fields",
        }

    schedules = _read_pipeline_schedules()

    if any(s.get("name") == name for s in schedules):
        return {"error": f"Schedule {name!r} already exists"}

    schedules.append(
        {
            "name": name,
            "expression": expression,
            "brand": brand,
            "category": category,
            "count": count,
        }
    )

    try:
        _write_pipeline_schedules(schedules)
        return {"added": True, "name": name}
    except Exception as exc:
        # MCP boundary: catch-all for YAML write errors
        return {"error": str(exc)}


def list_cron_schedules() -> dict[str, Any]:
    """List all cron schedule entries from ``cron/jobs.yaml``.

    Returns
    -------
    dict
        ``{"schedules": [...], "count": int}``.
    """
    try:
        schedules = _read_pipeline_schedules()
        schedules.sort(key=lambda s: s.get("name", ""))
        return {"schedules": schedules, "count": len(schedules)}
    except Exception as exc:
        # MCP boundary: catch-all for YAML read errors
        return {"schedules": [], "error": str(exc)}


def remove_cron_schedule(name: str) -> dict[str, Any]:
    """Remove a cron schedule entry by name.

    Parameters
    ----------
    name:
        Name of the schedule entry to remove.

    Returns
    -------
    dict
        ``{"removed": True, "name": str}`` or ``{"error": str}``.
    """
    schedules = _read_pipeline_schedules()

    before = len(schedules)
    schedules = [s for s in schedules if s.get("name") != name]

    if len(schedules) == before:
        return {"error": f"Schedule {name!r} not found"}

    try:
        _write_pipeline_schedules(schedules)
        return {"removed": True, "name": name}
    except Exception as exc:
        # MCP boundary: catch-all for YAML write errors
        return {"error": str(exc)}


def get_cron_health() -> dict[str, Any]:
    """Check cron system health.

    Validates the ``cron/jobs.yaml`` schedule definitions and reports
    schedule counts.  Does **not** include run-time monitoring data
    because AutoMedia has no built-in cron daemon — scheduling is
    delegated to an external crond.

    Returns
    -------
    dict
        ``{"jobs_valid": bool, "schedule_count": int,
          "valid_expressions": int, "invalid_expressions": int,
          "schedules": [...], "job_count": int, "static_jobs": [...],
          "note": str}``.
        Each schedule entry includes ``name``, ``expression``, ``valid``,
        ``next_triggers`` (list of 5 ISO-8601 timestamps, or ``None``),
        and ``next_triggers_note``.
    """
    path = _get_jobs_yaml_path()
    if not path.is_file():
        return {
            "jobs_valid": False,
            "schedule_count": 0,
            "job_count": 0,
            "static_jobs": [],
            "note": "cron/jobs.yaml not found",
        }

    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:
        # MCP boundary: YAML parse errors are non-fatal
        return {
            "jobs_valid": False,
            "schedule_count": 0,
            "job_count": 0,
            "static_jobs": [],
            "note": f"parse error: {exc}",
        }

    if not isinstance(data, dict):
        return {
            "jobs_valid": False,
            "schedule_count": 0,
            "job_count": 0,
            "static_jobs": [],
            "note": "jobs.yaml is not a valid dict",
        }

    pipeline_schedules = data.get("pipeline_schedules", []) or []
    if not isinstance(pipeline_schedules, list):
        pipeline_schedules = []

    static_jobs = data.get("jobs", []) or []
    if not isinstance(static_jobs, list):
        static_jobs = []

    import re

    valid_count = 0
    for sched in pipeline_schedules:
        expr = sched.get("expression", "")
        if isinstance(expr, str) and re.match(r"^(\S+\s+){4}\S+$", expr.strip()):
            valid_count += 1

    schedules: list[dict[str, Any]] = []
    croniter_note: str | None = None
    for sched in pipeline_schedules:
        name = sched.get("name", "")
        expr = sched.get("expression", "")
        valid = isinstance(expr, str) and bool(
            re.match(r"^(\S+\s+){4}\S+$", expr.strip())
        )

        entry: dict[str, Any] = {
            "name": name,
            "expression": expr,
            "valid": valid,
        }

        if valid:
            try:
                from datetime import datetime

                import croniter  # type: ignore[import-untyped]  # croniter has no type stubs

                cron = croniter.croniter(expr.strip(), datetime.now())
                next_triggers: list[str] = []
                for _ in range(5):
                    next_time = cron.get_next(datetime)
                    next_triggers.append(next_time.isoformat())
                entry["next_triggers"] = next_triggers
                entry["next_triggers_note"] = None
            except ImportError:
                entry["next_triggers"] = None
                croniter_note = (
                    "croniter not available — install with 'pip install croniter' "
                    "to compute next trigger times. Expression format is valid."
                )
                entry["next_triggers_note"] = croniter_note
            except Exception:
                # croniter failure on a syntactically valid expression
                entry["next_triggers"] = None
                entry["next_triggers_note"] = (
                    "Cron expression is syntactically valid but "
                    "croniter failed to compute next triggers."
                )
        else:
            entry["next_triggers"] = None
            entry["next_triggers_note"] = (
                "Expression does not match 5-field cron syntax."
            )

        schedules.append(entry)

    job_details: list[dict[str, Any]] = []
    for job in static_jobs:
        job_details.append(
            {
                "name": job.get("name", ""),
                "schedule": job.get("schedule", ""),
                "description": job.get("description", ""),
            }
        )

    notes: list[str] = [
        "Health tracking infrastructure not available — "
        "no cron daemon run history exists. "
        "Scheduling is delegated to an external crond "
        "that calls `automedia cron run <job>` at configured intervals.",
    ]
    if croniter_note:
        notes.append(croniter_note)

    return {
        "jobs_valid": True,
        "schedule_count": len(pipeline_schedules),
        "valid_expressions": valid_count,
        "invalid_expressions": len(pipeline_schedules) - valid_count,
        "schedules": schedules,
        "job_count": len(static_jobs),
        "static_jobs": job_details,
        "note": " ".join(notes),
    }


def test_cron_schedule(
    expression: str,
    count: int = 5,
) -> dict[str, Any]:
    """Validate a cron expression and compute its next N trigger times.

    Uses the same 5-field regex validation as :func:`add_cron_schedule`.
    If *croniter* is installed, computes the next *count* trigger times.
    Otherwise returns a validation-only result with a note.

    Parameters
    ----------
    expression:
        Cron expression with 5 fields (min hour day month weekday).
    count:
        Number of next trigger times to return (default 5, max 20).

    Returns
    -------
    dict
        ``{"valid": True, "expression": str, "next_triggers": [...],
        "note": None}`` on success with *croniter*, or
        ``{"valid": True, "expression": str, "next_triggers": None,
        "note": "croniter not available..."}`` without *croniter*, or
        ``{"valid": False, "expression": str, "error": str}`` on invalid
        syntax or computation failure.
    """
    import re

    if not re.match(r"^(\S+\s+){4}\S+$", expression.strip()):
        return {
            "valid": False,
            "expression": expression,
            "error": f"Invalid cron expression {expression!r}: must have exactly 5 fields",
        }

    count = max(1, min(count, 20))

    try:
        from datetime import datetime

        import croniter

        cron = croniter.croniter(expression.strip(), datetime.now())
        next_triggers: list[str] = []
        for _ in range(count):
            next_time = cron.get_next(datetime)
            next_triggers.append(next_time.isoformat())

        return {
            "valid": True,
            "expression": expression,
            "next_triggers": next_triggers,
            "note": None,
        }
    except ImportError:
        return {
            "valid": True,
            "expression": expression,
            "next_triggers": None,
            "note": (
                "croniter not available — install with 'pip install croniter' "
                "to compute next trigger times. The expression format is valid."
            ),
        }
    except Exception as exc:
        # MCP boundary: croniter computation failures are non-fatal
        return {
            "valid": False,
            "expression": expression,
            "error": f"Cron expression {expression!r} is syntactically valid but "
            f"croniter failed to compute next triggers: {exc}",
        }


def publish_content(
    project_id: str,
    platform: str,
    account_id: str = "",
    base_dir: str = "",
    mode: str = "auto",
) -> dict[str, Any]:
    """Publish a project to a platform.

    Parameters
    ----------
    project_id:
        Project identifier.
    platform:
        Target platform name (e.g. ``"xiaohongshu"``, ``"zhihu"``).
    account_id:
        Optional account identifier for PRD-4 account-aware publishing.
    base_dir:
        Root directory containing project directories.
    mode:
        Publish mode. ``"auto"`` (default) respects the brand profile's
        automation level.  ``"publish"`` forces full publish regardless
        of automation level (overrides ``"review"`` to ``"auto"``).

    Returns
    -------
    dict
        ``{"published": bool, "platform": str, "url": str, …}``
        or an error dict on failure.  When the automation level is
        ``"review"`` and mode is ``"auto"``, the result includes
        ``status: "draft_created"`` and ``draft_url``.
    """
    try:
        _require_allowed(base_dir, tool_name="publish_content")

        from automedia.adapters.publish_engine import PublishEngine

        projects_dir = base_dir or _resolve_projects_dir()
        projects = _discover_projects(projects_dir)
        match = [p for p in projects if p.get("project_id") == project_id]
        if not match:
            return {"published": False, "error": f"Project {project_id!r} not found"}

        proj = match[0]
        artifact_dir = proj["_dir"]

        # Resolve per-platform automation levels from brand profile
        from automedia.manifests.brand_profile_schema import load_brand_profiles  # noqa: PLC0415

        automation: dict[str, str] | None = None
        brand_name = proj.get("brand", "")
        if brand_name:
            profiles = load_brand_profiles()
            profile = profiles.get(brand_name)
            if profile is not None:
                automation = dict(profile.automation) if profile.automation else {}

        # mode="publish" overrides review → auto for the target platform
        if mode == "publish":
            if automation is None:
                automation = {}
            automation[platform] = "auto"

        engine = PublishEngine()
        account_ids = [account_id] if account_id else None
        result = engine.publish_all(
            artifact_dir=artifact_dir,
            project=proj,
            account_ids=account_ids,
            automation=automation,
        )

        platform_result = result.get(platform, {})
        status = platform_result.get("status", "")
        success = platform_result.get("success", False) or status in ("ok", "published")
        base_response: dict[str, Any] = {
            "published": success,
            "platform": platform,
            "url": platform_result.get("url", ""),
        }
        if status == "draft_created":
            base_response["status"] = "draft_created"
            base_response["draft_url"] = platform_result.get("draft_url", "")
            base_response["draft_id"] = platform_result.get("draft_id", "")
        elif status == "error":
            base_response["published"] = False
            base_response["error"] = platform_result.get("reason", "unknown error")
        return base_response
    except Exception as exc:
        # MCP boundary: catch-all for publish-engine / allowlist errors
        return {"published": False, "error": str(exc)}


def register_platform_adapter(
    platform_name: str,
    adapter_class: str = "",
) -> dict[str, Any]:
    """Register a platform adapter (stub — PRD-1 NG6).

    ------------------------------------------------------------------
    ╔══════════════════════════════════════════════════════════════════╗
    ║  STUB NOTICE: Per PRD-1 NG6, no new content production          ║
    ║  platforms are added in this phase.  This function serves as    ║
    ║  a **validated placeholder** that records the intent to         ║
    ║  register an adapter, but does *not* wire up real platform      ║
    ║  connectivity.                                                  ║
    ║                                                                ║
    ║  Future implementation path:                                     ║
    ║  1. Create a concrete adapter class in a new module under        ║
    ║     ``automedia/adapters/`` (e.g. ``wechat.py``).               ║
    ║  2. The class should inherit from a base adapter protocol        ║
    ║     (defined elsewhere) and implement ``publish()``.             ║
    ║  3. Call this function with the dotted path to that class.       ║
    ║  4. The dynamic import below will register it with               ║
    ║     ``AdapterRegistry`` for downstream use.                     ║
    ╚══════════════════════════════════════════════════════════════════╝
    ------------------------------------------------------------------

    Parameters
    ----------
    platform_name:
        Platform identifier (e.g. ``"wechat"``, ``"weibo"``).
        Must be non-empty and match ``[a-zA-Z0-9_-]+``.
    adapter_class:
        Dotted Python path to the adapter class (e.g.
        ``"automedia.adapters.wechat.WeChatAdapter"``).
        When empty the function acts as a pure stub.

    Returns
    -------
    dict
        With ``adapter_class``: ``{"registered": True, "platform": str,
        "class": str}`` on success.
        Without ``adapter_class``: ``{"registered": False, "stub": True,
        "platform": str, "message": str, "instructions": str}``.
        On error: ``{"registered": False, "error": str}``.
    """
    import re

    if not platform_name or not isinstance(platform_name, str):
        return {
            "registered": False,
            "error": "platform_name must be a non-empty string.",
        }
    if not re.match(r"^[a-zA-Z0-9_-]+$", platform_name):
        return {
            "registered": False,
            "error": (
                f"Invalid platform_name {platform_name!r}. "
                f"Use only letters, digits, underscores, and hyphens."
            ),
        }

    try:
        from automedia.adapters.registry import AdapterRegistry

        if adapter_class:
            module_path, _, class_name = adapter_class.rpartition(".")
            if not module_path:
                return {
                    "registered": False,
                    "error": (
                        f"Invalid adapter_class {adapter_class!r}: "
                        f"must be a dotted path (e.g. 'pkg.mod.ClassName')."
                    ),
                }
            if not module_path.startswith("automedia.adapters."):
                return {
                    "registered": False,
                    "error": (
                        f"Invalid adapter class: {adapter_class!r}. "
                        f"Must be in automedia.adapters.* namespace"
                    ),
                }
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", class_name):
                return {
                    "registered": False,
                    "error": (
                        f"Invalid class name in {adapter_class!r}. "
                        f"Class name must match [A-Za-z_][A-Za-z0-9_]*."
                    ),
                }
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            AdapterRegistry.register(cls)
            return {"registered": True, "platform": platform_name, "class": adapter_class}

        return {
            "registered": False,
            "platform": platform_name,
            "stub": True,
            "message": (
                f"Stub: adapter for {platform_name!r} acknowledged. "
                f"Provide a dotted ``adapter_class`` path to fully register."
            ),
            "instructions": (
                f"To implement the {platform_name!r} adapter:\n"
                f"  1. Create automedia/adapters/{platform_name}.py with a class\n"
                f"     that implements the adapter protocol.\n"
                f"  2. Call register_platform_adapter(\n"
                f"       platform_name={platform_name!r},\n"
                f"       adapter_class='automedia.adapters.{platform_name}.<ClassName>',\n"
                f"     )\n"
                f"  3. The adapter will be registered with AdapterRegistry."
            ),
        }

    except Exception as exc:
        # MCP boundary: catch-all for dynamic import / registry errors
        return {"registered": False, "error": str(exc)}


def extract_brief(
    file_path: str,
    source_lang: str = "auto",
    target_lang: str = "en",
) -> dict[str, Any]:
    """Extract a content brief from a document file using OPP.

    Processes the document through OPPAdapter.extract() to extract
    structured markdown content, a manifest JSON with segment metadata,
    and any warnings encountered during extraction.

    Parameters
    ----------
    file_path:
        Path to the source document file.
    source_lang:
        Source language code (``"auto"`` for auto-detection).
    target_lang:
        Target language code for extraction (default ``"en"``).

    Returns
    -------
    dict
        ``{"md_content": str, "manifest_json": dict, "warnings": list[str]}``
        or an error dict on failure.
    """
    try:
        _require_allowed(file_path, tool_name="extract_brief")
        from automedia.omni.opp_adapter import OPPAdapter

        adapter = OPPAdapter()
        result = adapter.extract(file_path, source_lang, target_lang)
        return {
            "md_content": result.md_content,
            "manifest_json": result.manifest,
            "warnings": result.warnings,
        }
    except Exception as exc:
        # MCP boundary: catch-all for OPP extraction errors
        return {"md_content": "", "manifest_json": {}, "warnings": [str(exc)]}


def localize_content(
    md_content: str,
    source_lang: str,
    target_lang: str,
) -> dict[str, Any]:
    """Translate markdown content from source to target language.

    Delegates to OLAdapter.translate() which uses the OL shield →
    LLM-translate → repair → unshield pipeline.  Returns the translated
    markdown, optional XLIFF path, and any warnings collected.

    Parameters
    ----------
    md_content:
        Source markdown content to translate.
    source_lang:
        Source language code (e.g. ``"zh"``, ``"ja"``).
    target_lang:
        Target language code (e.g. ``"en"``).

    Returns
    -------
    dict
        ``{"translated_md": str, "xliff_path": str | None, "warnings": list[str]}``
        or an error dict on failure.
    """
    try:
        from automedia.omni.ol_adapter import OLAdapter

        adapter = OLAdapter()
        result = adapter.translate(md_content, source_lang, target_lang)
        return {
            "translated_md": result.translated_md,
            "xliff_path": result.xliff_path,
            "warnings": result.warnings,
        }
    except Exception as exc:
        # MCP boundary: catch-all for OL translation errors
        return {"translated_md": "", "xliff_path": None, "warnings": [str(exc)]}


def localize_output(
    project_dir: str,
    target_langs: str,
) -> dict[str, Any]:
    """Translate all project drafts into multiple target languages.

    Reads markdown files from ``01_content/drafts/``, translates each into
    every target language via OLAdapter, writes to ``05_publish/{lang}/``,
    and returns a mapping of language → output file paths.

    Parameters
    ----------
    project_dir:
        Path to the project root directory.
    target_langs:
        Comma-separated language codes (e.g. ``"en,ja"``).

    Returns
    -------
    dict
        ``{"project_dir": str, "results": {lang: [file_path, ...]}, "warnings": [...]}``
        or error dict.
    """
    try:
        _require_allowed(project_dir, tool_name="localize_output")
        from pathlib import Path

        from automedia.omni.ol_adapter import OLAdapter

        proj = Path(project_dir)
        drafts_dir = proj / "01_content" / "drafts"

        results: dict[str, list[str]] = {}
        warnings: list[str] = []

        if not drafts_dir.is_dir():
            return {
                "project_dir": project_dir,
                "results": results,
                "warnings": [f"Drafts directory not found: {drafts_dir}"],
            }

        langs = [lang.strip() for lang in target_langs.split(",") if lang.strip()]
        if not langs:
            return {
                "project_dir": project_dir,
                "results": results,
                "warnings": ["No target languages specified"],
            }

        md_files = sorted(drafts_dir.glob("*.md"))
        if not md_files:
            return {
                "project_dir": project_dir,
                "results": results,
                "warnings": [f"No markdown files found in {drafts_dir}"],
            }

        adapter = OLAdapter()

        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8")
            for lang in langs:
                try:
                    trans_result = adapter.translate(
                        md_content=content,
                        source_lang="auto",
                        target_lang=lang,
                    )
                    publish_dir = proj / "05_publish" / lang
                    publish_dir.mkdir(parents=True, exist_ok=True)
                    output_file = publish_dir / md_file.name
                    output_file.write_text(trans_result.translated_md, encoding="utf-8")
                    results.setdefault(lang, []).append(str(output_file))
                except Exception as exc:
                    # Per-file catch-all: one file failure doesn't stop other translations
                    warnings.append(f"Translation failed for {md_file.name} → {lang}: {exc}")

        return {
            "project_dir": project_dir,
            "results": results,
            "warnings": warnings,
        }
    except Exception as exc:
        # MCP boundary: catch-all for file I/O / translation errors
        return {
            "project_dir": project_dir,
            "results": {},
            "warnings": [str(exc)],
        }


def format_output(
    content: str,
    target_format: str,
    **options: Any,  # noqa: ANN401 — pass-through to ORFAdapter.convert()
) -> dict[str, Any]:
    """Convert content to the specified output format.

    Delegates to ORFAdapter.convert() to transform content into the
    requested output format.  Returns the output path, format identifier,
    and any warnings or errors encountered during conversion.

    Parameters
    ----------
    content:
        Source content to convert (markdown text).
    target_format:
        Desired output format identifier (e.g. ``"html"``, ``"pdf"``).
    **options:
        Additional keyword arguments forwarded to the converter.

    Returns
    -------
    dict
        ``{"output_path": str, "output_format": str, "warnings": list[str]}``
        or an error dict on failure.
    """
    if "/" in target_format or "\\" in target_format or ".." in target_format:
        return {"error": f"Invalid format: {target_format!r} — path separators not allowed"}

    if target_format not in _ALLOWED_OUTPUT_FORMATS:
        return {"error": f"Unsupported format: {target_format!r}"}

    import tempfile

    temp_path: str | None = None
    try:
        from automedia.omni.orf_adapter import ORFAdapter

        # Compute the output path explicitly based on the target format.
        # ORFAdapter.convert expects a file path; write content to a
        # temporary file, then delete it after conversion completes.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(content)
            temp_path = fh.name

        output_path = temp_path + "." + target_format
        adapter = ORFAdapter()
        result = adapter.convert(
            file_path=temp_path,
            output_path=output_path,
            **options,
        )
        errors = result.get("errors", [])
        return {
            "output_path": output_path,
            "output_format": target_format,
            "warnings": errors if errors else [],
        }
    except Exception as exc:
        # MCP boundary: catch-all for ORF conversion errors
        return {"output_path": "", "output_format": target_format, "warnings": [str(exc)]}
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError:
                log.warning("Failed to clean up temp file %s", temp_path)


# ---------------------------------------------------------------------------
# Content quality evaluation tool
# ---------------------------------------------------------------------------


def evaluate_content_quality(
    content: str,
    criteria: str = "general",
    brand: str = "",
    pattern: str = "b",
) -> dict[str, Any]:
    """Evaluate content quality using an LLM with structured output.

    Uses the ``content_quality.j2`` prompt template in combination with
    ``ContentQualityOutput`` Pydantic model to produce a scored evaluation
    with issues, suggestions, and an overall assessment.

    Parameters
    ----------
    content:
        The content text to evaluate.
    criteria:
        Quality dimensions to evaluate — e.g. ``"general"``,
        ``"clarity, accuracy, brand voice, SEO readiness"``.
    brand:
        Optional brand identifier for brand-specific evaluation.
    pattern:
        When ``"a"``, return raw input data without calling the LLM.
        When ``"b"`` (default), use the LLM as usual.

    Returns
    -------
    dict
        ``{"quality_score": float, "issues": list[str],
        "suggestions": list[str], "overall_assessment": str}``
        or an error dict on failure.
    """
    if pattern == "a":
        return {"quality_score": 0.5, "note": "pattern_a_raw_data", "criteria": criteria}
    try:
        from automedia.core.llm_client import llm_complete_structured_safe
        from automedia.decision.pydantic import ContentQualityOutput
        from automedia.prompts import load_prompt

        prompt = load_prompt(
            "content_quality",
            content=content,
            criteria=criteria,
            brand=brand,
        )
        result = llm_complete_structured_safe(
            prompt,
            response_format=ContentQualityOutput,
        )
        return result.model_dump()
    except Exception as exc:
        # MCP boundary: catch-all for LLM/prompt errors
        return {
            "quality_score": 0.0,
            "issues": [],
            "suggestions": [],
            "overall_assessment": "",
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Health-check tool
# ---------------------------------------------------------------------------


def health_check() -> dict[str, Any]:
    """Return server health status — version, uptime, and tool count.

    Returns
    -------
    dict
        ``{"status": "ok", "version": str, "uptime_s": float, "tools_count": int}``
        or ``{"status": "error", "error": str}`` on failure.
    """
    try:
        from automedia._version import __version__

        uptime_s = time.monotonic() - _SERVER_START
        return {
            "status": "ok",
            "version": __version__,
            "uptime_s": round(uptime_s, 2),
            "tools_count": _tools_count,
        }
    except Exception as exc:
        # MCP boundary: catch-all for version import errors
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Config introspection tool
# ---------------------------------------------------------------------------

_SECRET_KEYWORDS: frozenset[str] = frozenset({"key", "secret", "password", "token"})


def _has_secret_keyword(key: str) -> bool:
    """Check if a key name contains any secret-related keyword (case-insensitive)."""
    return any(kw in key.lower() for kw in _SECRET_KEYWORDS)


def _redact_secrets(value: object) -> object:
    """Recursively replace secret values with ``***REDACTED***``."""
    if isinstance(value, dict):
        return {
            k: "***REDACTED***" if _has_secret_keyword(k) else _redact_secrets(v)
            for k, v in value.items()
        }
    return value


def _deep_get(data: dict, key_path: str) -> object | None:
    """Traverse a nested dict using dot-notation key paths.

    Parameters
    ----------
    data:
        The nested dictionary to traverse.
    key_path:
        Dot-separated path such as ``"llm.text_generation.temperature"``.

    Returns
    -------
    object | None
        The value at the given path, or *None* if any segment is missing.
    """
    current: object = data
    for part in key_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def get_config(key: str = "") -> dict[str, Any]:
    """Return merged configuration settings (excluding secrets).

    When *key* is empty, returns all non-secret config keys.  When *key*
    is specified, returns the value for that specific config key using
    dot-notation traversal (e.g. ``llm.temperature``).

    Parameters
    ----------
    key:
        Dot-notation config key to look up.  Empty string returns all config.

    Returns
    -------
    dict
        ``{"config": {...}}`` with secrets redacted, or
        ``{"value": ...}`` for a specific key lookup, or
        ``{"error": "config key '...' not found"}``, or
        ``{"error": "secret key not exposed"}`` when the key is secret.
    """
    try:
        from automedia.core.config_loader import load_config

        config = load_config()

        if not key:
            return {"config": _redact_secrets(config)}

        # Reject direct access to secret keys
        if _has_secret_keyword(key.split(".")[-1]):
            return {"error": "secret key not exposed"}

        value = _deep_get(config, key)
        if value is None:
            return {"error": f"config key '{key}' not found"}

        # Redact any sub-values if the result is a dict
        if isinstance(value, dict):
            value = _redact_secrets(value)

        return {"value": value}
    except Exception as exc:
        # MCP boundary: catch-all for config load errors
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Brand tools
# ---------------------------------------------------------------------------


def list_brands() -> dict[str, Any]:
    """Return all configured brands with full profile metadata.

    Reads from multi-brand config in ``~/.automedia/brand_profiles.yaml``
    via :func:`automedia.manifests.brand_profile_schema.load_brand_profiles`.

    Returns
    -------
    dict
        ``{"brands": [...], "total": N, "error": str | None}`` —
        never raises.  Each brand entry includes all fields from
        :class:`~automedia.manifests.brand_profile_schema.BrandProfile`.
    """
    try:
        from automedia.manifests.brand_profile_schema import load_brand_profiles

        profiles = load_brand_profiles()
        brands_list = [
            {
                "name": profile.brand_name,
                "aliases": profile.aliases,
                "cta_principles": profile.cta_principles,
                "blocked_words": profile.blocked_words,
                "tone_guidelines": profile.tone_guidelines,
                "brand_identity": profile.brand_identity,
                "languages": profile.languages,
                "industry": profile.industry,
                "target_audience": profile.target_audience,
                "personality": profile.personality,
                "platforms": profile.platforms,
            }
            for profile in profiles.values()
        ]
        return {"brands": brands_list, "total": len(brands_list), "error": None}
    except Exception as exc:
        # MCP boundary: catch-all for brand profile load errors
        return {"brands": [], "total": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Asset library tools
# ---------------------------------------------------------------------------


def search_assets(
    query: str,
    brand: str,
    limit: int = 10,
    type: str | None = None,
    tags: list[str] | None = None,
    lang: str | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    """Search the asset library for brand assets.

    Wraps :func:`automedia.asset_library.search_assets` — delegates to
    SQLite keyword search and Chroma semantic search, returns ranked
    results with relevance scores.

    Parameters
    ----------
    query : str
        Search query (keyword + semantic).  Empty string returns all
        assets filtered by the other criteria.
    brand : str
        Brand identifier to scope the search.
    limit : int
        Maximum number of results to return (default 10).
    type : str or None
        Optional asset type filter (e.g. ``"article"``, ``"brief"``).
    tags : list[str] or None
        Optional tag overlap filter.
    lang : str or None
        Optional language code filter (e.g. ``"zh"``, ``"en"``).
    stage : str or None
        Optional source-phase filter.

    Returns
    -------
    dict
        ``{"results": [...], "count": int, "error": str | None}`` —
        never raises.  Each result is a dict with at least ``title``,
        ``content``, ``_score``, and metadata keys.
    """
    try:
        from automedia.asset_library import search_assets as _search_assets

        filters: dict[str, Any] = {}
        if type is not None:
            filters["type"] = type
        if tags is not None:
            filters["tags"] = tags
        if lang is not None:
            filters["lang"] = lang
        if stage is not None:
            filters["phase"] = stage

        raw_results = _search_assets(query=query, brand=brand, filters=filters or None)
        limited = raw_results[:limit]
        return {"results": limited, "count": len(limited), "error": None}
    except Exception as exc:
        # MCP boundary: catch-all for asset library search errors
        return {"results": [], "count": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# LLM-driven tools
# ---------------------------------------------------------------------------


def run_brand_strategy(
    brand_name: str,
    industry: str,
    target_audience: str,
    context: str = "",
    pattern: str = "b",
) -> dict[str, Any]:
    """Generate a brand strategy using LLM-driven analysis.

    Loads the ``brand_strategy`` Jinja2 prompt template, fills in the
    parameters, and sends it to the configured LLM via
    :func:`~automedia.core.llm_client.llm_complete_structured_safe` with
    :class:`~automedia.decision.pydantic.BrandStrategyOutput` as the
    response schema.

    Parameters
    ----------
    brand_name:
        Name of the brand to analyse.
    industry:
        Industry or vertical (e.g. ``"SaaS"``, ``"e-commerce"``).
    target_audience:
        Description of the target audience.
    context:
        Optional additional context or constraints for the strategy.
    pattern:
        When ``"a"``, return raw input data without calling the LLM.
        When ``"b"`` (default), use the LLM as usual.

    Returns
    -------
    dict
        A dict matching the ``BrandStrategyOutput`` schema with keys:
        ``brand_positioning``, ``audience_analysis``,
        ``competitive_landscape``, ``key_differentiators``,
        ``suggested_messaging``.  On failure the dict contains an
        ``"error"`` key instead.
    """
    if pattern == "a":
        return {
            "note": "pattern_a_raw_data",
            "input": {
                "brand_name": brand_name,
                "industry": industry,
                "target_audience": target_audience,
                "context": context,
            },
        }
    try:
        from automedia.core.llm_client import llm_complete_structured_safe
        from automedia.decision.pydantic import BrandStrategyOutput
        from automedia.prompts import load_prompt

        prompt = load_prompt(
            "brand_strategy",
            brand_name=brand_name,
            industry=industry,
            target_audience=target_audience,
            context=context,
        )
        result = llm_complete_structured_safe(
            prompt,
            response_format=BrandStrategyOutput,
        )
        return result.model_dump()
    except Exception as exc:
        # MCP boundary: catch-all for LLM/strategy generation errors
        return {"error": str(exc)}


def run_pipeline_from_strategy(
    topic: str,
    brand: str,
    mode: str = "auto",
    strategy_context: str = "",
    pattern: str = "b",
) -> dict[str, Any]:
    """Generate a content strategy via LLM then execute the production pipeline.

    Loads the ``pipeline_strategy`` Jinja2 prompt template, fills in the
    parameters, and sends it to the configured LLM via
    :func:`~automedia.core.llm_client.llm_complete_structured_safe` with
    :class:`~automedia.decision.pydantic.PipelineStrategyOutput` as the
    response schema.  Then delegates to
    :func:`~automedia.pipelines.runner.run_full_pipeline` with the
    original *topic*, *brand*, and *mode* parameters.

    Parameters
    ----------
    topic:
        Content topic / subject.
    brand:
        Brand identifier.
    mode:
        Pipeline mode — ``"auto"``, ``"text_only"``,
        ``"text_with_cover"``, ``"video_only"``, ``"qa_only"``,
        ``"image-carousel"``, ``"social-thread"``, or
        ``"short-video"``.
    strategy_context:
        Optional additional context or constraints for the strategy
        (e.g. target audience, tone, platform hints).
    pattern:
        When ``"a"``, return raw input data without calling the LLM.
        When ``"b"`` (default), use the LLM as usual.

    Returns
    -------
    dict
        ``{"strategy": {...}, "pipeline_result": {...}}`` on success.
        On failure the dict contains an ``"error"`` key with the
        failure description.
    """
    if pattern == "a":
        return {
            "note": "pattern_a_raw_data",
            "input": {
                "topic": topic,
                "brand": brand,
                "mode": mode,
                "strategy_context": strategy_context,
            },
        }
    try:
        from automedia.core.llm_client import llm_complete_structured_safe
        from automedia.decision.pydantic import PipelineStrategyOutput
        from automedia.pipelines.runner import run_full_pipeline
        from automedia.prompts import load_prompt

        prompt = load_prompt(
            "pipeline_strategy",
            topic=topic,
            brand=brand,
            mode=mode,
            context=strategy_context,
        )
        strategy: PipelineStrategyOutput = llm_complete_structured_safe(
            prompt,
            response_format=PipelineStrategyOutput,
        )

        bind_correlation_id()
        pipeline_result = run_full_pipeline(
            topic=topic,
            brand=brand,
            mode=mode,
        )

        return {
            "strategy": strategy.model_dump(),
            "pipeline_result": _pipeline_result_to_dict(pipeline_result),
        }
    except Exception as exc:
        # MCP boundary: catch-all for strategy generation + pipeline errors
        return {"error": str(exc)}


def update_engine_config(
    modality: str,
    setting: str,
    value: str,
) -> dict[str, Any]:
    """Update an engine configuration setting.

    Writes a YAML override file to ``~/.automedia/overrides/rules/``.
    The change takes effect on the next config load (pipeline run).

    Parameters
    ----------
    modality:
        Engine modality: ``"tts"``, ``"asr"``, ``"image"``, or ``"video"``.
    setting:
        Setting name within the modality (e.g. ``"default"``, ``"voice"``,
        ``"host"``, ``"port"``, ``"model"``).
    value:
        Setting value (string). Numeric values will be auto-converted.

    Returns
    -------
    dict
        ``{"status": "ok", "modality": str, "setting": str, "value": str, "file": str}``
        or ``{"error": str}`` on failure.
    """
    from datetime import datetime, timezone

    _VALID_MODALITIES = {"tts", "asr", "image", "video"}

    if modality not in _VALID_MODALITIES:
        return {
            "error": f"Invalid modality '{modality}'. Valid: {', '.join(sorted(_VALID_MODALITIES))}",
        }

    try:
        overrides_dir = Path.home() / ".automedia" / "overrides" / "rules"
        overrides_dir.mkdir(parents=True, exist_ok=True)

        override_data = {
            "engines": {
                modality: {
                    setting: value,
                },
            },
        }

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = f"engine-override-{modality}-{ts}.yaml"
        filepath = overrides_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(override_data, f, default_flow_style=False)

        return {
            "status": "ok",
            "modality": modality,
            "setting": setting,
            "value": value,
            "file": str(filepath),
        }
    except Exception as exc:
        return {"error": str(exc)}


def engine_health() -> dict[str, Any]:
    """Check all engine-related dependencies and return their health status.

    Returns
    -------
    dict
        ``{"engines": [...], "healthy_count": int, "unhealthy_count": int}``
        or ``{"error": str}`` on failure.
    """
    try:
        from automedia.core.doctor import Doctor

        _ENGINE_DEPS = {"comfyui", "whisper", "edge-tts", "hyperframes", "chrome", "ffmpeg", "bun", "llm_api"}

        all_deps = Doctor().check_dependencies()
        engine_deps = [d for d in all_deps if d["name"] in _ENGINE_DEPS]
        healthy = sum(1 for d in engine_deps if d["installed"])
        unhealthy = len(engine_deps) - healthy

        return {
            "engines": engine_deps,
            "healthy_count": healthy,
            "unhealthy_count": unhealthy,
        }
    except Exception as exc:
        return {"error": str(exc)}
