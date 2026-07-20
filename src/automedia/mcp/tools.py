"""MCP tool handler functions (module-level for testability).

All tool handler functions plus the helper utilities they depend on.
Imported and registered by :func:`automedia.mcp.server.create_server`.
"""

from __future__ import annotations

import fcntl
import importlib
import json
import os
import threading
import time
import uuid
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict

import yaml
from pydantic import ValidationError
from structlog import get_logger

from automedia.core.llm_client import LLMError
from automedia.core.logging import bind_correlation_id
from automedia.exceptions import (
    AutoMediaError,
    BrandNotFoundError,
    ConfigError,
    ModuleLoadError,
    PipelineError,
)
from automedia.mcp._state import (
    _SERVER_START,
    _lock,
    _pipeline_tracker,
)
from automedia.mcp.allowlist import (
    _ALLOWED_OUTPUT_FORMATS,
)
from automedia.mcp.mcp_error import (
    MCPErrorCode,
    error_response,
    success_response,
    validation_error_response,
)
from automedia.mcp.server_types import (
    CronExpression,
    EngineModality,
    NonEmptyStr,
    PipelineMode,
    ProjectStatusFilter,
    ResearchPattern,
)
from automedia.pipelines.gate_engine import (
    PipelineProgress,
    PipelineResult,
    get_registered_engine,
    list_registered_engines,
)
from automedia.pipelines.runner import VALID_MODES


class CronScheduleEntry(TypedDict):
    name: str
    expression: str
    brand: str
    category: str
    count: int
    platform: str
    mode: str


# Track registered tool count (set dynamically by server.py after registration)
_tools_count: int = 0

# Default per-model cost-per-token rates (USD per 1M tokens).
# Used to estimate cost when token_usage is available.
# Model → (input_cost_per_1M, output_cost_per_1M)
_DEFAULT_COST_RATES: dict[str, tuple[float, float]] = {
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-haiku": (0.25, 1.25),
}
_FALLBACK_INPUT_RATE = 0.27
_FALLBACK_OUTPUT_RATE = 1.10


def _estimate_cost(usage: dict[str, Any]) -> float:
    """Estimate cost in USD from token usage.

    Iterates over per-call records to compute a precise estimate using
    model-specific rates.  Falls back to default rates for unknown models.
    """
    total: float = 0.0
    for call in usage.get("calls", []):
        model = call.get("model", "")
        pt = call.get("prompt_tokens", 0)
        ct = call.get("completion_tokens", 0)
        if model in _DEFAULT_COST_RATES:
            in_rate, out_rate = _DEFAULT_COST_RATES[model]
        else:
            in_rate, out_rate = _FALLBACK_INPUT_RATE, _FALLBACK_OUTPUT_RATE
        total += (pt * in_rate + ct * out_rate) / 1_000_000
    return round(total, 6)


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
# Concurrency limit and session tracker state
# ---------------------------------------------------------------------------

_max_concurrent_pipelines: int = 3
_pipeline_semaphore: threading.Semaphore | None = None


def _get_max_concurrent_pipelines() -> int:
    """Return the configured maximum concurrent pipeline count."""
    return _max_concurrent_pipelines


def _init_pipeline_semaphore() -> threading.Semaphore:
    """Create or return the global pipeline semaphore.

    Reads ``pipeline.max_concurrent_pipelines`` from the merged config
    and creates a :class:`threading.Semaphore` with that count.
    """
    global _pipeline_semaphore, _max_concurrent_pipelines
    if _pipeline_semaphore is None:
        from automedia.core.config_loader import load_config

        config = load_config()
        max_val = config.get("pipeline", {}).get("max_concurrent_pipelines", 3)
        _max_concurrent_pipelines = int(max_val) if max_val else 3
        _pipeline_semaphore = threading.Semaphore(_max_concurrent_pipelines)
    return _pipeline_semaphore


def _get_semaphore() -> threading.Semaphore:
    """Return the global semaphore, initialising it on first call."""
    sem = _pipeline_semaphore
    if sem is None:
        sem = _init_pipeline_semaphore()
    return sem


# Active-pipelines JSON persistence path.
_active_pipelines_path: Path | None = None


def _get_active_pipelines_path() -> Path:
    """Return the path to ``active_pipelines.json`` under ``~/.automedia/``."""
    global _active_pipelines_path
    if _active_pipelines_path is None:
        from automedia.core.paths import get_user_config_dir

        _active_pipelines_path = get_user_config_dir() / "active_pipelines.json"
    return _active_pipelines_path


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
# JSON session tracker helpers
# ---------------------------------------------------------------------------


def _read_active_pipelines() -> dict[str, dict[str, Any]]:
    """Read active pipelines from the JSON file, using flock for safety.

    Returns an empty dict when the file does not exist or is corrupt.
    """
    path = _get_active_pipelines_path()
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_SH)
            data: dict[str, dict[str, Any]] = json.load(fh)
    except (json.JSONDecodeError, OSError, ValueError):
        return {}
    return data


def _write_active_pipelines(data: dict[str, dict[str, Any]]) -> None:
    """Atomically write active pipelines dict to the JSON file.

    Uses ``fcntl.flock`` (exclusive) so concurrent writers never
    produce a corrupt file.
    """
    path = _get_active_pipelines_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.rename(path)
    except OSError:
        # Clean up temp file on failure
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _update_pipeline_entry(
    project_id: str,
    updates: dict[str, Any],
) -> None:
    """Read-modify-write a single pipeline entry with flock protection."""
    try:
        data = _read_active_pipelines()
        entry = data.get(project_id, {})
        entry.update(updates)
        data[project_id] = entry
        _write_active_pipelines(data)
    except OSError:
        log.warning(
            "Failed to update active_pipelines.json",
            project_id=project_id,
        )


def _mark_lost_entries() -> None:
    """On server start, mark entries >24h old as ``"lost"``.

    Entries whose ``started_at`` is more than 24 hours in the past
    and whose ``status`` is still ``"running"`` are transitioned to
    ``"lost"`` — they belong to a previous server session that did
    not clean up.
    """
    path = _get_active_pipelines_path()
    if not path.is_file():
        return
    try:
        data = _read_active_pipelines()
        now = datetime.now(UTC)
        changed = False
        for pid, entry in data.items():
            status = entry.get("status", "")
            if status != "running":
                continue
            started_raw = entry.get("started_at")
            if not started_raw:
                continue
            try:
                started = datetime.fromisoformat(started_raw)
            except (ValueError, TypeError):
                continue
            if now - started > timedelta(hours=24):
                entry["status"] = "lost"
                entry["ended_at"] = now.isoformat()
                changed = True
        if changed:
            _write_active_pipelines(data)
    except OSError:
        log.warning("Failed to mark lost entries in active_pipelines.json")


# Run at import time to clean stale entries from previous server sessions.
_mark_lost_entries()


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
        ``{"selected": null, "remaining_count": 0, "error": {...}}``
        where the error dict contains ``code``, ``message``, ``resolution`` keys.
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
            return {
                "selected": None,
                "remaining_count": 0,
                **error_response(
                    MCPErrorCode.NOT_FOUND,
                    "No pending topics found",
                    "Add topics to the pool first",
                ),
            }

        # Sort by score descending
        topics.sort(key=lambda t: t.get("score", 0.0), reverse=True)
        chosen = topics[0]
        db.mark_selected(chosen["id"])
        db.close()
        return success_response({"selected": chosen, "remaining_count": len(topics) - 1})

    except ImportError as exc:
        return {"selected": None, **error_response(MCPErrorCode.IMPORT_ERROR, str(exc))}
    except AutoMediaError as exc:
        return {"selected": None, **error_response(MCPErrorCode.PIPELINE_ERROR, str(exc))}
    except Exception as exc:
        return {"selected": None, **error_response(MCPErrorCode.UNKNOWN, str(exc))}


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
    pattern: ResearchPattern = "b",
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
        return success_response(
            {
                "topics": [],
                "category": category,
                "total_found": 0,
                "note": "pattern_a_raw_data",
            }
        )
    try:
        from automedia.core.llm_client import llm_complete_structured_safe
        from automedia.decision.pydantic import TopicResearchOutput
        from automedia.prompts import load_prompt

        if not trending_data:
            tavily_data = _fetch_tavily_trending(category)
            if tavily_data:
                trending_data = f'Real-time search results for "{category}":\n{tavily_data}'

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
        return success_response(result.model_dump())
    except LLMError as exc:
        return {
            "topics": [],
            "category": category,
            "total_found": 0,
            **error_response(MCPErrorCode.LLM_ERROR, str(exc)),
        }
    except ImportError as exc:
        return {
            "topics": [],
            "category": category,
            "total_found": 0,
            **error_response(MCPErrorCode.IMPORT_ERROR, str(exc)),
        }
    except ValidationError as exc:
        return {
            "topics": [],
            "category": category,
            "total_found": 0,
            **validation_error_response(
                f"LLM response validation failed: {exc}",
                errors=[{"field": str(e.get("loc", "unknown")), "message": e.get("msg", "")}
                        for e in (exc.errors() if hasattr(exc, "errors") else [])],
            ),
        }
    except Exception as exc:
        return {
            "topics": [],
            "category": category,
            "total_found": 0,
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
        }


