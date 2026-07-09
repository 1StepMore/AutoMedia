"""E2E: Asset Library — ingest, keyword search, type filtering, and Chroma fallback.

Verifies that the Asset Library can store and retrieve brand assets using
both SQLite keyword search and structured type filters.  Chroma integration
is tested in graceful-degradation mode (empty results when Chroma is not
available, which is the expected state in test/CI environments).

All storage is redirected to pytest's ``tmp_path`` so no data is written
to the real ``~/.automedia/`` directory.

PRD-3 W1 Asset Library: T23 — E2E Asset Library Ingest + Search.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from automedia.asset_library import AssetLibrary, search_assets
from automedia.asset_library.db import AssetDatabase, AssetDoc
from automedia.decision.base import DecisionArtifact


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def patch_asset_db_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``AssetDatabase._base_dir`` to a ``tmp_path``-scoped directory.

    This prevents tests from writing to ``~/.automedia/asset-library/`` and
    keeps every test run fully isolated.
    """
    base_dir = tmp_path / "asset-library"
    monkeypatch.setattr(
        AssetDatabase,
        "_base_dir",
        staticmethod(lambda: base_dir),
    )
    return base_dir


@pytest.fixture()
def sample_assets() -> list[dict[str, Any]]:
    """Return a list of raw asset dicts for ingest.

    These mimic the shape of ``AssetDoc`` constructor kwargs so they can
    be converted to ``AssetDoc`` instances and added to the database.
    """
    return [
        {
            "doc_id": "strat_001",
            "type": "strategy",
            "title": "Q4 2025 Content Strategy",
            "tags": ["quarterly", "content", "seo"],
            "lang": "en",
            "source_phase": "2",
        },
        {
            "doc_id": "strat_002",
            "type": "strategy",
            "title": "Brand Voice Guidelines v3",
            "tags": ["brand", "voice", "guidelines"],
            "lang": "en",
            "source_phase": "1b",
        },
        {
            "doc_id": "persona_001",
            "type": "persona",
            "title": "Primary Persona — Tech-Savvy Marketer",
            "tags": ["persona", "marketing", "b2b"],
            "lang": "en",
            "source_phase": "1b",
        },
        {
            "doc_id": "persona_002",
            "type": "persona",
            "title": "Secondary Persona — Content Creator",
            "tags": ["persona", "creator", "social-media"],
            "lang": "en",
            "source_phase": "1b",
        },
        {
            "doc_id": "content_001",
            "type": "content",
            "title": "AI Trends Blog Post — EN",
            "tags": ["blog", "ai", "trends"],
            "lang": "en",
            "source_phase": "2",
        },
        {
            "doc_id": "content_002",
            "type": "content",
            "title": "AI Trends Blog Post — ZH",
            "tags": ["blog", "ai", "trends"],
            "lang": "zh",
            "source_phase": "2",
        },
        {
            "doc_id": "product_001",
            "type": "product",
            "title": "Product Roadmap 2025",
            "tags": ["product", "roadmap", "engineering"],
            "lang": "en",
            "source_phase": "1b",
        },
        {
            "doc_id": "kol_001",
            "type": "kol_brief",
            "title": "KOL Brief — Summer Campaign",
            "tags": ["kol", "campaign", "summer"],
            "lang": "zh",
            "source_phase": "2",
        },
    ]


