from __future__ import annotations

from enum import StrEnum
from typing import Any


class MCPErrorCode(StrEnum):
    """Standardized error codes for MCP responses.

    Each member maps to a specific class of failure so that clients can
    pattern-match on ``error["code"]`` and present actionable guidance.
    """

    # -- Parameter / input errors -------------------------------------------
    INVALID_PARAM = "INVALID_PARAM"

    # -- Resource-not-found errors ------------------------------------------
    NOT_FOUND = "NOT_FOUND"
    BRAND_NOT_FOUND = "BRAND_NOT_FOUND"
    CONFIG_MISSING = "CONFIG_MISSING"

    # -- Pipeline / gate errors ---------------------------------------------
    PIPELINE_ERROR = "PIPELINE_ERROR"
    GATE_FAILURE = "GATE_FAILURE"
    ENGINE_ERROR = "ENGINE_ERROR"

    # -- LLM / AI provider errors -------------------------------------------
    LLM_ERROR = "LLM_ERROR"

    # -- Module / import errors ---------------------------------------------
    IMPORT_ERROR = "IMPORT_ERROR"

    # -- Data validation errors ---------------------------------------------
    VALIDATION_ERROR = "VALIDATION_ERROR"

    # -- Session / lifecycle errors -----------------------------------------
    SESSION_LOST = "SESSION_LOST"

    # -- Security / allowlist errors ----------------------------------------
    ALLOWLIST_DENIED = "ALLOWLIST_DENIED"

    # -- Catch-all ----------------------------------------------------------
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Resolution map — human‑readable guidance for every error code
# ---------------------------------------------------------------------------

_RESOLUTIONS: dict[str, str] = {
    "INVALID_PARAM": "Check the parameter values and try again",
    "NOT_FOUND": "Verify the resource identifier (e.g. project_id) and try again",
    "BRAND_NOT_FOUND": "Create a brand with add_brand() or automedia init",
    "CONFIG_MISSING": "Run automedia init to create configuration, then retry",
    "PIPELINE_ERROR": "Check gate logs for failure details and retry or skip the failing gate",
    "GATE_FAILURE": "Inspect the gate output, fix the underlying content or media issue, then retry",
    "ENGINE_ERROR": "Check engine dependencies with health_engine() and ensure the engine is running",
    "LLM_ERROR": "Verify AUTOMEDIA_LLM_API_KEY is set and the provider is accessible",
    "IMPORT_ERROR": "Install missing dependencies with 'pip install automedia[EXTRA]'",
    "VALIDATION_ERROR": "Check the input data types and constraints; fix the reported fields",
    "SESSION_LOST": "The pipeline session expired or was cancelled. Start a new pipeline",
    "ALLOWLIST_DENIED": "The requested path is not in the allowlist — verify the path or update mcp_allowlist.yaml",
    "UNKNOWN": "See documentation or contact support",
}


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def success_response(data: dict[str, Any]) -> dict[str, Any]:
    """Wrap a data dict with a success flag.

    If the dict already contains a ``"success"`` key, it is returned as-is
    without modification.
    """
    if "success" in data:
        return data
    return {"success": True, **data}


def error_response(
    code: MCPErrorCode | str,
    message: str,
    resolution: str = "",
) -> dict[str, Any]:
    """Build a structured error response.

    Parameters
    ----------
    code:
        Machine-readable error code. Accepts either an ``MCPErrorCode`` member
        or a plain string.
    message:
        Human-readable description of what went wrong.
    resolution:
        Optional guidance for resolving the error. Falls back to the
        built-in resolution map, then to a generic message when empty.
    """
    error_code = code.value if isinstance(code, MCPErrorCode) else code
    resolved = resolution or _RESOLUTIONS.get(str(error_code), "")
    return {
        "success": False,
        "error": {
            "code": error_code,
            "message": message,
            "resolution": resolved or "See documentation or contact support",
        },
    }


def validation_error_response(
    message: str,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a structured ``VALIDATION_ERROR`` response with per-field details.

    Parameters
    ----------
    message:
        Human-readable summary of the validation failure.
    errors:
        Optional list of per-field error dicts. Each entry should contain
        at least ``field`` and ``message`` keys; ``input`` is optional::

            [
                {"field": "brand", "message": "Field required"},
                {"field": "mode", "message": "Input should be 'auto', "
                 "'text_only', …", "input": "invalid_mode"},
            ]

    Returns
    -------
    dict
        A standard error dict with code ``VALIDATION_ERROR``, the summary
        *message*, a generic *resolution*, and an optional ``errors`` list
        with per-field breakdown.
    """
    error_code = MCPErrorCode.VALIDATION_ERROR
    payload: dict[str, Any] = {
        "success": False,
        "error": {
            "code": str(error_code),
            "message": message,
            "resolution": _RESOLUTIONS.get(str(error_code), ""),
        },
    }
    if errors:
        payload["error"]["errors"] = errors
    return payload


__all__ = ["success_response", "error_response", "validation_error_response", "MCPErrorCode"]