def run_pipeline(
    topic: NonEmptyStr,
    brand: NonEmptyStr,
    mode: PipelineMode = "auto",
    # DEPRECATED — kept for backward compatibility, scheduled for removal
    decision_mode: str = "build",
    tenant_id: str = "default",
    resume_from: str = "",
    source_path: str = "",
    source_url: str = "",
    workflow: str = "",
    director: bool = False,
    platforms: str = "",
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
    workflow:
        Optional named workflow to apply.  When provided, the workflow's
        mode, platforms, gates, prompts, and media spec are merged over
        the brand profile as a higher-priority config layer.
    director:
        When ``True``, enables director mode with ``pause_on_approval``
        and the ``director`` HITL preset.  Gates with
        ``requires_approval`` will pause for external approve/reject
        calls via the MCP tools.  Default: ``False``.
    platforms:
        Comma-separated list of target platform names (e.g. ``"xiaohongshu,zhihu"``).
        When provided, only gates relevant to those platforms are applied.
        Empty string (default) applies all gates for the brand profile's platforms.

    Returns
    -------
    dict
        ``{"project_id": str, "status": "started"}`` on success, or
        ``{"status": "failed", "error": {"code": ..., "message": ..., "resolution": ...}}``
        on immediate failure.
    """
    # Parse platforms string into list for downstream consumers
    parsed_platforms: list[str] = (
        [p.strip() for p in platforms.split(",") if p.strip()] if platforms else []
    )

    # Pre-validate mode to fail fast
    # Uses VALID_MODES shared constant from runner.py (single source of truth)
    if mode not in VALID_MODES:
        valid_modes = list(VALID_MODES)
        return {
            "status": "failed",
            **error_response(
                MCPErrorCode.INVALID_PARAM,
                f"Unknown pipeline mode {mode!r}. Choose from: {valid_modes}",
            ),
        }

    # Validate workflow name when provided
    if workflow:
        try:
            _validate_workflow(workflow)
        except (FileNotFoundError, ValueError) as exc:
            return {
                "status": "failed",
                **error_response(
                    MCPErrorCode.INVALID_PARAM,
                    f"Unknown workflow {workflow!r}: {exc}",
                ),
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

    # --- Concurrency limit (Part A) ---
    # Acquire the semaphore; reject immediately if at max capacity.
    sem = _get_semaphore()
    if not sem.acquire(blocking=False):
        max_n = _get_max_concurrent_pipelines()
        return {
            "status": "failed",
            **error_response(
                MCPErrorCode.INVALID_PARAM,
                f"At max concurrent pipelines ({max_n}). "
                "Wait for one to finish or cancel one.",
            ),
        }

    project_id = str(uuid.uuid4())[:12]
    progress = PipelineProgress(project_id=project_id)
    with _lock:
        _pipeline_tracker[project_id] = progress

    # --- JSON session tracker (Part B) ---
    _update_pipeline_entry(
        project_id,
        {
            "project_id": project_id,
            "status": "running",
            "started_at": datetime.now(UTC).isoformat(),
            "mode": mode,
            "topic": topic,
            "current_gate": None,
        },
    )

    def _run() -> None:
        """Background thread — wraps pipeline execution in try/except."""
        final_status = "completed"
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
                workflow=workflow or None,
                director=director,
                progress=progress,
                platforms=parsed_platforms,
            )
            progress.project_id = result.project_id
            # Store token usage and estimated cost for get_pipeline_progress
            if result.usage:
                progress.token_usage = {
                    "prompt_tokens": result.usage.get("prompt_tokens", 0),
                    "completion_tokens": result.usage.get("completion_tokens", 0),
                    "total_tokens": result.usage.get("total_tokens", 0),
                }
                progress.estimated_cost_usd = _estimate_cost(result.usage)
        except Exception as exc:
            # Background thread catch-all — pipeline errors stored in progress
            progress.error = str(exc)
            progress.mark_finished()
            final_status = "failed"
        finally:
            # Always release the semaphore so the next pipeline can start.
            # Always persist the final status to the JSON tracker.
            sem.release()
            _update_pipeline_entry(
                project_id,
                {
                    "status": final_status,
                    "ended_at": datetime.now(UTC).isoformat(),
                    "current_gate": progress.current_gate,
                },
            )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return success_response({"project_id": project_id, "status": "started"})


def run_batch(
    topics: list[str],
    brand: NonEmptyStr,
    mode: PipelineMode = "auto",
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
        "project_id": str, "error": dict | None}``.
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
            results.append(
                {
                    "topic": topic,
                    "status": pipeline_result.status,
                    "project_id": pipeline_result.project_id,
                    "error": pipeline_result.error,
                }
            )
        except Exception as exc:
            # MCP boundary: per-topic catch-all so one failure doesn't stop the batch
            results.append(
                {
                    "topic": topic,
                    "status": "failed",
                    "project_id": "",
                    "error": str(exc),
                }
            )

    passed = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - passed
    return success_response(
        {
            "results": results,
            "total": len(results),
            "passed": passed,
            "failed": failed,
        }
    )


def batch_run(
    topics: list[str],
    brand: NonEmptyStr,
    mode: PipelineMode = "auto",
) -> dict[str, Any]:
    """⚠️ DEPRECATED: Use :func:`run_batch` instead."""
    warnings.warn(
        "batch_run is deprecated, use run_batch instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return run_batch(topics=topics, brand=brand, mode=mode)


def get_pipeline_progress(
    project_id: NonEmptyStr,
    since_index: int = 0,
) -> dict[str, Any]:
    """Get current progress of a running pipeline by project_id.

    Poll this after ``run_pipeline`` to observe gate execution in real
    time.  Returns the current gate, a list of gate progress events
    (start / passed / failed), and any error captured from the background
    thread.

    Parameters
    ----------
    project_id:
        The project id returned by ``run_pipeline``.
    since_index:
        Optional index to filter events — only events at or after this
        index are returned.  Default ``0`` (return all events).

    Returns
    -------
    dict
        ``{"project_id", "current_gate", "gates_done", "gates_remaining",
        "total_gates", "events", "error", "is_running", "is_failed",
        "elapsed_s", "token_usage", "estimated_cost_usd"}`` or
        ``{"error": {"code": ..., "message": ..., "resolution": ...}}``.

        When the pipeline has completed (``is_running=false,
        is_failed=false``), ``token_usage`` contains
        ``{"prompt_tokens", "completion_tokens", "total_tokens"}``
        and ``estimated_cost_usd`` is a float cost estimate based on
        per-model pricing.
    """
    with _lock:
        progress = _pipeline_tracker.get(project_id)
    if not progress:
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"No active pipeline found for project_id {project_id!r}",
            "Check project_id or start a pipeline first",
        )
    data = dict(progress.get_progress())
    if since_index > 0:
        data["events"] = data.get("events", [])[since_index:]
    return success_response(data)


def list_active_pipelines() -> dict[str, Any]:
    """Return all active and recently-finished pipelines.

    Reads the ``active_pipelines.json`` session file and returns every
    entry whose status is ``"running"``, together with entries that
    finished within the last 5 minutes (for recovery context).

    This tool survives server restarts — entries from previous sessions
    that are older than 24h are marked ``"lost"``.

    Returns
    -------
    dict
        ``{"pipelines": [...], "count": int}`` where each entry contains
        ``project_id``, ``status``, ``current_gate``, ``elapsed_s``,
        ``mode``, and ``topic``.
    """
    try:
        data = _read_active_pipelines()
        now = datetime.now(UTC)
        five_min_ago = now - timedelta(minutes=5)
        pipelines: list[dict[str, Any]] = []
        for entry in data.values():
            status = entry.get("status", "unknown")
            current_gate: str | None = entry.get("current_gate")
            # Compute elapsed time from started_at
            started_raw = entry.get("started_at")
            elapsed_s = 0.0
            if started_raw:
                try:
                    started = datetime.fromisoformat(started_raw)
                    if status == "running":
                        elapsed_s = (now - started).total_seconds()
                    else:
                        ended_raw = entry.get("ended_at")
                        if ended_raw:
                            ended = datetime.fromisoformat(ended_raw)
                            elapsed_s = (ended - started).total_seconds()
                        else:
                            elapsed_s = (now - started).total_seconds()
                except (ValueError, TypeError):
                    pass
            # Include pipeline if it is "running", finished within 5 min,
            # or marked "lost" (so the caller can see what was lost).
            if status == "running" or status == "lost":
                pipelines.append(
                    {
                        "project_id": entry.get("project_id", ""),
                        "status": status,
                        "current_gate": current_gate,
                        "elapsed_s": round(elapsed_s, 1),
                        "mode": entry.get("mode", ""),
                        "topic": entry.get("topic", ""),
                    }
                )
            elif ended_raw_str := entry.get("ended_at"):
                try:
                    ended = datetime.fromisoformat(ended_raw_str)
                    if ended >= five_min_ago:
                        pipelines.append(
                            {
                                "project_id": entry.get("project_id", ""),
                                "status": status,
                                "current_gate": current_gate,
                                "elapsed_s": round(elapsed_s, 1),
                                "mode": entry.get("mode", ""),
                                "topic": entry.get("topic", ""),
                            }
                        )
                except (ValueError, TypeError):
                    pass

        pipelines.sort(key=lambda p: p.get("elapsed_s", 0.0), reverse=True)
        return success_response({"pipelines": pipelines, "count": len(pipelines)})
    except OSError as exc:
        return {"pipelines": [], "count": 0, **error_response(MCPErrorCode.UNKNOWN, f"File I/O error: {exc}")}
    except Exception as exc:
        return {"pipelines": [], **error_response(MCPErrorCode.UNKNOWN, str(exc))}


def get_pipeline_status(
    project_id: NonEmptyStr,
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
            return error_response(
                MCPErrorCode.NOT_FOUND,
                f"Project {project_id!r} not found",
                "Verify project_id",
            )
        proj = match[0]
        proj_dir = proj.get("_dir", "")
        subdirs = []
        if proj_dir and Path(proj_dir).is_dir():
            subdirs = sorted(
                str(p.relative_to(proj_dir)) for p in Path(proj_dir).iterdir() if p.is_dir()
            )
        return success_response({"project": proj, "subdirs": subdirs})

    except PermissionError as exc:
        return error_response(MCPErrorCode.UNKNOWN, f"Permission denied: {exc}")
    except OSError as exc:
        return error_response(MCPErrorCode.UNKNOWN, f"File I/O error: {exc}")


def list_projects(
    base_dir: str = ".",
    status: ProjectStatusFilter = "",
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
        return success_response({"projects": projects, "count": len(projects)})

    except PermissionError as exc:
        return {"projects": [], "count": 0, **error_response(MCPErrorCode.UNKNOWN, f"Permission denied: {exc}")}
    except OSError as exc:
        return {"projects": [], "count": 0, **error_response(MCPErrorCode.UNKNOWN, f"File I/O error scanning projects: {exc}")}
    except Exception as exc:
        return {"projects": [], **error_response(MCPErrorCode.UNKNOWN, str(exc))}


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
        return success_response({"assets": assets, "count": len(assets)})

    except PermissionError as exc:
        return {"assets": [], **error_response(MCPErrorCode.UNKNOWN, f"Permission denied: {exc}")}
    except OSError as exc:
        return {"assets": [], **error_response(MCPErrorCode.UNKNOWN, f"File I/O error scanning assets: {exc}")}
    except Exception as exc:
        return {"assets": [], **error_response(MCPErrorCode.UNKNOWN, str(exc))}


def archive_project(
    project_id: NonEmptyStr,
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
            return {
                "archived": False,
                **error_response(
                    MCPErrorCode.NOT_FOUND,
                    f"Project {project_id!r} not found",
                    "Verify project_id",
                ),
            }

        proj = match[0]
        status_val = str(proj.get("status", ""))
        if status_val != "published" and not force:
            return {
                "archived": False,
                **error_response(
                    MCPErrorCode.INVALID_PARAM,
                    (
                        f"Refused: project status is '{status_val}', not 'published'. "
                        f"Set force=True to override (Red Line 8)."
                    ),
                ),
            }

        project_dir = Path(proj["_dir"])
        archive_dir = project_dir.parent / f"{project_dir.name}_archived"
        if archive_dir.exists():
            return {
                "archived": False,
                **error_response(
                    MCPErrorCode.INVALID_PARAM,
                    f"Archive target already exists: {archive_dir}",
                ),
            }

        project_dir.rename(archive_dir)
        return success_response({"archived": True, "archive_dir": str(archive_dir)})

    except PermissionError as exc:
        return {"archived": False, **error_response(MCPErrorCode.UNKNOWN, f"Permission denied: {exc}", "Check file permissions")}
    except OSError as exc:
        return {"archived": False, **error_response(MCPErrorCode.UNKNOWN, f"File operation error: {exc}")}
    except Exception as exc:
        return {"archived": False, **error_response(MCPErrorCode.UNKNOWN, str(exc))}


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
        return success_response({"topics": topics, "count": len(topics)})

    except ImportError as exc:
        return {"topics": [], **error_response(MCPErrorCode.IMPORT_ERROR, str(exc))}
    except AutoMediaError as exc:
        return {"topics": [], **error_response(MCPErrorCode.PIPELINE_ERROR, str(exc))}
    except Exception as exc:
        return {"topics": [], **error_response(MCPErrorCode.UNKNOWN, str(exc))}


def add_pool_topic(
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
            _require_allowed(pool_db_path, tool_name="add_pool_topic")
            db = PoolDB(pool_db_path)
        else:
            db = PoolDB(":memory:")

        topic_id = db.add_topic(data={"title": title, "category": category})
        db.close()
        return success_response(
            {
                "id": topic_id,
                "title": title,
                "category": category,
                "status": "pending",
            }
        )
    except ImportError as exc:
        return error_response(MCPErrorCode.IMPORT_ERROR, str(exc))
    except AutoMediaError as exc:
        return error_response(MCPErrorCode.PIPELINE_ERROR, str(exc))
    except Exception as exc:
        return error_response(MCPErrorCode.UNKNOWN, str(exc))


def pool_add_topic(
    title: str,
    category: str = "",
    pool_db_path: str = "",
) -> dict[str, Any]:
    """⚠️ DEPRECATED: Use :func:`add_pool_topic` instead."""
    warnings.warn(
        "pool_add_topic is deprecated, use add_pool_topic instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return add_pool_topic(title=title, category=category, pool_db_path=pool_db_path)


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
        schedules: list[dict[str, Any]] = data.get("pipeline_schedules", []) or []
        # Ensure backward compat: default missing platform/mode to ""
        for s in schedules:
            s.setdefault("platform", "")
            s.setdefault("mode", "")
        return schedules
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
    name: NonEmptyStr,
    expression: CronExpression,
    brand: str = "",
    category: str = "",
    count: int = 1,
    platform: str = "",
    mode: str = "",
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
    platform:
        Target platform for the pipeline (optional, validated against known adapters).
    mode:
        Pipeline mode to use (optional, validated against VALID_MODES).

    Returns
    -------
    dict
        ``{"added": True, "name": str}`` or
        ``{"error": {"code": ..., "message": ..., "resolution": ...}}``.
    """
    import re

    if not re.match(r"^(\S+\s+){4}\S+$", expression.strip()):
        return error_response(
            MCPErrorCode.INVALID_PARAM,
            f"Invalid cron expression {expression!r}: must have exactly 5 fields",
        )

    if platform:
        from automedia.adapters.registry import AdapterRegistry

        known_platforms = AdapterRegistry.list()
        if platform not in known_platforms:
            return error_response(
                MCPErrorCode.INVALID_PARAM,
                f"Unknown platform {platform!r}. Choose from: {known_platforms}",
            )

    if mode and mode not in VALID_MODES:
        valid_modes = list(VALID_MODES)
        return error_response(
            MCPErrorCode.INVALID_PARAM,
            f"Unknown pipeline mode {mode!r}. Choose from: {valid_modes}",
        )

    schedules = _read_pipeline_schedules()

    if any(s.get("name") == name for s in schedules):
        return error_response(
            MCPErrorCode.INVALID_PARAM,
            f"Schedule {name!r} already exists",
        )

    schedules.append(
        {
            "name": name,
            "expression": expression,
            "brand": brand,
            "category": category,
            "count": count,
            "platform": platform,
            "mode": mode,
        }
    )

    try:
        _write_pipeline_schedules(schedules)
        return success_response({"added": True, "name": name})
    except OSError as exc:
        return error_response(MCPErrorCode.UNKNOWN, f"File I/O error writing schedule: {exc}")
    except yaml.YAMLError as exc:
        return error_response(MCPErrorCode.UNKNOWN, f"YAML serialization error: {exc}")


def list_cron_schedules(
    platform: str = "",
    mode: str = "",
) -> dict[str, Any]:
    """List cron schedule entries from ``cron/jobs.yaml``, with optional filters.

    Parameters
    ----------
    platform:
        Optional platform filter — only return schedules for this platform.
    mode:
        Optional pipeline mode filter — only return schedules matching this mode.

    Returns
    -------
    dict
        ``{"schedules": [...], "count": int}``.
    """
    try:
        schedules = _read_pipeline_schedules()
        if platform:
            schedules = [s for s in schedules if s.get("platform") == platform]
        if mode:
            schedules = [s for s in schedules if s.get("mode") == mode]
        schedules.sort(key=lambda s: s.get("name", ""))
        return success_response({"schedules": schedules, "count": len(schedules)})
    except OSError as exc:
        return {"schedules": [], **error_response(MCPErrorCode.UNKNOWN, f"File I/O error reading schedules: {exc}")}
    except yaml.YAMLError as exc:
        return {"schedules": [], **error_response(MCPErrorCode.UNKNOWN, f"YAML parse error: {exc}")}


def list_workflows() -> dict[str, Any]:
    """List all defined workflow configurations.

    Uses :class:`~automedia.core.workflow.WorkflowLoader` to discover
    workflow YAML files from both the project-level
    (``.automedia/workflows/``) and user-level
    (``~/.automedia/workflows/``) directories.  Returns summary metadata
    for each workflow — name, mode, target platforms, and optional
    schedule / brand / gates / prompts / media fields.

    Returns
    -------
    dict
        ``{"workflows": [...], "count": int}``.  Each entry is a flat
        dict with at least ``name``, ``mode``, and ``platforms`` keys.
        Returns empty list (not an error) when no workflows are defined.
    """
    try:
        from automedia.core.workflow import WorkflowLoader

        loader = WorkflowLoader()
        workflows = loader.load_all()

        result: list[dict[str, Any]] = []
        for name, wf in sorted(workflows.items()):
            entry: dict[str, Any] = {
                "name": wf.name,
                "mode": wf.mode,
                "platforms": wf.platforms,
            }
            if wf.brand is not None:
                entry["brand"] = wf.brand
            if wf.schedule is not None:
                entry["schedule"] = wf.schedule
            if wf.gates is not None:
                entry["gates"] = wf.gates
            if wf.prompts is not None:
                entry["prompts"] = wf.prompts
            if wf.media is not None:
                entry["media"] = wf.media
            if wf.extends is not None:
                entry["extends"] = wf.extends
            result.append(entry)

        return success_response({"workflows": result, "count": len(result)})

    except FileNotFoundError as exc:
        return {"workflows": [], **error_response(MCPErrorCode.CONFIG_MISSING, f"Workflow file not found: {exc}")}
    except ConfigError as exc:
        return {"workflows": [], **error_response(MCPErrorCode.CONFIG_MISSING, str(exc))}
    except Exception as exc:
        return {"workflows": [], **error_response(MCPErrorCode.UNKNOWN, str(exc))}


def _validate_workflow(name: str) -> None:
    """Validate that a workflow name exists.  Raises ValueError on failure."""
    from automedia.core.workflow import WorkflowLoader

    loader = WorkflowLoader()
    # Attempt to load — will raise FileNotFoundError if missing
    loader.load(name)


def remove_cron_schedule(name: NonEmptyStr) -> dict[str, Any]:
    """Remove a cron schedule entry by name.

    Parameters
    ----------
    name:
        Name of the schedule entry to remove.

    Returns
    -------
    dict
        ``{"removed": True, "name": str}`` or
        ``{"error": {"code": ..., "message": ..., "resolution": ...}}``.
    """
    schedules = _read_pipeline_schedules()

    before = len(schedules)
    schedules = [s for s in schedules if s.get("name") != name]

    if len(schedules) == before:
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"Schedule {name!r} not found",
            "Check schedule name",
        )

    try:
        _write_pipeline_schedules(schedules)
        return success_response({"removed": True, "name": name})
    except OSError as exc:
        return error_response(MCPErrorCode.UNKNOWN, f"File I/O error writing schedule: {exc}")
    except yaml.YAMLError as exc:
        return error_response(MCPErrorCode.UNKNOWN, f"YAML serialization error: {exc}")


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
        return success_response(
            {
                "jobs_valid": False,
                "schedule_count": 0,
                "job_count": 0,
                "static_jobs": [],
                "note": "cron/jobs.yaml not found",
            }
        )

    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:
        # MCP boundary: YAML parse errors are non-fatal
        return success_response(
            {
                "jobs_valid": False,
                "schedule_count": 0,
                "job_count": 0,
                "static_jobs": [],
                "note": f"parse error: {exc}",
            }
        )

    if not isinstance(data, dict):
        return success_response(
            {
                "jobs_valid": False,
                "schedule_count": 0,
                "job_count": 0,
                "static_jobs": [],
                "note": "jobs.yaml is not a valid dict",
            }
        )

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
        valid = isinstance(expr, str) and bool(re.match(r"^(\S+\s+){4}\S+$", expr.strip()))

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
            entry["next_triggers_note"] = "Expression does not match 5-field cron syntax."

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

    return success_response(
        {
            "jobs_valid": True,
            "schedule_count": len(pipeline_schedules),
            "valid_expressions": valid_count,
            "invalid_expressions": len(pipeline_schedules) - valid_count,
            "schedules": schedules,
            "job_count": len(static_jobs),
            "static_jobs": job_details,
            "note": " ".join(notes),
        }
    )


