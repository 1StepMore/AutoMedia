"""Tests for Pydantic v2 models in ``automedia.decision.pydantic``.

Covers all 6 models::

    BrandStrategyOutput
    PipelineStrategyOutput
    TopicResearchOutput
    ContentQualityOutput
    FactCheckOutput
    CopyReviewOutput

Each test suite verifies:
1. Valid construction with all fields
2. Default values when optional fields are omitted
3. Strict validation rejects invalid types (``ConfigDict(strict=True)``)
4. Constraint validation (range checks on ``ge`` / ``le`` fields)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from automedia.decision.pydantic import (
    BrandStrategyOutput,
    ContentQualityOutput,
    CopyReviewOutput,
    FactCheckOutput,
    PipelineStrategyOutput,
    TopicResearchOutput,
)

# ===================================================================
# BrandStrategyOutput
# ===================================================================


class TestBrandStrategyOutput:
    """BrandStrategyOutput — brand positioning and strategy output."""

    def test_valid_construction(self) -> None:
        """All required fields accepted."""
        model = BrandStrategyOutput(
            brand_positioning="Premium AI tools for creators",
            audience_analysis="SMBs in Southeast Asia, 25-45, tech-savvy",
            competitive_landscape="3 major players, 5 niche competitors",
            key_differentiators=["speed", "accuracy", "localization"],
            suggested_messaging=["trust", "innovation", "simplicity"],
        )
        assert model.brand_positioning == "Premium AI tools for creators"
        assert model.audience_analysis == "SMBs in Southeast Asia, 25-45, tech-savvy"
        assert model.competitive_landscape == "3 major players, 5 niche competitors"
        assert model.key_differentiators == ["speed", "accuracy", "localization"]
        assert model.suggested_messaging == ["trust", "innovation", "simplicity"]

    def test_defaults(self) -> None:
        """Optional list fields default to empty lists."""
        model = BrandStrategyOutput(
            brand_positioning="pos",
            audience_analysis="aud",
            competitive_landscape="comp",
        )
        assert model.key_differentiators == []
        assert model.suggested_messaging == []

    def test_minimal_construction(self) -> None:
        """Only required fields — no optionals."""
        model = BrandStrategyOutput(
            brand_positioning="x",
            audience_analysis="y",
            competitive_landscape="z",
        )
        assert model.brand_positioning == "x"

    def test_rejects_int_for_str_field(self) -> None:
        """Strict mode rejects int where str is expected."""
        with pytest.raises(ValidationError):
            BrandStrategyOutput(
                brand_positioning=42,  # type: ignore[arg-type]
                audience_analysis="ok",
                competitive_landscape="ok",
            )


# ===================================================================
# PipelineStrategyOutput
# ===================================================================


class TestPipelineStrategyOutput:
    """PipelineStrategyOutput — pipeline content strategy output."""

    def test_valid_construction(self) -> None:
        """All required and optional fields accepted."""
        model = PipelineStrategyOutput(
            topic_brief="AI video creation tools comparison 2026",
            content_structure=["intro", "comparison", "recommendation"],
            platform_distribution={"youtube": "long form", "tiktok": "shorts"},
            estimated_duration="8-12 minutes",
            key_angles=["time savings", "cost comparison"],
        )
        assert model.topic_brief == "AI video creation tools comparison 2026"
        assert model.content_structure == ["intro", "comparison", "recommendation"]
        assert model.platform_distribution == {"youtube": "long form", "tiktok": "shorts"}
        assert model.estimated_duration == "8-12 minutes"
        assert model.key_angles == ["time savings", "cost comparison"]

    def test_defaults(self) -> None:
        """Optional fields default correctly."""
        model = PipelineStrategyOutput(
            topic_brief="brief",
            content_structure=["a"],
        )
        assert model.platform_distribution == {}
        assert model.estimated_duration is None
        assert model.key_angles == []

    def test_estimated_duration_accepts_none(self) -> None:
        """estimated_duration is Optional[str] and accepts None."""
        model = PipelineStrategyOutput(
            topic_brief="brief",
            content_structure=["a"],
            estimated_duration=None,
        )
        assert model.estimated_duration is None

    def test_rejects_list_for_str_field(self) -> None:
        """Strict mode rejects list where str is expected."""
        with pytest.raises(ValidationError):
            PipelineStrategyOutput(
                topic_brief=["not", "a", "string"],  # type: ignore[arg-type]
                content_structure=["a"],
            )


# ===================================================================
# TopicResearchOutput
# ===================================================================


class TestTopicResearchOutput:
    """TopicResearchOutput — topic research results."""

    def test_valid_construction(self) -> None:
        """All fields accepted with valid values."""
        model = TopicResearchOutput(
            topics=[
                {"title": "AI in 2026", "score": 8.5},
                {"title": "Low-code trends", "score": 7.0},
            ],
            category="technology",
            total_found=2,
        )
        assert len(model.topics) == 2
        assert model.topics[0]["title"] == "AI in 2026"
        assert model.category == "technology"
        assert model.total_found == 2

    def test_defaults(self) -> None:
        """Optional fields default correctly."""
        model = TopicResearchOutput(category="science")
        assert model.topics == []
        assert model.total_found == 0

    def test_minimal_construction(self) -> None:
        """Only required field (category)."""
        model = TopicResearchOutput(category="business")
        assert model.category == "business"

    def test_rejects_int_for_category(self) -> None:
        """Strict mode rejects int where str is expected for required field."""
        with pytest.raises(ValidationError):
            TopicResearchOutput(category=123)  # type: ignore[arg-type]

    def test_rejects_str_for_total_found(self) -> None:
        """Strict mode rejects str where int is expected."""
        with pytest.raises(ValidationError):
            TopicResearchOutput(
                category="tech",
                total_found="five",  # type: ignore[arg-type]
            )

    def test_topics_accepts_dicts(self) -> None:
        """topics list accepts dict[str, object] entries."""
        model = TopicResearchOutput(
            category="health",
            topics=[{"name": "Wellness", "count": 42, "active": True}],
        )
        assert model.topics[0]["name"] == "Wellness"
        assert model.topics[0]["count"] == 42
        assert model.topics[0]["active"] is True


# ===================================================================
# ContentQualityOutput
# ===================================================================


class TestContentQualityOutput:
    """ContentQualityOutput — content quality assessment."""

    def test_valid_construction(self) -> None:
        """All fields accepted with valid values."""
        model = ContentQualityOutput(
            quality_score=0.85,
            issues=["weak intro", "missing CTA"],
            suggestions=["add hook", "include call to action"],
            overall_assessment="Good draft, needs polishing",
        )
        assert model.quality_score == 0.85
        assert model.issues == ["weak intro", "missing CTA"]
        assert model.suggestions == ["add hook", "include call to action"]
        assert model.overall_assessment == "Good draft, needs polishing"

    def test_defaults(self) -> None:
        """Optional fields default correctly."""
        model = ContentQualityOutput(quality_score=0.5)
        assert model.issues == []
        assert model.suggestions == []
        assert model.overall_assessment == ""

    def test_minimal_construction(self) -> None:
        """Only required field (quality_score)."""
        model = ContentQualityOutput(quality_score=0.0)
        assert model.quality_score == 0.0

    def test_rejects_quality_score_below_zero(self) -> None:
        """ge=0.0 rejects negative scores."""
        with pytest.raises(ValidationError):
            ContentQualityOutput(quality_score=-0.1)

    def test_rejects_quality_score_above_one(self) -> None:
        """le=1.0 rejects scores > 1.0."""
        with pytest.raises(ValidationError):
            ContentQualityOutput(quality_score=1.5)

    def test_accepts_boundary_values(self) -> None:
        """Boundary values (0.0, 1.0) are accepted."""
        low = ContentQualityOutput(quality_score=0.0)
        assert low.quality_score == 0.0
        high = ContentQualityOutput(quality_score=1.0)
        assert high.quality_score == 1.0

    def test_rejects_int_for_issues(self) -> None:
        """Strict mode rejects non-list for issues field."""
        with pytest.raises(ValidationError):
            ContentQualityOutput(
                quality_score=0.5,
                issues="not a list",  # type: ignore[arg-type]
            )


# ===================================================================
# FactCheckOutput
# ===================================================================


class TestFactCheckOutput:
    """FactCheckOutput — fact-check verification output."""

    def test_valid_construction_passed(self) -> None:
        """A passing fact check with high confidence."""
        model = FactCheckOutput(
            passed=True,
            confidence=0.95,
            verified_claims=["AI market to reach $500B by 2028"],
            disputed_claims=[],
        )
        assert model.passed is True
        assert model.confidence == 0.95
        assert model.verified_claims == ["AI market to reach $500B by 2028"]
        assert model.disputed_claims == []

    def test_valid_construction_failed(self) -> None:
        """A failing fact check with issues."""
        model = FactCheckOutput(
            passed=False,
            issues=["unverified statistic"],
            confidence=0.3,
            verified_claims=[],
            disputed_claims=["market growth figure"],
        )
        assert model.passed is False
        assert model.issues == ["unverified statistic"]
        assert model.confidence == 0.3
        assert model.disputed_claims == ["market growth figure"]

    def test_defaults(self) -> None:
        """Optional fields default correctly — passed defaults to True."""
        model = FactCheckOutput()
        assert model.passed is True
        assert model.issues == []
        assert model.confidence == 1.0
        assert model.verified_claims == []
        assert model.disputed_claims == []

    def test_rejects_confidence_below_zero(self) -> None:
        """ge=0.0 rejects negative confidence."""
        with pytest.raises(ValidationError):
            FactCheckOutput(confidence=-0.5)

    def test_rejects_confidence_above_one(self) -> None:
        """le=1.0 rejects confidence > 1.0."""
        with pytest.raises(ValidationError):
            FactCheckOutput(confidence=2.0)

    def test_rejects_str_for_passed(self) -> None:
        """Strict mode rejects str where bool is expected."""
        with pytest.raises(ValidationError):
            FactCheckOutput(passed="yes")  # type: ignore[arg-type]


# ===================================================================
# CopyReviewOutput
# ===================================================================


class TestCopyReviewOutput:
    """CopyReviewOutput — copy review quality gate output."""

    def test_valid_construction_passed(self) -> None:
        """A passing copy review."""
        model = CopyReviewOutput(
            passed=True,
            tone_score=0.9,
            brand_compliance=True,
            suggestions=["add more social proof"],
        )
        assert model.passed is True
        assert model.tone_score == 0.9
        assert model.brand_compliance is True
        assert model.suggestions == ["add more social proof"]

    def test_valid_construction_failed(self) -> None:
        """A failing copy review with issues."""
        model = CopyReviewOutput(
            passed=False,
            issues=["tone mismatch", "brand violation"],
            tone_score=0.4,
            brand_compliance=False,
            suggestions=["rewrite intro"],
        )
        assert model.passed is False
        assert model.issues == ["tone mismatch", "brand violation"]
        assert model.tone_score == 0.4
        assert model.brand_compliance is False

    def test_defaults(self) -> None:
        """Optional fields default correctly."""
        model = CopyReviewOutput()
        assert model.passed is True
        assert model.issues == []
        assert model.tone_score == 1.0
        assert model.brand_compliance is True
        assert model.suggestions == []

    def test_rejects_tone_score_below_zero(self) -> None:
        """ge=0.0 rejects negative tone_score."""
        with pytest.raises(ValidationError):
            CopyReviewOutput(tone_score=-0.1)

    def test_rejects_tone_score_above_one(self) -> None:
        """le=1.0 rejects tone_score > 1.0."""
        with pytest.raises(ValidationError):
            CopyReviewOutput(tone_score=1.5)

    def test_rejects_float_for_brand_compliance(self) -> None:
        """Strict mode rejects float where bool is expected."""
        with pytest.raises(ValidationError):
            CopyReviewOutput(brand_compliance=1.0)  # type: ignore[arg-type]

    def test_all_models_are_in_package_all(self) -> None:
        """All 6 models are listed in __all__."""
        from automedia.decision.pydantic import __all__ as all_models

        expected = {
            "BrandStrategyOutput",
            "PipelineStrategyOutput",
            "TopicResearchOutput",
            "ContentQualityOutput",
            "FactCheckOutput",
            "CopyReviewOutput",
        }
        assert set(all_models) == expected