# ---------------------------------------------------------------------------
# Tests — Ingest
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestAssetLibraryIngest:
    """Ingesting assets into the Asset Library — basic CRUD verification."""

    def test_asset_database_creates_and_stores(
        self,
        patch_asset_db_paths: Path,
    ) -> None:
        """AssetDatabase can create, store, and retrieve an asset."""
        db = AssetDatabase(brand="TestBrand")

        doc = AssetDoc(
            doc_id="test_001",
            type="strategy",
            title="Test Strategy Doc",
            tags=["test", "strategy"],
        )
        returned_id = db.add_asset(doc)
        assert returned_id == "test_001"

        fetched = db.get_asset("test_001")
        assert fetched is not None
        assert fetched["title"] == "Test Strategy Doc"
        assert fetched["type"] == "strategy"
        assert set(fetched["tags"]) == {"test", "strategy"}
        assert fetched["brand_id"] == "TestBrand"

        db.close()

    def test_ingest_multiple_assets(
        self,
        patch_asset_db_paths: Path,
        sample_assets: list[dict[str, Any]],
    ) -> None:
        """Multiple assets can be ingested and counted."""
        db = AssetDatabase(brand="TestBrand")
        for asset in sample_assets:
            doc = AssetDoc(**asset)
            db.add_asset(doc)

        assert db.count() == len(sample_assets), (
            f"Expected {len(sample_assets)} assets, got {db.count()}"
        )

        all_assets = db.list_all()
        assert len(all_assets) == len(sample_assets)

        db.close()

    def test_ingest_duplicate_doc_id_is_idempotent(
        self,
        patch_asset_db_paths: Path,
    ) -> None:
        """Inserting an asset with the same doc_id triggers an update (idempotent)."""
        db = AssetDatabase(brand="TestBrand")

        doc1 = AssetDoc(
            doc_id="dup_001",
            type="strategy",
            title="Original Title",
            tags=["original"],
        )
        db.add_asset(doc1)

        doc2 = AssetDoc(
            doc_id="dup_001",
            type="strategy",
            title="Updated Title",
            tags=["updated"],
        )
        db.add_asset(doc2)

        assert db.count() == 1, "Duplicate doc_id should upsert, not duplicate"

        fetched = db.get_asset("dup_001")
        assert fetched is not None
        assert fetched["title"] == "Updated Title"
        assert "updated" in fetched["tags"]

        db.close()

    def test_asset_database_without_chroma_does_not_crash(
        self,
        patch_asset_db_paths: Path,
    ) -> None:
        """AssetLibrary can be instantiated even when Chroma is unavailable."""
        library = AssetLibrary(brand="NoChromaBrand")
        assert library.brand == "NoChromaBrand"
        assert library.db is not None
        assert library.vector_store is not None
        library.close()

    def test_ingest_decision_artifacts_as_assets(
        self,
        patch_asset_db_paths: Path,
    ) -> None:
        """DecisionArtifact-like data can be stored in the Asset Library.

        This simulates the real-world pattern where Decision Layer outputs
        are persisted to the Asset Library for later retrieval.
        """
        artifacts_data = [
            DecisionArtifact(
                artifact_type="brand_dna",
                content={"brand_name": "FitBrand", "vision": "To lead fitness"},
            ),
            DecisionArtifact(
                artifact_type="market_report",
                content={"market_size": "$5B", "trends": ["AI", "Mobile"]},
            ),
            DecisionArtifact(
                artifact_type="persona_map",
                content={"personas": [{"name": "Pioneer Pete"}]},
            ),
        ]

        db = AssetDatabase(brand="ArtifactBrand")
        for i, art in enumerate(artifacts_data):
            doc = AssetDoc(
                doc_id=f"artifact_{i}",
                brand_id="ArtifactBrand",
                type=art.artifact_type,
                title=f"Decision Artifact — {art.artifact_type}",
                tags=[art.artifact_type, "decision-layer"],
                source_phase="1b",
            )
            db.add_asset(doc)

        assert db.count() == len(artifacts_data)
        db.close()


