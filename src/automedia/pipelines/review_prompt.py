"""Interactive stdin prompt for resolving a paused human-review gate.

Split out of ``gate_types.py``: this is terminal I/O plus a decision, whereas
that module is the in-process progress tracker. Keeping them apart also lets
the progress tracker stay a data structure rather than a UI.
"""

from __future__ import annotations

import sys
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from automedia.pipelines.gate_types import PipelineProgress


def start_interactive_review_prompt(
    progress: PipelineProgress,
    gate_name: str = "H0",
    project_id: str = "",
) -> threading.Thread | None:
    """Offer a same-process stdin prompt for a paused *gate_name*.

    This is the "same-process CLI surface" the review-audit note anticipated:
    the answering code shares the process with the pause, so it can call
    ``approve_hitl``/``reject_hitl`` directly.  It runs on a daemon thread so the
    engine's blocking wait stays where it is.

    Returns ``None`` — without starting anything — when stdin is not a
    interactive terminal, so a piped or CI run never blocks on a read it cannot
    satisfy.  In that case the caller should rely on the other delivery channels
    (``automedia hitl approve`` or the MCP ``review_decision`` tool).
    """
    if not sys.stdin or not sys.stdin.isatty():
        return None

    def _prompt() -> None:
        while True:
            try:
                answer = input(
                    f"\n[{gate_name}] human review required for project "
                    f"{project_id or progress.project_id or '(unknown)'}.\n"
                    "  [a]pprove  [r]eject\n"
                    "  (or decide from another shell: "
                    f"automedia hitl approve|reject {project_id or '<project_id>'})\n> "
                )
            except (EOFError, KeyboardInterrupt):
                print("\nNo decision entered; the pause will time out.")
                return
            choice = answer.strip().lower()
            if choice in ("a", "approve", "y", "yes"):
                progress.approve_hitl()
                return
            if choice in ("r", "reject", "n", "no"):
                progress.reject_hitl()
                return
            print("Please answer 'a' or 'r'.")

    thread = threading.Thread(target=_prompt, name="hitl-review-prompt", daemon=True)
    thread.start()
    return thread
