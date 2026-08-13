"""Unit tests for AssetDatabase — SQLite storage for brand assets.

Covers CRUD operations, tag/keyword search, checksum dedup, context
manager lifecycle, and empty-database edge cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from automedia.asset_library.db import ASSET_TYPES, AssetDatabase, AssetDoc

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture()
def db(patch_asset_db_paths: Path) -> AssetDatabase:
    """Open an AssetDatabase backed by tmp_path."""
    return AssetDatabase(brand="test-brand")


@pytest.fixture()
def db_with_sample(db: AssetDatabase, sample_asset_doc: AssetDoc) -> tuple[AssetDatabase, str]:
    """Database pre-loaded with one sample asset. Returns (db, doc_id)."""
    doc_id = db.add_asset(sample_asset_doc)
    return db, doc_id


# ===================================================================
# Tests — __init__ creates directories and DB file
# ===================================================================


class TestAssetDatabaseInit:
    """AssetDatabase.__init__ creates the brand directory and SQLite file."""

    def test_creates_directory_and_db_file(self, patch_asset_db_paths: Path) -> None:
        """Brand subdirectory and index.sqlite should exist after init."""
        db = AssetDatabase(brand="my-brand")

        brand_dir = patch_asset_db_paths / "asset-library" / "my-brand"
        assert brand_dir.is_dir()
        assert (brand_dir / "index.sqlite").is_file()

        db.close()

    def test_brand_property(self, db: AssetDatabase) -> None:
        """The .brand property should return the brand passed to __init__."""
        assert db.brand == "test-brand"

    def test_db_path_property(self, db: AssetDatabase, patch_asset_db_paths: Path) -> None:
        """The .db_path property should point to the resolved SQLite file."""
        expected = patch_asset_db_paths / "asset-library" / "test-brand" / "index.sqlite"
        assert db.db_path == expected


# ===================================================================
# Tests — add_asset
# ===================================================================


class TestAddAsset:
    """add_asset() inserts a row and returns a doc_id string."""

    def test_returns_uuid_string(self, db: AssetDatabase, sample_asset_doc: AssetDoc) -> None:
        """When doc_id is empty, a UUID string should be generated."""
        doc_id = db.add_asset(sample_asset_doc)

        assert isinstance(doc_id, str)
        assert len(doc_id) == 36  # UUID4 format

    def test_returns_provided_doc_id(self, db: AssetDatabase) -> None:
        """When doc_id is set, it should be returned as-is."""
        doc = AssetDoc(
            doc_id="custom-id-001",
            brand_id="test-brand",
            type="asset",
            title="Custom",
        )
        result = db.add_asset(doc)
        assert result == "custom-id-001"

    def test_with_empty_tags_list(self, db: AssetDatabase) -> None:
        """An asset with empty tags should be stored and retrievable."""
        doc = AssetDoc(
            brand_id="test-brand",
            type="content",
            tags=[],
            title="No Tags Doc",
        )
        doc_id = db.add_asset(doc)
        stored = db.get_asset(doc_id)

        assert stored is not None
        assert stored["tags"] == []

    def test_with_none_checksum(self, db: AssetDatabase) -> None:
        """An asset with empty checksum (None-like) should still be stored."""
        doc = AssetDoc(
            brand_id="test-brand",
            type="asset",
            title="No Checksum",
            checksum="",
        )
        doc_id = db.add_asset(doc)
        stored = db.get_asset(doc_id)

        assert stored is not None
        assert stored["checksum"] == ""

    def test_brand_id_forced_to_db_brand(
        self, db: AssetDatabase, sample_asset_doc: AssetDoc
    ) -> None:
        """brand_id in the stored row should match the database brand."""
        sample_asset_doc.brand_id = "other-brand"
        doc_id = db.add_asset(sample_asset_doc)
        stored = db.get_asset(doc_id)

        assert stored is not None
        assert stored["brand_id"] == "test-brand"


# ===================================================================
# Tests — get_asset
# ===================================================================


class TestGetAsset:
    """get_asset() retrieves a single asset by doc_id."""

    def test_returns_correct_doc(self, db_with_sample: tuple[AssetDatabase, str]) -> None:
        """Should return the exact doc that was inserted."""
        db, doc_id = db_with_sample
        result = db.get_asset(doc_id)

        assert result is not None
        assert result["doc_id"] == doc_id
        assert result["title"] == "Test Doc"
        assert result["type"] == "content"
        assert result["lang"] == "zh"

    def test_returns_none_for_nonexistent_id(self, db: AssetDatabase) -> None:
        """Should return None when doc_id does not exist."""
        result = db.get_asset("nonexistent-id-999")
        assert result is None

    def test_tags_deserialized_to_list(self, db_with_sample: tuple[AssetDatabase, str]) -> None:
        """Tags stored as JSON should be returned as a Python list."""
        db, doc_id = db_with_sample
        result = db.get_asset(doc_id)

        assert result is not None
        assert isinstance(result["tags"], list)
        assert "test" in result["tags"]
        assert "sample" in result["tags"]


# ===================================================================
# Tests — search_by_type
# ===================================================================


class TestSearchByType:
    """search_by_type() filters assets by the built-in type taxonomy."""

    def test_returns_matching_type(self, db: AssetDatabase, sample_asset_doc: AssetDoc) -> None:
        """Should return assets whose type matches the query."""
        db.add_asset(sample_asset_doc)
        results = db.search_by_type("content")

        assert len(results) == 1
        assert results[0]["type"] == "content"

    def test_returns_empty_for_nonexistent_type(self, db: AssetDatabase) -> None:
        """Should return empty list when no assets match the type."""
        results = db.search_by_type("strategy")
        assert results == []

    def test_excludes_other_types(self, db: AssetDatabase, sample_asset_doc: AssetDoc) -> None:
        """Should not return assets of a different type."""
        db.add_asset(sample_asset_doc)
        db.add_asset(
            AssetDoc(
                brand_id="test-brand",
                type="strategy",
                title="Strategy Doc",
            )
        )
        results = db.search_by_type("strategy")

        assert len(results) == 1
        assert results[0]["type"] == "strategy"


# ===================================================================
# Tests — search_by_tags
# ===================================================================


class TestSearchByTags:
    """search_by_tags() finds assets whose tags overlap with the query."""

    def test_returns_matching_tag(self, db: AssetDatabase, sample_asset_doc: AssetDoc) -> None:
        """Should return assets containing at least one of the query tags."""
        db.add_asset(sample_asset_doc)
        results = db.search_by_tags(["test"])

        assert len(results) == 1
        assert results[0]["title"] == "Test Doc"

    def test_returns_empty_for_non_matching_tags(
        self, db: AssetDatabase, sample_asset_doc: AssetDoc
    ) -> None:
        """Should return empty list when no tags match."""
        db.add_asset(sample_asset_doc)
        results = db.search_by_tags(["nonexistent-tag"])

        assert results == []

    def test_returns_empty_for_empty_tag_list(self, db: AssetDatabase) -> None:
        """Should return empty list when tag list is empty."""
        results = db.search_by_tags([])
        assert results == []

    def test_deduplicates_multi_tag_match(
        self, db: AssetDatabase, sample_asset_doc: AssetDoc
    ) -> None:
        """Asset matching multiple query tags should appear only once."""
        db.add_asset(sample_asset_doc)
        results = db.search_by_tags(["test", "sample"])

        assert len(results) == 1


# ===================================================================
# Tests — keyword_search
# ===================================================================


class TestKeywordSearch:
    """keyword_search() performs case-insensitive LIKE search on title."""

    def test_matches_substring(self, db: AssetDatabase, sample_asset_doc: AssetDoc) -> None:
        """Should match a substring of the title."""
        db.add_asset(sample_asset_doc)
        results = db.keyword_search("Test")

        assert len(results) == 1
        assert results[0]["title"] == "Test Doc"

    def test_case_insensitive(self, db: AssetDatabase) -> None:
        """LIKE search should be case-insensitive in SQLite."""
        db.add_asset(
            AssetDoc(
                brand_id="test-brand",
                type="asset",
                title="UPPERCASE TITLE",
            )
        )
        results = db.keyword_search("uppercase")
        assert len(results) == 1

    def test_returns_empty_for_no_match(
        self, db: AssetDatabase, sample_asset_doc: AssetDoc
    ) -> None:
        """Should return empty list when keyword doesn't match any title."""
        db.add_asset(sample_asset_doc)
        results = db.keyword_search("zzz_nonexistent_zzz")

        assert results == []


