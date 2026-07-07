"""Tests for the AutoMedia CLI layer — all 9 sub-commands.

Covers: run, pool, projects, archive, adapter, cron, init, doctor, and main app.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.pipelines.gate_engine import PipelineResult

runner = CliRunner()


# =========================================================================
# 1. Main app --help
# =========================================================================

class TestMainApp:
    """Tests for the root ``automedia`` command."""

    def test_help_lists_all_subcommands(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ("run", "pool", "projects", "archive", "adapter", "cron", "init", "doctor"):
            assert cmd in result.output

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
        assert "AutoMedia" in result.output


# =========================================================================
# 2. automedia run
# =========================================================================

class TestRunCommand:
    """Tests for ``automedia run``."""

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_run_success(self, mock_runner: MagicMock) -> None:
        mock_runner.return_value = PipelineResult(
            status="success",
            project_id="abc123",
            project_dir="/tmp/proj",
            topic="test",
            brand="test",
            total_duration_s=1.5,
        )
        result = runner.invoke(app, ["run", "--topic", "test", "--brand", "test"])
        assert result.exit_code == 0
        assert "Pipeline finished: success" in result.output
        mock_runner.assert_called_once_with("test", "test", mode="auto", resume_from=None)

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_run_with_mode(self, mock_runner: MagicMock) -> None:
        mock_runner.return_value = PipelineResult(
            status="success", total_duration_s=0.5,
        )
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b", "--mode", "text_only"])
        assert result.exit_code == 0
        mock_runner.assert_called_once_with("t", "b", mode="text_only", resume_from=None)

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_run_with_resume_from(self, mock_runner: MagicMock) -> None:
        mock_runner.return_value = PipelineResult(
            status="success", total_duration_s=0.5,
        )
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b", "--resume-from", "G3"])
        assert result.exit_code == 0
        mock_runner.assert_called_once_with("t", "b", mode="auto", resume_from="G3")

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_run_failure_exits_1(self, mock_runner: MagicMock) -> None:
        mock_runner.return_value = PipelineResult(
            status="failed", topic="t", brand="b", error="boom", total_duration_s=0.1,
        )
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b"])
        assert result.exit_code == 1

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_run_exception_exits_1(self, mock_runner: MagicMock) -> None:
        mock_runner.side_effect = RuntimeError("kaboom")
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b"])
        assert result.exit_code == 1
        assert "Pipeline failed" in result.output

    def test_run_missing_required_args(self) -> None:
        result = runner.invoke(app, ["run"])
        assert result.exit_code != 0


# =========================================================================
# 3. automedia pool
# =========================================================================

class TestPoolCommand:
    """Tests for ``automedia pool``."""

    def test_pool_list_empty(self, tmp_pool_db: Path) -> None:
        result = runner.invoke(app, ["pool", "list", "--db", str(tmp_pool_db)])
        assert result.exit_code == 0
        assert "No topics found" in result.output

    def test_pool_add_and_list(self, tmp_pool_db: Path) -> None:
        # Add
        result = runner.invoke(app, [
            "pool", "add", "--topic", "Test Topic", "--url", "https://x.com",
            "--source", "weibo", "--db", str(tmp_pool_db),
        ])
        assert result.exit_code == 0
        assert "Topic added" in result.output

        # List
        result = runner.invoke(app, ["pool", "list", "--db", str(tmp_pool_db)])
        assert result.exit_code == 0
        assert "Test Topic" in result.output

    def test_pool_list_by_status(self, tmp_pool_db: Path) -> None:
        runner.invoke(app, ["pool", "add", "--topic", "A", "--db", str(tmp_pool_db)])
        result = runner.invoke(app, ["pool", "list", "--status", "pending", "--db", str(tmp_pool_db)])
        assert result.exit_code == 0
        assert "A" in result.output

    def test_pool_prune(self, tmp_pool_db: Path) -> None:
        runner.invoke(app, ["pool", "add", "--topic", "Old", "--db", str(tmp_pool_db)])
        result = runner.invoke(app, ["pool", "prune", "--days", "0", "--db", str(tmp_pool_db)])
        assert result.exit_code == 0
        assert "Pruned" in result.output


# =========================================================================
# 4. automedia projects
# =========================================================================

class TestProjectsCommand:
    """Tests for ``automedia projects``."""

    def test_projects_list_empty(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["projects", "list", "--base-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "No projects found" in result.output

    def test_projects_list_finds_project(self, tmp_project: dict[str, Any]) -> None:
        result = runner.invoke(app, ["projects", "list", "--base-dir", tmp_project["base_dir"]])
        assert result.exit_code == 0
        assert tmp_project["project_id"] in result.output

    def test_projects_get(self, tmp_project: dict[str, Any]) -> None:
        result = runner.invoke(app, ["projects", "get", tmp_project["project_id"], "--base-dir", tmp_project["base_dir"]])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["project_id"] == tmp_project["project_id"]

    def test_projects_get_not_found(self, tmp_project: dict[str, Any]) -> None:
        result = runner.invoke(app, ["projects", "get", "nonexistent", "--base-dir", tmp_project["base_dir"]])
        assert result.exit_code == 1
        assert "not found" in result.output


# =========================================================================
# 5. automedia archive
# =========================================================================

class TestArchiveCommand:
    """Tests for ``automedia archive`` — Red Line 8 enforcement."""

    def test_archive_refuses_without_force(self, tmp_project: dict[str, Any]) -> None:
        """Red Line 8: non-published project must be rejected without --force."""
        result = runner.invoke(app, ["archive", tmp_project["project_id"], "--base-dir", tmp_project["base_dir"]])
        assert result.exit_code == 1
        assert "Refused" in result.output or "force" in result.output.lower()

    def test_archive_force_works(self, tmp_project: dict[str, Any]) -> None:
        result = runner.invoke(app, ["archive", tmp_project["project_id"], "--force", "--base-dir", tmp_project["base_dir"]])
        assert result.exit_code == 0
        assert "Archived" in result.output

    def test_archive_not_found(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["archive", "nonexistent", "--base-dir", str(tmp_path)])
        assert result.exit_code == 1
        assert "not found" in result.output


# =========================================================================
# 6. automedia adapter
# =========================================================================

class TestAdapterCommand:
    """Tests for ``automedia adapter``."""

    def test_adapter_list(self) -> None:
        result = runner.invoke(app, ["adapter", "list"])
        assert result.exit_code == 0

    def test_adapter_create(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "adapters"
        result = runner.invoke(app, ["adapter", "create", "--name", "youtube", "--output-dir", str(out_dir)])
        assert result.exit_code == 0
        assert "Adapter created" in result.output
        assert (out_dir / "youtube_adapter.py").is_file()

    def test_adapter_create_duplicate(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "adapters"
        runner.invoke(app, ["adapter", "create", "--name", "tiktok", "--output-dir", str(out_dir)])
        result = runner.invoke(app, ["adapter", "create", "--name", "tiktok", "--output-dir", str(out_dir)])
        assert result.exit_code == 1


# =========================================================================
# 7. automedia cron
# =========================================================================

class TestCronCommand:
    """Tests for ``automedia cron``."""

    def test_cron_run_known_job(self) -> None:
        result = runner.invoke(app, ["cron", "run", "pool-collect"])
        assert result.exit_code == 0
        assert "completed" in result.output

    def test_cron_run_unknown_job(self) -> None:
        result = runner.invoke(app, ["cron", "run", "nonexistent-job"])
        assert result.exit_code == 1
        assert "Unknown job" in result.output

    def test_cron_check_health(self) -> None:
        result = runner.invoke(app, ["cron", "check-health"])
        # May pass or fail depending on environment, but should not crash
        assert "Health Check" in result.output


# =========================================================================
# 8. automedia init
# =========================================================================

class TestInitCommand:
    """Tests for ``automedia init``."""

    def test_init_template_minimal(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init", "--template", "minimal"])
        assert result.exit_code == 0
        config = tmp_path / ".automedia" / "config.yaml"
        assert config.is_file()
        content = config.read_text()
        assert "openai" in content

    def test_init_unknown_template(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init", "--template", "bogus"])
        assert result.exit_code == 1
        assert "Unknown template" in result.output


# =========================================================================
# 9. automedia doctor
# =========================================================================

class TestDoctorCommand:
    """Tests for ``automedia doctor``."""

    def test_doctor_runs(self) -> None:
        result = runner.invoke(app, ["doctor"])
        assert "Dependency Check" in result.output
        # Exit code depends on installed tools; just check it doesn't crash
        assert result.exit_code in (0, 1)

    def test_doctor_shows_python(self) -> None:
        result = runner.invoke(app, ["doctor"])
        assert "python" in result.output.lower()
