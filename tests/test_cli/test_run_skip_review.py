"""``automedia run --skip-review`` wiring.

Proves the CLI forwards the unattended-review opt-in to ``run_full_pipeline``
as ``skip_review=True``.  Without the flag the default (``False``) is
preserved so H0 keeps pausing for human review.
"""

from __future__ import annotations

from pathlib import Path
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


def _result() -> PipelineResult:
    return PipelineResult(
        status="success",
        project_id="proj123",
        project_dir="projects/proj123",
        topic="t",
        brand="b",
        total_duration_s=0.1,
    )


class TestSkipReviewFlag:
    """``--skip-review`` is forwarded; absent flag keeps the default."""

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_skip_review_flag_threads_true(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result()
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b", "--skip-review"])
        assert result.exit_code == 0, result.output
        assert mock_runner.call_args.kwargs["skip_review"] is True

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_skip_review_defaults_false(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result()
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b"])
        assert result.exit_code == 0, result.output
        assert mock_runner.call_args.kwargs["skip_review"] is False

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_skip_review_threads_in_batch_mode(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result()
        result = runner.invoke(
            app,
            ["run", "--topics", "t1", "--brand", "b", "--mode", "text_only", "--skip-review"],
        )
        assert result.exit_code == 0, result.output
        assert mock_runner.call_args.kwargs["skip_review"] is True