def test_cron_schedule(
    expression: CronExpression,
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
        ``{"valid": False, "expression": str,
        "error": {"code": ..., "message": ..., "resolution": ...}}``
        on invalid syntax or computation failure.
    """
    import re

    if not re.match(r"^(\S+\s+){4}\S+$", expression.strip()):
        return {
            "valid": False,
            "expression": expression,
            **error_response(
                MCPErrorCode.INVALID_PARAM,
                f"Invalid cron expression {expression!r}: must have exactly 5 fields",
            ),
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

        return success_response(
            {
                "valid": True,
                "expression": expression,
                "next_triggers": next_triggers,
                "note": None,
            }
        )
    except ImportError:
        return success_response(
            {
                "valid": True,
                "expression": expression,
                "next_triggers": None,
                "note": (
                    "croniter not available — install with 'pip install croniter' "
                    "to compute next trigger times. The expression format is valid."
                ),
            }
        )
    except Exception as exc:
        # MCP boundary: croniter computation failures are non-fatal
        return {
            "valid": False,
            "expression": expression,
            **error_response(
                MCPErrorCode.UNKNOWN,
                f"Cron expression {expression!r} is syntactically valid but "
                f"croniter failed to compute next triggers: {exc}",
            ),
        }


# ---------------------------------------------------------------------------
# Prompt template metadata — known Jinja2 variables per template
# ---------------------------------------------------------------------------

_PROMPT_METADATA: dict[str, dict[str, Any]] = {
    "brand_strategy": {
        "variables": ["brand_name", "industry", "target_audience", "context"],
        "purpose": "Generate a brand positioning, audience analysis, and messaging strategy via LLM.",
    },
    "content_quality": {
        "variables": ["content", "criteria", "brand"],
        "purpose": "Score content quality against specified criteria using LLM evaluation.",
    },
    "content_writer": {
        "variables": ["topic", "brand"],
        "purpose": "Write a full article draft for Chinese social media platforms.",
    },
    "copy_review_g2": {
        "variables": ["content", "brand_guidelines"],
        "purpose": "Evaluate content tone, style, and brand compliance (Gate G2).",
    },
    "fact_check_g0": {
        "variables": ["content"],
        "purpose": "Verify factual claims in content against known knowledge (Gate G0).",
    },
    "fact_check_g0_plausibility": {
        "variables": ["content", "topic"],
        "purpose": "Plausibility check for content lacking source material (Gate G0).",
    },
    "humanizer_g1": {
        "variables": ["content"],
        "purpose": "Detect AI writing patterns and assess natural readability (Gate G1).",
    },
    "image_prompt": {
        "variables": ["topic", "brand", "image_index"],
        "purpose": "Generate Stable Diffusion / ComfyUI image prompts for cover art.",
    },
    "pipeline_strategy": {
        "variables": ["topic", "brand", "mode", "context"],
        "purpose": "Design content production strategy — structure, platform, and angles.",
    },
    "topic_research": {
        "variables": ["category", "count", "trending_data"],
        "purpose": "Research trending topics within a category and recommend angles.",
    },
    # Platform-specific overrides
    "platforms/wechat/content_writer": {
        "variables": ["topic", "brand", "tone", "platform", "audience", "brand_guidelines"],
        "purpose": "WeChat-specific content writer template (long-form, formal article).",
    },
}


def list_overridable_templates() -> dict[str, Any]:
    """List all overridable prompt templates with metadata and override status.

    Enumerates every known Jinja2 prompt template, checks whether a user
    override file exists in ``~/.automedia/overrides/prompts/``, and reports
    the template's variables, purpose, and override state.

    Returns
    -------
    dict
        ``{"templates": [...], "count": int, "overrides_dir": str}`` where
        each template entry contains ``name``, ``path``, ``variables``,
        ``purpose``, ``overridden``, ``override_path``, and
        ``platform_overrides``.
    """
    try:
        from automedia.prompts import load_prompt as _  # noqa: F401 — ensure prompts module loaded
    except Exception:
        pass

    from automedia.core.paths import get_user_config_dir

    prompts_pkg_dir = Path(__file__).resolve().parent.parent / "prompts"
    overrides_prompts_dir = get_user_config_dir() / "overrides" / "prompts"

    templates: list[dict[str, Any]] = []
    seen: set[str] = set()

    for stem, meta in sorted(_PROMPT_METADATA.items()):
        name = stem
        # Determine the built-in path
        if "/" in stem:
            # Platform-scoped template: platforms/wechat/content_writer
            builtin_path = prompts_pkg_dir / f"{stem.replace('/', '/')}.j2"
        else:
            builtin_path = prompts_pkg_dir / f"{stem}.j2"

        path = str(builtin_path) if builtin_path.exists() else ""

        # Check global override
        global_override = overrides_prompts_dir / f"{name.split('/')[-1]}.j2"
        overridden = global_override.exists()
        override_path = str(global_override) if overridden else ""

        # Check platform-scoped overrides
        platform_overrides: dict[str, str] = {}
        if overrides_prompts_dir.is_dir():
            for plat_dir in sorted(overrides_prompts_dir.iterdir()):
                if plat_dir.is_dir():
                    plat_override = plat_dir / f"{name.split('/')[-1]}.j2"
                    if plat_override.exists():
                        platform_overrides[plat_dir.name] = str(plat_override)

        templates.append(
            {
                "name": name,
                "path": path,
                "variables": meta["variables"],
                "purpose": meta["purpose"],
                "overridden": overridden,
                "override_path": override_path,
                "platform_overrides": platform_overrides,
            }
        )
        seen.add(name)

    return success_response(
        {
            "templates": templates,
            "count": len(templates),
            "overrides_dir": str(overrides_prompts_dir),
        }
    )


def publish_content(
    project_id: NonEmptyStr,
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
            return {
                "published": False,
                **error_response(
                    MCPErrorCode.NOT_FOUND,
                    f"Project {project_id!r} not found",
                    "Verify project_id",
                ),
            }

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

        # -- Log distribution attempts to asset library -------------------
        try:
            from automedia.asset_library.db import AssetDatabase

            db = AssetDatabase(brand_name or "default")
            for key, res in result.items():
                res_platform = res.get("platform", key)
                res_status = res.get("status", "")
                distro_status: str = "failure"
                if res_status in ("ok", "published", "success"):
                    distro_status = "success"
                elif res_status == "draft_created":
                    distro_status = "draft_created"
                elif res_status == "skipped":
                    distro_status = "skipped"

                db.log_distribution(
                    project_id=project_id,
                    platform=res_platform,
                    status=distro_status,
                    account_id=key if account_ids else "",
                    error_message=res.get("reason", res.get("error_message", "")),
                    url=res.get("url", ""),
                )
        except Exception as exc:
            log.warning("publish.distro_log_failed", error=str(exc))

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
        return success_response(base_response)
    except ImportError as exc:
        return {"published": False, **error_response(MCPErrorCode.IMPORT_ERROR, str(exc))}
    except OSError as exc:
        return {"published": False, **error_response(MCPErrorCode.UNKNOWN, f"File I/O error: {exc}")}
    except AutoMediaError as exc:
        return {"published": False, **error_response(MCPErrorCode.PIPELINE_ERROR, str(exc))}
    except Exception as exc:
        return {"published": False, **error_response(MCPErrorCode.UNKNOWN, str(exc))}


def cancel_pipeline(project_id: NonEmptyStr) -> dict[str, Any]:
    """Cancel a running pipeline by project_id.

    Sets the pipeline's cancellation flag so that the next gate
    boundary will exit early.

    Parameters
    ----------
    project_id:
        The project id returned by ``run_pipeline``.

    Returns
    -------
    dict
        ``{"cancelled": True, "project_id": str}`` or error.
    """
    with _lock:
        progress = _pipeline_tracker.get(project_id)
    if not progress:
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"No active pipeline found for project_id {project_id!r}",
            "Check project_id or start a pipeline first",
        )
    progress.cancel()
    return success_response({"cancelled": True, "project_id": project_id})


def pause_pipeline(project_id: NonEmptyStr) -> dict[str, Any]:
    """Pause a running pipeline by project_id.

    Signals the pipeline to pause after the current gate completes.

    Parameters
    ----------
    project_id:
        The project id returned by ``run_pipeline``.

    Returns
    -------
    dict
        ``{"paused": True, "project_id": str}`` or error.
    """
    with _lock:
        progress = _pipeline_tracker.get(project_id)
    if not progress:
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"No active pipeline found for project_id {project_id!r}",
            "Check project_id or start a pipeline first",
        )
    progress.pause()
    return success_response({"paused": True, "project_id": project_id})


def resume_pipeline(project_id: NonEmptyStr) -> dict[str, Any]:
    """Resume a paused pipeline by project_id.

    Resumes execution of a previously paused pipeline.

    Parameters
    ----------
    project_id:
        The project id returned by ``run_pipeline``.

    Returns
    -------
    dict
        ``{"resumed": True, "project_id": str}`` or error.
    """
    with _lock:
        progress = _pipeline_tracker.get(project_id)
    if not progress:
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"No active pipeline found for project_id {project_id!r}",
            "Check project_id or start a pipeline first",
        )
    progress.resume()
    return success_response({"resumed": True, "project_id": project_id})


def retry_gate(project_id: NonEmptyStr, gate_name: NonEmptyStr) -> dict[str, Any]:
    """Mark a specific gate for retry in a running pipeline.

    Tells the pipeline to re-execute the named gate on its next
    iteration.

    Parameters
    ----------
    project_id:
        The project id returned by ``run_pipeline``.
    gate_name:
        Name of the gate to retry (e.g. ``"G0"``, ``"V3"``).

    Returns
    -------
    dict
        ``{"retrying": True, "project_id": str, "gate_name": str}``
        or error.
    """
    with _lock:
        progress = _pipeline_tracker.get(project_id)
    if not progress:
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"No active pipeline found for project_id {project_id!r}",
            "Check project_id or start a pipeline first",
        )
    progress.mark_retry_gate(gate_name)
    return success_response({"retrying": True, "project_id": project_id, "gate_name": gate_name})


def skip_gate(project_id: NonEmptyStr, gate_name: NonEmptyStr) -> dict[str, Any]:
    """Mark a specific gate for skipping in a running pipeline.

    Tells the pipeline to skip the named gate on its next iteration.

    Parameters
    ----------
    project_id:
        The project id returned by ``run_pipeline``.
    gate_name:
        Name of the gate to skip (e.g. ``"G0"``, ``"V3"``).

    Returns
    -------
    dict
        ``{"skipping": True, "project_id": str, "gate_name": str}``
        or error.
    """
    with _lock:
        progress = _pipeline_tracker.get(project_id)
    if not progress:
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"No active pipeline found for project_id {project_id!r}",
            "Check project_id or start a pipeline first",
        )
    progress.mark_skip_gate(gate_name)
    return success_response({"skipping": True, "project_id": project_id, "gate_name": gate_name})


# ---------------------------------------------------------------------------
# Approval / rejection tools (director mode)
# ---------------------------------------------------------------------------


def approve_gate(
    project_id: NonEmptyStr,
    gate_name: NonEmptyStr,
    modifications: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Approve a gate output and resume pipeline execution.

    Finds the active :class:`GateEngine` for *project_id* and calls
    ``resume(gate_name, approved=True)`` to unblock a gate that is
    paused for approval.

    Parameters
    ----------
    project_id:
        The project id returned by ``run_pipeline``.
    gate_name:
        Name of the gate to approve (e.g. ``"G0"``, ``"V3"``).
    modifications:
        Optional modifications to apply to the gate result before
        continuing (e.g. ``{"content": "revised text"}``).

    Returns
    -------
    dict
        ``{"approved": True, "project_id": str, "gate_name": str}``
        or an error dict when the engine or gate is not found.
    """
    engine = get_registered_engine(project_id)
    if engine is None:
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"No active engine found for project_id {project_id!r}",
            "Check project_id or start a pipeline first",
        )
    try:
        engine.resume(gate_name=gate_name, approved=True, modifications=modifications)
    except KeyError as exc:
        return error_response(
            MCPErrorCode.INVALID_PARAM,
            str(exc),
            "Check gate_name — gate may not be paused for approval",
        )
    return success_response({"approved": True, "project_id": project_id, "gate_name": gate_name})


