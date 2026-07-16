"""H0 Human Review Gate — pauses pipeline for human content review.

When this gate executes it returns ``awaiting_hitl`` status, which signals
the GateEngine to pause and wait for human approval or rejection via
CLI ``automedia hitl approve/reject`` or MCP HITL tools.

Behaviour
---------
* If ``gate_context["skip_review"]`` is ``True`` → auto-passes (skipped).
* Otherwise returns ``status="awaiting_hitl"`` with a configurable timeout
  (default 24 hours).  On timeout the gate auto-passes.
* Approved → gate passes, pipeline continues.
* Rejected → gate fails with ``failure_mode="stop"``, pipeline halts.

Failure Mode
------------
``"stop"`` — if a human rejects the content, the pipeline should not
continue to publish.
"""

from __future__ import annotations

from typing import Any

from structlog import get_logger

from automedia.gates._context import GateContext
from automedia.gates.base import BaseGate

log = get_logger(__name__)

# Default HITL timeout: 24 hours
_DEFAULT_HITL_TIMEOUT_S: int = 86400


class H0HumanReviewGate(BaseGate):
    """Pre-publish human review gate.

    Pauses the pipeline and waits for a human to approve or reject the
    content before proceeding to publish.
    """

    _gate_name = "H0"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Execute the H0 gate.

        Parameters
        ----------
        gate_context:
            Pipeline context.  When ``skip_review`` is ``True`` the gate
            auto-passes.  ``hitl_timeout`` can be set to override the
            default 24-hour timeout.

        Returns
        -------
        dict
            ``{"passed": True, "gate": "H0", "status": "skipped"}`` when
            skipped, or ``{"passed": True, "gate": "H0",
            "status": "awaiting_hitl", "timeout_s": ...}`` when pausing
            for human review.
        """
        # If skip-review flag is set, auto-pass
        if gate_context.get("skip_review", False):
            return {
                "passed": True,
                "gate": "H0",
                "status": "skipped",
            }

        # Collect any escalated gates from auto-recovery
        escalated: list[dict[str, Any]] | list[str] = list(
            gate_context.get("_escalated_gates", [])
        )

        hitl_cfg: dict[str, Any] = gate_context.get("hitl_config", {})
        timeout_s = (
            gate_context.get("hitl_timeout")
            or hitl_cfg.get("timeout_s")
            or _DEFAULT_HITL_TIMEOUT_S
        )

        # Pause for human review
        return {
            "passed": True,
            "gate": "H0",
            "status": "awaiting_hitl",
            "escalated_gates": escalated,
            "timeout_s": timeout_s,
        }
