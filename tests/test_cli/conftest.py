"""Shared fixtures for CLI tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app


@pytest.fixture()
def runner() -> CliRunner:
    """Return a Typer CliRunner instance."""
    return CliRunner()


@pytest.fixture()
def tmp_pool_db(tmp_path: Path) -> Path:
    """Return a path to a temporary pool database."""
    return tmp_path / "test_pool.db"


@pytest.fixture()
def tmp_project(tmp_path: Path) -> dict[str, Any]:
    """Create a temporary project directory with info JSON.

    Returns a dict with ``base_dir``, ``project_dir``, and ``project_id``.
    """
    project_id = "abc123def456"
    slug = "test-topic"
    project_dir = tmp_path / f"20260707_{slug}"
    project_dir.mkdir(parents=True)
    (project_dir / "01_content").mkdir()

    info = {
        "project_id": project_id,
        "topic": "Test Topic",
        "brand": "TestBrand",
        "tenant_id": "default",
        "created_at": "2026-07-07T00:00:00+00:00",
    }
    (project_dir / "00_project_info.json").write_text(
        json.dumps(info, indent=2), encoding="utf-8"
    )

    return {
        "base_dir": str(tmp_path),
        "project_dir": str(project_dir),
        "project_id": project_id,
    }
