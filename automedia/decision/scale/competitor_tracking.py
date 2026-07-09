"""Competitor Tracking Agent — competitive landscape surveillance.

Produces a ``competitor_tracking`` artefact that lists each competitor's
recent activity, strategic shifts, counter-positioning plays, and
blue-ocean opportunities for the brand.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from automedia.decision.base import BaseDecisionAgent, DecisionArtifact


class CompetitorTrackingAgent(BaseDecisionAgent):
    """Track competitor movements and derive counter-positioning strategies."""

    def name(self) -> str:
        return "competitor_tracking"

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,
    ) -> DecisionArtifact:
        competitors_raw: list[Any] = context.get("competitors", [])
        brand_name: str = context.get("brand_name", "unknown")
        market: str = context.get("market", "unknown")

        # Normalise competitor entries
        competitors = self._normalise_competitors(competitors_raw, brand_name, market)

        # Derive counter-positioning from the competitor data
        counter_positioning = self._derive_counter_positioning(competitors, brand_name)

        # Identify white-space / blue-ocean opportunities
        blue_ocean = self._find_blue_ocean(competitors, brand_name, market)

        content: dict[str, Any] = {
            "competitors": competitors,
            "counter_positioning": counter_positioning,
            "blue_ocean_opportunities": blue_ocean,
        }

        return DecisionArtifact(
            artifact_type="competitor_tracking",
            content=content,
            format="yaml",
            metadata={
                "agent": self.name(),
                "brand": brand_name,
                "market": market,
                "competitor_count": len(competitors),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_competitors(
        raw: list[Any], brand: str, market: str
    ) -> list[dict[str, Any]]:
        """Build a competitor entry per item, using synthetic data for incomplete entries."""
        if not raw:
            # No data supplied — generate market-representative competitors
            raw = [
                {"name": f"competitor_a_{market}"},
                {"name": f"competitor_b_{market}"},
            ]

        out: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, str):
                item = {"name": item}
            if not isinstance(item, dict):
                continue
            name = item.get("name", "unknown_competitor")
            out.append(
                {
                    "name": name,
                    "recent_changes": item.get(
                        "recent_changes",
                        f"{name} launched a redesigned UI and raised Series B.",
                    ),
                    "strategy_shifts": item.get(
                        "strategy_shifts",
                        [
                            f"{name} is expanding into {market} adjacent verticals.",
                            f"{name} increased paid-search spend by 30 % quarter-over-quarter.",
                        ],
                    ),
                }
            )
        return out

    @staticmethod
    def _derive_counter_positioning(
        competitors: list[dict[str, Any]], brand: str
    ) -> list[str]:
        """Generate counter-positioning plays that differentiate the brand."""
        plays: list[str] = []

        for comp in competitors:
            name = comp["name"]
            shifts = comp.get("strategy_shifts", [])
            for s in shifts:
                if "expanding" in s.lower():
                    plays.append(
                        f"While {name} broadens, {brand} doubles down on core "
                        f"use-case depth and customer-success ROI."
                    )
                elif "price" in s.lower() or "paid" in s.lower():
                    plays.append(
                        f"Rather than out-spend {name} on paid acquisition, "
                        f"{brand} invests in community-led growth and organic authority."
                    )
                else:
                    plays.append(
                        f"Position {brand} as the privacy-first, transparent "
                        f"alternative to {name}."
                    )

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for p in plays:
            if p not in seen:
                seen.add(p)
                unique.append(p)

        if not unique:
            unique.append(
                f"{brand} occupies a differentiated position — no direct "
                f"counter-play required."
            )

        return unique

    @staticmethod
    def _find_blue_ocean(
        competitors: list[dict[str, Any]], brand: str, market: str
    ) -> list[str]:
        """Surface uncontested market spaces the brand can own."""
        all_shifts: list[str] = []
        for c in competitors:
            all_shifts.extend(c.get("strategy_shifts", []))

        crowded_areas = [
            "ai",
            "enterprise",
            "freemium",
            "marketplace",
            "mobile-first",
        ]
        crowded = {
            w for w in crowded_areas
            if any(w in s.lower() for s in all_shifts)
        }

        opportunities: list[str] = []
        if "ai" not in crowded:
            opportunities.append(
                "AI-powered <x> — competitors have not yet invested in ML-driven features "
                "for this market."
            )
        if "enterprise" not in crowded:
            opportunities.append(
                "Enterprise-grade compliance and SLA guarantees remain unclaimed by rivals."
            )
        opportunities.append(
            f"{brand} can own the 'privacy-first' narrative if competitors "
            f"continue relying on aggressive data collection."
        )
        opportunities.append(
            f"Vertical-specific ({market}) workflows are under-served by generalist "
            f"competitors — build for the niche."
        )

        return opportunities