# ===================================================================
# Tests — list_all
# ===================================================================


class TestListAll:
    """list_all() returns every asset ordered by created_at DESC."""

    def test_returns_sorted_desc(self, db: AssetDatabase) -> None:
        """Results should be ordered by created_at descending."""
        db.add_asset(
            AssetDoc(
                doc_id="first",
                brand_id="test-brand",
                type="asset",
                title="First",
            )
        )
        db.add_asset(
            AssetDoc(
                doc_id="second",
                brand_id="test-brand",
                type="asset",
                title="Second",
            )
        )

        results = db.list_all()

        assert len(results) == 2
        timestamps = [r["created_at"] for r in results]
        assert timestamps == sorted(timestamps, reverse=True)


# ===================================================================
# Tests — count
# ===================================================================


class TestCount:
    """count() returns the total number of rows in the assets table."""

    def test_returns_correct_count(self, db: AssetDatabase, sample_asset_doc: AssetDoc) -> None:
        """Count should match the number of inserted assets."""
        assert db.count() == 0

        db.add_asset(sample_asset_doc)
        assert db.count() == 1

        db.add_asset(
            AssetDoc(
                brand_id="test-brand",
                type="strategy",
                title="Another",
            )
        )
        assert db.count() == 2


# ===================================================================
# Tests — delete_asset
# ===================================================================


