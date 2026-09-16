"""Shared utilities, constants, and state for ``tools/`` submodules.

All symbols defined here are re-exported via ``tools/__init__.py`` so
that existing code (including tests) can continue to import from
``automedia.mcp.tools``.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import threading
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NotRequired, TypedDict, cast

import yaml
from pydantic import ValidationError
from structlog import get_logger

from automedia.core.llm_client import LLMError  # noqa: F401 — re-exported via tools/__init__.py
from automedia.core.logging import bind_correlation_id  # noqa: F401 — re-exported
from automedia.exceptions import (  # noqa: F401 — re-exported
    AutoMediaError,
    BrandNotFoundError,
    ConfigError,
    ModuleLoadError,
    PipelineError,
)
from automedia.mcp._state import (  # noqa: F401 — re-exported
    _SERVER_START,
    _lock,
    _pipeline_tracker,
)
from automedia.mcp.allowlist import (  # noqa: F401 — re-exported
    _ALLOWED_OUTPUT_FORMATS,
)
from automedia.mcp.mcp_error import (  # noqa: F401 — re-exported
    MCPErrorCode,
    error_response,
    success_response,
    validation_error_response,
)
from automedia.mcp.server_types import (  # noqa: F401 — re-exported
    CronExpression,
    EngineModality,
    NonEmptyStr,
    PipelineMode,
    ProjectStatusFilter,
    ResearchPattern,
)
from automedia.pipelines.gate_engine import (  # noqa: F401 — re-exported
    PipelineProgress,
    PipelineResult,
    get_registered_engine,
    list_registered_engines,
)
from automedia.pipelines.runner import VALID_MODES  # noqa: F401 — re-exported

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class CronScheduleEntry(TypedDict):
    name: str
    expression: str
    brand: str
    category: str
    count: int
    platform: str
    mode: str
    # Optional so legacy entries (MCP ``add_cron_schedule`` and pre-``kind``
    # files) remain constructible; an absent value is treated as "pipeline".
    kind: NotRequired[str]


# Track registered tool count (set dynamically by server.py after registration)
_tools_count: int = 0

# Default per-model cost-per-token rates (USD per 1M tokens).
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

_SECRET_KEYWORDS: frozenset[str] = frozenset({"key", "secret", "password", "token"})


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


def _estimate_cost(usage: dict[str, Any]) -> float:
    """Estimate cost in USD from token usage."""
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
    """Delegate to the server module's ``_require_allowed`` at call time."""
    from automedia.mcp import server as _srv

    _srv._require_allowed(path, tool_name=tool_name)


# ---------------------------------------------------------------------------
# Concurrency limit and session tracker state
# ---------------------------------------------------------------------------

_max_concurrent_pipelines: int = 3
_pipeline_semaphore: threading.Semaphore | None = None


def _get_max_concurrent_pipelines() -> int:
    """Return the configured maximum concurrent pipeline count."""
    return _max_concurrent_pipelines


def _init_pipeline_semaphore() -> threading.Semaphore:
    """Create or return the global pipeline semaphore."""
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
# Project / pipeline helpers
# ---------------------------------------------------------------------------


def _resolve_projects_dir() -> str:
    """Resolve the projects directory from env or config defaults."""
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
    """Read active pipelines from the JSON file, using flock for safety."""
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
    """Atomically write active pipelines dict to the JSON file."""
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
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
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
    """On server start, mark entries >24h old as ``"lost"``."""
    path = _get_active_pipelines_path()
    if not path.is_file():
        return
    try:
        data = _read_active_pipelines()
        now = datetime.now(UTC)
        changed = False
        for entry in data.values():
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
# Config helpers
# ---------------------------------------------------------------------------


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
    """Traverse a nested dict using dot-notation key paths."""
    current: object = data
    for part in key_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


# ---------------------------------------------------------------------------
# Cron helpers
# ---------------------------------------------------------------------------


def _get_jobs_yaml_path() -> Path:
    """Resolve the canonical pipeline schedules YAML file path."""
    from automedia.core.paths import get_user_config_dir

    return get_user_config_dir() / "pipeline_schedules.yaml"


