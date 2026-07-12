"""Tests for Scale-mode Decision Agents.

Covers all 5 scale agents: BrandHealthDiagnosisAgent,
MarketRevalidationAgent, AudienceDeepeningAgent,
CompetitorTrackingAgent, ContentAssetAuditAgent.
"""

from __future__ import annotations

from typing import Any

from automedia.decision.base import DecisionArtifact

SCALE_CONTEXT: dict[str, Any] = {
    "brand_name": "ScaleBrand",
    "market": "SaaS",
    "existing_data": {
        "social_mentions": 120,
        "search_volume_index": 60,
        "active_channels": ["website", "linkedin"],
        "brand_guidelines": True,
        "competitors": ["c1", "c2"],
        "unique_selling_points": ["speed", "support"],
    },
    "competitors": [
        {"name": "RivalA", "recent_changes": "Launched AI features"},
        {"name": "RivalB"},
    ],
    "existing_personas": [
        {"name": "tech_buyer", "segments": ["engineering"], "pain_points": ["slow setup"]},
    ],
    "search_results": [
        {"id": "a1", "title": "Blog post", "type": "blog", "age_days": 30, "performance_score": 90},
        {"id": "a2", "title": "Old guide", "type": "doc", "age_days": 800, "performance_score": 10},
    ],
    "existing_market_data": {
        "category_trends": ["AI adoption", "Usage-based pricing"],
        "emerging_opportunities": [{"area": "APAC", "description": "Growing market"}],
        "segment_recommendations": ["Focus on mid-market"],
    },
}


class TestBrandHealthDiagnosisAgent:
    """BrandHealthDiagnosisAgent produces a brand_health_report."""

    def test_name(self) -> None:
        from automedia.decision.scale import BrandHealthDiagnosisAgent

        assert BrandHealthDiagnosisAgent().name() == "brand_health_diagnosis"

    def test_execute_returns_artifact(self) -> None:
        from automedia.decision.scale import BrandHealthDiagnosisAgent

        result = BrandHealthDiagnosisAgent().execute(SCALE_CONTEXT)
        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "brand_health_report"

    def test_content_has_dimensions(self) -> None:
        from automedia.decision.scale import BrandHealthDiagnosisAgent

        result = BrandHealthDiagnosisAgent().execute(SCALE_CONTEXT)
        c = result.content
        assert "awareness" in c
        assert "consistency" in c
        assert "competitiveness" in c
        assert "overall_health" in c
        assert "recommendations" in c

    def test_metadata_contains_agent_and_brand(self) -> None:
        from automedia.decision.scale import BrandHealthDiagnosisAgent

        result = BrandHealthDiagnosisAgent().execute(SCALE_CONTEXT)
        assert result.metadata["agent"] == "brand_health_diagnosis"
        assert result.metadata["brand"] == "ScaleBrand"

    def test_empty_context_produces_defaults(self) -> None:
        from automedia.decision.scale import BrandHealthDiagnosisAgent

        result = BrandHealthDiagnosisAgent().execute({})
        assert result.artifact_type == "brand_health_report"
        assert result.metadata["brand"] == "unknown"


class TestMarketRevalidationAgent:
    """MarketRevalidationAgent produces a market_scan artifact."""

    def test_name(self) -> None:
        from automedia.decision.scale import MarketRevalidationAgent

        assert MarketRevalidationAgent().name() == "market_revalidation"

    def test_execute_returns_artifact(self) -> None:
        from automedia.decision.scale import MarketRevalidationAgent

        result = MarketRevalidationAgent().execute(SCALE_CONTEXT)
        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "market_scan"

    def test_content_has_core_fields(self) -> None:
        from automedia.decision.scale import MarketRevalidationAgent

        result = MarketRevalidationAgent().execute(SCALE_CONTEXT)
        c = result.content
        assert "category_trends" in c
        assert "emerging_opportunities" in c
        assert "segment_recommendations" in c

    def test_metadata_contains_agent_and_market(self) -> None:
        from automedia.decision.scale import MarketRevalidationAgent

        result = MarketRevalidationAgent().execute(SCALE_CONTEXT)
        assert result.metadata["agent"] == "market_revalidation"
        assert result.metadata["market"] == "SaaS"

    def test_empty_context_produces_defaults(self) -> None:
        from automedia.decision.scale import MarketRevalidationAgent

        result = MarketRevalidationAgent().execute({})
        assert result.artifact_type == "market_scan"
        assert len(result.content["category_trends"]) >= 1


