"""Tests for ``automedia doctor --fix`` flag (Gap 10)."""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app

# ===================================================================
# Test helpers
# ===================================================================

runner = CliRunner()


def _make_dep(
    name: str,
    installed: bool = False,
    version: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """Create a dependency result dict matching Doctor.check_dependencies()."""
    dep: dict[str, Any] = {
        "name": name,
        "installed": installed,
        "version": version,
        "path": path,
    }
    if name == "chrome":
        dep["headless_ok"] = False
        dep["headless_message"] = None
    return dep


# All deps missing (9 deps as defined in _DEPENDENCIES)
ALL_MISSING: list[dict[str, Any]] = [
    _make_dep("python"),
    _make_dep("bun"),
    _make_dep("ffmpeg"),
    _make_dep("whisper"),
    _make_dep("edge-tts"),
    _make_dep("hyperframes"),
    _make_dep("chrome"),
    _make_dep("comfyui"),
    _make_dep("llm_api"),
]

ALL_INSTALLED: list[dict[str, Any]] = [
    _make_dep("python", True, "Python 3.11.4", "/usr/bin/python3"),
    _make_dep("bun", True, "bun 1.2.3", "/usr/bin/bun"),
    _make_dep("ffmpeg", True, "ffmpeg 7.0", "/usr/bin/ffmpeg"),
    _make_dep("whisper", True, "1.0", "/usr/bin/whisper"),
    _make_dep("edge-tts", True, "1.0", "/usr/bin/edge-tts"),
    _make_dep("hyperframes", True, "1.0", "/usr/bin/hyperframes"),
    _make_dep("chrome", True, None, "/usr/bin/google-chrome"),
    _make_dep("comfyui", True, "ComfyUI reachable", None),
    _make_dep("llm_api", True, "API reachable", None),
]

# Only deps that have NO automated install commands
UNAVAILABLE_ONLY: list[dict[str, Any]] = [
    _make_dep("comfyui"),
    _make_dep("llm_api"),
]

# Mix: some installable, some unavailable
MIXED_MISSING: list[dict[str, Any]] = [
    _make_dep("ffmpeg"),
    _make_dep("comfyui"),
    _make_dep("llm_api"),
]

# ===================================================================
# Mock data for Doctor.get_install_instructions
# ===================================================================

_INSTALLABLE_INSTRUCTIONS: dict[str, str] = {
    "python": "sudo apt install python3.11",
    "bun": "curl -fsSL https://bun.sh/install | bash",
    "ffmpeg": "sudo apt install ffmpeg",
    "whisper": "pip install faster-whisper",
    "edge-tts": "pip install edge-tts",
    "hyperframes": "npm install -g hyperframes",
    "chrome": "sudo apt install google-chrome-stable",
}


def _mock_instructions(name: str) -> str | None:
    """Mock Doctor.get_install_instructions — returns commands for known deps only."""
    return _INSTALLABLE_INSTRUCTIONS.get(name)


# ===================================================================
# Tests
# ===================================================================


class TestDoctorFixDeclined:
    """--fix with user declining the prompt."""

    @patch("automedia.cli.commands.doctor.Doctor.check_dependencies")
    @patch("automedia.cli.commands.doctor.Doctor.get_install_instructions")
    @patch("subprocess.run")
    def test_declined_does_not_install(
        self,
        mock_run: MagicMock,
        mock_instructions: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        """User types 'n' — no installs run, exit code 1 (still missing)."""
        mock_check.return_value = ALL_MISSING
        mock_instructions.side_effect = _mock_instructions

        result = runner.invoke(app, ["doctor", "--fix"], input="n\n")

        assert result.exit_code == 1
        assert "Install missing dependencies?" in result.output
        mock_run.assert_not_called()

    @patch("automedia.cli.commands.doctor.Doctor.check_dependencies")
    @patch("automedia.cli.commands.doctor.Doctor.get_install_instructions")
    @patch("subprocess.run")
    def test_declined_shows_missing(
        self,
        mock_run: MagicMock,
        mock_instructions: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        """User types 'n' — output lists all missing deps."""
        mock_check.return_value = ALL_MISSING
        mock_instructions.side_effect = _mock_instructions

        result = runner.invoke(app, ["doctor", "--fix"], input="n\n")

        assert result.exit_code == 1
        assert "Dependencies to install:" in result.output
        assert "No automated install available:" in result.output
        for dep in ("python", "ffmpeg", "bun", "comfyui", "llm_api"):
            assert dep in result.output


class TestDoctorFixAccepted:
    """--fix with user accepting the prompt."""

    @patch("automedia.cli.commands.doctor.Doctor.check_dependencies")
    @patch("automedia.cli.commands.doctor.Doctor.get_install_instructions")
    @patch("subprocess.run")
    def test_accepted_runs_install_commands(
        self,
        mock_run: MagicMock,
        mock_instructions: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        """User types 'y' — install commands run for each installable dep."""
        # First call = initial check, second call = re-check after install
        mock_check.side_effect = [ALL_MISSING, ALL_INSTALLED]
        mock_instructions.side_effect = _mock_instructions

        result = runner.invoke(app, ["doctor", "--fix"], input="y\n")

        assert result.exit_code == 0
        # subprocess.run should be called for each installable dep (7 total)
        assert mock_run.call_count == 7
        # Verify specific commands were passed
        commands_run = [call[0][0] for call in mock_run.call_args_list]
        assert "sudo apt install ffmpeg" in commands_run
        assert "pip install faster-whisper" in commands_run
        assert "npm install -g hyperframes" in commands_run

    @patch("automedia.cli.commands.doctor.Doctor.check_dependencies")
    @patch("automedia.cli.commands.doctor.Doctor.get_install_instructions")
    @patch("subprocess.run")
    def test_accepted_rechecks_and_shows_ok(
        self,
        mock_run: MagicMock,
        mock_instructions: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        """After install, re-check runs and shows all satisfied."""
        mock_check.side_effect = [ALL_MISSING, ALL_INSTALLED]
        mock_instructions.side_effect = _mock_instructions

        result = runner.invoke(app, ["doctor", "--fix"], input="y\n")

        assert result.exit_code == 0
        assert "Re-checking dependencies" in result.output
        assert "All dependencies satisfied" in result.output
        # subprocess.run called with shell=True
        for call in mock_run.call_args_list:
            assert call.kwargs.get("shell") is True
            assert call.kwargs.get("check") is False

    @patch("automedia.cli.commands.doctor.Doctor.check_dependencies")
    @patch("automedia.cli.commands.doctor.Doctor.get_install_instructions")
    @patch("subprocess.run")
    def test_accepted_still_missing_after_install(
        self,
        mock_run: MagicMock,
        mock_instructions: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        """Some deps remain missing after install — exit code 1."""
        still_missing_after = [
            _make_dep("ffmpeg", True, "7.0", "/usr/bin/ffmpeg"),
            _make_dep("comfyui"),
            _make_dep("llm_api"),
        ]
        mock_check.side_effect = [MIXED_MISSING, still_missing_after]
        # Only ffmpeg has install instructions
        mock_instructions.side_effect = _mock_instructions

        result = runner.invoke(app, ["doctor", "--fix"], input="y\n")

        assert result.exit_code == 1
        assert "Some dependencies are still missing" in result.output
        # Only ffmpeg should have been installed (the other two are unavailable)
        assert mock_run.call_count == 1


class TestDoctorFixUnavailable:
    """--fix when only unavailable deps are missing (comfyui, llm_api)."""

    @patch("automedia.cli.commands.doctor.Doctor.check_dependencies")
    @patch("automedia.cli.commands.doctor.Doctor.get_install_instructions")
    @patch("subprocess.run")
    def test_unavailable_no_prompt(
        self,
        mock_run: MagicMock,
        mock_instructions: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        """When only unavailable deps are missing, no install prompt shown."""
        mock_check.return_value = UNAVAILABLE_ONLY
        mock_instructions.side_effect = _mock_instructions

        # Input is irrelevant since no prompt for installable deps
        result = runner.invoke(app, ["doctor", "--fix"], input="\n")

        assert result.exit_code == 1
        # Should show "No automated install available" for both
        assert "No automated install available:" in result.output
        assert "comfyui" in result.output
        assert "llm_api" in result.output
        # Should NOT show install prompt
        assert "Install missing dependencies?" not in result.output
        mock_run.assert_not_called()


class TestDoctorFixAllOk:
    """--fix when all dependencies are satisfied."""

    @patch("automedia.cli.commands.doctor.Doctor.check_dependencies")
    @patch("subprocess.run")
    def test_all_ok_no_fix_needed(
        self,
        mock_run: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        """When all deps are installed, --fix does nothing."""
        mock_check.return_value = ALL_INSTALLED

        result = runner.invoke(app, ["doctor", "--fix"])

        assert result.exit_code == 0
        assert "All dependencies satisfied" in result.output
        mock_run.assert_not_called()


class TestDoctorFixCurlBash:
    """--fix warning for piped shell scripts (curl | bash)."""

    @patch("automedia.cli.commands.doctor.Doctor.check_dependencies")
    @patch("automedia.cli.commands.doctor.Doctor.get_install_instructions")
    @patch("subprocess.run")
    def test_curl_bash_shows_warning(
        self,
        mock_run: MagicMock,
        mock_instructions: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        """curl | bash install commands display a piped-script warning."""
        bun_only = [
            _make_dep("python"),
            _make_dep("bun"),
        ]
        mock_check.side_effect = [bun_only, ALL_INSTALLED]
        mock_instructions.side_effect = _mock_instructions

        result = runner.invoke(app, ["doctor", "--fix"], input="y\n")

        assert result.exit_code == 0
        # Warning about piped script should be shown
        assert "⚠" in result.output or "piped shell script" in result.output.lower()
        assert "curl" in result.output.lower()

    @patch("automedia.cli.commands.doctor.Doctor.check_dependencies")
    @patch("automedia.cli.commands.doctor.Doctor.get_install_instructions")
    @patch("subprocess.run")
    def test_non_piped_has_no_warning(
        self,
        mock_run: MagicMock,
        mock_instructions: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        """Normal install commands (apt, pip, brew) don't show piped-script warning."""
        ffmpeg_only = [
            _make_dep("ffmpeg"),
        ]
        mock_check.side_effect = [ffmpeg_only, ALL_INSTALLED]
        mock_instructions.side_effect = _mock_instructions

        result = runner.invoke(app, ["doctor", "--fix"], input="y\n")

        assert result.exit_code == 0
        # Warning about piped script should NOT be shown for apt commands
        assert "piped shell script" not in result.output.lower()


class TestDoctorFixJsonMode:
    """--fix in JSON output mode (should be a no-op for fix)."""

    @patch("automedia.cli.commands.doctor.Doctor.check_dependencies")
    @patch("subprocess.run")
    def test_json_mode_ignores_fix(
        self,
        mock_run: MagicMock,
        mock_check: MagicMock,
    ) -> None:
        """In JSON mode, --fix should not trigger install logic (prompts don't work)."""
        mock_check.return_value = ALL_MISSING

        result = runner.invoke(app, ["--json", "doctor", "--fix"])

        import json

        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert "dependencies" in data
        mock_run.assert_not_called()
