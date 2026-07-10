"""RED tests for Build-mode Decision Agents (T03–T06).

Covers
------
1. BrandPositioningAgent  — brand DNA artifact shape and content
2. MarketResearchAgent   — mock-compatible market report
3. AudienceSegmentationAgent — persona map with 3–5 personas
4. CompetitorAnalysisAgent   — competitor matrix with exactly 5 entries
"""

from __future__ import annotations

from typing import Any

from automedia.decision.base import DecisionArtifact

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_IDEA = "AI-powered video creation"
SAMPLE_MARKET = "Southeast Asia"
MIN_CONTEXT: dict[str, Any] = {
    "idea": SAMPLE_IDEA,
    "market": SAMPLE_MARKET,
    "stage": "new",
    "mode": "build",
}


# ===================================================================
# T03 — BrandPositioningAgent
# ===================================================================


class TestBrandPositioningAgent:
    """BrandPositioningAgent produces a ``brand_dna`` artifact."""

    def test_name(self) -> None:
        from automedia.decision.build import BrandPositioningAgent

        agent = BrandPositioningAgent()
        assert agent.name() == "brand_positioning"

    def test_execute_returns_decision_artifact(self) -> None:
        from automedia.decision.build import BrandPositioningAgent

        agent = BrandPositioningAgent()
        result = agent.execute(MIN_CONTEXT)
        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "brand_dna"

    def test_content_contains_all_required_fields(self) -> None:
        from automedia.decision.build import BrandPositioningAgent

        agent = BrandPositioningAgent()
        result = agent.execute(MIN_CONTEXT)
        c = result.content
        assert "brand_name" in c and c["brand_name"]
        assert "vision" in c and c["vision"]
        assert "mission" in c and c["mission"]
        assert "values" in c and isinstance(c["values"], list) and len(c["values"]) >= 3
        assert "personality" in c and c["personality"]
        assert "tone_of_voice" in c and c["tone_of_voice"]

    def test_multilingual_slogans_has_all_locales(self) -> None:
        from automedia.decision.build import BrandPositioningAgent

        agent = BrandPositioningAgent()
        result = agent.execute(MIN_CONTEXT)
        slogans = result.content.get("multilingual_slogans", {})
        for lang in ("en", "zh", "ja", "ko"):
            assert lang in slogans, f"Missing slogan for '{lang}'"
            assert slogans[lang], f"Empty slogan for '{lang}'"

    def test_brand_name_derived_from_idea_when_not_provided(self) -> None:
        from automedia.decision.build import BrandPositioningAgent

        agent = BrandPositioningAgent()
        result = agent.execute({"idea": "Eco Bottle", "market": "US"})
        assert "Eco" in result.content["brand_name"] or "Bottle" in result.content["brand_name"]

    def test_brand_name_respects_explicit_value(self) -> None:
        from automedia.decision.build import BrandPositioningAgent

        agent = BrandPositioningAgent()
        ctx = {**MIN_CONTEXT, "brand_name": "MyExplicitBrand"}
        result = agent.execute(ctx)
        assert result.content["brand_name"] == "MyExplicitBrand"

    def test_metadata_contains_agent_name(self) -> None:
        from automedia.decision.build import BrandPositioningAgent

        agent = BrandPositioningAgent()
        result = agent.execute(MIN_CONTEXT)
        assert result.metadata.get("agent") == "brand_positioning"
        assert result.metadata.get("phase") == 3


# ===================================================================
# T04 — MarketResearchAgent
# ===================================================================


