"""``automedia run --platform`` resolution — issue #630.

``automedia run`` used to accept no platform at all, so the prompt loader saw
``platform=None``, skipped every ``prompts/platforms/<platform>/`` template and
rendered the generic writer (no length target).  A short-video run then produced
a ~100-character caption the video stages could not stretch to 30s.  These
tests pin the resolution rule and the pass-through to the pipeline.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.cli.commands.run import _resolve_platforms
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


def _result(status: str = "success") -> PipelineResult:
    return PipelineResult(
        status=status,
        project_id="proj123",
        project_dir="projects/proj123",
        topic="t",
        brand="b",
        total_duration_s=0.1,
    )


class TestResolvePlatforms:
    """The resolution rule itself — explicit wins, video modes default."""

    def test_short_video_defaults_to_douyin(self) -> None:
        assert _resolve_platforms(None, "short-video") == ["douyin"]

    def test_video_only_defaults_to_douyin(self) -> None:
        assert _resolve_platforms(None, "video_only") == ["douyin"]

    def test_text_only_keeps_no_platform(self) -> None:
        assert _resolve_platforms(None, "text_only") is None

    def test_explicit_platform_wins_over_the_default(self) -> None:
        assert _resolve_platforms("xiaohongshu", "short-video") == ["xiaohongshu"]

    def test_explicit_platform_applies_to_text_modes(self) -> None:
        assert _resolve_platforms("wechat", "text_only") == ["wechat"]

    def test_comma_separated_values_are_split_and_stripped(self) -> None:
        assert _resolve_platforms(" douyin , xiaohongshu ,", "text_only") == [
            "douyin",
            "xiaohongshu",
        ]

    def test_blank_value_falls_back_to_the_mode_default(self) -> None:
        assert _resolve_platforms("   ", "short-video") == ["douyin"]


class TestRunPassesPlatformsThrough:
    """Both entry paths hand the resolved list to ``run_full_pipeline``."""

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_short_video_without_flag_passes_douyin(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result()
        runner.invoke(app, ["run", "--topic", "t", "--brand", "b", "--mode", "short-video"])
        assert mock_runner.call_args.kwargs["platforms"] == ["douyin"]

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_explicit_flag_is_passed_verbatim(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result()
        runner.invoke(
            app,
            ["run", "--topic", "t", "--brand", "b", "--platform", "xiaohongshu"],
        )
        assert mock_runner.call_args.kwargs["platforms"] == ["xiaohongshu"]

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_text_only_without_flag_passes_none(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result()
        runner.invoke(app, ["run", "--topic", "t", "--brand", "b", "--mode", "text_only"])
        assert mock_runner.call_args.kwargs["platforms"] is None

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_batch_mode_passes_the_same_platforms(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result()
        runner.invoke(
            app,
            ["run", "--topics", "a,b", "--brand", "b", "--mode", "short-video"],
        )
        assert mock_runner.call_count == 2
        assert mock_runner.call_args.kwargs["platforms"] == ["douyin"]