def reject_gate(
    project_id: NonEmptyStr,
    gate_name: NonEmptyStr,
    reason: str = "",
) -> dict[str, Any]:
    """Reject a gate output and resume pipeline execution.

    Finds the active :class:`GateEngine` for *project_id* and calls
    ``resume(gate_name, approved=False)`` to unblock a gate that is
    paused for approval, marking the gate as rejected.

    Parameters
    ----------
    project_id:
        The project id returned by ``run_pipeline``.
    gate_name:
        Name of the gate to reject (e.g. ``"G0"``, ``"V3"``).
    reason:
        Optional human-readable explanation for the rejection.

    Returns
    -------
    dict
        ``{"rejected": True, "project_id": str, "gate_name": str}``
        or an error dict when the engine or gate is not found.
    """
    engine = get_registered_engine(project_id)
    if engine is None:
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"No active engine found for project_id {project_id!r}",
            "Check project_id or start a pipeline first",
        )
    modifications: dict[str, Any] = {"reason": reason} if reason else {}
    try:
        engine.resume(gate_name=gate_name, approved=False, modifications=modifications)
    except KeyError as exc:
        return error_response(
            MCPErrorCode.INVALID_PARAM,
            str(exc),
            "Check gate_name — gate may not be paused for approval",
        )
    return success_response({"rejected": True, "project_id": project_id, "gate_name": gate_name})


