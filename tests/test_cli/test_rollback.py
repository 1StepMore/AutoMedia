"""Tests for ``automedia rollback`` command.

Covers: success, declined, no-history, already-archived, not-found scenarios.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_history_db(project_dir: str, project_id: str = "test_project") -> None:
    """Create a minimal history.db with at least one row."""
    hist_dir = Path(project_dir) / ".automedia"
    hist_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(hist_dir / "history.db"))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS pipeline_history ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " project_id TEXT NOT NULL,"
        " action TEXT NOT NULL,"
        " timestamp REAL NOT NULL,"
        " metadata_json TEXT"
        ")"
    )
    conn.execute(
        "INSERT INTO pipeline_history (project_id, action, timestamp, metadata_json) "
        "VALUES (?, ?, ?, ?)",
        (project_id, "run_started", time.time(), "{}"),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_with_history(tmp_path: Path) -> dict[str, Any]:
    """Create a project with pipeline history DB and status='completed'."""
    project_id = "rollback-test-001"
    slug = "rollback-topic"
    project_dir = tmp_path / f"20260707_{slug}"
    project_dir.mkdir(parents=True)

    info = {
        "project_id": project_id,
        "topic": "Rollback Topic",
        "brand": "TestBrand",
        "status": "completed",
        "tenant_id": "default",
        "created_at": "2026-07-07T00:00:00+00:00",
    }
    (project_dir / "00_project_info.json").write_text(
        json.dumps(info, indent=2), encoding="utf-8"
    )

    _create_history_db(str(project_dir), project_id)

    return {
        "base_dir": str(tmp_path),
        "project_dir": str(project_dir),
        "project_id": project_id,
    }


@pytest.fixture()
def project_without_history(tmp_path: Path) -> dict[str, Any]:
    """Create a project WITHOUT pipeline history DB."""
    project_id = "no-hist-002"
    slug = "no-history-topic"
    project_dir = tmp_path / f"20260708_{slug}"
    project_dir.mkdir(parents=True)

    info = {
        "project_id": project_id,
        "topic": "No History Topic",
        "brand": "TestBrand",
        "status": "running",
        "tenant_id": "default",
        "created_at": "2026-07-08T00:00:00+00:00",
    }
    (project_dir / "00_project_info.json").write_text(
        json.dumps(info, indent=2), encoding="utf-8"
    )

    return {
        "base_dir": str(tmp_path),
        "project_dir": str(project_dir),
        "project_id": project_id,
    }


@pytest.fixture()
def archived_project(tmp_path: Path) -> dict[str, Any]:
    """Create a project whose directory name already ends with _archived."""
    project_id = "archived-003"
    slug = "already-archived"
    project_dir = tmp_path / f"20260709_{slug}_archived"
    project_dir.mkdir(parents=True)

    info = {
        "project_id": project_id,
        "topic": "Archived Topic",
        "brand": "TestBrand",
        "status": "archived",
        "tenant_id": "default",
        "created_at": "2026-07-09T00:00:00+00:00",
    }
    (project_dir / "00_project_info.json").write_text(
        json.dumps(info, indent=2), encoding="utf-8"
    )

    return {
        "base_dir": str(tmp_path),
        "project_dir": str(project_dir),
        "project_id": project_id,
    }


# =========================================================================
# Tests
# =========================================================================


class TestRollbackCommand:
    """Tests for ``automedia rollback <project_id>``."""

    def test_rollback_success(self, project_with_history: dict[str, Any]) -> None:
        """Happy path: project with history is archived, status reverted, ROLLED_BACK written."""
        result = runner.invoke(
            app,
            [
                "rollback",
                project_with_history["project_id"],
                "--base-dir",
                project_with_history["base_dir"],
            ],
            input="y\n",
        )
        assert result.exit_code == 0, f"Expected 0, got {result.exit_code}: {result.output}"
        assert "Rolled back" in result.output
        assert "draft" in result.output

        # 1 — Directory was renamed to _archived
        orig_dir = Path(project_with_history["project_dir"])
        archived_dir = orig_dir.parent / f"{orig_dir.name}_archived"
        assert archived_dir.is_dir(), f"Archived dir should exist: {archived_dir}"
        assert not orig_dir.is_dir(), "Original dir should no longer exist"

        # 2 — Status is now 'draft' in the archived info file
        info_path = archived_dir / "00_project_info.json"
        assert info_path.is_file()
        data = json.loads(info_path.read_text(encoding="utf-8"))
        assert data["status"] == "draft"

        # 3 — ROLLED_BACK was written to history.db (last row)
        conn = sqlite3.connect(str(archived_dir / ".automedia" / "history.db"))
        try:
            cur = conn.execute(
                "SELECT action FROM pipeline_history ORDER BY id DESC LIMIT 1"
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "rolled_back"
        finally:
            conn.close()

    def test_rollback_declined(self, project_with_history: dict[str, Any]) -> None:
        """User types 'n' — project is NOT touched."""
        result = runner.invoke(
            app,
            [
                "rollback",
                project_with_history["project_id"],
                "--base-dir",
                project_with_history["base_dir"],
            ],
            input="n\n",
        )
        assert result.exit_code == 0
        assert "cancelled" in result.output.lower()

        # Original directory remains untouched
        orig_dir = Path(project_with_history["project_dir"])
        assert orig_dir.is_dir()
        archived_dir = orig_dir.parent / f"{orig_dir.name}_archived"
        assert not archived_dir.exists()

        # Status unchanged
        info_path = orig_dir / "00_project_info.json"
        data = json.loads(info_path.read_text(encoding="utf-8"))
        assert data["status"] == "completed"

    def test_rollback_no_history(self, project_without_history: dict[str, Any]) -> None:
        """Project never ran a pipeline — error + exit 1."""
        result = runner.invoke(
            app,
            [
                "rollback",
                project_without_history["project_id"],
                "--base-dir",
                project_without_history["base_dir"],
            ],
            input="y\n",
        )
        assert result.exit_code == 1
        assert "no pipeline history" in result.output.lower()

    def test_rollback_already_archived(self, archived_project: dict[str, Any]) -> None:
        """Project dir already ends with _archived — graceful error."""
        result = runner.invoke(
            app,
            [
                "rollback",
                archived_project["project_id"],
                "--base-dir",
                archived_project["base_dir"],
            ],
            input="y\n",
        )
        assert result.exit_code == 1
        assert "already archived" in result.output.lower()

    def test_rollback_not_found(self, tmp_path: Path) -> None:
        """Nonexistent project ID — error + exit 1."""
        result = runner.invoke(
            app,
            ["rollback", "nonexistent", "--base-dir", str(tmp_path)],
            input="y\n",
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_rollback_json_output(self, project_with_history: dict[str, Any]) -> None:
        """--json flag produces parseable JSON output on success.

        NOTE: ``typer.confirm`` writes its prompt to stdout, so the
        first line(s) of output may be the prompt text.  We extract
        the last JSON line from the output.
        """
        result = runner.invoke(
            app,
            [
                "--json",
                "rollback",
                project_with_history["project_id"],
                "--base-dir",
                project_with_history["base_dir"],
            ],
            input="y\n",
        )
        assert result.exit_code == 0, f"JSON output: {result.output}"
        # Extract the JSON block (multi-line) after the confirm prompt
        lines = result.output.strip().splitlines()
        # Find first line that starts with "{"
        json_start = next((i for i, ln in enumerate(lines) if ln.strip().startswith("{")), None)
        if json_start is None:
            pytest.fail(f"No JSON object found in output:\n{result.output}")
        json_text = "\n".join(lines[json_start:])
        data = json.loads(json_text)
        assert data["status"] == "ok"
        assert data["project_id"] == project_with_history["project_id"]
        assert "archive_dir" in data
