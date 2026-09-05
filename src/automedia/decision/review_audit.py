"""Append-only review-decision audit logging.

Records every human review decision (approve/reject on a HITL-waiting gate)
to ``~/.automedia/audit/review_decisions.log`` — one JSON object per line.

Mirrors the force-provenance pattern in :mod:`automedia.decision.audit`
(user-level log via :func:`get_user_config_dir`, append-only, write errors
never propagate to the caller).  Full before/after texts stay on disk in the
todo-8 diff records (``<project_dir>/.automedia/gate_diffs/``); only the
diff-record *path* is logged, never the content.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from structlog import get_logger

from automedia.core.paths import get_user_config_dir

log = get_logger(__name__)

__all__ = ["record_review_decision"]


def record_review_decision(
    project_id: str,
    gate_name: str,
    decision: str,
    reason: str = "",
    diff_record_path: str | None = None,
    actor: str = "mcp",
) -> None:
    """Append one review-decision entry to the user-level audit log.

    Parameters
    ----------
    project_id:
        The project the decision applies to.
    gate_name:
        The gate that was awaiting human review (e.g. ``"H0"``).
    decision:
        ``"approve"`` or ``"reject"``.
    reason:
        Optional human-readable explanation captured from the reviewer.
    diff_record_path:
        Path of the todo-8 diff record shown for this decision, when one
        was rendered (``show_diff=True`` and a record existed).
    actor:
        Surface that recorded the decision (``"mcp"`` or ``"cli"``).

    Failure to append (unwritable dir, disk error, …) is logged and
    swallowed — an audit-write problem must never fail the review call.
    """
    entry: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "project_id": project_id,
        "gate_name": gate_name,
        "decision": decision,
        "reason": reason,
        "diff_record_path": diff_record_path,
        "actor": actor,
    }
    try:
        log_path = get_user_config_dir() / "audit" / "review_decisions.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("review_audit.write_failed", error=str(exc))
