"""Content Marketing Agent — message house, pillars, channels & calendar.

Consumes upstream artefacts (brand DNA, market report, persona map,
competitor matrix) and produces a ``strategy_doc`` that defines the
content-marketing blueprint.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from automedia.decision.base import BaseDecisionAgent, DecisionArtifact


class ContentMarketingAgent(BaseDecisionAgent):
    """Orchestrate content-marketing strategy from upstream artefacts."""

    def name(self) -> str:
        return "content_marketing"

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

        message_house = self._build_message_house(brand_dna, market_report)
        content_pillars = self._define_content_pillars(
            brand_dna, market_report, persona_map, competitor_matrix
        )
        channel_matrix = self._build_channel_matrix(brand_name, persona_map, market_report)
        calendar_framework = self._build_calendar_framework(content_pillars, channel_matrix)

        content: dict[str, Any] = {
            "core_message_house": message_house,
            "content_pillars": content_pillars,
            "channel_matrix": channel_matrix,
            "content_calendar_framework": calendar_framework,
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
    def _build_message_house(
        brand_dna: dict[str, Any],
        market_report: dict[str, Any],
    ) -> dict[str, Any]:
        """Construct the core-message-house framework."""
        root = brand_dna.get(
            "core_promise",
            brand_dna.get("value_proposition", "Trusted partner for growth"),
        )
        pillars = brand_dna.get("message_pillars", [])
        if not pillars:
            pillars = [
                "Innovation & thought leadership",
                "Customer success & community",
                "Product excellence & reliability",
            ]
        proof_points = brand_dna.get("proof_points", [])
        if not proof_points:
            proof_points = [
                "Industry awards and certifications",
                "Case studies with measurable ROI",
                "Customer testimonials and NPS score",
            ]

        return {
            "root_idea": root,
            "pillars": pillars,
            "proof_points": proof_points,
            "tone": brand_dna.get(
                "tone_of_voice",
                "Confident, approachable, data-informed",
            ),
        }

    @staticmethod
    def _define_content_pillars(
        brand_dna: dict[str, Any],
        market_report: dict[str, Any],
        persona_map: dict[str, Any],
        competitor_matrix: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Define 3‑5 content pillars with format and platform suggestions."""
        # Derive pillar themes from upstream data
        trends = market_report.get("category_trends", [])

        pillars_raw = brand_dna.get("content_pillars", [])
        if pillars_raw:
            return [
                {
                    "name": p.get("name", str(p)),
                    "description": p.get(
                        "description", f"Content pillar around {p.get('name', str(p))}"
                    ),
                    "formats": p.get("formats", ["blog_post", "video", "infographic"]),
                    "platforms": p.get("platforms", ["website", "linkedin", "youtube"]),
                }
                for p in pillars_raw
            ]

        pillar_defs = [
            {
                "name": "thought_leadership",
                "description": (
                    "Original research and POV content that positions"
                    " the brand as a category authority."
                ),
                "formats": ["white_paper", "data_report", "webinar", "linkedin_carousel"],
                "platforms": ["website", "linkedin", "industry_publications"],
            },
            {
                "name": "customer_stories",
                "description": (
                    "Real-world success narratives that build credibility and demonstrate ROI."
                ),
                "formats": ["case_study", "video_testimonial", "podcast_interview"],
                "platforms": ["website", "youtube", "sales_decks"],
            },
            {
                "name": "educational_how_to",
                "description": ("Practical guides and tutorials that help prospects self-educate."),
                "formats": ["blog_post", "video_tutorial", "template", "email_course"],
                "platforms": ["website", "youtube", "email", "search"],
            },
            {
                "name": "community_engagement",
                "description": (
                    "Interactive content that fosters peer-to-peer connection and advocacy."
                ),
                "formats": ["forum_qa", "user_group", "ama_session", "social_poll"],
                "platforms": ["slack_community", "linkedin_group", "discord"],
            },
            {
                "name": "product_innovation",
                "description": (
                    "Product-led content showcasing new features, roadmap, and technical depth."
                ),
                "formats": ["changelog", "demo_video", "technical_blog", "release_notes"],
                "platforms": ["website", "youtube", "twitter", "newsletter"],
            },
        ]

        # Add market-driven nuance where available
        if trends:
            pillar_defs.insert(
                1,
                {
                    "name": "trend_analysis",
                    "description": (
                        "Timely commentary on "
                        f"{trends[0].lower() if isinstance(trends[0], str) else 'industry shifts'}."
                    ),
                    "formats": ["trend_report", "infographic", "newsletter_analysis"],
                    "platforms": ["linkedin", "industry_publications", "email"],
                },
            )

        return pillar_defs

    @staticmethod
    def _build_channel_matrix(
        brand: str,
        persona_map: dict[str, Any],
        market_report: dict[str, Any],
    ) -> dict[str, Any]:
        """Map channels to audience segments and content types."""
        personas = persona_map.get("personas", [])
        persona_names = (
            [p["name"] for p in personas if isinstance(p, dict)]
            if personas
            else ["primary", "secondary", "tertiary"]
        )

        return {
            "website": {
                "primary_audience": persona_names,
                "content_types": ["blog", "case_studies", "product_pages", "resource_library"],
                "goal": "convert_search_traffic",
                "investment_level": "high",
            },
            "linkedin": {
                "primary_audience": persona_names[:2],
                "content_types": ["thought_leadership", "company_updates", "carousel_posts"],
                "goal": "build_authority",
                "investment_level": "high",
            },
            "youtube": {
                "primary_audience": persona_names[:1],
                "content_types": ["tutorials", "webinars", "customer_stories"],
                "goal": "top_of_funnel_awareness",
                "investment_level": "medium",
            },
            "email": {
                "primary_audience": persona_names,
                "content_types": ["newsletter", "nurture_sequence", "product_update"],
                "goal": "retention_and_repeat_traffic",
                "investment_level": "medium",
            },
            "twitter": {
                "primary_audience": persona_names[:1],
                "content_types": ["quick_tips", "community_updates", "threads"],
                "goal": "real_time_engagement",
                "investment_level": "low",
            },
            "search_organic": {
                "primary_audience": persona_names,
                "content_types": ["seo_optimised_blog", "landing_pages", "tools"],
                "goal": "demand_capture",
                "investment_level": "high",
            },
        }

    @staticmethod
    def _build_calendar_framework(
        content_pillars: list[dict[str, Any]],
        channel_matrix: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generate a high-level content calendar framework.

        Returns one entry per month with focus themes, channel mix, and
        campaign types.
        """
        pillar_names = [p["name"] for p in content_pillars if isinstance(p, dict)]
        if not pillar_names:
            pillar_names = ["awareness", "consideration", "conversion", "retention"]

        months = [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ]

        channel_keys = list(channel_matrix.keys()) if channel_matrix else ["website", "social"]

        calendar: list[dict[str, Any]] = []
        for i, month in enumerate(months):
            primary_pillar = pillar_names[i % len(pillar_names)]
            secondary_pillar = pillar_names[(i + 1) % len(pillar_names)]
            calendar.append(
                {
                    "month": month,
                    "theme": f"Focus on {primary_pillar.replace('_', ' ')}",
                    "primary_pillar": primary_pillar,
                    "secondary_pillar": secondary_pillar,
                    "channel_mix": channel_keys[:3],
                    "campaign_types": ["top_of_funnel", "nurture", "retention"],
                    "key_deliverable_count": max(4, 8 - i % 3),
                }
            )

        return calendar
