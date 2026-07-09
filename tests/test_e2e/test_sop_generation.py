"""E2E tests for SOP document generation via CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest
import typer
from typer.testing import CliRunner

from automedia.cli.app import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_output(tmp_path: Path) -> Generator[Path, None, None]:
    """Yield a temporary output directory, cleaned up after the test."""
    yield tmp_path


# ---------------------------------------------------------------------------
# sop generate — handbook
# ---------------------------------------------------------------------------


class TestHandbookGeneration:
    def test_handbook_generated_via_cli(self, tmp_output: Path) -> None:
        result = runner.invoke(
            app,
            ["sop", "generate", "--brand", "E2EBrand", "--output", str(tmp_output)],
        )
        assert result.exit_code == 0
        handbook = tmp_output / "execution_handbook.md"
        assert handbook.is_file()
        content = handbook.read_text(encoding="utf-8")
        assert "E2EBrand" in content
        assert "A/B Testing" in content

    def test_handbook_uses_default_output_dir(self) -> None:
        """When --output is omitted, files go to ~/.automedia/sop/<brand>/."""
        result = runner.invoke(
            app,
            ["sop", "generate", "--brand", "TempBrand"],
        )
        assert result.exit_code == 0
        expected = Path.home() / ".automedia" / "sop" / "TempBrand" / "execution_handbook.md"
        assert expected.is_file()
        # Clean up
        expected.unlink(missing_ok=True)

    def test_handbook_stdout_contains_success_message(self, tmp_output: Path) -> None:
        result = runner.invoke(
            app,
            ["sop", "generate", "--brand", "StdoutBrand", "--output", str(tmp_output)],
        )
        assert result.exit_code == 0
        assert "Handbook generated" in result.stdout


# ---------------------------------------------------------------------------
# sop generate-daily — YAML
# ---------------------------------------------------------------------------


class TestDailyTasksGeneration:
    def test_daily_tasks_yaml_is_valid(self, tmp_output: Path) -> None:
        result = runner.invoke(
            app,
            [
                "sop",
                "generate-daily",
                "--brand",
                "YamlBrand",
                "--date",
                "2026-07-10",
                "--output",
                str(tmp_output),
            ],
        )
        assert result.exit_code == 0
        yaml_path = tmp_output / "daily_tasks.yaml"
        assert yaml_path.is_file()

        import yaml

        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert data["date"] == "2026-07-10"
        assert data["brand"] == "YamlBrand"
        assert isinstance(data["tasks"], list)
        assert len(data["tasks"]) > 0

    def test_daily_tasks_without_date(self, tmp_output: Path) -> None:
        """Omitting --date should still produce valid YAML."""
        result = runner.invoke(
            app,
            [
                "sop",
                "generate-daily",
                "--brand",
                "NoDateBrand",
                "--output",
                str(tmp_output),
            ],
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# sop generate-report — progress report
# ---------------------------------------------------------------------------


class TestReportGeneration:
    def test_report_generated_via_cli(self, tmp_output: Path) -> None:
        result = runner.invoke(
            app,
            ["sop", "generate-report", "--brand", "ReportBrand", "--output", str(tmp_output)],
        )
        assert result.exit_code == 0
        report = tmp_output / "progress_report.md"
        assert report.is_file()
        content = report.read_text(encoding="utf-8")
        assert "ReportBrand" in content
        assert "KPI" in content or "kpi" in content.lower()

    def test_report_stdout_success(self, tmp_output: Path) -> None:
        result = runner.invoke(
            app,
            ["sop", "generate-report", "--brand", "ReportBrand2", "--output", str(tmp_output)],
        )
        assert result.exit_code == 0
        assert "Progress report generated" in result.stdout
