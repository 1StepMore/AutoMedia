"""Audience Deepening Agent — persona cluster analysis.

Consumes existing persona data and enriches it by identifying breakthrough
personas (high-intent, unserved clusters) and synthesising cross-cluster
insights.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from automedia.decision.base import BaseDecisionAgent, DecisionArtifact


class AudienceDeepeningAgent(BaseDecisionAgent):
    """Deepen audience understanding through persona clustering and gap analysis."""

    def name(self) -> str:
        return "audience_deepening"

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,
    ) -> DecisionArtifact:
        existing_personas: list[dict[str, Any]] = context.get(
            "personas", context.get("existing_personas", [])
        )
        brand_name: str = context.get("brand_name", "unknown")

        # Normalise existing personas to a consistent structure
        normalised = self._normalise_personas(existing_personas)

        breakthrough = self._identify_breakthrough_personas(normalised, brand_name)
        cluster_insights = self._generate_cluster_insights(
            normalised, breakthrough, brand_name
        )

        content: dict[str, Any] = {
            "existing_personas": normalised,
            "breakthrough_personas": breakthrough,
            "cluster_insights": cluster_insights,
        }

        return DecisionArtifact(
            artifact_type="audience_deepening",
            content=content,
            format="yaml",
            metadata={
                "agent": self.name(),
                "brand": brand_name,
                "persona_count": len(normalised),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_personas(
        raw: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Ensure every persona has at least ``name``, ``segments``, and ``pain_points``."""
        out: list[dict[str, Any]] = []
        for i, p in enumerate(raw):
            if not isinstance(p, dict):
                continue
            out.append(
                {
                    "name": p.get("name", f"persona_{i}"),
                    "segments": p.get("segments", p.get("segment", [])),
                    "pain_points": p.get("pain_points", p.get("pain_points", [])),
                    "goals": p.get("goals", p.get("objectives", [])),
                    "channels": p.get("channels", p.get("preferred_channels", [])),
                    "value_proposition": p.get(
                        "value_proposition", p.get("message", "")
                    ),
                }
            )
        if not out:
            out = [
                {
                    "name": "persona_0",
                    "segments": ["general"],
                    "pain_points": ["unmet need awareness"],
                    "goals": ["evaluate solution fit"],
                    "channels": ["search", "social"],
                    "value_proposition": "default value prop",
                }
            ]
        return out

    @staticmethod
    def _identify_breakthrough_personas(
        existing: list[dict[str, Any]], brand: str
    ) -> list[dict[str, Any]]:
        """Detect high-intent, unserved or under-served persona clusters.

        Breakthrough personas are inferred from gaps in the existing set.
        """
        known_names = {p["name"] for p in existing}
        known_segments: set[str] = set()
        for p in existing:
            known_segments.update(p.get("segments", []))

        breakthroughs = [
            {
                "name": "power_considerer",
                "description": (
                    "Deep-research buyer who evaluates 5+ vendors before shortlisting. "
                    "Needs detailed comparison content and technical validation."
                ),
                "estimated_size": "high",
                "urgency": "high",
                "gap": (
                    "No comparison or technical-deep-dive content in existing library."
                ),
            },
            {
                "name": "economic_buyer",
                "description": (
                    "Procurement / finance-led decision-maker focused on TCO, ROI, "
                    "and contract flexibility."
                ),
                "estimated_size": "medium",
                "urgency": "medium",
                "gap": "No ROI calculator or TCO white-paper available.",
            },
            {
                "name": "champion_networker",
                "description": (
                    "Internal evangelist who advocates for the brand within their "
                    "organisation. Needs shareable assets and community affiliation."
                ),
                "estimated_size": "medium",
                "urgency": "medium",
                "gap": "No advocacy program or referral incentive structure.",
            },
        ]

        # Filter out any that overlap heavily with existing personas
        return [b for b in breakthroughs if b["name"] not in known_names]

    @staticmethod
    def _generate_cluster_insights(
        existing: list[dict[str, Any]],
        breakthroughs: list[dict[str, Any]],
        brand: str,
    ) -> list[str]:
        """Cross-cluster analysis to surface actionable audience insights."""
        pain_points: list[str] = []
        for p in existing:
            pain_points.extend(p.get("pain_points", []))
        unique_pains = len(set(pain_points))

        total_segments: set[str] = set()
        for p in existing:
            total_segments.update(p.get("segments", []))
        for b in breakthroughs:
            total_segments.add(b.get("name", ""))

        insights = [
            f"Total distinct segments identified: {len(total_segments)}.",
            f"Across {len(existing)} existing persona(s), {unique_pains} unique pain point(s) documented.",
            (
                f"{len(breakthroughs)} breakthrough persona cluster(s) detected — "
                f"these represent high-intent audiences not yet explicitly targeted."
            ),
        ]

        if breakthroughs:
            insight_gaps = [
                b["gap"] for b in breakthroughs if b.get("gap")
            ]
            if insight_gaps:
                insights.append(
                    "Content gaps for breakthrough clusters: " + " ".join(insight_gaps)
                )

        return insights