def get_pending_approvals(
    project_id: str = "",
) -> dict[str, Any]:
    """List gates currently awaiting approval in active pipelines.

    When *project_id* is provided, only gates for that project are
    returned.  Otherwise returns all pending approvals across every
    active engine.

    Parameters
    ----------
    project_id:
        Optional project filter.  When empty, returns pending approvals
        from all active engines.

    Returns
    -------
    dict
        ``{"pending_approvals": [...], "count": int}``.  Each entry
        contains ``project_id``, ``gate_name``, and ``status``.
    """
    if project_id:
        engine = get_registered_engine(project_id)
        if engine is None:
            return success_response({"pending_approvals": [], "count": 0})
        pending = [{"project_id": project_id, **entry} for entry in engine.list_pending_approvals()]
        return success_response({"pending_approvals": pending, "count": len(pending)})

    all_pending: list[dict[str, Any]] = []
    for pid, engine in list_registered_engines().items():
        for entry in engine.list_pending_approvals():
            all_pending.append({"project_id": pid, **entry})
    return success_response({"pending_approvals": all_pending, "count": len(all_pending)})


def list_platforms() -> dict[str, Any]:
    """List all registered publishing platforms.

    Uses :class:`automedia.adapters.registry.AdapterRegistry` to enumerate
    all registered adapters by their platform name.

    Returns
    -------
    dict
        ``{"platforms": [...], "total": N}`` — sorted list of platform
        names and their count.  Never raises.  Returns empty list when
        no adapters are registered (not an error).
    """
    from automedia.adapters.registry import AdapterRegistry

    try:
        platforms = AdapterRegistry.list()
        return success_response({"platforms": platforms, "total": len(platforms)})
    except ImportError as exc:
        return {"platforms": [], "total": 0, **error_response(MCPErrorCode.IMPORT_ERROR, str(exc))}
    except AutoMediaError as exc:
        return {"platforms": [], "total": 0, **error_response(MCPErrorCode.ENGINE_ERROR, str(exc))}
    except Exception as exc:
        return {"platforms": [], "total": 0, **error_response(MCPErrorCode.UNKNOWN, str(exc))}


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
        On error: ``{"registered": False,
        "error": {"code": ..., "message": ..., "resolution": ...}}``.
    """
    import re

    if not platform_name or not isinstance(platform_name, str):
        return {
            "registered": False,
            **error_response(
                MCPErrorCode.INVALID_PARAM,
                "platform_name must be a non-empty string.",
            ),
        }
    if not re.match(r"^[a-zA-Z0-9_-]+$", platform_name):
        return {
            "registered": False,
            **error_response(
                MCPErrorCode.INVALID_PARAM,
                (
                    f"Invalid platform_name {platform_name!r}. "
                    f"Use only letters, digits, underscores, and hyphens."
                ),
            ),
        }

    try:
        from automedia.adapters.registry import AdapterRegistry

        if adapter_class:
            module_path, _, class_name = adapter_class.rpartition(".")
            if not module_path:
                return {
                    "registered": False,
                    **error_response(
                        MCPErrorCode.INVALID_PARAM,
                        (
                            f"Invalid adapter_class {adapter_class!r}: "
                            f"must be a dotted path (e.g. 'pkg.mod.ClassName')."
                        ),
                    ),
                }
            if not module_path.startswith("automedia.adapters."):
                return {
                    "registered": False,
                    **error_response(
                        MCPErrorCode.INVALID_PARAM,
                        (
                            f"Invalid adapter class: {adapter_class!r}. "
                            f"Must be in automedia.adapters.* namespace"
                        ),
                    ),
                }
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", class_name):
                return {
                    "registered": False,
                    **error_response(
                        MCPErrorCode.INVALID_PARAM,
                        (
                            f"Invalid class name in {adapter_class!r}. "
                            f"Class name must match [A-Za-z_][A-Za-z0-9_]*."
                        ),
                    ),
                }
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            AdapterRegistry.register(cls)
            return success_response(
                {
                    "registered": True,
                    "platform": platform_name,
                    "class": adapter_class,
                }
            )

        return success_response(
            {
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
        )

    except (ImportError, ModuleNotFoundError) as exc:
        return {
            "registered": False,
            **error_response(
                MCPErrorCode.IMPORT_ERROR,
                f"Could not import adapter class: {exc}",
            ),
        }
    except AttributeError as exc:
        return {
            "registered": False,
            **error_response(
                MCPErrorCode.INVALID_PARAM,
                f"Adapter class not found in module: {exc}",
            ),
        }
    except ModuleLoadError as exc:
        return {
            "registered": False,
            **error_response(
                MCPErrorCode.IMPORT_ERROR,
                str(exc),
            ),
        }
    except Exception as exc:
        return {"registered": False, **error_response(MCPErrorCode.UNKNOWN, str(exc))}


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
        return success_response(
            {
                "md_content": result.md_content,
                "manifest_json": result.manifest,
                "warnings": result.warnings,
            }
        )
    except OSError as exc:
        return {
            "md_content": "",
            "manifest_json": {},
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.UNKNOWN, f"File I/O error: {exc}"),
        }
    except ImportError as exc:
        return {
            "md_content": "",
            "manifest_json": {},
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.IMPORT_ERROR, str(exc)),
        }
    except Exception as exc:
        return {
            "md_content": "",
            "manifest_json": {},
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
        }


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
        return success_response(
            {
                "translated_md": result.translated_md,
                "xliff_path": result.xliff_path,
                "warnings": result.warnings,
            }
        )
    except ImportError as exc:
        return {
            "translated_md": "",
            "xliff_path": None,
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.IMPORT_ERROR, str(exc)),
        }
    except LLMError as exc:
        return {
            "translated_md": "",
            "xliff_path": None,
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.LLM_ERROR, str(exc)),
        }
    except Exception as exc:
        return {
            "translated_md": "",
            "xliff_path": None,
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
        }


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
            return success_response(
                {
                    "project_dir": project_dir,
                    "results": results,
                    "warnings": [f"Drafts directory not found: {drafts_dir}"],
                }
            )

        langs = [lang.strip() for lang in target_langs.split(",") if lang.strip()]
        if not langs:
            return success_response(
                {
                    "project_dir": project_dir,
                    "results": results,
                    "warnings": ["No target languages specified"],
                }
            )

        md_files = sorted(drafts_dir.glob("*.md"))
        if not md_files:
            return success_response(
                {
                    "project_dir": project_dir,
                    "results": results,
                    "warnings": [f"No markdown files found in {drafts_dir}"],
                }
            )

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

        return success_response(
            {
                "project_dir": project_dir,
                "results": results,
                "warnings": warnings,
            }
        )
    except OSError as exc:
        return {
            "project_dir": project_dir,
            "results": {},
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.UNKNOWN, f"File I/O error: {exc}"),
        }
    except LLMError as exc:
        return {
            "project_dir": project_dir,
            "results": {},
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.LLM_ERROR, str(exc)),
        }
    except Exception as exc:
        return {
            "project_dir": project_dir,
            "results": {},
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
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
        return error_response(
            MCPErrorCode.INVALID_PARAM,
            f"Invalid format: {target_format!r} — path separators not allowed",
        )

    if target_format not in _ALLOWED_OUTPUT_FORMATS:
        return error_response(MCPErrorCode.INVALID_PARAM, f"Unsupported format: {target_format!r}")

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
        return success_response(
            {
                "output_path": output_path,
                "output_format": target_format,
                "warnings": errors if errors else [],
            }
        )
    except ImportError as exc:
        return {
            "output_path": "",
            "output_format": target_format,
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.IMPORT_ERROR, str(exc)),
        }
    except AutoMediaError as exc:
        return {
            "output_path": "",
            "output_format": target_format,
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.PIPELINE_ERROR, str(exc)),
        }
    except Exception as exc:
        return {
            "output_path": "",
            "output_format": target_format,
            "warnings": [str(exc)],
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
        }
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
    pattern: ResearchPattern = "b",
    platform: str = "",
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
    platform:
        Optional platform name for platform-specific prompt variants.
        When provided and a platform-specific prompt exists (e.g.
        ``platforms/wechat/content_quality.j2``), that variant is used
        instead of the generic ``content_quality.j2``.  When empty
        (default), the generic prompt is used.

    Returns
    -------
    dict
        ``{"quality_score": float, "issues": list[str],
        "suggestions": list[str], "overall_assessment": str}``
        or an error dict on failure.
    """
    if pattern == "a":
        return success_response(
            {
                "quality_score": 0.5,
                "note": "pattern_a_raw_data",
                "criteria": criteria,
            }
        )
    try:
        from automedia.core.llm_client import llm_complete_structured_safe
        from automedia.decision.pydantic import ContentQualityOutput
        from automedia.prompts import load_prompt

        prompt = load_prompt(
            "content_quality",
            content=content,
            criteria=criteria,
            brand=brand,
            platform=platform if platform else None,
        )
        result = llm_complete_structured_safe(
            prompt,
            response_format=ContentQualityOutput,
        )
        return success_response(result.model_dump())
    except LLMError as exc:
        return {
            "quality_score": 0.0,
            "issues": [],
            "suggestions": [],
            "overall_assessment": "",
            **error_response(MCPErrorCode.LLM_ERROR, str(exc)),
        }
    except ImportError as exc:
        return {
            "quality_score": 0.0,
            "issues": [],
            "suggestions": [],
            "overall_assessment": "",
            **error_response(MCPErrorCode.IMPORT_ERROR, str(exc)),
        }
    except ValidationError as exc:
        return {
            "quality_score": 0.0,
            "issues": [],
            "suggestions": [],
            "overall_assessment": "",
            **validation_error_response(
                f"LLM response validation failed: {exc}",
                errors=[{"field": str(e.get("loc", "unknown")), "message": e.get("msg", "")}
                        for e in (exc.errors() if hasattr(exc, "errors") else [])],
            ),
        }
    except Exception as exc:
        return {
            "quality_score": 0.0,
            "issues": [],
            "suggestions": [],
            "overall_assessment": "",
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
        }


