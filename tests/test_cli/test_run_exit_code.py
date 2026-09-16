"""Exit-code contract for ``automedia run`` when a gate blocks the pipeline.

A pipeline that stops at a gate returns ``status="partial"`` (runner.py:1482);
a pipeline-level failure returns ``status="failed"`` (runner.py:1536).  Neither
may exit 0 — an unattended caller has to be able to tell the run was blocked.
``--allow-partial`` restores exit 0 for ``partial`` only; ``failed`` and raised
exceptions stay non-zero.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.pipelines.gate_engine import PipelineResult

runner = CliRunner()


@pytest.fixture()
def _model_config_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Create a dummy model_config.yaml so the pre-flight check passes."""
    import automedia.cli.commands.run as run_mod

    cfg_file = tmp_path / ".automedia" / "model_config.yaml"
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text("test: true\n")
    monkeypatch.setattr(run_mod, "_MODEL_CONFIG_PATH", cfg_file)


def _result(status: Literal["success", "failed", "partial"]) -> PipelineResult:
    return PipelineResult(
        status=status,
        project_id="proj123",
        project_dir="projects/proj123",
        topic="t",
        brand="b",
        total_duration_s=0.1,
    )


class TestSingleTopicExitCode:
    """Single-topic mode (``--topic``) — text and JSON output paths."""

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_partial_text_exits_nonzero(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("partial")
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b"])
        assert result.exit_code == 1, result.output

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_partial_text_exits_zero_with_allow_partial(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("partial")
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b", "--allow-partial"])
        assert result.exit_code == 0, result.output

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_partial_json_exits_nonzero(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("partial")
        result = runner.invoke(app, ["--json", "run", "--topic", "t", "--brand", "b"])
        assert result.exit_code == 1, result.output

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_partial_json_exits_zero_with_allow_partial(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("partial")
        result = runner.invoke(
            app, ["--json", "run", "--topic", "t", "--brand", "b", "--allow-partial"]
        )
        assert result.exit_code == 0, result.output

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_failed_stays_nonzero_with_allow_partial(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("failed")
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b", "--allow-partial"])
        assert result.exit_code == 1, result.output

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_failed_json_stays_nonzero_with_allow_partial(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("failed")
        result = runner.invoke(
            app, ["--json", "run", "--topic", "t", "--brand", "b", "--allow-partial"]
        )
        assert result.exit_code == 1, result.output

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_exception_stays_nonzero_with_allow_partial(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.side_effect = RuntimeError("kaboom")
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b", "--allow-partial"])
        assert result.exit_code == 1, result.output

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_success_stays_zero_with_allow_partial(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("success")
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b", "--allow-partial"])
        assert result.exit_code == 0, result.output


class TestBatchExitCode:
    """Batch mode (``--topics``) already counts any non-success as failed."""

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_batch_partial_exits_nonzero(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("partial")
        result = runner.invoke(
            app, ["run", "--topics", "t1", "--brand", "b", "--mode", "text_only"]
        )
        assert result.exit_code == 1, result.output

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_batch_success_exits_zero(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("success")
        result = runner.invoke(
            app, ["run", "--topics", "t1", "--brand", "b", "--mode", "text_only"]
        )
        assert result.exit_code == 0, result.output