class TestAudienceDeepeningAgent:
    """AudienceDeepeningAgent produces an audience_deepening artifact."""

    def test_name(self) -> None:
        from automedia.decision.scale import AudienceDeepeningAgent

        assert AudienceDeepeningAgent().name() == "audience_deepening"

    def test_execute_returns_artifact(self) -> None:
        from automedia.decision.scale import AudienceDeepeningAgent

        result = AudienceDeepeningAgent().execute(SCALE_CONTEXT)
        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "audience_deepening"

    def test_content_has_breakthrough_personas(self) -> None:
        from automedia.decision.scale import AudienceDeepeningAgent

        result = AudienceDeepeningAgent().execute(SCALE_CONTEXT)
        assert "breakthrough_personas" in result.content
        assert isinstance(result.content["breakthrough_personas"], list)

    def test_empty_context_produces_default_persona(self) -> None:
        from automedia.decision.scale import AudienceDeepeningAgent

        result = AudienceDeepeningAgent().execute({})
        personas = result.content["existing_personas"]
        assert len(personas) >= 1


class TestCompetitorTrackingAgent:
    """CompetitorTrackingAgent produces a competitor_tracking artifact."""

    def test_name(self) -> None:
        from automedia.decision.scale import CompetitorTrackingAgent

        assert CompetitorTrackingAgent().name() == "competitor_tracking"

    def test_execute_returns_artifact(self) -> None:
        from automedia.decision.scale import CompetitorTrackingAgent

        result = CompetitorTrackingAgent().execute(SCALE_CONTEXT)
        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "competitor_tracking"

    def test_content_has_competitors_and_opportunities(self) -> None:
        from automedia.decision.scale import CompetitorTrackingAgent

        result = CompetitorTrackingAgent().execute(SCALE_CONTEXT)
        c = result.content
        assert "competitors" in c
        assert "counter_positioning" in c
        assert "blue_ocean_opportunities" in c

    def test_empty_context_generates_synthetic_competitors(self) -> None:
        from automedia.decision.scale import CompetitorTrackingAgent

        result = CompetitorTrackingAgent().execute({})
        assert len(result.content["competitors"]) >= 2


class TestContentAssetAuditAgent:
    """ContentAssetAuditAgent produces an asset_audit artifact."""

    def test_name(self) -> None:
        from automedia.decision.scale import ContentAssetAuditAgent

        assert ContentAssetAuditAgent().name() == "content_asset_audit"

    def test_execute_returns_artifact(self) -> None:
        from automedia.decision.scale import ContentAssetAuditAgent

        result = ContentAssetAuditAgent().execute(SCALE_CONTEXT)
        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "asset_audit"

    def test_content_classifies_assets(self) -> None:
        from automedia.decision.scale import ContentAssetAuditAgent

        result = ContentAssetAuditAgent().execute(SCALE_CONTEXT)
        c = result.content
        assert "hero_content" in c
        assert "needs_update" in c
        assert "obsolete" in c
        assert "total_assets" in c
        assert c["total_assets"] >= 1

    def test_empty_context_produces_sample_assets(self) -> None:
        from automedia.decision.scale import ContentAssetAuditAgent

        result = ContentAssetAuditAgent().execute({})
        assert result.content["total_assets"] >= 1


class TestScalePackageExports:
    """All 5 scale agents are importable."""

    def test_all_importable(self) -> None:
        from automedia.decision.scale import (
            AudienceDeepeningAgent,
            BrandHealthDiagnosisAgent,
            CompetitorTrackingAgent,
            ContentAssetAuditAgent,
            MarketRevalidationAgent,
        )

        for cls in (
            AudienceDeepeningAgent,
            BrandHealthDiagnosisAgent,
            CompetitorTrackingAgent,
            ContentAssetAuditAgent,
            MarketRevalidationAgent,
        ):
            assert cls is not None

    def test_all_are_subclass_of_base(self) -> None:
        from automedia.decision.base import BaseDecisionAgent
        from automedia.decision.scale import (
            AudienceDeepeningAgent,
            BrandHealthDiagnosisAgent,
            CompetitorTrackingAgent,
            ContentAssetAuditAgent,
            MarketRevalidationAgent,
        )

        for cls in (
            AudienceDeepeningAgent,
            BrandHealthDiagnosisAgent,
            CompetitorTrackingAgent,
            ContentAssetAuditAgent,
            MarketRevalidationAgent,
        ):
            assert issubclass(cls, BaseDecisionAgent), f"{cls.__name__} is not a BaseDecisionAgent"
