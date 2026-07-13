"""Tests for automedia.pool.collector — HotCollector three-layer funnel."""

from __future__ import annotations

import pytest

from automedia.pool.collector import HotCollector

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def collector() -> HotCollector:
    """Default HotCollector with no seed topics."""
    return HotCollector()


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
    return HotCollector(seed_topics=seed)


# ===================================================================
# Tests — collect_all
# ===================================================================


class TestCollectAll:
    """collect_all() returns a merged, deduplicated list from all layers."""

    def test_returns_list(self, collector: HotCollector):
        result = collector.collect_all()
        assert isinstance(result, list)

    def test_returns_non_empty(self, collector: HotCollector):
        result = collector.collect_all()
        assert len(result) > 0

    def test_each_item_has_required_keys(self, collector: HotCollector):
        result = collector.collect_all()
        for item in result:
            assert "source" in item
            assert "title" in item
            assert "url" in item
            assert "heat_score" in item
            assert "collected_at" in item

    def test_heat_score_is_float(self, collector: HotCollector):
        result = collector.collect_all()
        for item in result:
            assert isinstance(item["heat_score"], (int, float))

    def test_no_duplicate_titles(self, collector: HotCollector):
        """Titles that appear in multiple layers should be deduplicated."""
        result = collector.collect_all()
        titles = [t["title"].strip().lower() for t in result]
        assert len(titles) == len(set(titles))

    def test_covers_tavily_and_aihot(self, collector_with_seed: HotCollector):
        """Result should contain items from tavily and aihot."""
        result = collector_with_seed.collect_all()
        sources = {t["source"] for t in result}
        assert "tavily" in sources
        assert "aihot" in sources

    def test_seed_topics_included(self, collector_with_seed: HotCollector):
        """Pre-seeded topics should appear in the output."""
        result = collector_with_seed.collect_all()
        titles = [t["title"] for t in result]
        assert "自媒体创作工具评测" in titles

    def test_collected_at_is_iso_format(self, collector: HotCollector):
        """All collected_at values should be valid ISO-8601."""
        result = collector.collect_all()
        for item in result:
            at = item["collected_at"]
            assert "T" in at  # basic ISO check
            assert "+" in at or "Z" in at.upper()  # has timezone


# ===================================================================
# Tests — individual collectors
# ===================================================================


class TestLayerCollectors:
    """Each platform collector returns correct results."""

    def test_tavily_returns_items(self):
        c = HotCollector()
        items = c._search_tavily(["ai", "视频"])
        assert len(items) > 0
        assert all(i["source"] == "tavily" for i in items)

    def test_tavily_empty_keywords(self):
        c = HotCollector()
        items = c._search_tavily([])
        assert items == []

    def test_aihot_returns_items(self):
        c = HotCollector()
        items = c._fetch_aihot()
        assert len(items) > 0
        assert all(i["source"] == "aihot" for i in items)

    def test_extract_keywords(self):
        c = HotCollector()
        topics = [
            {"title": "AI视频生成技术突破"},
            {"title": "大模型降价潮来袭"},
        ]
        kws = c._extract_keywords(topics)
        assert isinstance(kws, list)
        assert len(kws) > 0
