"""Brand Health Diagnosis Agent — 5-dimension brand health audit.

Produces a ``brand_health_report`` artefact that scores the brand across
awareness, consistency, and competitiveness, then synthesises an overall
health rating and actionable recommendations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from automedia.decision.base import BaseDecisionAgent, DecisionArtifact


class BrandHealthDiagnosisAgent(BaseDecisionAgent):
    """Evaluate brand health across awareness, consistency, and competitiveness."""

    def name(self) -> str:
        return "brand_health_diagnosis"

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,  # noqa: ANN401
    ) -> DecisionArtifact:
        brand_name: str = context.get("brand_name", "unknown")
        existing_data: dict[str, Any] = context.get("existing_data", {})

        # ---------- dimension scoring ----------
        awareness = self._score_awareness(brand_name, existing_data)
        consistency = self._score_consistency(brand_name, existing_data)
        competitiveness = self._score_competitiveness(brand_name, existing_data)

        overall_health = self._synthesise_overall(
            awareness["score"], consistency["score"], competitiveness["score"]
        )
        recommendations = self._generate_recommendations(
            awareness, consistency, competitiveness, overall_health
        )

        content: dict[str, Any] = {
            "awareness": awareness,
            "consistency": consistency,
            "competitiveness": competitiveness,
            "overall_health": overall_health,
            "recommendations": recommendations,
        }

        return DecisionArtifact(
            artifact_type="brand_health_report",
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
    def _score_awareness(brand: str, data: dict[str, Any]) -> dict[str, Any]:
        """Derive an awareness score (0‑100) from context clues."""
        raw = data.get("awareness", {})
        score = raw.get("score") if isinstance(raw, dict) else None
        if score is not None:
            return {
                "score": max(0, min(100, int(score))),
                "details": raw.get("details", "Provided by upstream."),
            }

        mentions = data.get("social_mentions", 0)
        search_volume = data.get("search_volume_index", 50)
        score = min(100, (mentions % 100) + (search_volume % 100)) // 2
        return {
            "score": score,
            "details": (
                f"Estimated from social mentions ({mentions}) and "
                f"search-volume index ({search_volume})."
            ),
        }

    @staticmethod
    def _score_consistency(brand: str, data: dict[str, Any]) -> dict[str, Any]:
        """Evaluate visual / tonal consistency across channels."""
        raw = data.get("consistency", {})
        score = raw.get("score") if isinstance(raw, dict) else None
        if score is not None:
            return {
                "score": max(0, min(100, int(score))),
                "details": raw.get("details", "Provided by upstream."),
            }

        channels = data.get("active_channels", [])
        has_guidelines = data.get("brand_guidelines", False)
        base = 60 if has_guidelines else 30
        channel_bonus = min(30, len(channels) * 5)
        score = min(100, base + channel_bonus)
        return {
            "score": score,
            "details": (
                f"Brand guidelines {'exist' if has_guidelines else 'missing'}; "
                f"{len(channels)} active channel(s) evaluated."
            ),
        }

    @staticmethod
    def _score_competitiveness(brand: str, data: dict[str, Any]) -> dict[str, Any]:
        """Benchmark brand against market peers."""
        raw = data.get("competitiveness", {})
        score = raw.get("score") if isinstance(raw, dict) else None
        if score is not None:
            return {
                "score": max(0, min(100, int(score))),
                "details": raw.get("details", "Provided by upstream."),
            }

        competitors = data.get("competitors", [])
        usp = data.get("unique_selling_points", [])
        base = 40 if usp else 20
        score = min(100, base + len(competitors) * 3 + len(usp) * 5)
        return {
            "score": score,
            "details": (f"{len(competitors)} competitor(s) tracked; {len(usp)} USP(s) identified."),
        }

    @staticmethod
    def _synthesise_overall(a: int, c: int, comp: int) -> str:
        avg = (a + c + comp) / 3.0
        if avg >= 80:
            return "healthy"
        if avg >= 55:
            return "moderate"
        if avg >= 30:
            return "at_risk"
        return "critical"

    @staticmethod
    def _generate_recommendations(
        awareness: dict[str, Any],
        consistency: dict[str, Any],
        competitiveness: dict[str, Any],
        overall: str,
    ) -> list[str]:
        recs: list[str] = []
        if awareness["score"] < 50:
            recs.append("Launch a top-of-funnel awareness campaign to improve brand recall.")
        if consistency["score"] < 50:
            recs.append("Audit all brand touchpoints and enforce visual / tonal guidelines.")
        if competitiveness["score"] < 50:
            recs.append("Conduct a competitive differentiation workshop to sharpen USP messaging.")
        if overall == "critical":
            recs.insert(
                0, "Immediate brand-strategy intervention required — engage executive steering."
            )
        elif overall == "at_risk":
            recs.insert(0, "Schedule a brand-health review within the next quarter.")
        if not recs:
            recs.append("Maintain current trajectory; monitor brand-health monthly.")
        return recs
