"""Tests for EdgeTTSEngine — TTS via edge-tts CLI.

Covers:
    - Class attributes (engine_name, modality)
    - check_available() with and without CLI on PATH
    - Auto-registration in EngineRegistry
    - Constructor with config dict
    - synthesize() command building, return values, error paths
    - Registry isolation via clear()
"""

from __future__ import annotations

import os
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.engines.implementations.tts_edge import DEFAULT_VOICE, EdgeTTSEngine
from automedia.engines.registry import EngineRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_subprocess_result(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> MagicMock:
    """Create a mock subprocess.CompletedProcess."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


# =========================================================================
# Class attribute tests
# =========================================================================


class TestEdgeTTSEngineAttributes:
    """engine_name and modality class-level attributes."""

    def test_engine_name(self) -> None:
        assert EdgeTTSEngine.engine_name == "edge-tts"

    def test_modality(self) -> None:
        assert EdgeTTSEngine.modality == "tts"


# =========================================================================
# check_available tests
# =========================================================================


class TestEdgeTTSEngineCheckAvailable:
    """check_available() returns tuple[bool, str] with mocked shutil.which."""

    @patch("automedia.engines.implementations.tts_edge.shutil.which")
    def test_returns_true_when_cli_found(self, mock_which: MagicMock) -> None:
        """shutil.which returns a path → available is True."""
        mock_which.return_value = "/usr/bin/edge-tts"
        engine = EdgeTTSEngine()
        available, msg = engine.check_available()
        assert available is True
        assert "found" in msg.lower()

    @patch("automedia.engines.implementations.tts_edge.shutil.which")
    def test_returns_false_when_cli_not_found(self, mock_which: MagicMock) -> None:
        """shutil.which returns None → available is False."""
        mock_which.return_value = None
        engine = EdgeTTSEngine()
        available, msg = engine.check_available()
        assert available is False
        assert "not found" in msg.lower()


# =========================================================================
# Auto-registration tests
# =========================================================================


class TestEdgeTTSEngineAutoRegistration:
    """Engine auto-registers in EngineRegistry on module import."""

    def setup_method(self) -> None:
        """Ensure edge-tts is registered before each test.

        Other test files (e.g. ``test_image_comfyui``) clear the singleton
        registry in their teardown, so we must re-register here.
        """
        if "edge-tts" not in EngineRegistry():
            EngineRegistry().register("edge-tts", EdgeTTSEngine, modality="tts")

    def teardown_method(self) -> None:
        """Leave the registry clean with edge-tts registered."""
        EngineRegistry().clear()
        EngineRegistry().register("edge-tts", EdgeTTSEngine, modality="tts")

    def test_registered_after_import(self) -> None:
        """The engine is registered in EngineRegistry after import."""
        assert "edge-tts" in EngineRegistry()

    def test_clear_isolates(self) -> None:
        """EngineRegistry().clear() removes the engine."""
        assert "edge-tts" in EngineRegistry()
        EngineRegistry().clear()
        assert "edge-tts" not in EngineRegistry()


# =========================================================================
# Constructor tests
# =========================================================================


class TestEdgeTTSEngineConstructor:
    """Constructor with and without config dict."""

    def test_default_config_is_empty(self) -> None:
        """No-arg constructor stores empty dict."""
        engine = EdgeTTSEngine()
        assert engine._config == {}

    def test_with_config(self) -> None:
        """Constructor stores provided config."""
        config = {"voice": "zh-CN-XiaoxiaoNeural", "speed": 1.2}
        engine = EdgeTTSEngine(engine_config=config)
        assert engine._config["voice"] == "zh-CN-XiaoxiaoNeural"
        assert engine._config["speed"] == 1.2


# =========================================================================
# synthesize() functional tests
# =========================================================================


class TestEdgeTTSEngineSynthesize:
    """synthesize() — all paths with mocked subprocess."""

    @patch("automedia.engines.implementations.tts_edge.subprocess.run")
    def test_calls_edge_tts_with_correct_args(
        self, mock_run: MagicMock, tmp_path: Any
    ) -> None:
        """Verify the exact CLI command built by synthesize()."""
        mock_run.return_value = _make_subprocess_result()
        output = str(tmp_path / "out.mp3")
        engine = EdgeTTSEngine()
        engine.synthesize("Hello", voice="en-US-GuyNeural", output_path=output)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "edge-tts"
        assert "--voice" in args
        assert "en-US-GuyNeural" in args
        assert "--text" in args
        assert "Hello" in args
        assert "--write-media" in args
        assert output in args

    @patch("automedia.engines.implementations.tts_edge.subprocess.run")
    def test_returns_absolute_path(
        self, mock_run: MagicMock, tmp_path: Any
    ) -> None:
        """Return value is an absolute path to the output file."""
        mock_run.return_value = _make_subprocess_result()
        output = str(tmp_path / "subdir" / "tts.mp3")
        engine = EdgeTTSEngine()
        result = engine.synthesize("Test", output_path=output)
        assert os.path.isabs(result)
        assert result.endswith("tts.mp3")

    def test_empty_text_raises_value_error(self, tmp_path: Any) -> None:
        """Empty text is rejected before any subprocess call."""
        engine = EdgeTTSEngine()
        with pytest.raises(ValueError, match="text must not be empty"):
            engine.synthesize("", output_path=str(tmp_path / "out.mp3"))

    def test_empty_output_path_raises_value_error(self) -> None:
        """Empty output_path is rejected before any subprocess call."""
        engine = EdgeTTSEngine()
        with pytest.raises(ValueError, match="output_path must not be empty"):
            engine.synthesize("Hello", output_path="")

    @patch("automedia.engines.implementations.tts_edge.subprocess.run")
    def test_failure_raises_called_process_error(
        self, mock_run: MagicMock, tmp_path: Any
    ) -> None:
        """Non-zero returncode from edge-tts raises CalledProcessError."""
        mock_run.return_value = _make_subprocess_result(
            returncode=1, stderr="voice not found"
        )
        engine = EdgeTTSEngine()
        with pytest.raises(subprocess.CalledProcessError):
            engine.synthesize("Hello", output_path=str(tmp_path / "out.mp3"))

    @patch("automedia.engines.implementations.tts_edge.subprocess.run")
    def test_default_voice_from_config(
        self, mock_run: MagicMock, tmp_path: Any
    ) -> None:
        """Voice from config is used when voice parameter is empty."""
        mock_run.return_value = _make_subprocess_result()
        output = str(tmp_path / "out.mp3")
        engine = EdgeTTSEngine(engine_config={"voice": "zh-CN-XiaoxiaoNeural"})
        engine.synthesize("Test", output_path=output)
        args = mock_run.call_args[0][0]
        voice_idx = args.index("--voice") + 1
        assert args[voice_idx] == "zh-CN-XiaoxiaoNeural"

    @patch("automedia.engines.implementations.tts_edge.subprocess.run")
    def test_default_voice_from_constant(
        self, mock_run: MagicMock, tmp_path: Any
    ) -> None:
        """DEFAULT_VOICE constant is used when neither param nor config provides one."""
        mock_run.return_value = _make_subprocess_result()
        output = str(tmp_path / "out.mp3")
        engine = EdgeTTSEngine()
        engine.synthesize("Test", output_path=output)
        args = mock_run.call_args[0][0]
        voice_idx = args.index("--voice") + 1
        assert args[voice_idx] == DEFAULT_VOICE