# ---------------------------------------------------------------------------
# Red-line introspection tool
# ---------------------------------------------------------------------------


def get_redlines() -> dict[str, Any]:
    """Return the list of agent red-line constraints.

    Returns
    -------
    dict
        ``{"redlines": [...], "total": N}`` —
        never raises. Each entry is a human-readable constraint description
        sourced from AGENTS.md §5.
    """
    redlines: list[str] = [
        "MUST NOT archive projects using --force unless status is 'published'",
        "MUST NOT commit real production data, topic pool contents, or credentials to git",
        "MUST NOT modify automedia/mcp/mcp_allowlist.yaml without explicit user request",
        "MUST use synthetic test fixtures from tests/fixtures/synth/ for testing",
        "MUST use 'automedia archive' command for archiving — never manual dir operations",
        "MUST follow gate naming convention: G0-G5, V0-V7, L1-L4, H0, pre-gate, CW",
        "MUST add new gates to automedia/gates/failure_modes.py",
        "MUST NOT skip pre-commit checks",
        "MUST respect GateHook readonly contract — hooks observe but never mutate",
    ]
    return success_response({"redlines": redlines, "total": len(redlines)})


# ---------------------------------------------------------------------------
# Health-check tool
# ---------------------------------------------------------------------------


def _detect_first_run() -> bool:
    """Detect if AutoMedia has never been configured (first run).

    Returns ``True`` when **no brands exist** AND (**no LLM API key is
    configured** OR **the ``~/.automedia/`` directory does not exist**).

    The result is purely informational — it does not gate any tool access.
    """
    try:
        from automedia.core.paths import get_user_config_dir

        user_cfg_dir = get_user_config_dir()
        has_config_dir = user_cfg_dir.is_dir()

        # Check for existing brands via brand_profiles.yaml
        brand_file = user_cfg_dir / "brand_profiles.yaml"
        has_brands = bool(
            brand_file.exists()
            and brand_file.stat().st_size > 0
            and brand_file.read_text(encoding="utf-8").strip()
        )

        # Check for LLM API key (env var or model_config.yaml)
        llm_key_env = bool(os.environ.get("AUTOMEDIA_LLM_API_KEY"))

        model_config = user_cfg_dir / "model_config.yaml"
        has_llm_config_file = False
        if model_config.exists():
            try:
                raw = model_config.read_text(encoding="utf-8")
                data = yaml.safe_load(raw) or {}
                llm = data.get("llm", {}).get("text_generation", {})
                has_llm_config_file = bool(llm.get("api_key"))
            except Exception:
                pass

        has_llm_key = llm_key_env or has_llm_config_file

        return not has_brands and (not has_llm_key or not has_config_dir)
    except Exception:
        # Fail-safe: if anything goes wrong, assume not first run
        return False


