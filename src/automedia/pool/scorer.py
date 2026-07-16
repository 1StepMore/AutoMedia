"""TopicScorer — v3 scoring formulas for topic pool.

Scoring formulas:
  - Growth (引流款): heat/10*0.30 + correlation*0.40 + freshness*0.30
  - Business (业务款): heat/10*0.10 + correlation*0.60 + freshness*0.30

Correlation uses a 4-tier keyword matching system, with optional LLM
semantic augmentation controlled by the ``enable_llm_scoring`` config flag.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from structlog import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic model for LLM structured output
# ---------------------------------------------------------------------------


class SemanticScoreResult(BaseModel):
    """Structured output from LLM semantic relevance evaluation."""

    relevance_score: float = Field(
        ...,
        description="Semantic relevance score between 0.0 and 1.0",
        ge=0.0,
        le=1.0,
    )
    reasoning: str = Field(
        "",
        description="Brief one-sentence reasoning for the relevance score",
    )

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
    """Score topics using v3 growth/business formulas with keyword correlation.

    When ``enable_llm_scoring`` is ``True`` (default) and ``brand_keywords``
    are provided, the correlation term is augmented with an LLM semantic
    relevance score via ``max(llm_score, keyword_correlation)``.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize scorer with optional config.

        Parameters
        ----------
        config : dict or None
            AutoMedia config dict.  Reads ``enable_llm_scoring`` (default
            ``True``) to control LLM-based semantic scoring.
        """
        self._config = config
        enable = True
        if isinstance(config, dict):
            enable = config.get("enable_llm_scoring", True)
        self._enable_llm_scoring = bool(enable)

    # ------------------------------------------------------------------
    # Public scoring API
    # ------------------------------------------------------------------

    def score_growth(
        self,
        topic: dict,
        brand_keywords: list[str] | None = None,
    ) -> float:
        """Compute growth (引流款) score.

        Formula: heat/10 * 0.30 + correlation * 0.40 + freshness * 0.30

        When *brand_keywords* is provided and LLM scoring is enabled, the
        correlation term becomes ``max(llm_score, keyword_correlation)``.

        Parameters
        ----------
        topic : dict
            Must contain ``heat_score`` (0-10), ``title``, ``collected_at``.
            ``tier_keywords`` is an optional dict override for correlation.
        brand_keywords : list of str or None
            Brand/project keywords used for LLM semantic scoring.

        Returns
        -------
        float
            Score in [0, 1] range.
        """
        heat = topic.get("heat_score", 0.0)
        tier_keywords = topic.get("tier_keywords", _default_tier_keywords())
        kw_corr = self.correlation_score(topic.get("title", ""), tier_keywords)
        title = topic.get("title", "")
        effective_corr = self._augment_correlation(
            title, kw_corr, brand_keywords,
        )
        fresh = self._freshness_score(topic.get("collected_at", ""))
        return (heat / 10.0) * 0.30 + effective_corr * 0.40 + fresh * 0.30

    def score_business(
        self,
        topic: dict,
        brand_keywords: list[str] | None = None,
    ) -> float:
        """Compute business (业务款) score.

        Formula: heat/10 * 0.10 + correlation * 0.60 + freshness * 0.30

        When *brand_keywords* is provided and LLM scoring is enabled, the
        correlation term becomes ``max(llm_score, keyword_correlation)``.

        Parameters
        ----------
        topic : dict
            Same structure as :meth:`score_growth`.
        brand_keywords : list of str or None
            Brand/project keywords used for LLM semantic scoring.

        Returns
        -------
        float
            Score in [0, 1] range.
        """
        heat = topic.get("heat_score", 0.0)
        tier_keywords = topic.get("tier_keywords", _default_tier_keywords())
        kw_corr = self.correlation_score(topic.get("title", ""), tier_keywords)
        title = topic.get("title", "")
        effective_corr = self._augment_correlation(
            title, kw_corr, brand_keywords,
        )
        fresh = self._freshness_score(topic.get("collected_at", ""))
        return (heat / 10.0) * 0.10 + effective_corr * 0.60 + fresh * 0.30

    # ------------------------------------------------------------------
    # Convenience scoring
    # ------------------------------------------------------------------

    def score_topic(
        self,
        topic: str,
        brand_keywords: list[str],
    ) -> float:
        """Score a single topic string, returning the effective correlation.

        Returns the augmented correlation score (0.0–1.0) for a topic string
        against the default tier keywords and optional LLM semantic scoring.
        Useful for quick ad-hoc evaluation without building a full topic dict.

        Parameters
        ----------
        topic : str
            The topic title to evaluate.
        brand_keywords : list of str
            Brand/project keywords for LLM semantic augmentation.

        Returns
        -------
        float
            Effective correlation score in [0, 1].
        """
        kw_corr = self.correlation_score(topic, _default_tier_keywords())
        return self._augment_correlation(topic, kw_corr, brand_keywords)

    # ------------------------------------------------------------------
    # Correlation scoring
    # ------------------------------------------------------------------

    def _augment_correlation(
        self,
        title: str,
        kw_corr: float,
        brand_keywords: list[str] | None,
    ) -> float:
        """Optionally augment keyword correlation with LLM semantic score.

        When LLM scoring is enabled and *brand_keywords* is provided,
        returns ``max(llm_score, kw_corr)``.  Otherwise returns *kw_corr*
        unchanged.
        """
        if not brand_keywords or not self._enable_llm_scoring:
            return kw_corr
        llm_score = self._llm_correlation_score(title, brand_keywords)
        if llm_score is not None:
            return max(kw_corr, llm_score)
        return kw_corr

    def _llm_correlation_score(
        self,
        topic: str,
        brand_keywords: list[str],
    ) -> float | None:
        """Rate semantic relevance of *topic* against *brand_keywords* via LLM.

        Returns a float in [0.0, 1.0] on success, or *None* on any LLM
        failure (network error, timeout, parse error) — callers fall back
        to keyword-only correlation.
        """
        try:
            # Lazy import to avoid circular dependency at module level
            from automedia.core.llm_client import llm_complete_structured_safe

            kw_list = ", ".join(brand_keywords)
            prompt = (
                f"Rate the semantic relevance of the topic \"{topic}\" "
                f"to these brand keywords: {kw_list}. "
                "Return a relevance score between 0.0 (completely irrelevant) "
                "and 1.0 (highly relevant and on-brand)."
            )
            system_prompt = (
                "You are a precise topic-relevance evaluator for a brand "
                "content team. Output only valid JSON matching the requested "
                "schema."
            )
            result = llm_complete_structured_safe(
                prompt=prompt,
                response_format=SemanticScoreResult,
                system_prompt=system_prompt,
                task_type="text_generation",
            )
            score = float(result.relevance_score)
            return max(0.0, min(1.0, score))
        except Exception:
            log.warning(
                "LLM semantic scoring failed for topic=%r; "
                "falling back to keyword-only correlation",
                topic,
            )
            return None

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