# ---------------------------------------------------------------------------
# Tests — Search
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestAssetLibrarySearch:
    """Searching the Asset Library — keyword, type filter, and combined search."""

    @pytest.fixture(autouse=True)
    def _ingest_sample_assets(
        self,
        patch_asset_db_paths: Path,
        sample_assets: list[dict[str, Any]],
    ) -> None:
        """Ingest sample assets before every search test."""
        db = AssetDatabase(brand="SearchBrand")
        for asset in sample_assets:
            doc = AssetDoc(**asset)
            db.add_asset(doc)
        db.close()

    # ------------------------------------------------------------------
    # Keyword search
    # ------------------------------------------------------------------

    def test_keyword_search_finds_by_title(self) -> None:
        """Keyword search finds assets whose title contains the query."""
        library = AssetLibrary(brand="SearchBrand")
        results = library.search(query="Content Strategy")
        library.close()

        assert len(results) >= 1
        titles = [r["title"] for r in results]
        assert "Q4 2025 Content Strategy" in titles

    def test_keyword_search_case_insensitive(self) -> None:
        """Keyword search is case-insensitive."""
        library = AssetLibrary(brand="SearchBrand")
        results_lower = library.search(query="content strategy")
        results_upper = library.search(query="CONTENT STRATEGY")
        library.close()

        assert len(results_lower) >= 1
        assert len(results_lower) == len(results_upper)

    def test_keyword_search_returns_empty_for_no_match(self) -> None:
        """Keyword search returns empty list for non-matching query."""
        library = AssetLibrary(brand="SearchBrand")
        results = library.search(query="zzz_nonexistent_xyz")
        library.close()

        assert isinstance(results, list)
        assert len(results) == 0

    def test_keyword_search_empty_query(self) -> None:
        """Empty query returns all assets (filter-only mode)."""
        library = AssetLibrary(brand="SearchBrand")
        results = library.search(query="")
        library.close()

        assert isinstance(results, list)
        # Empty query returns all assets so that filters can narrow them
        assert len(results) > 0, "Empty query should return all assets"

    # ------------------------------------------------------------------
    # Type filter
    # ------------------------------------------------------------------

    def test_type_filter_strategy(self) -> None:
        """Filtering by type='strategy' returns only strategy assets."""
        library = AssetLibrary(brand="SearchBrand")
        results = library.search(
            query="",
            filters={"type": "strategy"},
        )
        library.close()

        assert len(results) == 2, f"Expected 2 strategy assets, got {len(results)}"
        for r in results:
            assert r["type"] == "strategy", (
                f"Expected 'strategy', got '{r['type']}' for '{r['title']}'"
            )

    def test_type_filter_persona(self) -> None:
        """Filtering by type='persona' returns only persona assets."""
        library = AssetLibrary(brand="SearchBrand")
        results = library.search(
            query="",
            filters={"type": "persona"},
        )
        library.close()

        assert len(results) == 2, f"Expected 2 persona assets, got {len(results)}"
        for r in results:
            assert r["type"] == "persona"

    def test_type_filter_content(self) -> None:
        """Filtering by type='content' returns only content assets."""
        library = AssetLibrary(brand="SearchBrand")
        results = library.search(
            query="",
            filters={"type": "content"},
        )
        library.close()

        assert len(results) == 2, f"Expected 2 content assets, got {len(results)}"
        for r in results:
            assert r["type"] == "content"

    def test_type_filter_kol_brief(self) -> None:
        """Filtering by type='kol_brief' returns the KOL brief asset."""
        library = AssetLibrary(brand="SearchBrand")
        results = library.search(
            query="",
            filters={"type": "kol_brief"},
        )
        library.close()

        assert len(results) == 1
        assert results[0]["type"] == "kol_brief"
        assert results[0]["title"] == "KOL Brief — Summer Campaign"

    def test_type_filter_no_match(self) -> None:
        """Filtering by a type with no matches returns empty list."""
        library = AssetLibrary(brand="SearchBrand")
        results = library.search(
            query="",
            filters={"type": "asset"},
        )
        library.close()

        assert isinstance(results, list)
        assert len(results) == 0

    # ------------------------------------------------------------------
    # Combined keyword + type filter
    # ------------------------------------------------------------------

    def test_keyword_and_type_filter_combined(self) -> None:
        """Keyword + type filter narrows results correctly."""
        library = AssetLibrary(brand="SearchBrand")

        results = library.search(
            query="Persona",
            filters={"type": "persona"},
        )
        library.close()

        assert len(results) >= 1
        for r in results:
            assert r["type"] == "persona"
            assert "persona" in r["title"].lower()

    # ------------------------------------------------------------------
    # Tag filter
    # ------------------------------------------------------------------

    def test_tag_filter(self) -> None:
        """Filtering by tag returns assets with matching tag."""
        library = AssetLibrary(brand="SearchBrand")
        results = library.search(
            query="",
            filters={"tags": ["ai"]},
        )
        library.close()

        assert len(results) >= 2, (
            f"Expected at least 2 assets with 'ai' tag, got {len(results)}"
        )
        for r in results:
            tags_lower = {t.lower() for t in (r.get("tags") or [])}
            assert "ai" in tags_lower, (
                f"Asset '{r['title']}' missing 'ai' tag. Tags: {r.get('tags')}"
            )

    # ------------------------------------------------------------------
    # Lang filter
    # ------------------------------------------------------------------

    def test_lang_filter_zh(self) -> None:
        """Filtering by lang='zh' returns only Chinese-language assets."""
        library = AssetLibrary(brand="SearchBrand")
        results = library.search(
            query="",
            filters={"lang": "zh"},
        )
        library.close()

        assert len(results) == 2, (
            f"Expected 2 zh assets, got {len(results)}: "
            f"{[r['title'] for r in results]}"
        )
        for r in results:
            assert r.get("lang") == "zh"

    def test_lang_filter_en(self) -> None:
        """Filtering by lang='en' returns only English-language assets."""
        library = AssetLibrary(brand="SearchBrand")
        results = library.search(
            query="",
            filters={"lang": "en"},
        )
        library.close()

        assert len(results) == 6, (
            f"Expected 6 en assets, got {len(results)}: "
            f"{[r['title'] for r in results]}"
        )

    # ------------------------------------------------------------------
    # Phase filter
    # ------------------------------------------------------------------

    def test_phase_filter(self) -> None:
        """Filtering by source_phase returns assets from that phase."""
        library = AssetLibrary(brand="SearchBrand")
        results = library.search(
            query="",
            filters={"phase": "2"},
        )
        library.close()

        assert len(results) >= 4, (
            f"Expected at least 4 phase-2 assets, got {len(results)}"
        )
        for r in results:
            assert r.get("source_phase") == "2"


