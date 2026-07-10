"""Build-mode Decision Agents — brand strategy from scratch.

Exports
-------
- ``BrandPositioningAgent`` — define brand DNA (voice, values, differentiators)
- ``MarketResearchAgent`` — market landscape & opportunity sizing
- ``AudienceSegmentationAgent`` — persona definition & prioritisation
- ``CompetitorAnalysisAgent`` — competitive positioning & gap analysis
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from automedia.decision.base import BaseDecisionAgent, DecisionArtifact


class BrandPositioningAgent(BaseDecisionAgent):
    """Define brand DNA — voice, values, positioning, and differentiators."""

    def name(self) -> str:
        return "brand_positioning"

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,
    ) -> DecisionArtifact:
        brand_name: str = context.get("brand_name", "unknown")
        brand_goal: str = context.get("brand_goal", "")
        existing_data: dict[str, Any] = context.get("existing_data", {})

        brand_dna = self._build_dna(brand_name, brand_goal, existing_data)
        positioning = self._build_positioning(brand_dna, existing_data)

        content: dict[str, Any] = {
            "brand_dna": brand_dna,
            "positioning": positioning,
            "brand_name": brand_name,
        }

        return DecisionArtifact(
            artifact_type="brand_dna",
            content=content,
            format="yaml",
            metadata={
                "agent": self.name(),
                "brand": brand_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _build_dna(
        self, brand_name: str, brand_goal: str, existing_data: dict[str, Any]
    ) -> dict[str, Any]:
        core_values = existing_data.get("values", [])
        if not core_values:
            core_values = ["authenticity", "quality", "innovation"]

        return {
            "brand_name": brand_name,
            "mission": brand_goal or existing_data.get("description", ""),
            "values": core_values,
            "voice_attributes": existing_data.get("voice", ["professional", "approachable"]),
            "differentiators": existing_data.get("differentiators", []),
        }

    def _build_positioning(
        self, dna: dict[str, Any], existing_data: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "target_audience": existing_data.get("target_audience", ""),
            "market_category": existing_data.get("category", ""),
            "value_proposition": existing_data.get("value_proposition", ""),
            "brand_promise": existing_data.get("brand_promise", ""),
        }


class MarketResearchAgent(BaseDecisionAgent):
    """Analyse market landscape — trends, opportunities, and threat vectors."""

    def name(self) -> str:
        return "market_research"

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,
    ) -> DecisionArtifact:
        brand_name: str = context.get("brand_name", "unknown")
        existing_data: dict[str, Any] = context.get("existing_data", {})

        landscape = self._analyse_landscape(brand_name, existing_data)
        opportunities = self._identify_opportunities(landscape, existing_data)
        threats = self._identify_threats(landscape)

        content: dict[str, Any] = {
            "market_landscape": landscape,
            "opportunities": opportunities,
            "threats": threats,
            "brand_name": brand_name,
        }

        return DecisionArtifact(
            artifact_type="market_report",
            content=content,
            format="yaml",
            metadata={
                "agent": self.name(),
                "brand": brand_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _analyse_landscape(
        self, brand_name: str, existing_data: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "category": existing_data.get("category", ""),
            "market_size": existing_data.get("market_size", ""),
            "growth_trends": existing_data.get("trends", []),
            "key_players": existing_data.get("competitors", []),
        }

    def _identify_opportunities(
        self, landscape: dict[str, Any], existing_data: dict[str, Any]
    ) -> list[dict[str, str]]:
        gaps = existing_data.get("market_gaps", [])
        return [{"gap": g, "opportunity": f"Address {g}"} for g in gaps] if gaps else []

    def _identify_threats(self, landscape: dict[str, Any]) -> list[dict[str, str]]:
        return []


class AudienceSegmentationAgent(BaseDecisionAgent):
    """Define audience personas — demographics, psychographics, and intent clusters."""

    def name(self) -> str:
        return "audience_segmentation"

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,
    ) -> DecisionArtifact:
        brand_name: str = context.get("brand_name", "unknown")
        existing_data: dict[str, Any] = context.get("existing_data", {})

        personas = self._build_personas(brand_name, existing_data)
        primary_segments = self._prioritise_segments(personas)

        content: dict[str, Any] = {
            "personas": personas,
            "primary_segments": primary_segments,
            "brand_name": brand_name,
        }

        return DecisionArtifact(
            artifact_type="persona_map",
            content=content,
            format="yaml",
            metadata={
                "agent": self.name(),
                "brand": brand_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _build_personas(
        self, brand_name: str, existing_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        raw_personas = existing_data.get("personas", [])
        if raw_personas:
            return raw_personas
        return [
            {
                "name": "Primary Buyer",
                "demographics": {},
                "psychographics": {},
                "pain_points": [],
                "channels": [],
            }
        ]

    def _prioritise_segments(
        self, personas: list[dict[str, Any]]
    ) -> list[str]:
        return [p.get("name", str(i)) for i, p in enumerate(personas)]


class CompetitorAnalysisAgent(BaseDecisionAgent):
    """Competitive landscape — positioning matrix, strengths, and weaknesses."""

    def name(self) -> str:
        return "competitor_analysis"

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,
    ) -> DecisionArtifact:
        brand_name: str = context.get("brand_name", "unknown")
        existing_data: dict[str, Any] = context.get("existing_data", {})

        competitors = self._gather_competitors(brand_name, existing_data)
        positioning_matrix = self._build_positioning_matrix(competitors)
        swot = self._build_swot(brand_name, positioning_matrix)

        content: dict[str, Any] = {
            "competitors": competitors,
            "positioning_matrix": positioning_matrix,
            "swot": swot,
            "brand_name": brand_name,
        }

        return DecisionArtifact(
            artifact_type="competitor_matrix",
            content=content,
            format="yaml",
            metadata={
                "agent": self.name(),
                "brand": brand_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _gather_competitors(
        self, brand_name: str, existing_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return existing_data.get("competitors", [])

    def _build_positioning_matrix(
        self, competitors: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return [
            {
                "name": c.get("name", "unknown"),
                "strengths": c.get("strengths", []),
                "weaknesses": c.get("weaknesses", []),
                "market_share": c.get("market_share", ""),
            }
            for c in competitors
        ]

    def _build_swot(
        self, brand_name: str, matrix: list[dict[str, Any]]
    ) -> dict[str, list[str]]:
        return {
            "strengths": [],
            "weaknesses": [],
            "opportunities": [],
            "threats": [],
        }
