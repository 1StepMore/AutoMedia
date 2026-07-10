"""Search — combined keyword + semantic search over the Asset Library.

Provides the top-level ``AssetLibrary`` class used by the Decision Layer
and other subsystems to find relevant brand assets.

The search pipeline
-------------------
1. **SQLite keyword search** — ``LIKE`` on title (fast, deterministic).
2. **Chroma semantic search** — vector similarity on full-text content.
3. **Merge & deduplicate** — results are merged by ``doc_id`` with
   keyword hits preferred when both sources match.
4. **Filter & sort** — post-filter by ``type`` and tag overlap, then
   sort by relevance score.
"""

from __future__ import annotations

import logging
from typing import Any

from automedia.asset_library.db import AssetDatabase
from automedia.asset_library.ingest import IngestResult, ingest_artifacts
from automedia.asset_library.vector_store import VectorStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KEYWORD_WEIGHT = 1.0  # weight multiplier for keyword-match results
_SEMANTIC_WEIGHT = 0.8  # weight multiplier for semantic-only results

# ---------------------------------------------------------------------------
# Standalone search function
# ---------------------------------------------------------------------------


def search_assets(
    query: str,
    brand: str,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Search assets across SQLite and Chroma, returning combined results.

    This is a convenience function that creates a temporary
    ``AssetLibrary`` instance, performs the search, and closes it.

    Parameters
    ----------
    query : str
        Search query (used for both keyword and semantic search).
    brand : str
        Brand identifier.
    filters : dict or None
        Optional filters with keys:

        * ``type`` (str) — one of the built-in asset types
        * ``tags`` (list[str]) — overlap filter on custom tags
        * ``lang`` (str) — language code filter
        * ``phase`` (str) — source phase filter

    Returns
    -------
    list[dict]
        Each result dict contains all DB columns plus a ``_score`` key
        indicating relevance (higher is better).
    """
    lib = AssetLibrary(brand=brand)
    try:
        return lib.search(query=query, filters=filters)
    finally:
        lib.close()


# ---------------------------------------------------------------------------
# AssetLibrary — top-level orchestrator
# ---------------------------------------------------------------------------


class AssetLibrary:
    """Top-level orchestrator for a brand's Asset Library.

    Manages both the SQLite database and the Chroma vector store, and
    exposes the combined search API used by the Decision Layer.

    Parameters
    ----------
    brand : str
        Brand identifier.
    """

    def __init__(self, brand: str) -> None:
        self._brand = brand
        self._db = AssetDatabase(brand=brand)
        self._vector_store = VectorStore(brand=brand)

    # -- Properties -----------------------------------------------------------

    @property
    def brand(self) -> str:
        return self._brand

    @property
    def db(self) -> AssetDatabase:
        return self._db

    @property
    def vector_store(self) -> VectorStore:
        return self._vector_store

    # -- Public API -----------------------------------------------------------

    def ingest(self, project_dir: str, brand: str | None = None) -> IngestResult:
        """Ingest artifacts from a project directory.

        Parameters
        ----------
        project_dir : str
            Path to the project root directory.
        brand : str or None
            Brand identifier.  Defaults to the library's brand.

        Returns
        -------
        IngestResult
            Summary of the ingestion run.
        """
        target_brand = brand or self._brand
        return ingest_artifacts(project_dir, target_brand)

    def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Combined keyword + semantic search with optional filters.

        Parameters
        ----------
        query : str
            Search query string.
        filters : dict or None
            Optional filters (see ``search_assets`` for supported keys).

        Returns
        -------
        list[dict]
            Deduplicated, filtered, and sorted result list.  Empty when
            no matches are found.
        """
        filters = filters or {}

        # 1. Gather results from both sources.
        keyword_results = self._keyword_search(query)
        semantic_results = self._semantic_search(query)

        # 2. Merge by doc_id with deduplication.
        merged = self._merge_results(keyword_results, semantic_results)

        # 3. Apply post-filters.
        merged = self._apply_filters(merged, filters)

        # 4. Sort by relevance score descending.
        merged.sort(key=lambda r: r.get("_score", 0.0), reverse=True)

        return merged

    def close(self) -> None:
        """Close database and vector store connections."""
        self._db.close()

    # -- Internal search helpers ----------------------------------------------

    def _keyword_search(self, query: str) -> list[dict[str, Any]]:
        """Run keyword search against SQLite.

        Returns results with ``_score`` set to ``_KEYWORD_WEIGHT`` and
        ``_source`` set to ``"keyword"``.

        When *query* is empty, returns *all* assets so that callers
        can still apply filters (type, tag, lang, phase).
        """
        if not query.strip():
            # Return all assets for filter-only queries
            results = self._db.list_all()
            for r in results:
                r["_score"] = _KEYWORD_WEIGHT * 0.5  # lower weight for unfiltered
                r["_source"] = "keyword"
            return results
        results = self._db.keyword_search(query.strip())
        for r in results:
            r["_score"] = _KEYWORD_WEIGHT
            r["_source"] = "keyword"
        return results

    def _semantic_search(self, query: str) -> list[dict[str, Any]]:
        """Run semantic search against Chroma.

        Returns results with ``_score`` derived from cosine distance
        and ``_source`` set to ``"semantic"``.  Falls back to empty
        list when Chroma is unavailable.
        """
        if not query.strip():
            return []

        raw = self._vector_store.search(query.strip(), n_results=10)
        results: list[dict[str, Any]] = []
        for item in raw:
            # Convert distance to a similarity score (0..1, higher = better).
            distance = item.get("distance", 1.0)
            if distance is None:
                distance = 1.0
            score = _SEMANTIC_WEIGHT * (1.0 - min(distance, 1.0))

            # Enrich with DB data if available.
            doc_id = item.get("id", "")
            db_row = self._db.get_asset(doc_id) if doc_id else None

            result: dict[str, Any] = {
                "_score": score,
                "_source": "semantic",
                "doc_id": doc_id,
            }
            if db_row:
                result.update(db_row)
                # Boost score when both sources matched.
                result["_score"] = max(score, _KEYWORD_WEIGHT * 0.5)
            else:
                # Chroma-only result (no DB row).
                result["title"] = item.get("document", "")[:120]
                result["type"] = (item.get("metadata") or {}).get("type", "content")

            results.append(result)

        return results

    # -- Merge logic ----------------------------------------------------------

    @staticmethod
    def _merge_results(
        keyword_results: list[dict[str, Any]],
        semantic_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge keyword and semantic results by ``doc_id``.

        When the same ``doc_id`` appears in both lists the keyword
        version is kept (higher base weight).  Semantic-only results
        are appended.
        """
        seen: set[str] = set()
        merged: list[dict[str, Any]] = []

        # Keyword results first (higher confidence).
        for r in keyword_results:
            doc_id = r.get("doc_id", "")
            if doc_id:
                seen.add(doc_id)
            merged.append(r)

        # Append semantic results that don't duplicate keyword hits.
        for r in semantic_results:
            doc_id = r.get("doc_id", "")
            if doc_id and doc_id in seen:
                continue
            # If the semantic result has no doc_id, use a content hash.
            if not doc_id:
                title = r.get("title", "")
                if title in seen:
                    continue
                seen.add(title)
            merged.append(r)

        return merged

    # -- Filter logic ---------------------------------------------------------

    @staticmethod
    def _apply_filters(
        results: list[dict[str, Any]],
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Apply type, tag, lang, and phase filters to result list."""
        filtered = results

        type_filter = filters.get("type")
        if type_filter:
            filtered = [r for r in filtered if r.get("type", "").lower() == type_filter.lower()]

        tags_filter = filters.get("tags")
        if tags_filter and isinstance(tags_filter, list):
            tags_lower = {t.lower() for t in tags_filter}
            filtered = [r for r in filtered if _has_tag_overlap(r.get("tags", []), tags_lower)]

        lang_filter = filters.get("lang")
        if lang_filter:
            filtered = [r for r in filtered if r.get("lang", "").lower() == lang_filter.lower()]

        phase_filter = filters.get("phase")
        if phase_filter:
            filtered = [r for r in filtered if r.get("source_phase", "") == phase_filter]

        return filtered

    # -- Context manager ------------------------------------------------------

    def __enter__(self) -> AssetLibrary:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _has_tag_overlap(
    asset_tags: Any,  # noqa: ANN401 — JSON-deserialized, type varies
    filter_tags: set[str],
) -> bool:
    """Check whether any of *filter_tags* appear in the asset's tags."""
    if not asset_tags:
        return False
    if isinstance(asset_tags, str):
        import json

        try:
            asset_tags = json.loads(asset_tags)
        except (json.JSONDecodeError, TypeError):
            asset_tags = [asset_tags]
    if not isinstance(asset_tags, list):
        asset_tags = [str(asset_tags)]
    asset_lower = {t.lower() for t in asset_tags}
    return bool(asset_lower & filter_tags)
