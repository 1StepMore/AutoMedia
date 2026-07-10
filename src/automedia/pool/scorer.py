"""TopicScorer — v3 scoring formulas for topic pool.

Pure deterministic logic — no LLM calls.

Scoring formulas:
  - Growth (引流款): heat/10*0.30 + correlation*0.40 + freshness*0.30
  - Business (业务款): heat/10*0.10 + correlation*0.60 + freshness*0.30

Correlation uses a 4-tier keyword matching system.
"""

from __future__ import annotations

from datetime import UTC, datetime

# 4-tier keyword classification
# Each tier maps keywords to (tier_score_high, tier_score_low)
_TIER1_KEYWORDS: list[str] = [
    "aigc",
    "ai视频",
    "ai video",
    "自媒体工具",
    "ai绘画",
    "ai写作",
    "ai剪辑",
    "ai配音",
    "ai生成",
    "content creator",
    "ai content",
]
_TIER2_KEYWORDS: list[str] = [
    "人工智能",
    "大模型",
    "机器学习",
    "深度学习",
    "chatgpt",
    "gpt",
    "llm",
    "transformer",
    "ai agent",
    "ai助手",
]
_TIER3_KEYWORDS: list[str] = [
    "科技",
    "互联网",
    "芯片",
    "半导体",
    "云计算",
    "大数据",
    "5g",
    "区块链",
    "元宇宙",
    "vr",
    "ar",
]
_TIER4_KEYWORDS: list[str] = [
    "体育",
    "娱乐",
    "明星",
    "综艺",
    "电影",
    "音乐",
    "游戏",
    "美食",
    "旅游",
    "时尚",
]


class TopicScorer:
    """Score topics using v3 growth/business formulas with keyword correlation."""

    # ------------------------------------------------------------------
    # Public scoring API
    # ------------------------------------------------------------------

    def score_growth(self, topic: dict) -> float:
        """Compute growth (引流款) score.

        Formula: heat/10 * 0.30 + correlation * 0.40 + freshness * 0.30

        Parameters
        ----------
        topic : dict
            Must contain ``heat_score`` (0-10), ``title``, ``collected_at``.
            ``tier_keywords`` is an optional dict override for correlation.

        Returns
        -------
        float
            Score in [0, 1] range.
        """
        heat = topic.get("heat_score", 0.0)
        tier_keywords = topic.get("tier_keywords", _default_tier_keywords())
        corr = self.correlation_score(topic.get("title", ""), tier_keywords)
        fresh = self._freshness_score(topic.get("collected_at", ""))
        return (heat / 10.0) * 0.30 + corr * 0.40 + fresh * 0.30

    def score_business(self, topic: dict) -> float:
        """Compute business (业务款) score.

        Formula: heat/10 * 0.10 + correlation * 0.60 + freshness * 0.30

        Parameters
        ----------
        topic : dict
            Same structure as :meth:`score_growth`.

        Returns
        -------
        float
            Score in [0, 1] range.
        """
        heat = topic.get("heat_score", 0.0)
        tier_keywords = topic.get("tier_keywords", _default_tier_keywords())
        corr = self.correlation_score(topic.get("title", ""), tier_keywords)
        fresh = self._freshness_score(topic.get("collected_at", ""))
        return (heat / 10.0) * 0.10 + corr * 0.60 + fresh * 0.30

    # ------------------------------------------------------------------
    # Correlation scoring
    # ------------------------------------------------------------------

    @staticmethod
    def correlation_score(topic_title: str, tier_keywords: dict) -> float:
        """Compute keyword correlation score using 4-tier matching.

        Parameters
        ----------
        topic_title : str
            The topic title to evaluate.
        tier_keywords : dict
            Mapping of tier name to keyword list.  Expected keys:
            ``tier1``, ``tier2``, ``tier3``, ``tier4``.
            Each value is a list of lowercase keyword strings.

        Returns
        -------
        float
            Score in [0, 1].  Matches in higher tiers yield higher scores.
            Tier1 → 1.0 or 0.9, Tier2 → 0.8 or 0.7, etc.
        """
        title_lower = topic_title.lower()

        # Tier scores: (keyword_list, high_score, low_score)
        tiers = [
            (tier_keywords.get("tier1", []), 1.0, 0.9),
            (tier_keywords.get("tier2", []), 0.8, 0.7),
            (tier_keywords.get("tier3", []), 0.6, 0.5),
            (tier_keywords.get("tier4", []), 0.3, 0.2),
        ]

        for kw_list, high, low in tiers:
            for i, kw in enumerate(kw_list):
                if kw.lower() in title_lower:
                    # First keyword in tier → high score, rest → low score
                    return high if i == 0 else low

        return 0.0

    # ------------------------------------------------------------------
    # Freshness scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _freshness_score(collected_at: str) -> float:
        """Score freshness based on how recent the topic is.

        Returns 1.0 for just-collected, decaying toward 0.0 over 24 hours.
        Returns 0.5 if the timestamp is missing or unparseable.
        """
        if not collected_at:
            return 0.5
        try:
            # Handle both timezone-aware and naive ISO strings
            ts = collected_at
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            now = datetime.now(UTC)
            delta_hours = (now - dt).total_seconds() / 3600.0
            if delta_hours < 0:
                return 1.0  # future timestamp → treat as fresh
            # Linear decay: 1.0 at 0h → 0.0 at 24h
            return max(0.0, 1.0 - delta_hours / 24.0)
        except (ValueError, TypeError):
            return 0.5


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _default_tier_keywords() -> dict:
    """Return the default 4-tier keyword mapping."""
    return {
        "tier1": _TIER1_KEYWORDS,
        "tier2": _TIER2_KEYWORDS,
        "tier3": _TIER3_KEYWORDS,
        "tier4": _TIER4_KEYWORDS,
    }