class TestMarketResearchAgent:
    """MarketResearchAgent produces a ``market_report`` artifact."""

    def test_name(self) -> None:
        from automedia.decision.build import MarketResearchAgent

        agent = MarketResearchAgent()
        assert agent.name() == "market_research"

    def test_execute_returns_decision_artifact(self) -> None:
        from automedia.decision.build import MarketResearchAgent

        agent = MarketResearchAgent()
        result = agent.execute(MIN_CONTEXT)
        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "market_report"

    def test_content_contains_all_required_fields(self) -> None:
        from automedia.decision.build import MarketResearchAgent

        agent = MarketResearchAgent()
        result = agent.execute(MIN_CONTEXT)
        c = result.content
        assert "market_size" in c and c["market_size"]
        assert "consumer_profile" in c
        assert isinstance(c["consumer_profile"], dict)
        assert "cultural_taboos" in c and isinstance(c["cultural_taboos"], list)
        assert "compliance_requirements" in c and isinstance(c["compliance_requirements"], list)
        assert "competitors_overview" in c and c["competitors_overview"]

    def test_consumer_profile_has_required_keys(self) -> None:
        from automedia.decision.build import MarketResearchAgent

        agent = MarketResearchAgent()
        result = agent.execute(MIN_CONTEXT)
        profile = result.content["consumer_profile"]
        for key in ("age_range", "gender_split", "income_level", "education", "values"):
            assert key in profile, f"Missing consumer_profile key: {key}"

    def test_mock_mode_by_default(self) -> None:
        """The agent defaults to mock=True so it never calls external APIs."""
        from automedia.decision.build import MarketResearchAgent

        agent = MarketResearchAgent()
        result = agent.execute(MIN_CONTEXT)
        # Should still produce valid content even without external calls
        assert result.content["market_size"]
        assert result.metadata.get("mock") is True

    def test_explicit_mock_flag(self) -> None:
        from automedia.decision.build import MarketResearchAgent

        agent = MarketResearchAgent()
        result = agent.execute({**MIN_CONTEXT, "mock": False})
        # Currently both paths return mock data; the flag is recorded
        assert "mock" in result.metadata

    def test_empty_idea_fallback(self) -> None:
        from automedia.decision.build import MarketResearchAgent

        agent = MarketResearchAgent()
        result = agent.execute({"idea": "", "market": ""})
        assert result.content["market_size"]
        assert result.content["competitors_overview"]


# ===================================================================
# T05 — AudienceSegmentationAgent
# ===================================================================


class TestAudienceSegmentationAgent:
    """AudienceSegmentationAgent produces a ``persona_map`` artifact."""

    def test_name(self) -> None:
        from automedia.decision.build import AudienceSegmentationAgent

        agent = AudienceSegmentationAgent()
        assert agent.name() == "audience_segmentation"

    def test_execute_returns_decision_artifact(self) -> None:
        from automedia.decision.build import AudienceSegmentationAgent

        agent = AudienceSegmentationAgent()
        result = agent.execute(MIN_CONTEXT)
        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "persona_map"

    def test_persona_count_between_3_and_5(self) -> None:
        from automedia.decision.build import AudienceSegmentationAgent

        agent = AudienceSegmentationAgent()
        result = agent.execute(MIN_CONTEXT)
        personas = result.content.get("personas", [])
        assert 3 <= len(personas) <= 5, f"Expected 3-5 personas, got {len(personas)}"

    def test_each_persona_has_required_fields(self) -> None:
        from automedia.decision.build import AudienceSegmentationAgent

        agent = AudienceSegmentationAgent()
        result = agent.execute(MIN_CONTEXT)
        required = {
            "name",
            "age_range",
            "gender",
            "income_level",
            "location",
            "values",
            "interests",
            "challenges",
            "content_preferences",
            "platforms",
            "pain_points",
            "content_resonance_map",
        }
        for idx, p in enumerate(result.content["personas"]):
            missing = required - set(p.keys())
            assert not missing, f"Persona {idx} ('{p.get('name')}') missing: {missing}"

    def test_content_resonance_map_is_dict_with_scores(self) -> None:
        from automedia.decision.build import AudienceSegmentationAgent

        agent = AudienceSegmentationAgent()
        result = agent.execute(MIN_CONTEXT)
        for p in result.content["personas"]:
            crm = p.get("content_resonance_map", {})
            assert isinstance(crm, dict)
            assert all(isinstance(v, int) for v in crm.values())

    def test_platforms_is_nonempty_list(self) -> None:
        from automedia.decision.build import AudienceSegmentationAgent

        agent = AudienceSegmentationAgent()
        result = agent.execute(MIN_CONTEXT)
        for p in result.content["personas"]:
            assert isinstance(p.get("platforms"), list)
            assert len(p["platforms"]) >= 1

    def test_metadata_contains_agent_and_phase(self) -> None:
        from automedia.decision.build import AudienceSegmentationAgent

        agent = AudienceSegmentationAgent()
        result = agent.execute(MIN_CONTEXT)
        assert result.metadata.get("agent") == "audience_segmentation"
        assert result.metadata.get("phase") == 5


# ===================================================================
# T06 — CompetitorAnalysisAgent
# ===================================================================


