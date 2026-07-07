"""AutoMedia pool — topic pool database access, collection, scoring, dedup."""

from automedia.pool.collector import HotCollector
from automedia.pool.db import PoolDB
from automedia.pool.dedup import TopicDeduplicator
from automedia.pool.scorer import TopicScorer

__all__ = [
    "HotCollector",
    "PoolDB",
    "TopicDeduplicator",
    "TopicScorer",
]