class TestDeleteAsset:
    """delete_asset() removes the row with the given doc_id."""

    def test_removes_row(self, db_with_sample: tuple[AssetDatabase, str]) -> None:
        """After deletion, get_asset should return None."""
        db, doc_id = db_with_sample
        assert db.get_asset(doc_id) is not None

        db.delete_asset(doc_id)
        assert db.get_asset(doc_id) is None

    def test_count_decreases(self, db_with_sample: tuple[AssetDatabase, str]) -> None:
        """Count should decrease after deletion."""
        db, doc_id = db_with_sample
        assert db.count() == 1

        db.delete_asset(doc_id)
        assert db.count() == 0

    def test_delete_nonexistent_is_noop(self, db: AssetDatabase) -> None:
        """Deleting a nonexistent doc_id should not raise."""
        db.delete_asset("no-such-id")
        assert db.count() == 0


# ===================================================================
# Tests — asset_exists_by_checksum
# ===================================================================


class TestAssetExistsByChecksum:
    """asset_exists_by_checksum() checks for duplicate content by hash."""

    def test_returns_true_for_existing_checksum(
        self, db: AssetDatabase, sample_asset_doc: AssetDoc
    ) -> None:
        """Should return True when a matching checksum exists."""
        db.add_asset(sample_asset_doc)
        assert db.asset_exists_by_checksum("abc123") is True

    def test_returns_false_for_missing_checksum(self, db: AssetDatabase) -> None:
        """Should return False when no asset has that checksum."""
        assert db.asset_exists_by_checksum("no-such-checksum") is False


# ===================================================================
# Tests — context manager
# ===================================================================


class TestContextManager:
    """AssetDatabase supports `with` statement for automatic cleanup."""

    def test_context_manager_closes_connection(self, patch_asset_db_paths: Path) -> None:
        """__exit__ should close the connection cleanly."""
        with AssetDatabase(brand="ctx-test") as db:
            doc_id = db.add_asset(
                AssetDoc(
                    brand_id="ctx-test",
                    type="asset",
                    title="Context Doc",
                )
            )
            assert db.get_asset(doc_id) is not None

        # After exiting, internal conn should be None
        assert db._conn is None


# ===================================================================
# Tests — empty database edge cases
# ===================================================================


class TestEmptyDatabase:
    """All search methods should return empty results on an empty database."""

    def test_list_all_empty(self, db: AssetDatabase) -> None:
        assert db.list_all() == []

    def test_search_by_type_empty(self, db: AssetDatabase) -> None:
        assert db.search_by_type("content") == []

    def test_search_by_tags_empty(self, db: AssetDatabase) -> None:
        assert db.search_by_tags(["any-tag"]) == []

    def test_keyword_search_empty(self, db: AssetDatabase) -> None:
        assert db.keyword_search("anything") == []

    def test_count_zero(self, db: AssetDatabase) -> None:
        assert db.count() == 0

    def test_asset_exists_by_checksum_false(self, db: AssetDatabase) -> None:
        assert db.asset_exists_by_checksum("abc") is False


# ===================================================================
# Tests — ASSET_TYPES constant
# ===================================================================


class TestAssetTypesConstant:
    """ASSET_TYPES should contain the built-in type taxonomy."""

    def test_contains_expected_types(self) -> None:
        expected = {"strategy", "persona", "product", "content", "kol_brief", "asset"}
        assert expected == ASSET_TYPES

    def test_is_frozenset(self) -> None:
        assert isinstance(ASSET_TYPES, frozenset)
