"""Tests for MCP brand tools — ``list_brands``.

Tests the ``list_brands`` MCP tool handler in ``automedia.mcp.tools``.
Uses ``@patch`` on ``load_brand_profiles`` to avoid file-system
dependencies on ``~/.automedia/brand_profiles.yaml``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from automedia.manifests.brand_profile_schema import BrandProfile
from automedia.mcp.tools import list_brands

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

MOCK_PROFILE_TECH: dict[str, Any] = {
    "brand_name": "wechat-tech",
    "aliases": ["wtech", "wechat-tech-channel"],
    "cta_principles": ["Subscribe for weekly tech insights"],
    "blocked_words": ["spam", "clickbait"],
    "tone_guidelines": "Professional yet approachable, use technical accuracy",
    "brand_identity": "Tech thought leader in AI and software development",
    "languages": {"zh": {"name": "微信科技"}, "en": {"name": "WeChat Tech"}},
}

MOCK_PROFILE_LIFESTYLE: dict[str, Any] = {
    "brand_name": "lifestyle-mag",
    "aliases": ["lifestyle", "life-mag"],
    "cta_principles": ["Follow for daily lifestyle tips"],
    "blocked_words": ["scam", "miracle"],
    "tone_guidelines": "Warm, inviting, and relatable",
    "brand_identity": "Modern lifestyle brand focusing on wellness and culture",
    "languages": {"zh": {"name": "生活杂志"}},
}


def _build_profile(data: dict[str, Any]) -> BrandProfile:
    """Build a BrandProfile from a dict (matches load_brand_profiles logic)."""
    return BrandProfile(
        brand_name=data.get("brand_name", ""),
        aliases=data.get("aliases", []),
        cta_principles=data.get("cta_principles", []),
        blocked_words=data.get("blocked_words", []),
        tone_guidelines=data.get("tone_guidelines", ""),
        brand_identity=data.get("brand_identity", ""),
        languages=data.get("languages", {}),
        platforms=data.get("platforms", []),
    )


# ===================================================================
# Tests: list_brands
# ===================================================================


class TestListBrands:
    """Tests for the ``list_brands`` MCP tool."""

    @patch("automedia.manifests.brand_profile_schema.load_brand_profiles")
    def test_list_brands_with_data(self, mock_load: MagicMock) -> None:
        """list_brands returns all configured brands with their metadata."""
        tech_profile = _build_profile(MOCK_PROFILE_TECH)
        lifestyle_profile = _build_profile(MOCK_PROFILE_LIFESTYLE)
        mock_load.return_value = {
            "wechat-tech": tech_profile,
            "lifestyle-mag": lifestyle_profile,
        }

        result = list_brands()

        assert result["total"] == 2
        assert len(result["brands"]) == 2

        # Verify first brand
        tech = next(b for b in result["brands"] if b["name"] == "wechat-tech")
        assert tech["name"] == "wechat-tech"
        assert tech["aliases"] == ["wtech", "wechat-tech-channel"]
        assert tech["cta_principles"] == ["Subscribe for weekly tech insights"]
        assert tech["blocked_words"] == ["spam", "clickbait"]
        assert tech["tone_guidelines"] == "Professional yet approachable, use technical accuracy"
        assert tech["brand_identity"] == "Tech thought leader in AI and software development"
        assert tech["languages"]["zh"]["name"] == "微信科技"

        # Verify second brand
        lifestyle = next(b for b in result["brands"] if b["name"] == "lifestyle-mag")
        assert lifestyle["name"] == "lifestyle-mag"
        assert lifestyle["aliases"] == ["lifestyle", "life-mag"]
        assert result["error"] is None

    @patch("automedia.manifests.brand_profile_schema.load_brand_profiles")
    def test_list_brands_empty(self, mock_load: MagicMock) -> None:
        """list_brands returns empty list when no brands configured."""
        mock_load.return_value = {}

        result = list_brands()

        assert result["total"] == 0
        assert result["brands"] == []
        # Empty state is not an error
        assert result["error"] is None

    @patch("automedia.manifests.brand_profile_schema.load_brand_profiles")
    def test_list_brands_error(self, mock_load: MagicMock) -> None:
        """list_brands returns empty list with error on failure."""
        mock_load.side_effect = RuntimeError("Failed to load brand profiles")

        result = list_brands()

        assert result["total"] == 0
        assert result["brands"] == []
        assert "error" in result
        assert "Failed to load brand profiles" in result["error"]
