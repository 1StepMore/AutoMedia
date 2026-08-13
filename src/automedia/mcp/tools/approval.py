"""Director mode approval/rejection MCP tools."""
from __future__ import annotations

from typing import Any

from structlog import get_logger

from automedia.mcp.tools._shared import (
    MCPErrorCode,
    NonEmptyStr,
    error_response,
    get_registered_engine,
    list_registered_engines,
    success_response,
)

log = get_logger(__name__)

__all__ = [
    "approve_gate",
    "get_pending_approvals",
    "reject_gate",
]


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
