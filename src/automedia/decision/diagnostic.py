"""Diagnostic Agent — phase 0 of the Decision Layer.

Responsibilities
----------------
1. Deliver a structured brand questionnaire
2. Route user to Build or Scale mode based on their stage
3. Scan existing assets when a brand name is available
"""

from __future__ import annotations

import logging
from typing import Any

from automedia.decision.base import BaseDecisionAgent, DecisionArtifact

logger = logging.getLogger(__name__)


def assign_mode(user_input: str) -> str:
    """Determine whether the user should enter Build or Scale mode.

    Returns ``"build"`` for new brands, ``"scale"`` for existing ones.
    Defaults to ``"build"`` when the input is empty or ambiguous.
    """
    lowered = user_input.lower().strip()
    if not lowered:
        return "build"
    # Keywords indicating an existing brand
    scale_keywords = ("already", "existing", "running", "current", "have a brand")
    if any(kw in lowered for kw in scale_keywords):
        return "scale"
    return "build"


def questionnaire(answers: dict[str, str]) -> dict[str, Any]:
    """Build a structured Brief dict from user answers.

    Parameters
    ----------
    answers:
        Dict with optional keys ``idea``, ``market``, ``stage``.

    Returns
    -------
    dict
        A structured Brief with routing information.
    """
    idea = answers.get("idea", "")
    market = answers.get("market", "")
    stage = answers.get("stage", "")

    mode = "build" if stage in ("new", "", "from scratch") else "scale"

    return {
        "idea": idea,
        "market": market,
        "stage": stage,
        "mode": mode,
        "completed_phases": [],
    }


class DiagnosticAgent(BaseDecisionAgent):
    """Phase-0 agent: questionnaire + Build/Scale routing + asset scan."""

    def name(self) -> str:
        return "diagnostic"

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,  # noqa: ANN401
    ) -> DecisionArtifact:
        """Run the diagnostic: route user, scan assets, return structured Brief."""
        idea = context.get("idea", "")
        market = context.get("market", "")
        stage = context.get("stage", "new")

        # 1. Determine mode
        mode = assign_mode(stage)

        # 2. Scan existing assets (if asset library is available)
        existing_count = 0
        if asset_library is not None:
            try:
                results = asset_library.search(query=idea)  # type: ignore[union-attr]
                existing_count = len(results) if results else 0
            except (AttributeError, ValueError, RuntimeError):
                logger.debug("AssetLibrary search failed, assuming zero existing assets")
                existing_count = 0

        content: dict[str, Any] = {
            "idea": idea,
            "market": market,
            "stage": stage,
            "mode": mode,
            "existing_assets": existing_count,
            "completed_phases": [],
        }

        return DecisionArtifact(
            artifact_type="brief",
            content=content,
            metadata={"agent": self.name(), "phase": 0},
        )
