"""H0 Human Review Gate — pauses pipeline for human content review.

When this gate executes it returns ``awaiting_hitl`` status, which signals
the GateEngine to pause and wait for a human approval or rejection. The pause
can be resolved three ways:

* interactively, with ``automedia run --wait-for-review``, which prompts on
  stdin in the running process;
* from another process, with ``automedia hitl approve <project_id>`` /
  ``automedia hitl reject <project_id>``, which writes ``.hitl_state.json``
  into the project directory for the waiting run to pick up;
* from an MCP client, with the ``review_decision`` tool, which resolves the
  pause in the same process (same-process only).

Behaviour
---------
* If ``gate_context["skip_review"]`` is ``True`` → auto-passes (skipped).
* Otherwise returns ``status="awaiting_hitl"`` with a pause budget from
  ``gate_context["hitl_timeout"]``, ``hitl_config["timeout_s"]``, or the
  one-hour default.  On timeout the gate applies ``on_timeout``.
* ``on_timeout`` defaults to ``"reject"``, so an undecided pause fails the
  pipeline rather than shipping unreviewed content.  Set
  ``gate_engine.hitl_on_timeout: approve`` (or pass ``--hitl-on-timeout
  approve``) to restore the legacy fail-open behaviour.
* Approved → gate passes, pipeline continues.
* Rejected → gate fails with ``failure_mode="stop"``, pipeline halts.

Failure Mode
------------
``"stop"`` — if a human rejects the content, or the review times out under the
default policy, the pipeline should not continue to publish.
"""

from __future__ import annotations

from typing import Any

from structlog import get_logger

from automedia.gates._context import GateContext
from automedia.gates.base import BaseGate
from automedia.hitl.constants import HITL_DEFAULT_TIMEOUT_S

log = get_logger(__name__)

# Default HITL pause budget, in seconds. This was a hardcoded 86400 (24 hours),
# which made a non-interactive `automedia run` hang for a day and then quietly
# auto-approve.  Override with `gate_engine.hitl_timeout_s` or `--hitl-timeout`.
# The value lives in `automedia.hitl.constants` so this gate, the gate engine,
# and `wait_for_hitl` cannot drift apart; the alias keeps the gate's own name.
_DEFAULT_HITL_TIMEOUT_S: int = HITL_DEFAULT_TIMEOUT_S

# What a pause does when nobody decides. "reject" fails the pipeline so
# unreviewed content cannot ship; "approve" restores the legacy fail-open
# behaviour.  An unrecognised value falls back to "reject".
_DEFAULT_HITL_ON_TIMEOUT: str = "reject"
_HITL_ON_TIMEOUT_CHOICES: frozenset[str] = frozenset({"approve", "reject"})


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
            default one-hour pause budget
            (``HITL_DEFAULT_TIMEOUT_S`` in :mod:`automedia.hitl.constants`,
            mirrored by ``gate_engine.hitl_timeout_s``).

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
        escalated: list[dict[str, Any]] | list[str] = list(gate_context.get("_escalated_gates", []))

        hitl_cfg: dict[str, Any] = gate_context.get("hitl_config", {})
        timeout_s = (
            gate_context.get("hitl_timeout") or hitl_cfg.get("timeout_s") or _DEFAULT_HITL_TIMEOUT_S
        )
        configured_on_timeout = hitl_cfg.get("on_timeout")
        on_timeout = (
            str(configured_on_timeout).strip().lower()
            if configured_on_timeout is not None
            else _DEFAULT_HITL_ON_TIMEOUT
        )
        if on_timeout not in _HITL_ON_TIMEOUT_CHOICES:
            log.warning(
                "h0.unknown_on_timeout",
                configured=configured_on_timeout,
                fallback=_DEFAULT_HITL_ON_TIMEOUT,
            )
            on_timeout = _DEFAULT_HITL_ON_TIMEOUT

        # Pause for human review
        return {
            "passed": True,
            "gate": "H0",
            "status": "awaiting_hitl",
            "escalated_gates": escalated,
            "timeout_s": timeout_s,
            "on_timeout": on_timeout,
        }
