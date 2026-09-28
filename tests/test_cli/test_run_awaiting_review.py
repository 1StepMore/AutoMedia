"""Exit-code 3 and the new HITL flags for ``automedia run`` — issue #108.

A run that parks at the H0 human-review gate returns
``status="awaiting_review"``: the gates that ran passed, but a human decision
is still outstanding, so the run is neither success (exit 0) nor failure
(exit 1) — it exits 3.  ``--hitl-block`` forces blocking at H0 even without a
TTY; ``--project-id`` resumes a parked project to consume a decision
delivered by ``automedia hitl approve``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.cli.commands.run import EXIT_AWAITING_REVIEW, _is_failure_status
from automedia.core.project import Project
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


def _result(status: str) -> PipelineResult:
    return PipelineResult(
        status=status,
        project_id="proj123",
        project_dir="projects/proj123",
        topic="t",
        brand="b",
        total_duration_s=0.1,
    )


class TestAwaitingReviewExitCode:
    """A parked run exits 3 — not 0, not 1 — in both output modes."""

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_awaiting_review_exits_three(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("awaiting_review")
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b"])
        assert result.exit_code == 3, result.output
        assert result.exit_code not in (0, 1)

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_awaiting_review_exits_three_in_json_mode(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("awaiting_review")
        result = runner.invoke(app, ["--json", "run", "--topic", "t", "--brand", "b"])
        assert result.exit_code == 3, result.output
        assert result.exit_code not in (0, 1)

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_awaiting_review_text_names_the_next_steps(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        """The text summary points the human at the HITL decision tooling."""
        mock_runner.return_value = _result("awaiting_review")
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b"])
        assert "awaiting" in result.output.lower(), result.output
        assert "hitl approve" in result.output.lower(), result.output
        assert "--project-id" in result.output, result.output


class TestFlagThreading:
    """``--hitl-block`` / ``--project-id`` reach ``run_full_pipeline``."""

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_hitl_block_threads_block_on_hitl_true(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("success")
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b", "--hitl-block"])
        assert result.exit_code == 0, result.output
        assert mock_runner.call_args.kwargs["block_on_hitl"] is True

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_no_flags_leaves_block_on_hitl_none(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        """Without the flag the runner keeps its TTY-based default."""
        mock_runner.return_value = _result("success")
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b"])
        assert result.exit_code == 0, result.output
        assert mock_runner.call_args.kwargs["block_on_hitl"] is None

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_project_id_threads_resume_project_id(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("success")
        result = runner.invoke(
            app, ["run", "--topic", "t", "--brand", "b", "--project-id", "abc123"]
        )
        assert result.exit_code == 0, result.output
        assert mock_runner.call_args.kwargs["resume_project_id"] == "abc123"

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_resume_project_id_defaults_none(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("success")
        result = runner.invoke(app, ["run", "--topic", "t", "--brand", "b"])
        assert result.exit_code == 0, result.output
        assert mock_runner.call_args.kwargs["resume_project_id"] is None


class TestFlagConflictMatrix:
    """``--skip-review`` contradicts any human-consulting flag; blockers combine."""

    def test_skip_review_and_hitl_block_conflict(self, _model_config_present: None) -> None:
        result = runner.invoke(
            app, ["run", "--topic", "t", "--brand", "b", "--skip-review", "--hitl-block"]
        )
        assert result.exit_code == 1, result.output
        assert "--skip-review" in result.output, result.output
        assert "--hitl-block" in result.output, result.output

    def test_skip_review_and_wait_for_review_conflict(self, _model_config_present: None) -> None:
        """Regression guard for the pre-existing mutual exclusion."""
        result = runner.invoke(
            app, ["run", "--topic", "t", "--brand", "b", "--skip-review", "--wait-for-review"]
        )
        assert result.exit_code == 1, result.output
        assert "--skip-review" in result.output, result.output
        assert "--wait-for-review" in result.output, result.output

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_wait_for_review_and_hitl_block_is_allowed(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        """Both force blocking; combining them is not a usage error."""
        mock_runner.return_value = _result("success")
        result = runner.invoke(
            app, ["run", "--topic", "t", "--brand", "b", "--wait-for-review", "--hitl-block"]
        )
        assert result.exit_code != 2, result.output
        assert result.exit_code == 0, result.output


class TestBatchAwaitingAccounting:
    """Batch mode counts ``awaiting_review`` separately and exits 3 when only parked."""

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_batch_with_awaiting_exits_three(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("awaiting_review")
        result = runner.invoke(
            app, ["run", "--topics", "t1", "--brand", "b", "--mode", "text_only"]
        )
        assert result.exit_code == 3, result.output
        assert result.exit_code not in (0, 1)

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_batch_mixed_awaiting_and_failed_exits_one(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        """Failure outranks awaiting: a failed topic still exits 1."""
        mock_runner.side_effect = [_result("awaiting_review"), _result("failed")]
        result = runner.invoke(
            app, ["run", "--topics", "t1,t2", "--brand", "b", "--mode", "text_only"]
        )
        assert result.exit_code == 1, result.output

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_batch_summary_reports_awaiting(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        mock_runner.return_value = _result("awaiting_review")
        result = runner.invoke(
            app, ["run", "--topics", "t1", "--brand", "b", "--mode", "text_only"]
        )
        assert "1 awaiting" in result.output, result.output
        assert "0 failed" in result.output, result.output


class TestAwaitingIsNotFailure:
    """``_is_failure_status`` treats ``awaiting_review`` as its own category."""

    @pytest.mark.parametrize("allow_partial", [False, True])
    def test_awaiting_review_is_not_treated_as_failure(self, allow_partial: bool) -> None:
        assert _is_failure_status("awaiting_review", allow_partial) is False

    def test_failed_still_fails(self) -> None:
        assert _is_failure_status("failed", False) is True


class TestResumeSuppliesIdentity:
    """``--project-id`` must make ``--topic``/``--brand`` optional (#108).

    The parked project already records both, so forcing the operator to retype
    them made the documented park -> approve -> resume recipe fail outright.
    Found by running that recipe against the real CLI, not by a test.
    """

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_topic_still_required_without_project_id(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        result = runner.invoke(app, ["run", "--brand", "b"])
        assert result.exit_code != 0
        assert "topic" in result.output.lower()

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_brand_still_required_without_project_id(
        self, mock_runner: MagicMock, _model_config_present: None
    ) -> None:
        result = runner.invoke(app, ["run", "--topic", "t"])
        assert result.exit_code != 0
        assert "brand" in result.output.lower()

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_resume_reads_topic_and_brand_from_the_project(
        self,
        mock_runner: MagicMock,
        _model_config_present: None,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(tmp_path))
        project = Project.init("stored-topic", "stored-brand", base_dir=str(tmp_path))
        mock_runner.return_value = _result("awaiting_review")

        result = runner.invoke(
            app, ["run", "--project-id", project.project_id, "--resume-from", "H0"]
        )

        assert result.exit_code == EXIT_AWAITING_REVIEW, result.output
        args = mock_runner.call_args.args
        assert args[0] == "stored-topic"
        assert args[1] == "stored-brand"
        assert mock_runner.call_args.kwargs["resume_project_id"] == project.project_id

    @patch("automedia.cli.commands.run.run_full_pipeline")
    def test_explicit_topic_and_brand_still_win(
        self,
        mock_runner: MagicMock,
        _model_config_present: None,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(tmp_path))
        project = Project.init("stored-topic", "stored-brand", base_dir=str(tmp_path))
        mock_runner.return_value = _result("awaiting_review")

        runner.invoke(
            app,
            ["run", "--project-id", project.project_id, "--topic", "override", "--brand", "over"],
        )

        args = mock_runner.call_args.args
        assert args[0] == "override"
        assert args[1] == "over"
