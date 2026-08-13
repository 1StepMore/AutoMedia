"""Tests for ``automedia history`` CLI command.

Covers querying pipeline history for existing and nonexistent projects,
JSON output mode, and projects with no history rows.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.hooks.pipeline_history import _db_path, _ensure_schema

runner = CliRunner()


# =========================================================================
# Fixtures
# =========================================================================


def _create_project_with_history(
    tmp_path: Path,
    project_id: str = "test-proj-001",
    num_rows: int = 3,
) -> dict[str, Any]:
    """Create a temporary project with history DB rows.

    Returns a dict with ``base_dir``, ``project_dir``, ``project_id``.
    """
    slug = "test-topic"
    project_dir = tmp_path / f"20260707_{slug}"
    project_dir.mkdir(parents=True)

    info = {
        "project_id": project_id,
        "topic": "Test Topic",
        "brand": "TestBrand",
        "tenant_id": "default",
        "created_at": "2026-07-07T00:00:00+00:00",
    }
    (project_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

    # Populate history DB
    db_file = Path(_db_path(str(project_dir)))
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    try:
        _ensure_schema(conn)
        base_ts = time.time()
        actions = ["lint:started", "lint:completed", "content_writer:started"]
        for i in range(num_rows):
            conn.execute(
                "INSERT INTO pipeline_history (project_id, action, timestamp, metadata_json) "
                "VALUES (?, ?, ?, ?)",
                (
                    project_id,
                    actions[i] if i < len(actions) else f"gate_{i}:completed",
                    base_ts + i,
                    json.dumps({"gate": actions[i].split(":")[0] if i < len(actions) else f"gate_{i}"}),
                ),
            )
        conn.commit()
    finally:
        conn.close()

    return {
        "base_dir": str(tmp_path),
        "project_dir": str(project_dir),
        "project_id": project_id,
    }


def _create_project_no_history(
    tmp_path: Path,
    project_id: str = "empty-proj-002",
) -> dict[str, Any]:
    """Create a temporary project with NO history DB."""
    slug = "empty-topic"
    project_dir = tmp_path / f"20260708_{slug}"
    project_dir.mkdir(parents=True)

    info = {
        "project_id": project_id,
        "topic": "Empty Topic",
        "brand": "EmptyBrand",
        "tenant_id": "default",
        "created_at": "2026-07-08T00:00:00+00:00",
    }
    (project_dir / "00_project_info.json").write_text(json.dumps(info), encoding="utf-8")

    return {
        "base_dir": str(tmp_path),
        "project_dir": str(project_dir),
        "project_id": project_id,
    }


# =========================================================================
# Tests: history with data
# =========================================================================


class TestHistoryWithData:
    """Tests for ``automedia history <project_id>`` when history exists."""

    def test_history_shows_rows(self, tmp_path: Path) -> None:
        """History rows are printed in a table."""
        proj = _create_project_with_history(tmp_path)
        result = runner.invoke(
            app, ["history", proj["project_id"], "--base-dir", proj["base_dir"]]
        )
        assert result.exit_code == 0
        assert "Timestamp" in result.output
        assert "Action" in result.output
        assert "Details" in result.output
        assert "lint:started" in result.output
        assert "lint:completed" in result.output
        assert "content_writer:started" in result.output

    def test_history_json_format(self, tmp_path: Path) -> None:
        """--json returns history rows as structured data."""
        proj = _create_project_with_history(tmp_path)
        result = runner.invoke(
            app, ["--json", "history", proj["project_id"], "--base-dir", proj["base_dir"]]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["project_id"] == proj["project_id"]
        assert len(data["items"]) == 3
        assert data["count"] == 3
        assert data["items"][0]["action"] == "lint:started"


# =========================================================================
# Tests: history for nonexistent project
# =========================================================================


class TestHistoryNonexistent:
    """Tests for ``automedia history <nonexistent>``."""

    def test_history_nonexistent_project(self, tmp_path: Path) -> None:
        """Nonexistent project_id prints 'No history found'."""
        # Create a project so base_dir is valid but project_id doesn't match
        _create_project_with_history(tmp_path, project_id="other-proj")
        result = runner.invoke(
            app, ["history", "nonexistent", "--base-dir", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert "No history found" in result.output

    def test_history_nonexistent_base_dir(self, tmp_path: Path) -> None:
        """Non-existent base_dir prints 'No history found'."""
        result = runner.invoke(
            app, ["history", "any-id", "--base-dir", str(tmp_path / "nope")]
        )
        assert result.exit_code == 0
        assert "No history found" in result.output

    def test_history_json_nonexistent(self, tmp_path: Path) -> None:
        """--json with nonexistent project returns JSON with empty items."""
        result = runner.invoke(
            app, ["--json", "history", "nonexistent", "--base-dir", str(tmp_path)]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["count"] == 0
        assert data["items"] == []


# =========================================================================
# Tests: history for project with no history rows
# =========================================================================


class TestHistoryEmpty:
    """Tests for ``automedia history`` when project exists but has no history."""

    def test_history_no_rows(self, tmp_path: Path) -> None:
        """Project with no history DB shows 'No history found'."""
        proj = _create_project_no_history(tmp_path)
        result = runner.invoke(
            app, ["history", proj["project_id"], "--base-dir", proj["base_dir"]]
        )
        assert result.exit_code == 0
        assert "No history found" in result.output

    def test_history_json_no_rows(self, tmp_path: Path) -> None:
        """--json for project with no history returns empty items."""
        proj = _create_project_no_history(tmp_path)
        result = runner.invoke(
            app, ["--json", "history", proj["project_id"], "--base-dir", proj["base_dir"]]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["count"] == 0
        assert data["items"] == []


# =========================================================================
# Tests: command registration
# =========================================================================


class TestHistoryRegistration:
    """Tests that the history command is properly registered."""

    def test_command_appears_in_help(self) -> None:
        """The history command appears in the main help output."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "history" in result.output

    def test_history_help(self) -> None:
        """``automedia history --help`` shows usage."""
        result = runner.invoke(app, ["history", "--help"])
        assert result.exit_code == 0
        # Help should reference the project_id argument (typer prints it as [PROJECT_ID])
        assert "PROJECT_ID" in result.output or "project" in result.output.lower()
