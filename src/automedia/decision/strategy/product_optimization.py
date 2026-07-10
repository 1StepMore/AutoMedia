"""Product Optimization Agent — positioning & feature prioritisation.

Consumes upstream artefacts (brand DNA, market report, persona map,
competitor matrix) and produces a ``strategy_doc`` with actionable
product-positioning and feature-priority guidance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from automedia.decision.base import BaseDecisionAgent, DecisionArtifact


class ProductOptimizationAgent(BaseDecisionAgent):
    """Synthesise upstream artefacts into product-level strategy."""

    def name(self) -> str:
        return "product_optimization"

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,  # noqa: ANN401
    ) -> DecisionArtifact:
        brand_dna: dict[str, Any] = context.get("brand_dna", {})
        market_report: dict[str, Any] = context.get("market_report", {})
        persona_map: dict[str, Any] = context.get("persona_map", {})
        competitor_matrix: dict[str, Any] = context.get("competitor_matrix", {})

        brand_name: str = (
            brand_dna.get("brand_name")
            or market_report.get("brand_name")
            or persona_map.get("brand_name")
            or context.get("brand_name", "unknown")
        )

        positioning = self._build_positioning(
            brand_name, brand_dna, market_report, competitor_matrix
        )
        feature_priorities = self._prioritise_features(
            brand_dna, market_report, persona_map, competitor_matrix
        )
        localization_selling_points = self._localize_selling_points(
            brand_name, brand_dna, market_report
        )
        recommendations = self._generate_recommendations(
            positioning, feature_priorities, localization_selling_points
        )

        content: dict[str, Any] = {
            "product_positioning": positioning,
            "feature_priorities": feature_priorities,
            "localization_selling_points": localization_selling_points,
            "optimization_recommendations": recommendations,
        }

        return DecisionArtifact(
            artifact_type="strategy_doc",
            content=content,
            format="yaml",
            metadata={
                "agent": self.name(),
                "brand": brand_name,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_positioning(
        brand: str,
        brand_dna: dict[str, Any],
        market_report: dict[str, Any],
        competitor_matrix: dict[str, Any],
    ) -> str:
        """Craft a concise product-positioning statement."""
        value_prop = brand_dna.get(
            "value_proposition",
            brand_dna.get("core_value", "differentiated solution"),
        )
        target = brand_dna.get(
            "target_audience",
            brand_dna.get("ideal_customer_profile", "target buyers"),
        )
        category = market_report.get("market", "the category")
        differentiator = competitor_matrix.get(
            "differentiator",
            "unique approach",
        )

        return (
            f"For {target} in {category}, {brand} delivers {value_prop} "
            f"by leveraging {differentiator}, unlike competitors that rely on "
            f"legacy approaches."
        )

    @staticmethod
    def _prioritise_features(
        brand_dna: dict[str, Any],
        market_report: dict[str, Any],
        persona_map: dict[str, Any],
        competitor_matrix: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Rank features by strategic importance, market pull, and persona need."""
        candidates: list[dict[str, Any]] = []

        # Extract feature hints from upstream artefacts
        from_brand = brand_dna.get("features", [])
        if isinstance(from_brand, list):
            for f in from_brand:
                candidates.append(
                    {
                        "feature": f if isinstance(f, str) else f.get("name", str(f)),
                        "source": "brand_dna",
                        "strategic_weight": 9,
                        "market_pull": 7,
                        "persona_alignment": 8,
                    }
                )

        from_market = market_report.get("feature_opportunities", [])
        if isinstance(from_market, list):
            for f in from_market:
                candidates.append(
                    {
                        "feature": f if isinstance(f, str) else f.get("name", str(f)),
                        "source": "market_report",
                        "strategic_weight": 8,
                        "market_pull": 9,
                        "persona_alignment": 6,
                    }
                )

        from_persona = persona_map.get("wishlist_features", [])
        if isinstance(from_persona, list):
            for f in from_persona:
                candidates.append(
                    {
                        "feature": f if isinstance(f, str) else f.get("name", str(f)),
                        "source": "persona_map",
                        "strategic_weight": 7,
                        "market_pull": 6,
                        "persona_alignment": 10,
                    }
                )

        if not candidates:
            candidates = [
                {
                    "feature": "ai-powered_recommendations",
                    "source": "default",
                    "strategic_weight": 8,
                    "market_pull": 9,
                    "persona_alignment": 7,
                },
                {
                    "feature": "self_service_onboarding",
                    "source": "default",
                    "strategic_weight": 7,
                    "market_pull": 8,
                    "persona_alignment": 9,
                },
                {
                    "feature": "advanced_analytics_dashboard",
                    "source": "default",
                    "strategic_weight": 6,
                    "market_pull": 7,
                    "persona_alignment": 8,
                },
                {
                    "feature": "seamless_integration_api",
                    "source": "default",
                    "strategic_weight": 9,
                    "market_pull": 6,
                    "persona_alignment": 6,
                },
                {
                    "feature": "localisation_multi_currency",
                    "source": "default",
                    "strategic_weight": 7,
                    "market_pull": 5,
                    "persona_alignment": 5,
                },
            ]

        # Sort by composite score descending
        for c in candidates:
            c["composite_score"] = (
                c.get("strategic_weight", 0) * 0.4
                + c.get("market_pull", 0) * 0.35
                + c.get("persona_alignment", 0) * 0.25
            )

        candidates.sort(key=lambda x: x["composite_score"], reverse=True)
        return candidates

    @staticmethod
    def _localize_selling_points(
        brand: str, brand_dna: dict[str, Any], market_report: dict[str, Any]
    ) -> list[str]:
        """Tailor selling points for different regional / vertical contexts."""
        markets = market_report.get("target_markets", [])
        if not markets:
            markets = ["north_america", "europe", "apac"]

        usp = brand_dna.get("unique_selling_points", [])
        if not usp:
            usp = ["quality", "innovation", "support"]

        points: list[str] = []
        for m in markets:
            for u in usp[:2]:
                points.append(f"[{m}] Emphasise {u} — resonates strongest with {m} buyers.")
        return points[:5]  # cap at 5

    @staticmethod
    def _generate_recommendations(
        positioning: str,
        feature_priorities: list[dict[str, Any]],
        localization_selling_points: list[str],
    ) -> list[str]:
        """Synthesise final optimisation recommendations."""
        recs: list[str] = [
            "Adopt the positioning statement above as the North Star for all product messaging.",
        ]

        if feature_priorities:
            top_3 = [f["feature"] for f in feature_priorities[:3]]
            recs.append(f"Prioritise engineering sprints for: {', '.join(top_3)}.")

        if localization_selling_points:
            recs.append("Implement the localised selling-points in regional campaign briefs.")

        recs.append(
            "Schedule quarterly product-positioning reviews to stay ahead of market shifts."
        )
        return recs
