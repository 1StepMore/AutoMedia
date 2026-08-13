"""Tests for automedia.pool.dedup — TopicDeduplicator."""

from __future__ import annotations

import pytest

from automedia.pool.dedup import TopicDeduplicator, _normalize

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def dedup() -> TopicDeduplicator:
    """Default deduplicator with 0.75 threshold."""
    return TopicDeduplicator()


@pytest.fixture
def strict_dedup() -> TopicDeduplicator:
    """Stricter deduplicator with 0.50 threshold."""
    return TopicDeduplicator(threshold=0.50)


# ===================================================================
# Tests — is_duplicate
# ===================================================================


class TestIsDuplicate:
    """Title similarity check against pool."""

    def test_exact_match_is_duplicate(self, dedup: TopicDeduplicator):
        pool = ["AI视频生成技术突破", "大模型降价潮来袭"]
        assert dedup.is_duplicate("AI视频生成技术突破", pool) is True

    def test_similar_is_duplicate(self, dedup: TopicDeduplicator):
        """Very similar titles (>0.75) should be duplicates."""
        pool = ["AI视频生成技术突破与应用前景"]
        assert dedup.is_duplicate("AI视频生成技术突破", pool) is True

    def test_different_is_not_duplicate(self, dedup: TopicDeduplicator):
        pool = ["体育赛事精彩集锦"]
        assert dedup.is_duplicate("AI视频生成技术突破", pool) is False

    def test_empty_title_not_duplicate(self, dedup: TopicDeduplicator):
        pool = ["AI视频生成技术突破"]
        assert dedup.is_duplicate("", pool) is False

    def test_empty_pool_not_duplicate(self, dedup: TopicDeduplicator):
        assert dedup.is_duplicate("AI视频生成技术突破", []) is False

    def test_case_insensitive(self, dedup: TopicDeduplicator):
        pool = ["AI Video Generation"]
        assert dedup.is_duplicate("ai video generation", pool) is True

    def test_whitespace_insensitive(self, dedup: TopicDeduplicator):
        pool = ["  AI  视频  生成  "]
        assert dedup.is_duplicate("AI视频生成", pool) is True

    def test_strict_threshold_more_sensitive(self, strict_dedup: TopicDeduplicator):
        """With 0.50 threshold, even moderately similar titles are duplicates."""
        pool = ["人工智能改变教育方式和前景"]
        # These share enough characters → similarity > 0.50
        assert strict_dedup.is_duplicate("人工智能改变教育", pool) is True


# ===================================================================
# Tests — mark_cluster_duplicates
# ===================================================================


class TestMarkClusterDuplicates:
    """Pool-level cluster deduplication."""

    def test_no_duplicates(self, dedup: TopicDeduplicator):
        topics = [
            {"title": "AI视频生成"},
            {"title": "体育赛事集锦"},
            {"title": "美食探店推荐"},
        ]
        dups = dedup.mark_cluster_duplicates(topics)
        assert dups == []

    def test_identical_titles_detected(self, dedup: TopicDeduplicator):
        topics = [
            {"title": "AI视频生成技术突破"},
            {"title": "AI视频生成技术突破"},
        ]
        dups = dedup.mark_cluster_duplicates(topics)
        assert len(dups) == 1
        assert dups[0] == "AI视频生成技术突破"

    def test_similar_titles_detected(self, dedup: TopicDeduplicator):
        topics = [
            {"title": "AI视频生成技术突破与应用前景"},
            {"title": "AI视频生成技术突破"},
        ]
        dups = dedup.mark_cluster_duplicates(topics)
        assert len(dups) == 1

    def test_first_occurrence_kept(self, dedup: TopicDeduplicator):
        """The first topic is always kept; later duplicates are returned."""
        topics = [
            {"title": "AIGC内容创作指南"},
            {"title": "体育赛事集锦"},
            {"title": "AIGC内容创作指南详解"},  # similar to first
        ]
        dups = dedup.mark_cluster_duplicates(topics)
        assert "AIGC内容创作指南" not in dups  # first one kept
        assert "AIGC内容创作指南详解" in dups

    def test_empty_list(self, dedup: TopicDeduplicator):
        assert dedup.mark_cluster_duplicates([]) == []

    def test_single_topic(self, dedup: TopicDeduplicator):
        topics = [{"title": "唯一话题"}]
        assert dedup.mark_cluster_duplicates(topics) == []

    def test_multiple_duplicates(self, dedup: TopicDeduplicator):
        topics = [
            {"title": "AI技术最新突破"},
            {"title": "体育新闻"},
            {"title": "AI技术最新突破详解"},
            {"title": "AI技术最新突破深度分析"},
        ]
        dups = dedup.mark_cluster_duplicates(topics)
        assert len(dups) == 2
        assert "体育新闻" not in dups


# ===================================================================
# Tests — normalize helper
# ===================================================================


class TestNormalize:
    """Text normalization for comparison."""

    def test_strips_whitespace(self):
        assert _normalize("  hello  ") == "hello"

    def test_lowercases(self):
        assert _normalize("Hello World") == "hello world"

    def test_collapses_spaces(self):
        assert _normalize("hello   world") == "hello world"

    def test_chinese_text(self):
        assert _normalize("  AI视频  生成  ") == "ai视频 生成"
