"""TopicDeduplicator — title-based deduplication for the topic pool.

Uses ``difflib.SequenceMatcher`` for string similarity.
Threshold: similarity > 0.75 → duplicate.
"""

from __future__ import annotations

from difflib import SequenceMatcher


class TopicDeduplicator:
    """Deduplicate topics by title similarity.

    Parameters
    ----------
    threshold : float
        Similarity threshold above which two titles are considered duplicates.
        Default is 0.75.
    """

    def __init__(self, threshold: float = 0.75) -> None:
        self._threshold = threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_duplicate(self, title: str, pool_topics: list[str]) -> bool:
        """Check whether *title* is a duplicate of any title in *pool_topics*.

        Parameters
        ----------
        title : str
            The candidate title.
        pool_topics : list[str]
            Existing titles in the pool.

        Returns
        -------
        bool
            ``True`` if similarity to any pool title exceeds the threshold.
        """
        if not title or not pool_topics:
            return False
        title_norm = _normalize(title)
        for existing in pool_topics:
            existing_norm = _normalize(existing)
            ratio = SequenceMatcher(None, title_norm, existing_norm).ratio()
            if ratio > self._threshold:
                return True
        return False

    def mark_cluster_duplicates(self, topics: list[dict]) -> list[str]:
        """Identify cluster-level duplicates in a list of topics.

        Scans pairwise and collects titles that are duplicates of an
        earlier (kept) topic.  The first occurrence is always kept.

        Parameters
        ----------
        topics : list[dict]
            Each dict must have a ``title`` key.

        Returns
        -------
        list[str]
            Titles that should be **removed** (duplicates).
        """
        if not topics:
            return []

        kept: list[str] = []
        duplicates: list[str] = []

        for t in topics:
            title = t.get("title", "")
            if self.is_duplicate(title, kept):
                duplicates.append(title)
            else:
                kept.append(title)

        return duplicates

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def threshold(self) -> float:
        """Return the current similarity threshold."""
        return self._threshold


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Normalize text for comparison: strip, lowercase, collapse whitespace."""
    return " ".join(text.strip().lower().split())
