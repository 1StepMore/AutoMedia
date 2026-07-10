"""E2E test for asset library migration (SQLite+Chroma -> PostgreSQL+pgvector).

Tests the ``migrate_assets()`` function in dry-run mode, verifying that it
correctly reads source data from SQLite and Chroma and produces an accurate
migration report with counts and checksums.

Actual PostgreSQL insertion is not tested here (requires a live PG instance).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from automedia.asset_library.db import AssetDatabase, AssetDoc
from automedia.asset_library.migrate import migrate_assets


@pytest.fixture()
def patch_asset_db_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect AssetDatabase._base_dir to a tmp_path-scoped directory."""
    base_dir = tmp_path / "asset-library"
    monkeypatch.setattr(
        AssetDatabase,
        "_base_dir",
        staticmethod(lambda: base_dir),
    )
    return base_dir


@pytest.mark.e2e
class TestAssetLibraryMigration:
    """E2E: Asset library migration scenarios."""

    def _seed_assets(self, brand: str) -> int:
        """Create sample assets in the database and return the count."""
        db = AssetDatabase(brand=brand)
        assets = [
            AssetDoc(
                doc_id="mig_001",
                type="strategy",
                title="Migration Test Strategy",
                tags=["test", "migration"],
                lang="en",
                checksum="abc123",
            ),
            AssetDoc(
                doc_id="mig_002",
                type="persona",
                title="Migration Test Persona",
                tags=["test", "persona"],
                lang="zh",
                checksum="def456",
            ),
            AssetDoc(
                doc_id="mig_003",
                type="content",
                title="Migration Test Content",
                tags=["blog", "test"],
                lang="en",
                checksum="ghi789",
            ),
        ]
        for doc in assets:
            db.add_asset(doc)
        count = db.count()
        db.close()
        return count

    def test_dry_run_migration(self, patch_asset_db_paths: Path) -> None:
        """Creates assets, runs migrate with dry_run=True, verifies report."""
        brand = "DryRunBrand"
        expected_count = self._seed_assets(brand)

        report = migrate_assets(brand=brand, dry_run=True)

        assert report["brand"] == brand
        assert report["dry_run"] is True
        assert report["asset_count"] == expected_count, (
            f"Expected {expected_count} assets, got {report['asset_count']}"
        )
        assert report["success_count"] == expected_count, (
            f"Expected {expected_count} success, got {report['success_count']}"
        )
        assert report["fail_count"] == 0
        assert len(report["errors"]) == 0
        assert report["pg_uri_configured"] is False

        # Verify checksums
        assert "mig_001" in report["checksums"]
        assert report["checksums"]["mig_001"] == "abc123"
        assert report["checksums"]["mig_002"] == "def456"
        assert report["checksums"]["mig_003"] == "ghi789"

    def test_dry_run_empty_database(self, patch_asset_db_paths: Path) -> None:
        """Empty database produces zero-count report without errors."""
        report = migrate_assets(brand="EmptyBrand", dry_run=True)

        assert report["brand"] == "EmptyBrand"
        assert report["asset_count"] == 0
        assert report["success_count"] == 0
        assert report["fail_count"] == 0
        assert len(report["errors"]) == 0
        assert len(report["checksums"]) == 0

    def test_dry_run_with_pg_uri_ignored(self, patch_asset_db_paths: Path) -> None:
        """A pg_uri is accepted in dry-run mode but not used."""
        brand = "URIBrand"
        self._seed_assets(brand)

        report = migrate_assets(
            brand=brand,
            pg_uri="postgresql://user:pass@localhost:5432/test",
            dry_run=True,
        )

        assert report["dry_run"] is True
        assert report["pg_uri_configured"] is True
        assert report["asset_count"] == 3
        assert report["fail_count"] == 0
        assert len(report["errors"]) == 0

    def test_dry_run_non_existent_brand(self, patch_asset_db_paths: Path) -> None:
        """A brand with no database generates a report (new DB is created empty)."""
        # AssetDatabase creates the DB on init, so a non-existent brand
        # actually creates an empty database.  The migration should handle
        # this gracefully with zero counts and no errors.
        report = migrate_assets(brand="NonExistentBrand", dry_run=True)

        assert report["brand"] == "NonExistentBrand"
        # The DB is created empty on AssetDatabase.__init__
        assert report["asset_count"] == 0
        assert report["success_count"] == 0
        assert report["fail_count"] == 0
        assert len(report["errors"]) == 0
