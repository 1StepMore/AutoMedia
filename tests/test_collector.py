"""Tests for automedia.pool.collector — HotCollector three-layer funnel."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from automedia.pool.collector import HotCollector

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def collector() -> HotCollector:
    """Default HotCollector with no seed topics and no API key."""
    return HotCollector(tavily_api_key="")


@pytest.fixture
def collector_with_key() -> HotCollector:
    """HotCollector with a fake Tavily API key for tests."""
    return HotCollector(tavily_api_key="tvly-test-key")


@pytest.fixture
def collector_with_seed() -> HotCollector:
    """HotCollector with pre-seeded topics."""
    seed = [
        {
            "source": "seed",
            "title": "自媒体创作工具评测",
            "url": "https://seed.com/tools",
            "heat_score": 9.0,
            "collected_at": "2025-01-01T00:00:00+00:00",
        },
    ]
    return HotCollector(seed_topics=seed, tavily_api_key="")


# ===================================================================
# Tests — collect_all
# ===================================================================


class TestCollectAll:
    """collect_all() returns a merged, deduplicated list from all layers."""

    def test_returns_list(self, collector: HotCollector):
        result = collector.collect_all()
        assert isinstance(result, list)

    def test_returns_empty_when_no_keys(self, collector: HotCollector):
        """Without API keys, all collectors return [] so the result is []."""
        result = collector.collect_all()
        assert result == []

    def test_returns_non_empty_with_seed(self, collector_with_seed: HotCollector):
        """Seed topics should appear even without API keys."""
        result = collector_with_seed.collect_all()
        assert len(result) > 0

    def test_each_item_has_required_keys(self, collector_with_seed: HotCollector):
        result = collector_with_seed.collect_all()
        for item in result:
            assert "source" in item
            assert "title" in item
            assert "url" in item
            assert "heat_score" in item
            assert "collected_at" in item

    def test_heat_score_is_float(self, collector_with_seed: HotCollector):
        result = collector_with_seed.collect_all()
        for item in result:
            assert isinstance(item["heat_score"], (int, float))

    def test_no_duplicate_titles(self, collector_with_seed: HotCollector):
        """Titles that appear in multiple layers should be deduplicated."""
        result = collector_with_seed.collect_all()
        titles = [t["title"].strip().lower() for t in result]
        assert len(titles) == len(set(titles))

    @patch("httpx.Client")
    @patch("automedia.core.llm_client.llm_complete")
    def test_covers_tavily_and_aihot(
        self,
        mock_llm: MagicMock,
        mock_client_cls: MagicMock,
    ):
        """With mocked APIs, results contain items from tavily and aihot."""
        # Mock Tavily API response (context manager pattern)
        mock_client_instance = MagicMock()
        mock_client_cls.return_value = mock_client_instance
        mock_client_instance.__enter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = MagicMock(
            **{
                "raise_for_status.return_value": None,
                "json.return_value": {
                    "results": [
                        {
                            "title": "AI Breakthrough",
                            "url": "https://example.com/ai",
                            "score": 0.92,
                        },
                    ],
                },
            }
        )

        # Mock LLM response
        mock_llm.return_value = json.dumps([
            {
                "title": "Trending Topic",
                "url": "https://example.com/trend",
                "heat_score": 8.0,
            },
        ])

        # Create a collector with CJK keyword seed so _extract_keywords works
        seed = [
            {
                "source": "seed",
                "title": "人工智能大模型",
                "url": "https://seed.com",
                "heat_score": 9.0,
                "collected_at": "2025-01-01T00:00:00+00:00",
            },
        ]
        c = HotCollector(seed_topics=seed, tavily_api_key="tvly-test-key")
        result = c.collect_all()
        sources = {t["source"] for t in result}
        assert "tavily" in sources
        assert "aihot" in sources

    def test_seed_topics_included(self, collector_with_seed: HotCollector):
        """Pre-seeded topics should appear in the output."""
        result = collector_with_seed.collect_all()
        titles = [t["title"] for t in result]
        assert "自媒体创作工具评测" in titles

    def test_collected_at_is_iso_format(self, collector_with_seed: HotCollector):
        """All collected_at values should be valid ISO-8601."""
        result = collector_with_seed.collect_all()
        for item in result:
            at = item["collected_at"]
            assert "T" in at  # basic ISO check
            assert "+" in at or "Z" in at.upper()  # has timezone


# ===================================================================
# Tests — _search_tavily
# ===================================================================


class TestSearchTavily:
    """_search_tavily() calls the real Tavily API or returns empty."""

    def test_no_key_returns_empty(self):
        c = HotCollector(tavily_api_key="")
        items = c._search_tavily(["ai"])
        assert items == []

    def test_empty_keywords_returns_empty(self, collector_with_key: HotCollector):
        items = collector_with_key._search_tavily([])
        assert items == []

    def test_blank_keywords_returns_empty(self, collector_with_key: HotCollector):
        items = collector_with_key._search_tavily(["  "])
        assert items == []

    @patch("httpx.Client")
    def test_parses_tavily_response(self, mock_client_cls: MagicMock):
        """Verify correct parsing of Tavily API response."""
        mock_client_instance = MagicMock()
        mock_client_cls.return_value = mock_client_instance
        mock_client_instance.__enter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = MagicMock(
            **{
                "raise_for_status.return_value": None,
                "json.return_value": {
                    "results": [
                        {
                            "title": "AI News Today",
                            "url": "https://example.com/ai-news",
                            "score": 0.95,
                            "content": "Some content...",
                        },
                        {
                            "title": "ML Research Update",
                            "url": "https://example.com/ml-update",
                            "score": 0.82,
                            "content": "More content...",
                        },
                    ],
                },
            }
        )

        c = HotCollector(tavily_api_key="tvly-test")
        items = c._search_tavily(["AI", "machine learning"])

        assert len(items) == 2
        assert items[0]["source"] == "tavily"
        assert items[0]["title"] == "AI News Today"
        assert items[0]["url"] == "https://example.com/ai-news"
        assert items[0]["heat_score"] == 9.5
        assert items[1]["heat_score"] == 8.2

        # Verify the API was called correctly
        mock_client_instance.post.assert_called_once()
        call_kwargs = mock_client_instance.post.call_args[1]
        assert call_kwargs["json"]["api_key"] == "tvly-test"
        assert "AI" in call_kwargs["json"]["query"]
        assert call_kwargs["json"]["max_results"] == 5

    @patch("httpx.Client")
    def test_skips_items_without_title_or_url(self, mock_client_cls: MagicMock):
        """Items missing title or url should be filtered out."""
        mock_client_instance = MagicMock()
        mock_client_cls.return_value = mock_client_instance
        mock_client_instance.__enter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = MagicMock(
            **{
                "raise_for_status.return_value": None,
                "json.return_value": {
                    "results": [
                        {"title": "Valid Title", "url": "https://example.com", "score": 0.9},
                        {"title": "", "url": "https://example.com/no-title", "score": 0.8},
                        {"title": "No URL", "url": "", "score": 0.7},
                    ],
                },
            }
        )

        c = HotCollector(tavily_api_key="tvly-test")
        items = c._search_tavily(["test"])
        assert len(items) == 1
        assert items[0]["title"] == "Valid Title"

    @patch("httpx.Client")
    def test_api_failure_returns_empty(self, mock_client_cls: MagicMock):
        """Transient API failures should return empty list, not crash."""
        mock_client_instance = MagicMock()
        mock_client_cls.return_value = mock_client_instance
        mock_client_instance.__enter__.return_value = mock_client_instance
        mock_client_instance.post.side_effect = Exception("API timeout")

        c = HotCollector(tavily_api_key="tvly-test")
        items = c._search_tavily(["AI"])
        assert items == []


# ===================================================================
# Tests — _fetch_aihot
# ===================================================================


class TestFetchAIHOT:
    """_fetch_aihot() uses LLM-based trending generation."""

    def test_no_key_returns_empty(self):
        """Even without LLM key, should return empty gracefully."""
        c = HotCollector()
        items = c._fetch_aihot()
        # Without LLM configured, llm_complete will raise, so returns []
        assert items == []

    def test_parses_llm_trending_response(self):
        """Verify correct parsing of LLM-generated trending topics."""
        mock_data = json.dumps([
            {
                "title": "AI Agent框架全面爆发",
                "url": "https://example.com/ai-agent",
                "heat_score": 9.2,
            },
            {
                "title": "开源大模型最新进展",
                "url": "https://example.com/oss-llm",
                "heat_score": 8.5,
            },
        ])

        with patch(
            "automedia.core.llm_client.llm_complete",
            return_value=mock_data,
        ):
            c = HotCollector()
            items = c._fetch_aihot()

        assert len(items) == 2
        assert items[0]["source"] == "aihot"
        assert items[0]["title"] == "AI Agent框架全面爆发"
        assert items[0]["heat_score"] == 9.2
        assert items[0]["url"] == "https://example.com/ai-agent"

    def test_handles_markdown_code_fence(self):
        """LLM responses wrapped in ```json fences should still parse."""
        with patch(
            "automedia.core.llm_client.llm_complete",
            return_value="```json\n[{\"title\": \"AI Trend\", \"url\": \"https://example.com\", \"heat_score\": 7.5}]\n```",
        ):
            c = HotCollector()
            items = c._fetch_aihot()

        assert len(items) == 1
        assert items[0]["title"] == "AI Trend"

    def test_llm_failure_returns_empty(self):
        """LLM errors should return empty list gracefully."""
        with patch(
            "automedia.core.llm_client.llm_complete",
            side_effect=Exception("LLM unavailable"),
        ):
            c = HotCollector()
            items = c._fetch_aihot()

        assert items == []

    def test_invalid_json_returns_empty(self):
        """Non-JSON LLM responses should return empty list."""
        with patch(
            "automedia.core.llm_client.llm_complete",
            return_value="This is not JSON at all",
        ):
            c = HotCollector()
            items = c._fetch_aihot()

        assert items == []


# ===================================================================
# Tests — _extract_keywords
# ===================================================================


class TestExtractKeywords:
    """Keyword extraction from topic titles."""

    def test_extract_keywords(self):
        c = HotCollector()
        topics = [
            {"title": "AI视频生成技术突破"},
            {"title": "大模型降价潮来袭"},
        ]
        kws = c._extract_keywords(topics)
        assert isinstance(kws, list)
        assert len(kws) > 0
