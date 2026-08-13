"""Pydantic v2 models for MCP tool output validation.

All models use ``ConfigDict(strict=True)`` for strict type enforcement
and are designed to be used with ``llm_complete_structured_safe()``
as the ``response_format`` parameter.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class BrandStrategyOutput(BaseModel):
    """Brand positioning and strategy output."""

    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True)

    brand_positioning: str
    audience_analysis: str
    competitive_landscape: str
    key_differentiators: list[str] = Field(default_factory=list)
    suggested_messaging: list[str] = Field(default_factory=list)


class PipelineStrategyOutput(BaseModel):
    """Pipeline content strategy output."""

    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True)

    topic_brief: str
    content_structure: list[str]
    platform_distribution: dict[str, str] = Field(default_factory=dict)
    estimated_duration: str | None = None
    key_angles: list[str] = Field(default_factory=list)


class TopicResearchOutput(BaseModel):
    """Topic research results output."""

    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True)

    topics: list[dict[str, object]] = Field(default_factory=list)
    category: str
    total_found: int = 0


class ContentQualityOutput(BaseModel):
    """Content quality assessment output."""

    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True)

    quality_score: float = Field(ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    overall_assessment: str = ""


class FactCheckOutput(BaseModel):
    """Fact-check verification output."""

    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True)

    passed: bool = True
    issues: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    verified_claims: list[str] = Field(default_factory=list)
    disputed_claims: list[str] = Field(default_factory=list)


class CopyReviewOutput(BaseModel):
    """Copy review quality gate output."""

    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True)

    passed: bool = True
    issues: list[str] = Field(default_factory=list)
    tone_score: float = Field(default=1.0, ge=0.0, le=1.0)
    brand_compliance: bool = True
    suggestions: list[str] = Field(default_factory=list)


__all__ = [
    "BrandStrategyOutput",
    "PipelineStrategyOutput",
    "TopicResearchOutput",
    "ContentQualityOutput",
    "FactCheckOutput",
    "CopyReviewOutput",
]
