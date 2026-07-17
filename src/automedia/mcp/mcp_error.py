from __future__ import annotations

from enum import StrEnum
from typing import Any


class MCPErrorCode(StrEnum):
    """Standardized error codes for MCP responses."""

    INVALID_PARAM = "INVALID_PARAM"
    NOT_FOUND = "NOT_FOUND"
    PIPELINE_ERROR = "PIPELINE_ERROR"
    ENGINE_ERROR = "ENGINE_ERROR"
    ALLOWLIST_DENIED = "ALLOWLIST_DENIED"
    UNKNOWN = "UNKNOWN"


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
        Optional guidance for resolving the error. Falls back to a generic
        message when left empty.
    """
    error_code = code.value if isinstance(code, MCPErrorCode) else code
    return {
        "success": False,
        "error": {
            "code": error_code,
            "message": message,
            "resolution": resolution or "See documentation or contact support",
        },
        "error_message": message,
    }


__all__ = ["success_response", "error_response", "MCPErrorCode"]
