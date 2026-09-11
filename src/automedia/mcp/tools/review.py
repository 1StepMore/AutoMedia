"""Live HITL review tool — ``review_decision`` (productization-roadmap todo 9).

Unlike :mod:`automedia.mcp.tools.approval` (the dormant ``pause_on_approval``
mechanism), this module drives the LIVE H0 pause path:
``H0HumanReviewGate`` → ``GateEngine._run`` HITL wait →
``PipelineProgress.wait_for_hitl``.  A paused pipeline registers its
:class:`PipelineProgress` in ``_hitl_waiters`` (keyed by the MCP
``project_id``), so a review from another MCP worker thread is same-process
and directly reachable — ``get_registered_engine`` is deliberately NOT used
(its id-namespace never contains a live MCP pipeline mid-pause).

SAME-PROCESS CONSTRAINT: pipelines started by the CLI run in a separate
process, so their waiters are invisible here.  Such requests are rejected
fast with a structured error — never a deadlock, never a 24-hour stall.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any, Literal

from structlog import get_logger

from automedia.decision.review_audit import record_review_decision
from automedia.mcp.tools._shared import (
    MCPErrorCode,
    NonEmptyStr,
    _discover_projects,
    _require_allowed,
    _resolve_projects_dir,
    error_response,
    success_response,
)
from automedia.pipelines.gate_types import PipelineProgress, _hitl_lock, _hitl_waiters

log = get_logger(__name__)

__all__ = ["review_decision"]


def _latest_diff_record(project_dir: str, gate_name: str) -> tuple[Path, dict[str, Any]] | None:
    """Return the newest todo-8 diff record for *gate_name* in *project_dir*.

    Records live at ``<project_dir>/.automedia/gate_diffs/<gate>_<seq>.json``
    and are numbered per run; the latest is the highest sequence.  When the
    gate produced no records, fall back to the newest record of any gate so
    the director still sees the most recent rewrite context.
    """
    diffs_dir = Path(project_dir) / ".automedia" / "gate_diffs"
    if not diffs_dir.is_dir():
        return None
    gate_paths = sorted(diffs_dir.glob(f"{gate_name}_*.json"))
    paths = gate_paths or sorted(diffs_dir.glob("*.json"))
    if not paths:
        return None
    path = paths[-1]
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(record, dict) or "before" not in record or "after" not in record:
        return None
    return path, record


def _render_unified_diff(record: dict[str, Any]) -> str:
    """Render one diff record's before/after texts as a unified diff."""
    return "".join(
        difflib.unified_diff(
            str(record.get("before", "")).splitlines(keepends=True),
            str(record.get("after", "")).splitlines(keepends=True),
            fromfile="before",
            tofile="after",
        )
    )


def _resolve_diff_payload(
    project_id: str,
    gate_name: str,
) -> dict[str, Any]:
    """Resolve the on-disk project from *project_id* and render its latest
    diff record.  Returns a partial response fragment:
    ``diff`` + ``diff_record_path`` when a record exists, or
    ``diff_unavailable: True`` otherwise."""
    fragment: dict[str, Any] = {"diff_unavailable": True}
    base_dir = _resolve_projects_dir()
    try:
        _require_allowed(base_dir, tool_name="review_decision")
        projects = _discover_projects(base_dir)
    except PermissionError as exc:
        log.warning("review_decision.diff_allowlist_denied", error=str(exc))
        return fragment
    match = [p for p in projects if p.get("project_id") == project_id]
    if not match:
        return fragment
    project_dir = str(match[0].get("_dir", ""))
    if not project_dir:
        return fragment
    found = _latest_diff_record(project_dir, gate_name)
    if found is None:
        return fragment
    path, record = found
    fragment["diff"] = _render_unified_diff(record)
    fragment["diff_record_path"] = str(path)
    fragment["diff_unavailable"] = False
    return fragment


def review_decision(
    project_id: NonEmptyStr,
    gate_name: NonEmptyStr,
    action: Literal["approve", "reject"],
    reason: str = "",
    show_diff: bool = False,
) -> dict[str, Any]:
    """Approve or reject a pipeline paused at a HITL review gate (live H0 path).

    Resolves the paused pipeline through the in-process ``_hitl_waiters``
    registry — the same-process registry every MCP-started pipeline's
    ``PipelineProgress`` registers itself in while it waits for a human
    decision.  Approve resumes the pipeline; reject halts it (the gate
    result becomes a stop-failure).

    Parameters
    ----------
    project_id:
        The pipeline id returned by ``run_pipeline`` (uuid[:12]).
    gate_name:
        The gate awaiting review (e.g. ``"H0"``).
    action:
        ``"approve"`` to continue the pipeline, ``"reject"`` to halt it.
    reason:
        Optional reviewer explanation, recorded to the audit log.
    show_diff:
        When ``True``, resolve the on-disk project and render a unified
        diff from the latest ``.automedia/gate_diffs/`` record.  With no
        record the response carries ``diff_unavailable: True``.

    Returns
    -------
    dict
        ``{"approved": True, ...}`` or ``{"rejected": True, ...}`` plus the
        diff fragment when requested, or a structured error.

    Same-process constraint
    -----------------------
    Only MCP-started pipelines (daemon threads of this server process) can
    be resumed here.  A CLI-started pipeline lives in a different process,
    so its project_id will not be in the registry — the call returns a
    structured ``NOT_FOUND`` error immediately instead of waiting.
    """
    if action not in ("approve", "reject"):
        return error_response(
            MCPErrorCode.INVALID_PARAM,
            f"action must be 'approve' or 'reject', got {action!r}",
        )

    with _hitl_lock:
        progress: PipelineProgress | None = _hitl_waiters.get(project_id)

    if progress is None:
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"No paused HITL gate found for project_id {project_id!r} "
            f"waiting at gate {gate_name!r} in this process",
            "review_decision only reaches pipelines started by THIS MCP server "
            "process (run_pipeline daemon threads paused at a HITL gate). "
            "A CLI-started pipeline runs in a separate process and cannot be "
            "resumed here — approve/reject it in its own terminal. Check "
            "get_pipeline_progress to confirm the pipeline is awaiting_hitl.",
        )

    diff_fragment = _resolve_diff_payload(project_id, gate_name) if show_diff else {}
    diff_record_path = diff_fragment.get("diff_record_path")

    try:
        if action == "approve":
            progress.approve_hitl()
        else:
            progress.reject_hitl()
    except Exception as exc:  # signalling must never crash the tool
        return error_response(MCPErrorCode.ENGINE_ERROR, f"Failed to signal decision: {exc}")

    try:
        record_review_decision(
            project_id=project_id,
            gate_name=gate_name,
            decision=action,
            reason=reason,
            diff_record_path=diff_record_path,
            actor="mcp",
        )
    except Exception as exc:  # audit failure must not fail the review
        log.warning("review_decision.audit_error", error=str(exc))

    payload: dict[str, Any] = {
        "project_id": project_id,
        "gate_name": gate_name,
        "action": action,
    }
    if action == "approve":
        payload["approved"] = True
    else:
        payload["rejected"] = True
    if reason:
        payload["reason"] = reason
    payload.update(diff_fragment)
    return success_response(payload)
