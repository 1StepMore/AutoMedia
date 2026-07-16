"""AutoMedia pool — topic pool database access, collection, scoring, dedup."""

from structlog import get_logger

from automedia.pool.collector import HotCollector

log = get_logger(__name__)
from automedia.pool.db import PoolDB
from automedia.pool.dedup import TopicDeduplicator
from automedia.pool.scorer import TopicScorer

__all__ = [
    "HotCollector",
    "PoolDB",
    "TopicDeduplicator",
    "TopicScorer",
]
