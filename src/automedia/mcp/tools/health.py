"""Health-check MCP tools — server status, engine health, first-run detection."""

from __future__ import annotations

import os
import time
import warnings
from typing import Any

import yaml
from structlog import get_logger

from automedia.exceptions import AutoMediaError
from automedia.mcp._state import _SERVER_START
from automedia.mcp.mcp_error import MCPErrorCode, error_response, success_response
import automedia.mcp.tools._shared as _shared_mod

log = get_logger(__name__)


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
                "tools_count": _shared_mod._tools_count,
                "first_run": _detect_first_run(),
            }
        )
    except ImportError as exc:
        return {"status": "error", **error_response(MCPErrorCode.IMPORT_ERROR, str(exc))}
    except Exception as exc:
        return {"status": "error", **error_response(MCPErrorCode.UNKNOWN, str(exc))}


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
