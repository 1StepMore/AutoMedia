"""Unit tests for the asset_library migrate module.

Tests _format_for_pgvector with various asset/embedding combinations,
and migrate_assets in dry_run mode with mocked database and vector store.
No real PostgreSQL connection is needed.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from automedia.asset_library.migrate import _format_for_pgvector, migrate_assets

# ---------------------------------------------------------------------------
# _format_for_pgvector
# ---------------------------------------------------------------------------


class TestFormatForPgvector:
    """Verify asset-to-pgvector row formatting."""

    def test_matching_assets_and_embeddings(self) -> None:
        assets = [
            {
                "doc_id": "doc1",
                "brand_id": "brand-a",
                "type": "strategy",
                "source_phase": "1b",
                "title": "Market Report",
                "tags": ["marketing", "brand"],
                "lang": "zh",
                "file_path": "/project/decision/report.md",
                "vector_id": "vec1",
                "source_project_id": "proj1",
                "created_at": "2025-01-01 00:00:00",
                "updated_at": "2025-01-02 00:00:00",
                "checksum": "abc123",
            },
        ]
        embeddings = [
            {
                "id": "doc1",
                "document": "Full text of the market report.",
                "metadata": {"type": "strategy"},
            },
        ]
        rows = _format_for_pgvector(assets, embeddings)
        assert len(rows) == 1
        row = rows[0]
        assert row["doc_id"] == "doc1"
        assert row["brand_id"] == "brand-a"
        assert row["title"] == "Market Report"
        assert row["document_text"] == "Full text of the market report."
        assert row["embedding"] is None  # placeholder

    def test_tags_serialized_to_json(self) -> None:
        assets = [
            {
                "doc_id": "doc1",
                "brand_id": "b",
                "type": "content",
                "title": "T",
                "tags": ["ai", "video", "brand"],
                "lang": "en",
                "file_path": "/f",
                "source_phase": "2",
                "vector_id": "",
                "source_project_id": "",
                "created_at": "",
                "updated_at": "",
                "checksum": "",
            },
        ]
        rows = _format_for_pgvector(assets, [])
        assert rows[0]["tags"] == json.dumps(["ai", "video", "brand"])

    def test_asset_with_no_matching_embedding(self) -> None:
        assets = [
            {
                "doc_id": "doc_no_emb",
                "brand_id": "b",
                "type": "content",
                "title": "Orphan Doc",
                "tags": [],
                "lang": "zh",
                "file_path": "/f",
                "source_phase": "",
                "vector_id": "",
                "source_project_id": "",
                "created_at": "",
                "updated_at": "",
                "checksum": "xyz",
            },
        ]
        rows = _format_for_pgvector(assets, [])
        assert len(rows) == 1
        assert rows[0]["document_text"] == ""  # no embedding text
        assert rows[0]["embedding"] is None

    def test_empty_assets_and_embeddings(self) -> None:
        rows = _format_for_pgvector([], [])
        assert rows == []

    def test_tags_already_json_string(self) -> None:
        """When tags is already a string (not a list), it passes through."""
        assets = [
            {
                "doc_id": "doc1",
                "brand_id": "b",
                "type": "content",
                "title": "T",
                "tags": '["a", "b"]',
                "lang": "zh",
                "file_path": "/f",
                "source_phase": "",
                "vector_id": "",
                "source_project_id": "",
                "created_at": "",
                "updated_at": "",
                "checksum": "",
            },
        ]
        rows = _format_for_pgvector(assets, [])
        assert rows[0]["tags"] == '["a", "b"]'

    def test_tags_none_defaults_to_empty_array(self) -> None:
        assets = [
            {
                "doc_id": "doc1",
                "brand_id": "b",
                "type": "content",
                "title": "T",
                "tags": None,
                "lang": "zh",
                "file_path": "/f",
                "source_phase": "",
                "vector_id": "",
                "source_project_id": "",
                "created_at": "",
                "updated_at": "",
                "checksum": "",
            },
        ]
        rows = _format_for_pgvector(assets, [])
        assert rows[0]["tags"] == "[]"

    def test_multiple_assets_with_partial_embeddings(self) -> None:
        assets = [
            {
                "doc_id": "d1",
                "brand_id": "b",
                "type": "strategy",
                "title": "A",
                "tags": [],
                "lang": "zh",
                "file_path": "/a",
                "source_phase": "",
                "vector_id": "",
                "source_project_id": "",
                "created_at": "",
                "updated_at": "",
                "checksum": "c1",
            },
            {
                "doc_id": "d2",
                "brand_id": "b",
                "type": "content",
                "title": "B",
                "tags": [],
                "lang": "en",
                "file_path": "/b",
                "source_phase": "",
                "vector_id": "",
                "source_project_id": "",
                "created_at": "",
                "updated_at": "",
                "checksum": "c2",
            },
        ]
        embeddings = [
            {"id": "d1", "document": "text for d1", "metadata": {}},
        ]
        rows = _format_for_pgvector(assets, embeddings)
        assert len(rows) == 2
        assert rows[0]["document_text"] == "text for d1"
        assert rows[1]["document_text"] == ""  # d2 has no embedding


# ---------------------------------------------------------------------------
# migrate_assets (dry_run)
# ---------------------------------------------------------------------------


class TestMigrateAssetsDryRun:
    """Verify dry-run migration report structure."""

    @patch("automedia.asset_library.migrate.VectorStore")
    @patch("automedia.asset_library.migrate.AssetDatabase")
    def test_dry_run_report_structure(self, mock_db_cls: MagicMock, mock_vs_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.list_all.return_value = [
            {
                "doc_id": "doc1",
                "brand_id": "brand-a",
                "type": "strategy",
                "title": "Report",
                "tags": ["marketing"],
                "lang": "zh",
                "file_path": "/f",
                "source_phase": "1b",
                "vector_id": "",
                "source_project_id": "p1",
                "created_at": "2025-01-01",
                "updated_at": "2025-01-01",
                "checksum": "abc",
            },
        ]

        mock_vs = MagicMock()
        mock_vs_cls.return_value = mock_vs
        mock_vs.get_all_embeddings.return_value = [
            {
                "id": "doc1",
                "document": "Full text",
                "metadata": {"type": "strategy"},
            },
        ]

        report = migrate_assets(brand="brand-a", dry_run=True)

        assert report["brand"] == "brand-a"
        assert report["dry_run"] is True
        assert report["asset_count"] == 1
        assert report["embedding_count"] == 1
        assert report["success_count"] == 1
        assert report["fail_count"] == 0
        assert report["errors"] == []
        assert "doc1" in report["checksums"]
        assert report["pg_uri_configured"] is False

    @patch("automedia.asset_library.migrate.VectorStore")
    @patch("automedia.asset_library.migrate.AssetDatabase")
    def test_dry_run_empty_database(self, mock_db_cls: MagicMock, mock_vs_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.list_all.return_value = []

        mock_vs = MagicMock()
        mock_vs_cls.return_value = mock_vs
        mock_vs.get_all_embeddings.return_value = []

        report = migrate_assets(brand="empty-brand", dry_run=True)

        assert report["asset_count"] == 0
        assert report["embedding_count"] == 0
        assert report["success_count"] == 0
        assert report["fail_count"] == 0
        assert report["checksums"] == {}

    @patch("automedia.asset_library.migrate.VectorStore")
    @patch("automedia.asset_library.migrate.AssetDatabase")
    def test_dry_run_does_not_call_pg(self, mock_db_cls: MagicMock, mock_vs_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.list_all.return_value = []

        mock_vs = MagicMock()
        mock_vs_cls.return_value = mock_vs
        mock_vs.get_all_embeddings.return_value = []

        # No pg_uri provided — should not attempt any PG connection
        report = migrate_assets(brand="test", dry_run=True)
        assert report["pg_uri_configured"] is False

    @patch("automedia.asset_library.migrate.VectorStore")
    @patch("automedia.asset_library.migrate.AssetDatabase")
    def test_dry_run_with_pg_uri_configured(
        self, mock_db_cls: MagicMock, mock_vs_cls: MagicMock
    ) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.list_all.return_value = []

        mock_vs = MagicMock()
        mock_vs_cls.return_value = mock_vs
        mock_vs.get_all_embeddings.return_value = []

        report = migrate_assets(brand="test", pg_uri="postgresql://localhost/test", dry_run=True)
        # pg_uri was provided but dry_run=True → PG is not called
        assert report["pg_uri_configured"] is True
        assert report["dry_run"] is True

    @patch("automedia.asset_library.migrate.VectorStore")
    @patch("automedia.asset_library.migrate.AssetDatabase")
    def test_dry_run_db_failure(self, mock_db_cls: MagicMock, mock_vs_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.list_all.side_effect = RuntimeError("DB connection failed")

        mock_vs = MagicMock()
        mock_vs_cls.return_value = mock_vs

        report = migrate_assets(brand="broken", dry_run=True)
        assert report["fail_count"] == 1
        assert len(report["errors"]) == 1
        assert "DB connection failed" in report["errors"][0]