def health_check() -> dict[str, Any]:
    """Return server health status — version, uptime, tool count, and first_run.

    The ``first_run`` field indicates whether AutoMedia appears to be
    unconfigured (no brands AND no LLM key).  It is **informational only**
    and does not block any tools.

    Returns
    -------
    dict
        ``{"status": "ok", "version": str, "uptime_s": float,
        "tools_count": int, "first_run": bool}``
        or ``{"status": "error",
        "error": {"code": ..., "message": ..., "resolution": ...}}``
        on failure.
    """
    try:
        from automedia._version import __version__

        uptime_s = time.monotonic() - _SERVER_START
        return success_response(
            {
                "status": "ok",
                "version": __version__,
                "uptime_s": round(uptime_s, 2),
                "tools_count": _tools_count,
                "first_run": _detect_first_run(),
            }
        )
    except ImportError as exc:
        return {"status": "error", **error_response(MCPErrorCode.IMPORT_ERROR, str(exc))}
    except Exception as exc:
        return {"status": "error", **error_response(MCPErrorCode.UNKNOWN, str(exc))}


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
        ``{"error": {"code": "NOT_FOUND", "message": "config key '...' not found"}}``, or
        ``{"error": {"code": "ALLOWLIST_DENIED",
        "message": "secret key not exposed"}}`` when the key is secret.
    """
    try:
        from automedia.core.config_loader import load_config

        config = load_config()

        if not key:
            return success_response({"config": _redact_secrets(config)})

        # Reject direct access to secret keys
        if _has_secret_keyword(key.split(".")[-1]):
            return error_response(MCPErrorCode.ALLOWLIST_DENIED, "secret key not exposed")

        value = _deep_get(config, key)
        if value is None:
            return error_response(
                MCPErrorCode.NOT_FOUND,
                f"config key '{key}' not found",
                "Check config key name",
            )

        # Redact any sub-values if the result is a dict
        if isinstance(value, dict):
            value = _redact_secrets(value)

        return success_response({"value": value})
    except ConfigError as exc:
        return error_response(
            MCPErrorCode.CONFIG_MISSING,
            f"Configuration load failed: {exc}",
        )
    except Exception as exc:
        return error_response(MCPErrorCode.UNKNOWN, str(exc))


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
        ``{"brands": [...], "total": N}`` —
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
        return success_response({"brands": brands_list, "total": len(brands_list)})
    except BrandNotFoundError as exc:
        return {"brands": [], "total": 0, **error_response(MCPErrorCode.BRAND_NOT_FOUND, str(exc))}
    except ConfigError as exc:
        return {"brands": [], "total": 0, **error_response(MCPErrorCode.CONFIG_MISSING, str(exc))}
    except Exception as exc:
        return {"brands": [], "total": 0, **error_response(MCPErrorCode.UNKNOWN, str(exc))}


# ---------------------------------------------------------------------------
# Asset library tools
# ---------------------------------------------------------------------------


def search_assets(
    query: str,
    brand: NonEmptyStr,
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
        return success_response({"results": limited, "count": len(limited), "error": None})
    except ImportError as exc:
        return {"results": [], "count": 0, **error_response(MCPErrorCode.IMPORT_ERROR, str(exc))}
    except AutoMediaError as exc:
        return {"results": [], "count": 0, **error_response(MCPErrorCode.UNKNOWN, str(exc))}


# ---------------------------------------------------------------------------
# LLM-driven tools
# ---------------------------------------------------------------------------


def run_brand_strategy(
    brand_name: str,
    industry: str,
    target_audience: str,
    context: str = "",
    pattern: ResearchPattern = "b",
    platform: str = "",
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
    platform:
        Optional platform name for platform-specific prompt variants.
        When provided and a platform-specific prompt exists (e.g.
        ``platforms/wechat/brand_strategy.j2``), that variant is used.

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
        return success_response(
            {
                "note": "pattern_a_raw_data",
                "input": {
                    "brand_name": brand_name,
                    "industry": industry,
                    "target_audience": target_audience,
                    "context": context,
                },
            }
        )
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
            platform=platform if platform else None,
        )
        result = llm_complete_structured_safe(
            prompt,
            response_format=BrandStrategyOutput,
        )
        return success_response(result.model_dump())
    except LLMError as exc:
        return error_response(
            MCPErrorCode.LLM_ERROR,
            f"Brand strategy generation failed: {exc}",
        )
    except ImportError as exc:
        return error_response(MCPErrorCode.IMPORT_ERROR, str(exc))
    except ValidationError as exc:
        return validation_error_response(
            f"LLM response validation failed: {exc}",
            errors=[{"field": str(e.get("loc", "unknown")), "message": e.get("msg", "")}
                    for e in (exc.errors() if hasattr(exc, "errors") else [])],
        )
    except Exception as exc:
        return error_response(MCPErrorCode.UNKNOWN, str(exc))


def run_pipeline_from_strategy(
    topic: NonEmptyStr,
    brand: NonEmptyStr,
    mode: PipelineMode = "auto",
    strategy_context: str = "",
    pattern: ResearchPattern = "b",
    platform: str = "",
    workflow: str = "",
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
    platform:
        Optional platform name for platform-specific prompt variants.
        When provided and a platform-specific prompt exists (e.g.
        ``platforms/wechat/pipeline_strategy.j2``), that variant is used.
    workflow:
        Optional named workflow to apply.  When provided, the workflow's
        mode, platforms, gates, prompts, and media spec are merged over
        the brand profile as a higher-priority config layer.

    Returns
    -------
    dict
        ``{"strategy": {...}, "pipeline_result": {...}}`` on success.
        On failure the dict contains an ``"error"`` key with the
        failure description.
    """
    if pattern == "a":
        return success_response(
            {
                "note": "pattern_a_raw_data",
                "input": {
                    "topic": topic,
                    "brand": brand,
                    "mode": mode,
                    "strategy_context": strategy_context,
                },
            }
        )

    # Validate workflow name when provided
    if workflow:
        try:
            _validate_workflow(workflow)
        except (FileNotFoundError, ValueError) as exc:
            return error_response(
                MCPErrorCode.INVALID_PARAM,
                f"Unknown workflow {workflow!r}: {exc}",
            )

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
            platform=platform if platform else None,
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
            workflow=workflow or None,
        )

        return success_response(
            {
                "strategy": strategy.model_dump(),
                "pipeline_result": _pipeline_result_to_dict(pipeline_result),
            }
        )
    except LLMError as exc:
        return error_response(
            MCPErrorCode.LLM_ERROR,
            f"Strategy generation failed: {exc}",
        )
    except PipelineError as exc:
        return error_response(
            MCPErrorCode.PIPELINE_ERROR,
            f"Pipeline execution failed: {exc}",
        )
    except ValidationError as exc:
        return validation_error_response(
            f"LLM response validation failed: {exc}",
            errors=[{"field": str(e.get("loc", "unknown")), "message": e.get("msg", "")}
                    for e in (exc.errors() if hasattr(exc, "errors") else [])],
        )
    except Exception as exc:
        return error_response(MCPErrorCode.UNKNOWN, str(exc))


