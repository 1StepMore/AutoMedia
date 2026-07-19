"""Tests for automedia.pipelines.rollback_types — Gap 9 rollback infrastructure types."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest  # noqa: F401  # used for test collection

from automedia.pipelines.rollback_types import (
    ProjectAction,
    RollbackResult,
    is_eligible_for_rollback,
    read_project_status,
    update_project_status,
)

# ===================================================================
# ProjectAction enum
# ===================================================================


class TestProjectAction:
    """Enum values must match the expected set."""

    def test_members(self):
        expected = {"RUN_STARTED", "GATE_PASSED", "GATE_FAILED", "ROLLED_BACK", "PUBLISHED"}
        assert set(ProjectAction.__members__) == expected

    def test_values_are_strings(self):
        for action in ProjectAction:
            assert isinstance(action.value, str)

    def test_run_started_value(self):
        assert ProjectAction.RUN_STARTED.value == "run_started"

    def test_gate_passed_value(self):
        assert ProjectAction.GATE_PASSED.value == "gate_passed"

    def test_gate_failed_value(self):
        assert ProjectAction.GATE_FAILED.value == "gate_failed"

    def test_rolled_back_value(self):
        assert ProjectAction.ROLLED_BACK.value == "rolled_back"

    def test_published_value(self):
        assert ProjectAction.PUBLISHED.value == "published"


# ===================================================================
# RollbackResult dataclass
# ===================================================================


class TestRollbackResult:
    """Dataclass fields and defaults."""

    def test_dataclass_fields(self):
        result = RollbackResult(
            success=True,
            project_id="abc123def456",
            previous_status="published",
            new_status="completed",
        )
        assert result.success is True
        assert result.project_id == "abc123def456"
        assert result.previous_status == "published"
        assert result.new_status == "completed"

    def test_default_success(self):
        result = RollbackResult(project_id="p1")
        assert result.success is True

    def test_default_new_status(self):
        result = RollbackResult(project_id="p1")
        assert result.new_status == ""

    def test_failure_result(self):
        result = RollbackResult(
            success=False,
            project_id="abc123",
            previous_status="running",
            new_status="running",
        )
        assert result.success is False


# ===================================================================
# read / update project status helpers
# ===================================================================


class TestReadProjectStatus:
    """Reading status from project_info.json."""

    def test_reads_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = {"project_id": "p1", "status": "published"}
            info_path = Path(tmp) / "00_project_info.json"
            with open(info_path, "w", encoding="utf-8") as fh:
                json.dump(info, fh)

            assert read_project_status(tmp) == "published"

    def test_returns_empty_when_no_status_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = {"project_id": "p1"}
            info_path = Path(tmp) / "00_project_info.json"
            with open(info_path, "w", encoding="utf-8") as fh:
                json.dump(info, fh)

            assert read_project_status(tmp) == ""

    def test_returns_empty_when_no_info_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert read_project_status(tmp) == ""

    def test_returns_empty_on_corrupt_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            info_path = Path(tmp) / "00_project_info.json"
            with open(info_path, "w", encoding="utf-8") as fh:
                fh.write("not valid json")

            assert read_project_status(tmp) == ""


class TestUpdateProjectStatus:
    """Writing status to project_info.json."""

    def test_updates_existing_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = {"project_id": "p1", "status": "running"}
            info_path = Path(tmp) / "00_project_info.json"
            with open(info_path, "w", encoding="utf-8") as fh:
                json.dump(info, fh)

            result = update_project_status(tmp, "published")
            assert result is True

            with open(info_path, encoding="utf-8") as fh:
                updated = json.load(fh)
            assert updated["status"] == "published"
            assert updated["project_id"] == "p1"

    def test_adds_status_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = {"project_id": "p1"}
            info_path = Path(tmp) / "00_project_info.json"
            with open(info_path, "w", encoding="utf-8") as fh:
                json.dump(info, fh)

            result = update_project_status(tmp, "completed")
            assert result is True

            with open(info_path, encoding="utf-8") as fh:
                updated = json.load(fh)
            assert updated["status"] == "completed"

    def test_returns_false_when_no_info_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = update_project_status(tmp, "published")
            assert result is False

    def test_returns_false_on_corrupt_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            info_path = Path(tmp) / "00_project_info.json"
            with open(info_path, "w", encoding="utf-8") as fh:
                fh.write("not valid json")

            result = update_project_status(tmp, "published")
            assert result is False


# ===================================================================
# is_eligible_for_rollback
# ===================================================================


class TestIsEligibleForRollback:
    """Checks eligibility via .automedia/history.db existence + rows."""

    def test_eligible_when_history_db_has_rows(self):
        """history.db exists and has non-zero size → eligible."""
        with tempfile.TemporaryDirectory() as tmp:
            history_dir = Path(tmp) / ".automedia"
            history_dir.mkdir(parents=True, exist_ok=True)
            db_path = history_dir / "history.db"
            db_path.write_text("some data")  # non-empty file

            assert is_eligible_for_rollback(tmp) is True

    def test_not_eligible_when_history_db_missing(self):
        """No history.db file → not eligible."""
        with tempfile.TemporaryDirectory() as tmp:
            assert is_eligible_for_rollback(tmp) is False

    def test_not_eligible_when_history_db_empty(self):
        """history.db exists but is empty → not eligible (no history rows)."""
        with tempfile.TemporaryDirectory() as tmp:
            history_dir = Path(tmp) / ".automedia"
            history_dir.mkdir(parents=True, exist_ok=True)
            db_path = history_dir / "history.db"
            db_path.write_text("")  # empty file

            assert is_eligible_for_rollback(tmp) is False

    def test_not_eligible_when_dir_does_not_exist(self):
        """Non-existent project directory → not eligible."""
        with tempfile.TemporaryDirectory() as tmp:
            nonexistent = os.path.join(tmp, "does_not_exist")
            assert is_eligible_for_rollback(nonexistent) is False

    def test_eligible_ignores_other_files(self):
        """Only history.db matters — other files in .automedia are ignored."""
        with tempfile.TemporaryDirectory() as tmp:
            history_dir = Path(tmp) / ".automedia"
            history_dir.mkdir(parents=True, exist_ok=True)
            (history_dir / "pool.db").write_text("other data")
            db_path = history_dir / "history.db"
            db_path.write_text("some data")

            assert is_eligible_for_rollback(tmp) is True

    def test_not_eligible_when_history_dir_missing(self):
        """Entire .automedia/ directory missing → not eligible."""
        with tempfile.TemporaryDirectory() as tmp:
            assert is_eligible_for_rollback(tmp) is False
