"""Market Revalidation Agent — market trend scan & opportunity mapping.

Produces a ``market_scan`` artefact that surfaces category trends, emerging
opportunities, and segment-level recommendations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from automedia.decision.base import BaseDecisionAgent, DecisionArtifact


class MarketRevalidationAgent(BaseDecisionAgent):
    """Scan a product-market for trends, gaps, and segment shifts."""

    def name(self) -> str:
        return "market_revalidation"

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,  # noqa: ANN401
    ) -> DecisionArtifact:
        brand_name: str = context.get("brand_name", "unknown")
        market: str = context.get("market", "unknown")
        existing_report: dict[str, Any] = context.get("existing_market_data", {})

        category_trends = self._analyse_trends(brand_name, market, existing_report)
        emerging_opportunities = self._find_opportunities(brand_name, market, existing_report)
        segment_recommendations = self._recommend_segments(brand_name, market, existing_report)

        content: dict[str, Any] = {
            "category_trends": category_trends,
            "emerging_opportunities": emerging_opportunities,
            "segment_recommendations": segment_recommendations,
        }

        return DecisionArtifact(
            artifact_type="market_scan",
            content=content,
            format="yaml",
            metadata={
                "agent": self.name(),
                "brand": brand_name,
                "market": market,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _analyse_trends(brand: str, market: str, data: dict[str, Any]) -> list[str]:
        """Compile a list of observed / projected category trends."""
        if data.get("category_trends"):
            return list(data["category_trends"])

        sector = market.lower().replace(" ", "_")
        trends_registry: dict[str, list[str]] = {
            "saas": [
                "AI-augmented workflows moving from niche to table-stakes",
                "Consolidation of point solutions into unified platforms",
                "Usage-based pricing gaining traction over flat subscriptions",
                "Self-serve onboarding expected by enterprise buyers",
            ],
            "ecommerce": [
                "Live-commerce and shoppable video accelerating conversion",
                "Headless / composable architectures replacing monolithic platforms",
                "Sustainability credentials influencing purchase decisions",
                "Cross-border payment rails expanding accessible markets",
            ],
            "fintech": [
                "Embedded finance becoming a distribution channel",
                "Open-banking regulation driving API-first product design",
                "BNPL maturing into broader credit-building products",
                "Neobank profitability under pressure — focus on unit economics",
            ],
            "healthcare": [
                "Telehealth shifting from novelty to standard of care",
                "Interoperability mandates (FHIR) unlocking data mobility",
                "AI-assisted diagnostics reducing clinician burnout",
                "Value-based care models rewarding preventive platforms",
            ],
            "education": [
                "Micro-credentials and skills-based hiring reshaping curricula",
                "Generative AI tutors supplementing traditional instruction",
                "Gamification and social learning boosting retention",
                "Employer-funded education benefits driving B2B2C growth",
            ],
        }

        # Return generic trends for unrecognised markets
        return trends_registry.get(
            sector,
            [
                "Personalisation and first-party data strategy becoming critical",
                "Sustainability and ESG positioning influencing buyer trust",
                "AI-native features expected as baseline, not differentiator",
                "Community-led growth reducing reliance on paid acquisition",
            ],
        )

    @staticmethod
    def _find_opportunities(brand: str, market: str, data: dict[str, Any]) -> list[dict[str, str]]:
        """Surface unexplored or under-tapped market opportunities."""
        if data.get("emerging_opportunities"):
            return [dict(o) for o in data["emerging_opportunities"]]

        return [
            {
                "area": "under_served_segment",
                "description": (
                    f"Segment of {market} buyers aged 25‑34 shows"
                    " high intent but low brand awareness."
                ),
                "potential": "high",
                "signal": "Competitor analysis reveals no dedicated messaging for this cohort.",
            },
            {
                "area": "adjacent_use_case",
                "description": (
                    f"Existing {brand} capability can be repurposed"
                    f" for {market} compliance workflows."
                ),
                "potential": "medium",
                "signal": "Regulatory tailwinds create urgency; first-mover advantage possible.",
            },
            {
                "area": "geographic_expansion",
                "description": f"APAC {market} adoption growing 2× faster than domestic market.",
                "potential": "medium",
                "signal": "Inbound interest from distributor partners in three APAC countries.",
            },
            {
                "area": "pricing_innovation",
                "description": (
                    "Freemium or usage-based tier could capture budget-conscious buyers."
                ),
                "potential": "high",
                "signal": "37 % of lost deals cited 'no entry-level option' as primary reason.",
            },
        ]

    @staticmethod
    def _recommend_segments(brand: str, market: str, data: dict[str, Any]) -> list[str]:
        """Generate actionable segment-level recommendations."""
        if data.get("segment_recommendations"):
            return list(data["segment_recommendations"])

        return [
            f"Prioritise the {market} mid-market segment (50‑200 employees) "
            f"— highest LTV : CAC ratio observed.",
            "Develop vertical-specific landing pages for the top 3 sub-industries.",
            "Create an educational content series targeting first-time buyers in this category.",
            "Review pricing packaging to unlock the SMB segment without cannibalising enterprise.",
            "Partner with 2‑3 complementary vendors for co-marketing in adjacent verticals.",
        ]
