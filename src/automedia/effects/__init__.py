"""Effects — content analytics package.

Provides statistical analysis functions for project content,
including word count, sentiment, readability, brand mentions,
and SEO score aggregation.

Top-level exports
-----------------
* ``word_count`` — word/character/sentence counting
* ``sentiment_score`` — simple keyword-based sentiment analysis
* ``readability_index`` — Flesch Reading Ease approximation
* ``brand_mention_frequency`` — count brand name mentions in text
* ``seo_score_aggregation`` — aggregate SEO scores from gate context
* ``analyze_content`` — compute all stats for a project directory
"""

from __future__ import annotations

from automedia.effects.stats import (
    brand_mention_frequency,
    readability_index,
    sentiment_score,
    seo_score_aggregation,
    word_count,
)

__all__ = [
    "analyze_content",
    "brand_mention_frequency",
    "readability_index",
    "sentiment_score",
    "seo_score_aggregation",
    "word_count",
]


def __getattr__(name: str):
    """Lazy-import the ``analyze_content`` MCP tool function."""
    _lazy: dict[str, tuple[str, str]] = {
        "analyze_content": ("automedia.effects.mcp", "analyze_content"),
    }
    if name in _lazy:
        import importlib  # noqa: PLC0415

        mod_path, attr = _lazy[name]
        mod = importlib.import_module(mod_path)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
