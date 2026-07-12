"""Tests for Strategy Engine Decision Agents.

Covers ContentMarketingAgent and ProductOptimizationAgent — both produce
``strategy_doc`` artifacts from upstream artefacts.
"""

from __future__ import annotations

from typing import Any

from automedia.decision.base import DecisionArtifact

SAMPLE_CONTEXT: dict[str, Any] = {
    "brand_dna": {
        "brand_name": "TestBrand",
        "core_promise": "Reliable AI tools",
        "tone_of_voice": "Professional",
        "value_proposition": "AI-powered efficiency",
        "target_audience": "SMBs in SEA",
        "features": ["auto_scheduling", "smart_analytics"],
        "content_pillars": [
            {"name": "innovation", "description": "New tech insights", "formats": ["blog"], "platforms": ["web"]},
        ],
        "unique_selling_points": ["speed", "accuracy"],
    },
    "market_report": {
        "market": "SaaS",
        "category_trends": ["AI adoption", "Cloud migration"],
    },
    "persona_map": {
        "personas": [
            {"name": "tech_lead", "segments": ["engineering"]},
            {"name": "marketing_mgr", "segments": ["marketing"]},
        ],
        "wishlist_features": ["api_access", "custom_dashboards"],
    },
    "competitor_matrix": {
        "differentiator": "open-source core",
        "competitors": [],
    },
}


class TestContentMarketingAgent:
    """ContentMarketingAgent produces a strategy_doc artifact."""

    def test_name(self) -> None:
        from automedia.decision.strategy import ContentMarketingAgent

        agent = ContentMarketingAgent()
        assert agent.name() == "content_marketing"

    def test_execute_returns_decision_artifact(self) -> None:
        from automedia.decision.strategy import ContentMarketingAgent

        agent = ContentMarketingAgent()
        result = agent.execute(SAMPLE_CONTEXT)
        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "strategy_doc"

    def test_content_has_core_fields(self) -> None:
        from automedia.decision.strategy import ContentMarketingAgent

        agent = ContentMarketingAgent()
        result = agent.execute(SAMPLE_CONTEXT)
        c = result.content
        assert "core_message_house" in c
        assert "content_pillars" in c
        assert "channel_matrix" in c
        assert "content_calendar_framework" in c

    def test_metadata_contains_agent_name(self) -> None:
        from automedia.decision.strategy import ContentMarketingAgent

        agent = ContentMarketingAgent()
        result = agent.execute(SAMPLE_CONTEXT)
        assert result.metadata["agent"] == "content_marketing"
        assert result.metadata["brand"] == "TestBrand"

    def test_calendar_has_12_months(self) -> None:
        from automedia.decision.strategy import ContentMarketingAgent

        agent = ContentMarketingAgent()
        result = agent.execute(SAMPLE_CONTEXT)
        cal = result.content["content_calendar_framework"]
        assert len(cal) == 12

    def test_empty_context_produces_defaults(self) -> None:
        from automedia.decision.strategy import ContentMarketingAgent

        agent = ContentMarketingAgent()
        result = agent.execute({})
        assert result.artifact_type == "strategy_doc"
        assert result.metadata["brand"] == "unknown"


class TestProductOptimizationAgent:
    """ProductOptimizationAgent produces a strategy_doc artifact."""

    def test_name(self) -> None:
        from automedia.decision.strategy import ProductOptimizationAgent

        agent = ProductOptimizationAgent()
        assert agent.name() == "product_optimization"

    def test_execute_returns_decision_artifact(self) -> None:
        from automedia.decision.strategy import ProductOptimizationAgent

        agent = ProductOptimizationAgent()
        result = agent.execute(SAMPLE_CONTEXT)
        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "strategy_doc"

    def test_content_has_core_fields(self) -> None:
        from automedia.decision.strategy import ProductOptimizationAgent

        agent = ProductOptimizationAgent()
        result = agent.execute(SAMPLE_CONTEXT)
        c = result.content
        assert "product_positioning" in c
        assert "feature_priorities" in c
        assert "localization_selling_points" in c
        assert "optimization_recommendations" in c

    def test_metadata_contains_agent_name(self) -> None:
        from automedia.decision.strategy import ProductOptimizationAgent

        agent = ProductOptimizationAgent()
        result = agent.execute(SAMPLE_CONTEXT)
        assert result.metadata["agent"] == "product_optimization"

    def test_feature_priorities_sorted_by_composite_score(self) -> None:
        from automedia.decision.strategy import ProductOptimizationAgent

        agent = ProductOptimizationAgent()
        result = agent.execute(SAMPLE_CONTEXT)
        fps = result.content["feature_priorities"]
        scores = [f["composite_score"] for f in fps]
        assert scores == sorted(scores, reverse=True)

    def test_empty_context_produces_defaults(self) -> None:
        from automedia.decision.strategy import ProductOptimizationAgent

        agent = ProductOptimizationAgent()
        result = agent.execute({})
        assert result.artifact_type == "strategy_doc"
        assert result.metadata["brand"] == "unknown"
        assert len(result.content["feature_priorities"]) >= 3


class TestStrategyPackageExports:
    """Both strategy agents are importable from the package."""

    def test_imports(self) -> None:
        from automedia.decision.strategy import ContentMarketingAgent, ProductOptimizationAgent

        assert ContentMarketingAgent is not None
        assert ProductOptimizationAgent is not None

    def test_both_are_subclass_of_base(self) -> None:
        from automedia.decision.base import BaseDecisionAgent
        from automedia.decision.strategy import ContentMarketingAgent, ProductOptimizationAgent

        assert issubclass(ContentMarketingAgent, BaseDecisionAgent)
        assert issubclass(ProductOptimizationAgent, BaseDecisionAgent)
