"""Tests for automedia.pool.scorer — TopicScorer v3 scoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from automedia.pool.scorer import TopicScorer, _default_tier_keywords

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def scorer() -> TopicScorer:
    return TopicScorer()


@pytest.fixture
def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@pytest.fixture
def hours_ago_iso() -> str:
    """Return ISO timestamp from 6 hours ago."""
    dt = datetime.now(UTC) - timedelta(hours=6)
    return dt.isoformat()


@pytest.fixture
def tier_keywords() -> dict:
    return _default_tier_keywords()


# ===================================================================
# Tests — correlation_score
# ===================================================================


class TestCorrelationScore:
    """Keyword tier matching returns correct scores."""

    def test_tier1_match_high_score(self, scorer: TopicScorer, tier_keywords: dict):
        """First Tier1 keyword match → 1.0."""
        score = scorer.correlation_score("AIGC内容创作指南", tier_keywords)
        assert score == 1.0

    def test_tier1_match_low_score(self, scorer: TopicScorer, tier_keywords: dict):
        """Second+ Tier1 keyword match → 0.9."""
        score = scorer.correlation_score("AI视频和AI绘画对比", tier_keywords)
        assert score == 0.9

    def test_tier2_match_high_score(self, scorer: TopicScorer, tier_keywords: dict):
        """First Tier2 keyword match → 0.8."""
        score = scorer.correlation_score("人工智能如何改变教育", tier_keywords)
        assert score == 0.8

    def test_tier2_match_low_score(self, scorer: TopicScorer, tier_keywords: dict):
        """Second+ Tier2 keyword → 0.7."""
        score = scorer.correlation_score("机器学习和大模型实战", tier_keywords)
        assert score == 0.7

    def test_tier3_match(self, scorer: TopicScorer, tier_keywords: dict):
        """Tier3 keyword match → 0.6 or 0.5."""
        score = scorer.correlation_score("芯片行业最新动态", tier_keywords)
        assert score in (0.6, 0.5)

    def test_tier4_match(self, scorer: TopicScorer, tier_keywords: dict):
        """Tier4 keyword match → 0.3 or 0.2."""
        score = scorer.correlation_score("体育赛事精彩集锦", tier_keywords)
        assert score in (0.3, 0.2)

    def test_no_match_returns_zero(self, scorer: TopicScorer, tier_keywords: dict):
        """No keyword match → 0.0."""
        score = scorer.correlation_score("今天天气真好", tier_keywords)
        assert score == 0.0

    def test_case_insensitive(self, scorer: TopicScorer, tier_keywords: dict):
        """Matching is case-insensitive."""
        score = scorer.correlation_score("AIGC is amazing", tier_keywords)
        assert score == 1.0

    def test_empty_title(self, scorer: TopicScorer, tier_keywords: dict):
        """Empty title → 0.0."""
        score = scorer.correlation_score("", tier_keywords)
        assert score == 0.0

    def test_custom_tier_keywords(self, scorer: TopicScorer):
        """Custom tier keywords override defaults."""
        custom = {"tier1": ["custom_keyword"], "tier2": [], "tier3": [], "tier4": []}
        score = scorer.correlation_score("custom_keyword is here", custom)
        assert score == 1.0


# ===================================================================
# Tests — score_growth
# ===================================================================


class TestScoreGrowth:
    """Growth scoring: heat/10*0.30 + correlation*0.40 + freshness*0.30."""

    def test_returns_float(self, scorer: TopicScorer, now_iso: str):
        topic = {"heat_score": 8.0, "title": "AIGC内容创作", "collected_at": now_iso}
        score = scorer.score_growth(topic)
        assert isinstance(score, float)

    def test_score_in_range(self, scorer: TopicScorer, now_iso: str):
        topic = {"heat_score": 10.0, "title": "AIGC内容创作指南", "collected_at": now_iso}
        score = scorer.score_growth(topic)
        assert 0.0 <= score <= 1.0

    def test_higher_heat_higher_score(self, scorer: TopicScorer, now_iso: str):
        low = scorer.score_growth({"heat_score": 1.0, "title": "无关内容", "collected_at": now_iso})
        high = scorer.score_growth(
            {"heat_score": 9.0, "title": "无关内容", "collected_at": now_iso}
        )
        assert high > low

    def test_higher_correlation_higher_score(self, scorer: TopicScorer, now_iso: str):
        low_corr = scorer.score_growth(
            {"heat_score": 5.0, "title": "无关内容", "collected_at": now_iso}
        )
        high_corr = scorer.score_growth(
            {"heat_score": 5.0, "title": "AIGC内容创作指南", "collected_at": now_iso}
        )
        assert high_corr > low_corr

    def test_missing_fields_default(self, scorer: TopicScorer):
        """Missing keys should default gracefully."""
        score = scorer.score_growth({})
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


# ===================================================================
# Tests — score_business
# ===================================================================


class TestScoreBusiness:
    """Business scoring: heat/10*0.10 + correlation*0.60 + freshness*0.30."""

    def test_returns_float(self, scorer: TopicScorer, now_iso: str):
        topic = {"heat_score": 8.0, "title": "AIGC内容创作", "collected_at": now_iso}
        score = scorer.score_business(topic)
        assert isinstance(score, float)

    def test_correlation_more_important_than_growth(self, scorer: TopicScorer, now_iso: str):
        """Business formula weights correlation higher than growth formula."""
        topic = {"heat_score": 5.0, "title": "AIGC内容创作指南", "collected_at": now_iso}
        biz = scorer.score_business(topic)
        growth = scorer.score_growth(topic)
        # For a high-correlation topic, business score should be >= growth
        assert biz >= growth

    def test_business_vs_growth_heat_weight(self, scorer: TopicScorer, now_iso: str):
        """Heat matters less in business formula (0.10 vs 0.30)."""
        high_heat = {"heat_score": 10.0, "title": "无关内容体育娱乐", "collected_at": now_iso}
        biz = scorer.score_business(high_heat)
        growth = scorer.score_growth(high_heat)
        # With no correlation, growth benefits more from heat
        assert growth > biz

    def test_score_in_range(self, scorer: TopicScorer, now_iso: str):
        topic = {"heat_score": 10.0, "title": "AIGC内容创作指南", "collected_at": now_iso}
        score = scorer.score_business(topic)
        assert 0.0 <= score <= 1.0


# ===================================================================
# Tests — freshness
# ===================================================================


class TestFreshness:
    """Freshness scoring decays over 24 hours."""

    def test_just_collected_is_1(self):
        now = datetime.now(UTC).isoformat()
        score = TopicScorer._freshness_score(now)
        assert score >= 0.99

    def test_twelve_hours_ago_is_half(self):
        dt = datetime.now(UTC) - timedelta(hours=12)
        score = TopicScorer._freshness_score(dt.isoformat())
        assert 0.4 <= score <= 0.6

    def test_twenty_four_hours_ago_is_zero(self):
        dt = datetime.now(UTC) - timedelta(hours=24)
        score = TopicScorer._freshness_score(dt.isoformat())
        assert score == pytest.approx(0.0, abs=0.05)

    def test_empty_string_returns_half(self):
        score = TopicScorer._freshness_score("")
        assert score == 0.5

    def test_invalid_string_returns_half(self):
        score = TopicScorer._freshness_score("not-a-date")
        assert score == 0.5
