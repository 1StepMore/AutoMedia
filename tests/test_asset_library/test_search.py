"""Unit tests for the asset_library search module.

Tests _has_tag_overlap, _apply_filters, and _merge_results with pure
data — no database or vector store dependencies. External dependencies
(AssetDatabase, VectorStore) are mocked via unittest.mock.patch.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.asset_library.search import (
    AssetLibrary,
    _has_tag_overlap,
)

# ---------------------------------------------------------------------------
# _has_tag_overlap
# ---------------------------------------------------------------------------


class TestHasTagOverlap:
    """Verify tag overlap detection across input types."""

    def test_matching_tags(self) -> None:
        assert _has_tag_overlap(["marketing", "strategy"], {"marketing"}) is True

    def test_no_matching_tags(self) -> None:
        assert _has_tag_overlap(["marketing", "strategy"], {"video"}) is False

    def test_empty_asset_tags(self) -> None:
        assert _has_tag_overlap([], {"marketing"}) is False

    def test_empty_filter_tags(self) -> None:
        # Empty set intersection is always False
        assert _has_tag_overlap(["marketing"], set()) is False

    def test_both_empty(self) -> None:
        assert _has_tag_overlap([], set()) is False

    def test_none_asset_tags(self) -> None:
        assert _has_tag_overlap(None, {"marketing"}) is False

    def test_string_asset_tag(self) -> None:
        # A plain string (not JSON) should be wrapped in a list
        assert _has_tag_overlap("marketing", {"marketing"}) is True

    def test_json_string_asset_tags(self) -> None:
        tags_json = json.dumps(["marketing", "strategy"])
        assert _has_tag_overlap(tags_json, {"strategy"}) is True

    def test_json_string_no_match(self) -> None:
        tags_json = json.dumps(["marketing", "strategy"])
        assert _has_tag_overlap(tags_json, {"video"}) is False

    def test_case_insensitive_matching(self) -> None:
        assert _has_tag_overlap(["Marketing"], {"marketing"}) is True

    def test_integer_asset_tag_coerced(self) -> None:
        # Non-list, non-string types are coerced via str()
        assert _has_tag_overlap(42, {"42"}) is True

    def test_multiple_filter_tags_any_match(self) -> None:
        assert _has_tag_overlap(["a", "b"], {"b", "c"}) is True

    def test_invalid_json_string_treated_as_single_tag(self) -> None:
        assert _has_tag_overlap("not-json", {"not-json"}) is True


# ---------------------------------------------------------------------------
# _apply_filters
# ---------------------------------------------------------------------------


class TestApplyFilters:
    """Verify post-search filter application."""

    @pytest.fixture()
    def sample_results(self) -> list[dict[str, Any]]:
        return [
            {
                "doc_id": "1",
                "type": "strategy",
                "tags": ["marketing", "brand"],
                "lang": "zh",
                "source_phase": "1b",
                "title": "Strategy Doc",
            },
            {
                "doc_id": "2",
                "type": "content",
                "tags": ["video", "ai"],
                "lang": "en",
                "source_phase": "2",
                "title": "Video Script",
            },
            {
                "doc_id": "3",
                "type": "persona",
                "tags": ["persona", "brand"],
                "lang": "zh",
                "source_phase": "1b",
                "title": "Persona Map",
            },
        ]

    def test_filter_by_type(self, sample_results: list[dict[str, Any]]) -> None:
        filtered = AssetLibrary._apply_filters(sample_results, {"type": "strategy"})
        assert len(filtered) == 1
        assert filtered[0]["doc_id"] == "1"

    def test_filter_by_type_case_insensitive(self, sample_results: list[dict[str, Any]]) -> None:
        filtered = AssetLibrary._apply_filters(sample_results, {"type": "Strategy"})
        assert len(filtered) == 1

    def test_filter_by_tags(self, sample_results: list[dict[str, Any]]) -> None:
        filtered = AssetLibrary._apply_filters(sample_results, {"tags": ["brand"]})
        assert len(filtered) == 2
        doc_ids = {r["doc_id"] for r in filtered}
        assert doc_ids == {"1", "3"}

    def test_filter_by_lang(self, sample_results: list[dict[str, Any]]) -> None:
        filtered = AssetLibrary._apply_filters(sample_results, {"lang": "en"})
        assert len(filtered) == 1
        assert filtered[0]["doc_id"] == "2"

    def test_filter_by_phase(self, sample_results: list[dict[str, Any]]) -> None:
        filtered = AssetLibrary._apply_filters(sample_results, {"phase": "2"})
        assert len(filtered) == 1
        assert filtered[0]["doc_id"] == "2"

    def test_combined_filters(self, sample_results: list[dict[str, Any]]) -> None:
        filtered = AssetLibrary._apply_filters(sample_results, {"type": "persona", "lang": "zh"})
        assert len(filtered) == 1
        assert filtered[0]["doc_id"] == "3"

    def test_empty_filters_passthrough(self, sample_results: list[dict[str, Any]]) -> None:
        filtered = AssetLibrary._apply_filters(sample_results, {})
        assert len(filtered) == 3

    def test_no_matches(self, sample_results: list[dict[str, Any]]) -> None:
        filtered = AssetLibrary._apply_filters(sample_results, {"type": "nonexistent"})
        assert len(filtered) == 0

    def test_empty_results(self) -> None:
        filtered = AssetLibrary._apply_filters([], {"type": "strategy"})
        assert filtered == []

    def test_filter_tags_with_json_string_tags(self) -> None:
        results = [
            {"doc_id": "1", "type": "content", "tags": json.dumps(["ai", "video"])},
        ]
        filtered = AssetLibrary._apply_filters(results, {"tags": ["ai"]})
        assert len(filtered) == 1


# ---------------------------------------------------------------------------
# _merge_results
# ---------------------------------------------------------------------------


class TestMergeResults:
    """Verify keyword + semantic result merging and deduplication."""

    def test_dedup_by_doc_id(self) -> None:
        keyword = [{"doc_id": "1", "title": "A", "_score": 1.0, "_source": "keyword"}]
        semantic = [
            {"doc_id": "1", "title": "A", "_score": 0.5, "_source": "semantic"},
        ]
        merged = AssetLibrary._merge_results(keyword, semantic)
        assert len(merged) == 1
        assert merged[0]["_source"] == "keyword"  # keyword wins

    def test_keyword_priority_over_semantic(self) -> None:
        keyword = [{"doc_id": "1", "title": "A", "_score": 1.0, "_source": "keyword"}]
        semantic = [
            {"doc_id": "1", "title": "A Different Title", "_score": 0.9, "_source": "semantic"},
        ]
        merged = AssetLibrary._merge_results(keyword, semantic)
        assert len(merged) == 1
        assert merged[0]["title"] == "A"  # keyword version kept

    def test_append_semantic_only_results(self) -> None:
        keyword = [{"doc_id": "1", "title": "A", "_score": 1.0}]
        semantic = [{"doc_id": "2", "title": "B", "_score": 0.6}]
        merged = AssetLibrary._merge_results(keyword, semantic)
        assert len(merged) == 2
        doc_ids = [r["doc_id"] for r in merged]
        assert doc_ids == ["1", "2"]

    def test_title_dedup_for_semantic_without_doc_id(self) -> None:
        keyword: list[dict[str, Any]] = []
        semantic = [
            {"doc_id": "", "title": "Same Title", "_score": 0.5},
            {"doc_id": "", "title": "Same Title", "_score": 0.4},
        ]
        merged = AssetLibrary._merge_results(keyword, semantic)
        assert len(merged) == 1

    def test_both_empty(self) -> None:
        merged = AssetLibrary._merge_results([], [])
        assert merged == []

    def test_only_keyword(self) -> None:
        keyword = [{"doc_id": "1", "title": "A"}]
        merged = AssetLibrary._merge_results(keyword, [])
        assert len(merged) == 1

    def test_only_semantic(self) -> None:
        semantic = [{"doc_id": "1", "title": "A"}]
        merged = AssetLibrary._merge_results([], semantic)
        assert len(merged) == 1

    def test_order_preserved(self) -> None:
        keyword = [
            {"doc_id": "1", "title": "First"},
            {"doc_id": "2", "title": "Second"},
        ]
        semantic = [{"doc_id": "3", "title": "Third"}]
        merged = AssetLibrary._merge_results(keyword, semantic)
        assert [r["title"] for r in merged] == ["First", "Second", "Third"]

    def test_semantic_with_no_doc_id_no_title_dedup(self) -> None:
        """Semantic results with different titles (no doc_id) are both kept."""
        keyword: list[dict[str, Any]] = []
        semantic = [
            {"doc_id": "", "title": "Title A", "_score": 0.5},
            {"doc_id": "", "title": "Title B", "_score": 0.4},
        ]
        merged = AssetLibrary._merge_results(keyword, semantic)
        assert len(merged) == 2


# ---------------------------------------------------------------------------
# AssetLibrary.search (mocked integration)
# ---------------------------------------------------------------------------


class TestAssetLibrarySearch:
    """Test the search orchestrator with mocked DB and VectorStore."""

    @patch("automedia.asset_library.search.VectorStore")
    @patch("automedia.asset_library.search.AssetDatabase")
    def test_search_calls_merge_and_filter(
        self, mock_db_cls: MagicMock, mock_vs_cls: MagicMock
    ) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.keyword_search.return_value = [
            {"doc_id": "1", "type": "strategy", "title": "Strategy"},
        ]
        mock_db.get_asset.return_value = None
        mock_db.list_all.return_value = []

        mock_vs = MagicMock()
        mock_vs_cls.return_value = mock_vs
        mock_vs.search.return_value = []

        with AssetLibrary(brand="test") as lib:
            results = lib.search("strategy", filters={"type": "strategy"})

        assert len(results) == 1
        assert results[0]["doc_id"] == "1"
        mock_db.close.assert_called_once()

    @patch("automedia.asset_library.search.VectorStore")
    @patch("automedia.asset_library.search.AssetDatabase")
    def test_search_empty_query_uses_list_all(
        self, mock_db_cls: MagicMock, mock_vs_cls: MagicMock
    ) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.list_all.return_value = [
            {"doc_id": "1", "type": "content", "title": "All Doc"},
        ]
        mock_db.get_asset.return_value = None

        mock_vs = MagicMock()
        mock_vs_cls.return_value = mock_vs
        mock_vs.search.return_value = []

        lib = AssetLibrary(brand="test")
        results = lib.search("", filters=None)

        mock_db.list_all.assert_called_once()
        assert len(results) == 1

    @patch("automedia.asset_library.search.VectorStore")
    @patch("automedia.asset_library.search.AssetDatabase")
    def test_search_closes_on_error(self, mock_db_cls: MagicMock, mock_vs_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.keyword_search.side_effect = RuntimeError("DB error")

        mock_vs = MagicMock()
        mock_vs_cls.return_value = mock_vs

        with pytest.raises(RuntimeError, match="DB error"), AssetLibrary(brand="test") as lib:
            lib.search("query")

        mock_db.close.assert_called_once()

    @patch("automedia.asset_library.search.VectorStore")
    @patch("automedia.asset_library.search.AssetDatabase")
    def test_context_manager(self, mock_db_cls: MagicMock, mock_vs_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_vs_cls.return_value = MagicMock()

        with AssetLibrary(brand="test") as lib:
            assert lib.brand == "test"

        mock_db.close.assert_called_once()
