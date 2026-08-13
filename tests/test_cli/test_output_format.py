"""Tests for :mod:`automedia.cli.output_format` — user-friendly error formatting."""

from __future__ import annotations

import re
from unittest.mock import patch

from typer.testing import CliRunner

from automedia.cli.output_format import (
    _failing_gate,
    output_formatted_error,
    output_pipeline_error,
)
from automedia.pipelines.gate_engine import GateLogEntry

runner = CliRunner()


# =========================================================================
# _failing_gate
# =========================================================================


class TestFailingGate:
    """Tests for the internal ``_failing_gate`` helper."""

    def test_finds_gate_from_log(self) -> None:
        log = [
            GateLogEntry("pre-gate", "passed", 0.5),
            GateLogEntry("G0", "failed", 1.2, error="Brand CTA mismatch"),
        ]
        assert _failing_gate("Brand CTA mismatch", log) == "G0"

    def test_finds_first_failed_gate(self) -> None:
        log = [
            GateLogEntry("pre-gate", "passed", 0.5),
            GateLogEntry("CW", "failed", 2.0, error="Content too short"),
            GateLogEntry("G0", "failed", 1.0, error="Fact check failed"),
        ]
        assert _failing_gate("Content too short", log) == "CW"

    def test_fallback_to_error_string(self) -> None:
        assert _failing_gate("G3 brand CTA mismatch", None) == "G3"

    def test_fallback_to_G_prefix(self) -> None:
        assert _failing_gate("V5 subtitle sync error", None) == "V5"

    def test_returns_none_for_unmatched(self) -> None:
        assert _failing_gate("random system error", None) is None

    def test_returns_none_for_empty_error(self) -> None:
        assert _failing_gate("", None) is None

    def test_recognizes_H0_from_log(self) -> None:
        """H0 gate (human review) is found from gate log entries."""
        log = [
            GateLogEntry("pre-gate", "passed", 0.5),
            GateLogEntry("H0", "failed", 2.0, error="Human review rejected"),
        ]
        assert _failing_gate("Human review rejected", log) == "H0"

    def test_recognizes_H0_from_error_string(self) -> None:
        """H0 is found via fallback prefix matching in error string."""
        assert _failing_gate("H0 human review rejected", None) == "H0"


class TestGatePrefixCoverage:
    """Comprehensive coverage: every gate name used by the runner has a prefix."""

    def test_all_runner_gates_have_prefixes(self) -> None:
        """All gate names across every pipeline mode are in _GATE_PREFIXES."""
        from automedia.cli.output_format import _GATE_PREFIXES
        from automedia.pipelines.runner import _MODE_MAP

        all_runner_gates: set[str] = {
            name for names in _MODE_MAP.values() for name in names
        }
        missing = all_runner_gates - set(_GATE_PREFIXES)
        assert not missing, (
            f"Gate name(s) present in runner but missing from "
            f"_GATE_PREFIXES: {sorted(missing)}"
        )


# =========================================================================
# output_formatted_error (via CliRunner stderr capture)
# =========================================================================


class TestOutputFormattedError:
    """Tests for ``output_formatted_error`` via typer test app."""

    def test_known_gate_error_shows_gate_name(self) -> None:
        """When a gate name is detected, it appears in the bold part."""
        log = [GateLogEntry("G0", "failed", 1.0, error="Brand CTA mismatch")]

        with patch("automedia.cli.output_format.typer.secho") as mock_secho:
            output_formatted_error(
                "Pipeline stopped",
                error="Brand CTA mismatch",
                gates_log=log,
            )
            # Should have called typer.secho at least once with the gate name
            calls = [c for c in mock_secho.call_args_list if "G0" in str(c)]
            assert calls, "Expected gate name 'G0' in secho output"

    def test_H0_gate_error_shows_gate_name(self) -> None:
        """H0 gate failure correctly shows H0 in error output."""
        log = [GateLogEntry("H0", "failed", 1.5, error="Human review rejected")]

        with patch("automedia.cli.output_format.typer.secho") as mock_secho:
            output_formatted_error(
                "Pipeline stopped",
                error="Human review rejected",
                gates_log=log,
            )
            calls = [c for c in mock_secho.call_args_list if "H0" in str(c)]
            assert calls, "Expected gate name 'H0' in secho output"

    def test_unknown_error_shows_verbose_hint(self) -> None:
        """Unknown errors suggest --verbose."""
        with patch("automedia.cli.output_format.typer.secho") as mock_secho:
            output_formatted_error(
                "Pipeline stopped",
                error="Something broke",
            )
            all_text = " ".join(str(c) for c in mock_secho.call_args_list)
            assert "--verbose" in all_text

    def test_known_gate_shows_suggested_fix(self) -> None:
        """When a known gate has FAILURE_MODES entries, 'Suggested fix:' is shown."""
        from automedia.gates.failure_modes import FAILURE_MODES

        gate = "G0"
        fixes = FAILURE_MODES[gate]["fixes"]
        log = [GateLogEntry(gate, "failed", 1.0, error="Brand CTA mismatch")]

        with patch("automedia.cli.output_format.typer.secho") as mock_secho:
            output_formatted_error(
                "Pipeline stopped",
                error="Brand CTA mismatch",
                gates_log=log,
            )
            all_text = " ".join(str(c) for c in mock_secho.call_args_list)
            assert "Suggested fix:" in all_text
            assert fixes[0] in all_text

    def test_unknown_gate_no_suggested_fix(self) -> None:
        """When no gate is identified, 'Suggested fix:' is NOT shown."""
        with patch("automedia.cli.output_format.typer.secho") as mock_secho:
            output_formatted_error(
                "Pipeline stopped",
                error="Something broke",
            )
            all_text = " ".join(str(c) for c in mock_secho.call_args_list)
            assert "Suggested fix:" not in all_text

    def test_verbose_prints_traceback(self) -> None:
        """When verbose=True, traceback.print_exception is called."""
        with patch("automedia.cli.output_format.traceback.print_exception") as mock_tb:
            try:
                raise ValueError("test error")
            except ValueError as exc:
                output_formatted_error(
                    "Pipeline stopped",
                    error="test error",
                    verbose=True,
                    exc_info=exc,
                )
            mock_tb.assert_called_once()