class TestCompetitorAnalysisAgent:
    """CompetitorAnalysisAgent produces a ``competitor_matrix`` artifact."""

    def test_name(self) -> None:
        from automedia.decision.build import CompetitorAnalysisAgent

        agent = CompetitorAnalysisAgent()
        assert agent.name() == "competitor_analysis"

    def test_execute_returns_decision_artifact(self) -> None:
        from automedia.decision.build import CompetitorAnalysisAgent

        agent = CompetitorAnalysisAgent()
        result = agent.execute(MIN_CONTEXT)
        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "competitor_matrix"

    def test_exactly_five_competitors(self) -> None:
        from automedia.decision.build import CompetitorAnalysisAgent

        agent = CompetitorAnalysisAgent()
        result = agent.execute(MIN_CONTEXT)
        competitors = result.content.get("competitors", [])
        assert len(competitors) == 5, f"Expected exactly 5 competitors, got {len(competitors)}"

    def test_each_competitor_has_required_fields(self) -> None:
        from automedia.decision.build import CompetitorAnalysisAgent

        agent = CompetitorAnalysisAgent()
        result = agent.execute(MIN_CONTEXT)
        required = {"name", "swot", "market_share", "differentiation_gaps"}
        for idx, comp in enumerate(result.content["competitors"]):
            missing = required - set(comp.keys())
            assert not missing, f"Competitor {idx} ('{comp.get('name')}') missing: {missing}"

    def test_swot_contains_all_four_categories(self) -> None:
        from automedia.decision.build import CompetitorAnalysisAgent

        agent = CompetitorAnalysisAgent()
        result = agent.execute(MIN_CONTEXT)
        swot_keys = {"strengths", "weaknesses", "opportunities", "threats"}
        for comp in result.content["competitors"]:
            missing = swot_keys - set(comp["swot"].keys())
            assert not missing, f"'{comp['name']}' SWOT missing: {missing}"
            for key in swot_keys:
                assert isinstance(comp["swot"][key], list)
                assert len(comp["swot"][key]) >= 1, f"'{comp['name']}' SWOT.{key} is empty"

    def test_top_opportunities_and_white_space_present(self) -> None:
        from automedia.decision.build import CompetitorAnalysisAgent

        agent = CompetitorAnalysisAgent()
        result = agent.execute(MIN_CONTEXT)
        assert "top_opportunities" in result.content
        assert isinstance(result.content["top_opportunities"], list)
        assert len(result.content["top_opportunities"]) >= 1
        assert "white_space_recommendations" in result.content
        assert isinstance(result.content["white_space_recommendations"], list)
        assert len(result.content["white_space_recommendations"]) >= 1

    def test_works_with_market_report_context(self) -> None:
        """When a market_report sub-dict is provided, use it as source."""
        from automedia.decision.build import CompetitorAnalysisAgent

        agent = CompetitorAnalysisAgent()
        ctx = {
            "market_report": {
                "market": "Europe",
                "idea": "No-code analytics",
            },
        }
        result = agent.execute(ctx)
        assert len(result.content["competitors"]) == 5

    def test_metadata_contains_agent_and_phase(self) -> None:
        from automedia.decision.build import CompetitorAnalysisAgent

        agent = CompetitorAnalysisAgent()
        result = agent.execute(MIN_CONTEXT)
        assert result.metadata.get("agent") == "competitor_analysis"
        assert result.metadata.get("phase") == 6


# ===================================================================
# Cross-agent — all four are importable via the build package
# ===================================================================


class TestBuildPackageExports:
    """The ``automedia.decision.build`` package exports all 4 agents."""

    def test_all_agents_importable(self) -> None:
        from automedia.decision.build import (
            AudienceSegmentationAgent,
            BrandPositioningAgent,
            CompetitorAnalysisAgent,
            MarketResearchAgent,
        )

        assert BrandPositioningAgent is not None
        assert MarketResearchAgent is not None
        assert AudienceSegmentationAgent is not None
        assert CompetitorAnalysisAgent is not None

    def test_all_agents_are_subclass_of_base(self) -> None:
        from automedia.decision.base import BaseDecisionAgent
        from automedia.decision.build import (
            AudienceSegmentationAgent,
            BrandPositioningAgent,
            CompetitorAnalysisAgent,
            MarketResearchAgent,
        )

        for cls in (
            BrandPositioningAgent,
            MarketResearchAgent,
            AudienceSegmentationAgent,
            CompetitorAnalysisAgent,
        ):
            assert issubclass(cls, BaseDecisionAgent), f"{cls.__name__} is not a BaseDecisionAgent"
