"""Build-mode Decision Agents — brand strategy from scratch.

Exports
-------
- ``BrandPositioningAgent`` — define brand DNA (vision, mission, values, personality, tone)
- ``MarketResearchAgent`` — market sizing, consumer profiling, competitors overview
- ``AudienceSegmentationAgent`` — persona definition (3-5 personas with rich fields)
- ``CompetitorAnalysisAgent`` — competitive positioning (5 entries, SWOT, opportunities)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from automedia.decision.base import BaseDecisionAgent, DecisionArtifact


class BrandPositioningAgent(BaseDecisionAgent):
    """Define brand DNA — vision, mission, values, personality, tone, multilingual slogans."""

    def name(self) -> str:
        return "brand_positioning"

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,
    ) -> DecisionArtifact:
        idea: str = context.get("idea", "")
        brand_name: str = context.get("brand_name", "") or idea.strip().title() or "unknown"
        market: str = context.get("market", "")

        slogan = f"{brand_name}: {idea}" if idea else f"{brand_name}: Your trusted partner"

        content: dict[str, Any] = {
            "brand_name": brand_name,
            "vision": f"To become the leading brand in {market or 'the industry'}",
            "mission": f"Deliver exceptional {idea.lower() if idea else 'products'}",
            "values": ["innovation", "quality", "customer-centric", "integrity"],
            "personality": "innovative and trustworthy",
            "tone_of_voice": "professional yet approachable",
            "differentiators": [],
            "multilingual_slogans": {
                "en": slogan,
                "zh": f"{brand_name}：{idea}",
                "ja": f"{brand_name}：{idea}",
                "ko": f"{brand_name}：{idea}",
            },
        }

        return DecisionArtifact(
            artifact_type="brand_dna",
            content=content,
            format="yaml",
            metadata={
                "agent": self.name(),
                "phase": 3,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )


class MarketResearchAgent(BaseDecisionAgent):
    """Analyse market landscape — sizing, consumer profile, cultural factors."""

    def name(self) -> str:
        return "market_research"

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,
    ) -> DecisionArtifact:
        idea: str = context.get("idea", "")
        market: str = context.get("market", "global")
        mock: bool = context.get("mock", True)

        content: dict[str, Any] = {
            "market_size": f"$1B+ TAM in {market}" if market else "$1B+ TAM",
            "consumer_profile": {
                "age_range": "25-45",
                "gender_split": "50/50",
                "income_level": "middle to upper-middle",
                "education": "college or above",
                "values": ["quality", "innovation", "convenience"],
            },
            "cultural_taboos": [],
            "compliance_requirements": [],
            "competitors_overview": f"Key players in {idea.lower() if idea else 'the'} market"
            if idea
            else "Key players in the market",
        }

        metadata: dict[str, Any] = {
            "agent": self.name(),
            "phase": 4,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        metadata["mock"] = mock

        return DecisionArtifact(
            artifact_type="market_report",
            content=content,
            format="yaml",
            metadata=metadata,
        )


class AudienceSegmentationAgent(BaseDecisionAgent):
    """Define audience personas — 3-5 personas with rich demographic and psychographic fields."""

    def name(self) -> str:
        return "audience_segmentation"

    @staticmethod
    def _make_persona(
        name: str,
        age_range: str,
        gender: str,
        income_level: str,
        location: str,
        values: list[str],
        interests: list[str],
        challenges: list[str],
        content_preferences: list[str],
        platforms: list[str],
        pain_points: list[str],
        resonance_scores: dict[str, int],
    ) -> dict[str, Any]:
        return {
            "name": name,
            "age_range": age_range,
            "gender": gender,
            "income_level": income_level,
            "location": location,
            "values": values,
            "interests": interests,
            "challenges": challenges,
            "content_preferences": content_preferences,
            "platforms": platforms,
            "pain_points": pain_points,
            "content_resonance_map": resonance_scores,
        }

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,
    ) -> DecisionArtifact:
        content: dict[str, Any] = {
            "personas": [
                self._make_persona(
                    name="Early Adopter",
                    age_range="22-35",
                    gender="all",
                    income_level="middle",
                    location="urban",
                    values=["innovation", "convenience"],
                    interests=["tech", "trends", "gadgets"],
                    challenges=["information overload", "high expectations"],
                    content_preferences=["video", "interactive"],
                    platforms=["youtube", "tiktok", "twitter"],
                    pain_points=["Needs solution now", "Wants early access"],
                    resonance_scores={"video": 9, "text": 5, "audio": 6},
                ),
                self._make_persona(
                    name="Value Seeker",
                    age_range="28-50",
                    gender="all",
                    income_level="middle to upper-middle",
                    location="suburban",
                    values=["quality", "affordability", "trust"],
                    interests=["reviews", "comparisons", "deals"],
                    challenges=["limited time", "brand skepticism"],
                    content_preferences=["long-form", "comparison"],
                    platforms=["email", "search", "linkedin"],
                    pain_points=["Wants best value", "Needs proof"],
                    resonance_scores={"video": 7, "text": 8, "audio": 5},
                ),
                self._make_persona(
                    name="Brand Loyalist",
                    age_range="35-60",
                    gender="all",
                    income_level="upper-middle",
                    location="urban and suburban",
                    values=["loyalty", "consistency", "premium"],
                    interests=["brand stories", "quality content", "rewards"],
                    challenges=["hard to switch", "high standards"],
                    content_preferences=["stories", "community"],
                    platforms=["referral", "community", "instagram"],
                    pain_points=["Expects quality", "Wants recognition"],
                    resonance_scores={"video": 8, "text": 7, "audio": 7},
                ),
            ],
        }

        return DecisionArtifact(
            artifact_type="persona_map",
            content=content,
            format="yaml",
            metadata={
                "agent": self.name(),
                "phase": 5,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )


class CompetitorAnalysisAgent(BaseDecisionAgent):
    """Competitive landscape — exactly 5 competitors with SWOT, market share, gaps."""

    def name(self) -> str:
        return "competitor_analysis"

    @staticmethod
    def _make_competitor(
        name: str,
        swot_strengths: list[str],
        swot_weaknesses: list[str],
        swot_opportunities: list[str],
        swot_threats: list[str],
        market_share: str,
        differentiation_gaps: list[str],
    ) -> dict[str, Any]:
        return {
            "name": name,
            "swot": {
                "strengths": swot_strengths,
                "weaknesses": swot_weaknesses,
                "opportunities": swot_opportunities,
                "threats": swot_threats,
            },
            "market_share": market_share,
            "differentiation_gaps": differentiation_gaps,
        }

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,
    ) -> DecisionArtifact:
        content: dict[str, Any] = {
            "competitors": [
                self._make_competitor(
                    "Competitor A",
                    swot_strengths=["market leader", "strong brand recognition"],
                    swot_weaknesses=["slow to innovate", "high prices"],
                    swot_opportunities=["emerging markets", "new demographics"],
                    swot_threats=["new entrants", "changing regulations"],
                    market_share="35%",
                    differentiation_gaps=["limited personalisation", "slow support"],
                ),
                self._make_competitor(
                    "Competitor B",
                    swot_strengths=["strong brand", "loyal customer base"],
                    swot_weaknesses=["limited distribution", "outdated tech"],
                    swot_opportunities=["digital transformation", "partnerships"],
                    swot_threats=["direct competitors", "market saturation"],
                    market_share="25%",
                    differentiation_gaps=["no mobile app", "weak social media"],
                ),
                self._make_competitor(
                    "Competitor C",
                    swot_strengths=["low cost", "wide reach"],
                    swot_weaknesses=["low quality", "poor reputation"],
                    swot_opportunities=["premium segment", "quality improvement"],
                    swot_threats=["price wars", "commoditisation"],
                    market_share="20%",
                    differentiation_gaps=["no premium offering", "weak branding"],
                ),
                self._make_competitor(
                    "Competitor D",
                    swot_strengths=["innovative", "agile"],
                    swot_weaknesses=["small market share", "limited funding"],
                    swot_opportunities=["niche segments", "venture capital"],
                    swot_threats=["copycats", "market consolidation"],
                    market_share="12%",
                    differentiation_gaps=["limited scale", "narrow product line"],
                ),
                self._make_competitor(
                    "Competitor E",
                    swot_strengths=["global reach", "diverse portfolio"],
                    swot_weaknesses=["impersonal service", "bureaucracy"],
                    swot_opportunities=["localisation", "AI-driven service"],
                    swot_threats=["regional competitors", "regulatory hurdles"],
                    market_share="8%",
                    differentiation_gaps=["slow response time", "generic messaging"],
                ),
            ],
            "top_opportunities": [
                "Differentiate through personalisation",
                "Target underserved niche segments",
            ],
            "white_space_recommendations": [
                "Focus on customer experience as key differentiator",
                "Invest in emerging market presence",
            ],
        }

        return DecisionArtifact(
            artifact_type="competitor_matrix",
            content=content,
            format="yaml",
            metadata={
                "agent": self.name(),
                "phase": 6,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
