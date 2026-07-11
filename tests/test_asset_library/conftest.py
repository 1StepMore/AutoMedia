"""Shared fixtures for asset_library unit tests.

All fixtures produce synthetic data only — zero production data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from automedia.asset_library.db import AssetDatabase, AssetDoc


@pytest.fixture()
def patch_asset_db_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect AssetDatabase._base_dir to tmp_path for test isolation."""
    test_base = tmp_path / "asset-library"
    monkeypatch.setattr(
        AssetDatabase, "_base_dir", staticmethod(lambda: test_base)
    )
    return tmp_path


@pytest.fixture()
def sample_asset_doc() -> AssetDoc:
    """Return a minimal AssetDoc for testing."""
    return AssetDoc(
        brand_id="test-brand",
        type="content",
        tags=["test", "sample"],
        file_path="test.md",
        title="Test Doc",
        checksum="abc123",
        lang="zh",
    )