def _get_package_jobs_yaml_path() -> Path:
    """Resolve the legacy package-shipped ``cron/jobs.yaml`` path."""
    import automedia as _am_pkg

    return Path(_am_pkg.__file__).resolve().parent / "cron" / "jobs.yaml"


def _infer_schedule_kind(entry: Mapping[str, Any]) -> str:
    """Infer ``"distribute"`` vs ``"pipeline"`` from a legacy entry's shape."""
    command = entry.get("command")
    if isinstance(command, str) and command.strip().startswith("automedia distribute"):
        return "distribute"
    if "platforms" in entry or "project_id" in entry:
        return "distribute"
    return "pipeline"


def _migrate_legacy_package_schedules() -> None:
    """Copy legacy package-side schedules into the canonical store once.

    The migration is idempotent: it only runs when the canonical file is
    absent, and afterwards the canonical file exists so it is never repeated.
    """
    path = _get_jobs_yaml_path()
    if path.is_file():
        return

    package_path = _get_package_jobs_yaml_path()
    if not package_path.is_file():
        return

    try:
        data = yaml.safe_load(package_path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return
    if not isinstance(data, dict):
        return

    entries = data.get("pipeline_schedules", [])
    if not isinstance(entries, list) or not entries:
        return

    migrated: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        migrated_entry = dict(entry)
        if "kind" not in migrated_entry:
            migrated_entry["kind"] = _infer_schedule_kind(migrated_entry)
        migrated.append(migrated_entry)

    if migrated:
        _write_pipeline_schedules(migrated)


def _read_pipeline_schedules() -> list[CronScheduleEntry]:
    """Read pipeline schedules from the canonical YAML file.

    The YAML file uses a ``{"pipeline_schedules": [...]}`` structure,
    consistent with :func:`get_cron_health` and the cron CLI tests.  A missing
    canonical file is seeded once from the legacy package ``cron/jobs.yaml``.
    Entries that omit ``kind`` are treated as ``"pipeline"``.
    """
    _migrate_legacy_package_schedules()

    path = _get_jobs_yaml_path()
    if not path.is_file():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        if isinstance(data, list):
            data = {}
        entries: list = data.get("pipeline_schedules", [])
        result: list[CronScheduleEntry] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            normalized: dict[str, Any] = dict(entry)
            normalized.setdefault("kind", _infer_schedule_kind(normalized))
            result.append(cast("CronScheduleEntry", normalized))
        return result
    except (yaml.YAMLError, OSError, ValidationError):
        log.warning("Failed to read pipeline schedules from %s", path)
        return []


def _write_pipeline_schedules(schedules: Sequence[Mapping[str, Any]]) -> None:
    """Write pipeline schedules to the canonical YAML file.

    Writes in ``{"pipeline_schedules": [...]}`` structure so that
    ``get_cron_health`` and the cron CLI tests read the correct format.
    Preserves other top-level keys (e.g. ``jobs``) from the existing file.
    """
    path = _get_jobs_yaml_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = path.read_text(encoding="utf-8")
            loaded = yaml.safe_load(raw)
            if isinstance(loaded, dict):
                existing = loaded
        except Exception as exc:  # best-effort preserve
            log.debug("Failed to read existing pipeline schedules; starting fresh", error=str(exc))

    existing["pipeline_schedules"] = [dict(s) for s in schedules]

    try:
        path.write_text(
            yaml.dump(
                existing,
                default_flow_style=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
    except OSError:
        log.warning("Failed to write pipeline schedules to %s", path)


def _validate_workflow(name: str) -> str | None:
    """Check that *name* references a valid workflow.

    Returns *None* on success, or an error message string on failure.
    """
    from automedia.core.config_loader import load_config

    try:
        config = load_config()
    except Exception:
        return "Could not load configuration"
    workflows = config.get("workflows", {})
    if name and name not in workflows:
        valid = ", ".join(sorted(workflows))
        return f"Unknown workflow '{name}'. Valid: {valid}"
    return None