# ---------------------------------------------------------------------------
# Tests — Chroma fallback
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestAssetLibraryChromaFallback:
    """Chroma integration — graceful fallback when Chroma is not available.

    The ``VectorStore`` class degrades gracefully when ``chromadb`` is not
    installed.  All search operations return empty results instead of
    crashing.
    """

    def test_vector_store_available_reflects_chromadb_installed(
        self,
        patch_asset_db_paths: Path,
    ) -> None:
        """VectorStore.available matches the module-level chromadb check."""
        from automedia.asset_library.vector_store import _chromadb_installed

        store = AssetLibrary(brand="ChromaBrand").vector_store
        assert store.available == _chromadb_installed

    def test_search_works_without_chroma(
        self,
        patch_asset_db_paths: Path,
    ) -> None:
        """AssetLibrary.search() works even when Chroma is unavailable."""
        db = AssetDatabase(brand="ChromaBrand")
        db.add_asset(
            AssetDoc(
                doc_id="chroma_test_001",
                type="strategy",
                title="Chroma Test Doc",
                tags=["chroma", "test"],
            )
        )
        db.close()

        library = AssetLibrary(brand="ChromaBrand")
        results = library.search(query="Chroma Test")
        library.close()

        assert len(results) >= 1
        assert results[0]["title"] == "Chroma Test Doc"

    def test_semantic_search_fallback_empty(
        self,
        patch_asset_db_paths: Path,
    ) -> None:
        """Semantic search returns empty list when Chroma is unavailable."""
        store = AssetLibrary(brand="ChromaBrand").vector_store
        results = store.search("any query")
        assert isinstance(results, list)
        if not store.available:
            assert len(results) == 0


# ---------------------------------------------------------------------------
# Tests — Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestAssetLibraryEdgeCases:
    """Edge cases for the Asset Library."""

    def test_search_results_include_doc_id(
        self,
        patch_asset_db_paths: Path,
    ) -> None:
        """Search results include doc_id for every result."""
        db = AssetDatabase(brand="EdgeBrand")
        db.add_asset(
            AssetDoc(
                doc_id="edge_001",
                type="strategy",
                title="Edge Test Doc",
                tags=["edge"],
            )
        )
        db.close()

        library = AssetLibrary(brand="EdgeBrand")
        results = library.search(query="Edge Test")
        library.close()

        assert len(results) >= 1
        assert "doc_id" in results[0]
        assert results[0]["doc_id"] == "edge_001"

    def test_search_multiple_filters_combined(
        self,
        patch_asset_db_paths: Path,
    ) -> None:
        """Multiple filters (type + lang) narrow results correctly."""
        db = AssetDatabase(brand="MultiFilterBrand")
        for doc_data in [
            AssetDoc(doc_id="mf_001", type="content", title="EN Blog", tags=[], lang="en"),
            AssetDoc(doc_id="mf_002", type="content", title="ZH Blog", tags=[], lang="zh"),
            AssetDoc(doc_id="mf_003", type="strategy", title="EN Strategy", tags=[], lang="en"),
        ]:
            db.add_asset(doc_data)
        db.close()

        library = AssetLibrary(brand="MultiFilterBrand")
        results = library.search(
            query="",
            filters={"type": "content", "lang": "en"},
        )
        library.close()

        assert len(results) == 1
        assert results[0]["title"] == "EN Blog"

    def test_delete_asset(
        self,
        patch_asset_db_paths: Path,
    ) -> None:
        """Assets can be deleted from the database."""
        db = AssetDatabase(brand="DeleteBrand")
        db.add_asset(
            AssetDoc(doc_id="del_001", type="strategy", title="To Delete", tags=[])
        )
        assert db.count() == 1

        db.delete_asset("del_001")
        assert db.count() == 0
        assert db.get_asset("del_001") is None
        db.close()

    def test_standalone_search_assets_function(
        self,
        patch_asset_db_paths: Path,
    ) -> None:
        """The standalone ``search_assets()`` function works correctly."""
        db = AssetDatabase(brand="StandaloneBrand")
        db.add_asset(
            AssetDoc(
                doc_id="sa_001",
                type="persona",
                title="Standalone Persona",
                tags=["standalone"],
            )
        )
        db.close()

        results = search_assets(
            query="Standalone",
            brand="StandaloneBrand",
            filters={"type": "persona"},
        )

        assert len(results) >= 1
        assert results[0]["title"] == "Standalone Persona"