def update_engine_config(
    modality: EngineModality,
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
        or ``{"error": {"code": ..., "message": ..., "resolution": ...}}`` on failure.
    """
    from datetime import datetime

    valid_modalities = {"tts", "asr", "image", "video"}

    if modality not in valid_modalities:
        valid_str = ", ".join(sorted(valid_modalities))
        return error_response(
            MCPErrorCode.INVALID_PARAM,
            f"Invalid modality '{modality}'. Valid: {valid_str}",
        )

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

        ts = datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S")
        filename = f"engine-override-{modality}-{ts}.yaml"
        filepath = overrides_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(override_data, f, default_flow_style=False)

        return success_response(
            {
                "status": "ok",
                "modality": modality,
                "setting": setting,
                "value": value,
                "file": str(filepath),
            }
        )
    except OSError as exc:
        return error_response(MCPErrorCode.UNKNOWN, f"File I/O error writing override: {exc}")
    except yaml.YAMLError as exc:
        return error_response(MCPErrorCode.UNKNOWN, f"YAML serialization error: {exc}")


def health_engine() -> dict[str, Any]:
    """Check all engine-related dependencies and return their health status.

    Returns
    -------
    dict
        ``{"engines": [...], "healthy_count": int, "unhealthy_count": int}``
        or ``{"error": {"code": ..., "message": ..., "resolution": ...}}`` on failure.
    """
    try:
        from automedia.core.doctor import Doctor

        engine_deps_set = {
            "comfyui",
            "whisper",
            "edge-tts",
            "hyperframes",
            "chrome",
            "ffmpeg",
            "bun",
            "llm_api",
        }

        all_deps = Doctor().check_dependencies()
        engine_deps = [d for d in all_deps if d["name"] in engine_deps_set]
        healthy = sum(1 for d in engine_deps if d["installed"])
        unhealthy = len(engine_deps) - healthy

        return success_response(
            {
                "engines": engine_deps,
                "healthy_count": healthy,
                "unhealthy_count": unhealthy,
            }
        )
    except ImportError as exc:
        return error_response(
            MCPErrorCode.IMPORT_ERROR,
            f"Doctor module not available: {exc}",
            "Install automedia[doctor] or check your installation",
        )
    except AutoMediaError as exc:
        return error_response(MCPErrorCode.ENGINE_ERROR, str(exc))


def engine_health() -> dict[str, Any]:
    """⚠️ DEPRECATED: Use :func:`health_engine` instead."""
    warnings.warn(
        "engine_health is deprecated, use health_engine instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return health_engine()


# ---------------------------------------------------------------------------
# Setup / Configuration tools (first-time setup)
# ---------------------------------------------------------------------------


def init_config(project_dir: str = "") -> dict[str, Any]:
    """Initialize AutoMedia configuration with sensible defaults.

    Creates the ``.automedia/`` directory structure and a default
    ``config.yaml`` in the target directory.  If *project_dir* is
    provided, creates there; otherwise uses the current working
    directory.

    Parameters
    ----------
    project_dir:
        Optional path to the project root.  When empty, the current
        working directory is used.

    Returns
    -------
    dict
        ``{"success": True, "config_dir": str, "config_file": str}``
        on success, or an error dict on failure.
    """
    try:
        target = Path(project_dir).resolve() if project_dir else Path.cwd()
        automedia_dir = target / ".automedia"
        automedia_dir.mkdir(parents=True, exist_ok=True)

        # Write a minimal config.yaml if one doesn't already exist
        config_path = automedia_dir / "config.yaml"
        if not config_path.exists():
            config: dict[str, Any] = {
                "project": {"name": target.name},
            }
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False)
            os.chmod(config_path, 0o600)

        return success_response(
            {
                "success": True,
                "config_dir": str(automedia_dir),
                "config_file": str(config_path),
            }
        )
    except OSError as exc:
        return {
            "success": False,
            **error_response(MCPErrorCode.UNKNOWN, f"File I/O error initializing config: {exc}"),
        }
    except yaml.YAMLError as exc:
        return {
            "success": False,
            **error_response(MCPErrorCode.UNKNOWN, f"YAML serialization error: {exc}"),
        }


def configure_llm(
    provider: str = "",
    model: str = "",
    api_key: str = "",
) -> dict[str, Any]:
    """Configure the LLM provider for AutoMedia.

    Writes LLM configuration (provider, model, optional API key) to
    ``~/.automedia/model_config.yaml`` by reusing path constants from
    the existing CLI ``init`` command.

    .. warning::

       Storing API keys in config files is less secure than using
       environment variables.  Prefer setting ``AUTOMEDIA_LLM_API_KEY``
       in your shell profile, ``.env`` file, or MCP server ``env`` map.

    Parameters
    ----------
    provider:
        LLM provider name (e.g. ``"openai"``, ``"deepseek"``,
        ``"anthropic"``).
    model:
        Model identifier (e.g. ``"gpt-4o-mini"``, ``"deepseek-chat"``).
        When empty, only the provider is set.
    api_key:
        Optional API key.  Logs a warning that env vars are preferred.

    Returns
    -------
    dict
        ``{"success": True, "provider": str, "model": str,
        "config_file": str}`` on success, or an error dict on failure.
    """
    try:
        from automedia.cli.commands.init_cmd import (
            _MODEL_CONFIG_FILE,
            _USER_CFG_DIR,
        )

        if api_key:
            log.warning(
                "configure_llm: API key stored in plaintext. "
                "Prefer AUTOMEDIA_LLM_API_KEY environment variable instead."
            )

        _USER_CFG_DIR.mkdir(parents=True, exist_ok=True)

        llm_config: dict[str, Any] = {
            "llm": {
                "text_generation": {
                    "provider": provider,
                },
            },
        }
        if model:
            llm_config["llm"]["text_generation"]["model"] = model
        if api_key:
            llm_config["llm"]["text_generation"]["api_key"] = api_key

        with open(_MODEL_CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(llm_config, f, default_flow_style=False)
        os.chmod(_MODEL_CONFIG_FILE, 0o600)

        return success_response(
            {
                "success": True,
                "provider": provider,
                "model": model,
                "config_file": str(_MODEL_CONFIG_FILE),
            }
        )
    except OSError as exc:
        return {
            "success": False,
            **error_response(MCPErrorCode.UNKNOWN, f"File I/O error writing config: {exc}"),
        }
    except yaml.YAMLError as exc:
        return {
            "success": False,
            **error_response(MCPErrorCode.UNKNOWN, f"YAML serialization error: {exc}"),
        }


def add_brand(
    name: str,
    industry: str = "",
    target_audience: str = "",
) -> dict[str, Any]:
    """Create a new brand profile.

    Uses :func:`automedia.manifests.brand_profile_schema.save_brand_profile`
    to write the profile into ``~/.automedia/brand_profiles.yaml``.
    The brand *name* is required; *industry* and *target_audience* are
    optional.

    Parameters
    ----------
    name:
        Brand name (required).  Used as the key in the profiles YAML.
    industry:
        Optional industry / vertical (e.g. ``"SaaS"``, ``"e-commerce"``).
    target_audience:
        Optional audience description (e.g. ``"Tech professionals"``).

    Returns
    -------
    dict
        ``{"success": True, "brand_name": str, "industry": str,
        "target_audience": str}`` on success, or an error dict on
        failure (e.g. empty brand name).
    """
    try:
        from automedia.manifests.brand_profile_schema import (
            save_brand_profile,
        )

        data: dict[str, Any] = {"brand_name": name}
        if industry:
            data["industry"] = industry
        if target_audience:
            data["target_audience"] = target_audience

        save_brand_profile(name, data)

        return success_response(
            {
                "success": True,
                "brand_name": name,
                "industry": industry,
                "target_audience": target_audience,
            }
        )
    except ConfigError as exc:
        return {
            "success": False,
            **error_response(MCPErrorCode.CONFIG_MISSING, str(exc), "Check brand profile configuration"),
        }
    except OSError as exc:
        return {
            "success": False,
            **error_response(MCPErrorCode.UNKNOWN, f"File I/O error saving brand: {exc}"),
        }


def onboard(
    brand_name: str = "",
    llm_provider: str = "",
    llm_key: str = "",
    base_url: str = "",
) -> dict[str, Any]:
    """One-step onboarding: configure LLM and create a brand profile.

    Delegates to the same config-writing logic as the CLI ``automedia onboard``
    wizard (``configure_llm`` for LLM settings, ``add_brand`` for brand) but
    accepts all parameters directly without interactive prompts.

    Parameters
    ----------
    brand_name:
        Brand name to create (optional — skip by leaving empty).
    llm_provider:
        LLM provider name (e.g. ``"openai"``, ``"deepseek"``).
        When empty, LLM configuration is skipped.
    llm_key:
        LLM API key.  Prefer ``AUTOMEDIA_LLM_API_KEY`` env var instead.
    base_url:
        Optional custom API base URL.

    Returns
    -------
    dict
        ``{"success": True, "brand_name": str, "llm_provider": str,
        "config_file": str}`` on success, or an error dict on failure.
    """
    try:
        from automedia.core.paths import get_user_config_dir

        results: dict[str, Any] = {}
        user_cfg_dir = get_user_config_dir()

        # Configure LLM via configure_llm (delegates to CLI init logic)
        if llm_provider:
            llm_result = configure_llm(provider=llm_provider, api_key=llm_key)
            results["llm"] = {
                "provider": llm_provider,
                "config_file": str(user_cfg_dir / "model_config.yaml"),
            }

            # Write base_url separately if provided
            if base_url:
                cfg_path = user_cfg_dir / "model_config.yaml"
                if cfg_path.exists():
                    raw = cfg_path.read_text(encoding="utf-8")
                    data = yaml.safe_load(raw) or {}
                    llm_node = data.setdefault("llm", {}).setdefault(
                        "text_generation", {}
                    )
                    llm_node["base_url"] = base_url
                    cfg_path.write_text(
                        yaml.dump(
                            data, default_flow_style=False, allow_unicode=True
                        ),
                        encoding="utf-8",
                    )

        # Create brand profile via add_brand (delegates to brand profile schema)
        if brand_name:
            brand_result = add_brand(name=brand_name)
            results["brand"] = {
                "brand_name": brand_name,
                "config_file": str(user_cfg_dir / "brand_profiles.yaml"),
            }

        return success_response(
            {
                "success": True,
                "brand_name": brand_name or "",
                "llm_provider": llm_provider or "",
                "config_dir": str(user_cfg_dir),
                **results,
            }
        )
    except Exception as exc:
        # MCP boundary: catch-all for file I/O errors
        return {
            "success": False,
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
        }