# =========================================================================
# output_pipeline_error
# =========================================================================


class TestOutputPipelineError:
    """Tests for ``output_pipeline_error``."""

    def test_known_gate_shows_resume_hint(self) -> None:
        """When a gate name is detected, the output includes --resume-from."""
        log = [GateLogEntry("V0", "failed", 0.5, error="Lint errors")]

        with patch("automedia.cli.output_format.typer.secho") as mock_secho:
            output_pipeline_error(
                "Lint errors",
                gates_log=log,
            )
            all_text = " ".join(str(c) for c in mock_secho.call_args_list)
            assert "--resume-from V0" in all_text

    def test_unknown_error_fallback(self) -> None:
        """When no gate is matched, the error is printed directly."""
        with patch("automedia.cli.output_format.typer.secho") as mock_secho:
            output_pipeline_error(
                "Something unexpected happened",
            )
            all_text = " ".join(str(c) for c in mock_secho.call_args_list)
            assert "Something unexpected happened" in all_text

    def test_pipeline_known_gate_shows_suggested_fix(self) -> None:
        """output_pipeline_error shows 'Suggested fix:' for known gates."""
        from automedia.gates.failure_modes import FAILURE_MODES

        gate = "CW"
        fixes = FAILURE_MODES[gate]["fixes"]
        log = [GateLogEntry(gate, "failed", 2.0, error="LLM returned empty")]

        with patch("automedia.cli.output_format.typer.secho") as mock_secho:
            output_pipeline_error(
                "LLM returned empty",
                gates_log=log,
            )
            all_text = " ".join(str(c) for c in mock_secho.call_args_list)
            assert "Suggested fix:" in all_text
            assert fixes[0] in all_text

    def test_pipeline_unknown_gate_no_suggested_fix(self) -> None:
        """output_pipeline_error does NOT show 'Suggested fix:' for unknown gates."""
        with patch("automedia.cli.output_format.typer.secho") as mock_secho:
            output_pipeline_error(
                "Something unexpected happened",
            )
            all_text = " ".join(str(c) for c in mock_secho.call_args_list)
            assert "Suggested fix:" not in all_text

    def test_verbose_message(self) -> None:
        """verbose=True prints an additional note."""
        with patch("automedia.cli.output_format.typer.secho") as mock_secho:
            output_pipeline_error(
                "Lint errors",
                gates_log=[GateLogEntry("V0", "failed", 0.5, error="Lint errors")],
                verbose=True,
            )
            extra_call = [c for c in mock_secho.call_args_list if "traceback" in str(c).lower()]
            assert extra_call, "Expected a 'no traceback' note when verbose=True"


# =========================================================================
# CLI integration — automedia run --verbose
# =========================================================================


class TestRunVerboseFlag:
    """Integration: the ``--verbose`` flag on ``automedia run``."""

    def test_run_verbose_flag_accepted(self) -> None:
        """--verbose is a valid flag and doesn't break --help."""
        from automedia.cli.app import app

        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        # Strip ANSI escape codes — CI may render help with rich/color formatting
        clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", result.output)
        assert "--verbose" in clean

    def test_run_verbose_with_exception(self, tmp_path) -> None:
        """When pipeline raises and --verbose is set, hint is shown."""
        from unittest.mock import patch

        import automedia.cli.commands.run as run_mod
        from automedia.cli.app import app

        # Monkey-patch _MODEL_CONFIG_PATH to a temp file so the check passes
        cfg = tmp_path / "model_config.yaml"
        cfg.write_text("dummy")
        with patch.object(run_mod, "_MODEL_CONFIG_PATH", cfg):
            with patch.object(run_mod, "run_full_pipeline") as mock_runner:
                mock_runner.side_effect = RuntimeError("kaboom")
                result = runner.invoke(
                    app,
                    ["run", "--topic", "t", "--brand", "b", "--verbose"],
                )
        assert result.exit_code == 1
        # The error message should mention "kaboom" as part of the friendly message
        assert "kaboom" in result.output
        # It should NOT say "Pipeline failed:" (the old format)
        assert "Pipeline failed:" not in result.output

    def test_run_verbose_shows_traceback(self, tmp_path) -> None:
        """--verbose prints traceback info in the output (traceback hint)."""
        from unittest.mock import patch

        import automedia.cli.commands.run as run_mod
        from automedia.cli.app import app

        cfg = tmp_path / "model_config.yaml"
        cfg.write_text("dummy")
        with patch.object(run_mod, "_MODEL_CONFIG_PATH", cfg):
            with patch.object(run_mod, "run_full_pipeline") as mock_runner:
                mock_runner.side_effect = RuntimeError("kaboom")
                result = runner.invoke(
                    app,
                    ["run", "--topic", "t", "--brand", "b", "--verbose"],
                )
        assert result.exit_code == 1
        # The "verbose traceback" marker should be in stderr
        assert "verbose traceback" in result.output
