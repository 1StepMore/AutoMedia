"""Tests for MCP tool ``search_assets`` handler.

Tests the ``search_assets`` MCP tool handler in ``automedia.mcp.tools``.
Uses ``@patch`` on ``automedia.asset_library.search_assets`` to avoid
database dependencies.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from automedia.mcp.tools import search_assets

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

MOCK_RESULTS: list[dict[str, Any]] = [
    {
        "title": "AI Video Production Guide",
        "content": "A comprehensive guide to AI-powered video production.",
        "type": "article",
        "lang": "en",
        "phase": "research",
        "_score": 0.92,
        "_source": "semantic",
    },
    {
        "title": "Brand Voice Guidelines",
        "content": "Official brand voice and tone guidelines document.",
        "type": "brief",
        "lang": "en",
        "phase": "brand",
        "_score": 0.78,
        "_source": "keyword",
    },
    {
        "title": "市场趋势分析 2024",
        "content": "2024年短视频市场趋势与机会分析。",
        "type": "report",
        "lang": "zh",
        "phase": "research",
        "_score": 0.65,
        "_source": "semantic",
    },
]


# ===================================================================
# Tests: search_assets
# ===================================================================


class TestSearchAssets:
    """Tests for the ``search_assets`` MCP tool."""

    @patch("automedia.asset_library.search_assets")
    def test_search_returns_structured_response(self, mock_search: MagicMock) -> None:
        """search_assets returns dict with results and count keys."""
        mock_search.return_value = MOCK_RESULTS

        result = search_assets(query="AI video", brand="my-brand", limit=5)

        assert "results" in result
        assert "count" in result
        assert result["count"] == 3
        assert len(result["results"]) == 3
        assert result["error"] is None

        # Verify result shape matches underlying function output
        first = result["results"][0]
        assert first["title"] == "AI Video Production Guide"
        assert first["_score"] == 0.92
        assert first["type"] == "article"
        assert first["lang"] == "en"

    @patch("automedia.asset_library.search_assets")
    def test_search_respects_limit(self, mock_search: MagicMock) -> None:
        """search_assets limits results to the requested count."""
        many_results = [dict(r, title=f"Result {i}") for i in range(25) for r in MOCK_RESULTS[:1]]
        # Actually build 25 distinct items
        many_results = [
            {**MOCK_RESULTS[0], "title": f"Result {i}", "_score": 1.0 - i * 0.01}
            for i in range(25)
        ]
        mock_search.return_value = many_results

        result = search_assets(query="test", brand="my-brand", limit=10)

        assert result["count"] == 10
        assert len(result["results"]) == 10
        assert result["error"] is None

    @patch("automedia.asset_library.search_assets")
    def test_search_empty_query(self, mock_search: MagicMock) -> None:
        """search_assets handles empty query gracefully (returns all assets)."""
        mock_search.return_value = MOCK_RESULTS

        result = search_assets(query="", brand="my-brand")

        assert "results" in result
        assert "count" in result
        assert result["count"] == 3
        assert result["error"] is None

    @patch("automedia.asset_library.search_assets")
    def test_search_with_filters(self, mock_search: MagicMock) -> None:
        """search_assets forwards filters to the underlying function."""
        mock_search.return_value = [MOCK_RESULTS[0]]

        result = search_assets(
            query="AI",
            brand="my-brand",
            limit=5,
            type="article",
            tags=["video", "AI"],
            lang="en",
            stage="research",
        )

        # Verify filters were passed through
        _call_filters = mock_search.call_args[1].get("filters")
        assert _call_filters is not None
        assert _call_filters["type"] == "article"
        assert _call_filters["tags"] == ["video", "AI"]
        assert _call_filters["lang"] == "en"
        assert _call_filters["phase"] == "research"

        assert result["count"] == 1
        assert result["error"] is None

    @patch("automedia.asset_library.search_assets")
    def test_search_error_handling(self, mock_search: MagicMock) -> None:
        """search_assets returns structured error on failure."""
        mock_search.side_effect = RuntimeError("Database connection failed")

        result = search_assets(query="AI", brand="my-brand")

        assert result["results"] == []
        assert result["count"] == 0
        assert "error" in result
        assert "Database connection failed" in result["error"]
