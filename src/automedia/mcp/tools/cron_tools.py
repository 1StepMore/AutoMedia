"""Cron schedule management MCP tools."""
from __future__ import annotations

import re
from typing import Any

import yaml
from structlog import get_logger

from automedia.mcp.tools._shared import (
    CronExpression,
    CronScheduleEntry,
    MCPErrorCode,
    NonEmptyStr,
    VALID_MODES,
    _get_jobs_yaml_path,
    _read_pipeline_schedules,
    _write_pipeline_schedules,
    error_response,
    log,
    success_response,
)
from automedia.exceptions import ConfigError

log = get_logger(__name__)

__all__ = [
    "add_cron_schedule",
    "get_cron_health",
    "list_cron_schedules",
    "list_workflows",
    "remove_cron_schedule",
    "test_cron_schedule",
]


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
