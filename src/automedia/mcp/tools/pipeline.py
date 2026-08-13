"""Pipeline execution and lifecycle MCP tools."""
from __future__ import annotations

import threading
import uuid
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from structlog import get_logger

from automedia.mcp.tools._shared import (
    VALID_MODES,
    MCPErrorCode,
    NonEmptyStr,
    PipelineMode,
    PipelineProgress,
    _discover_projects,
    _estimate_cost,
    _get_max_concurrent_pipelines,
    _get_semaphore,
    _lock,
    _pipeline_tracker,
    _read_active_pipelines,
    _require_allowed,
    _update_pipeline_entry,
    _validate_workflow,
    bind_correlation_id,
    error_response,
    success_response,
)

log = get_logger(__name__)

__all__ = [
    "batch_run",
    "cancel_pipeline",
    "get_pipeline_progress",
    "get_pipeline_status",
    "list_active_pipelines",
    "pause_pipeline",
    "resume_pipeline",
    "retry_gate",
    "run_batch",
    "run_pipeline",
    "skip_gate",
]


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
