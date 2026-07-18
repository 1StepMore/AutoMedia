"""Tests for WhisperASREngine — ASR via whisper CLI.

Covers:
    - Class attributes (engine_name, modality)
    - check_available() with and without CLI on PATH
    - Auto-registration in EngineRegistry
    - Constructor with config dict
    - transcribe() command building, JSON parsing, fallback paths, error paths
    - Registry isolation via clear()
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.engines.implementations.asr_whisper import WhisperASREngine
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


def _write_fake_whisper_json(json_path: str, segments: list[dict[str, Any]] | None = None) -> None:
    """Write a fake Whisper JSON output file."""
    if segments is None:
        segments = [
            {"start": 0.0, "end": 2.5, "text": " Hello world"},
            {"start": 3.0, "end": 5.0, "text": " This is a test"},
        ]
    data = {
        "text": " ".join(s["text"].strip() for s in segments),
        "segments": segments,
    }
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)


def _create_fake_audio(audio_path: str) -> None:
    """Create a minimal fake audio file so os.path.isfile passes."""
    os.makedirs(os.path.dirname(audio_path), exist_ok=True)
    with open(audio_path, "wb") as fh:
        fh.write(b"fake audio data")


# =========================================================================
# Class attribute tests
# =========================================================================


class TestWhisperASREngineAttributes:
    """engine_name and modality class-level attributes."""

    def test_engine_name(self) -> None:
        assert WhisperASREngine.engine_name == "whisper"

    def test_modality(self) -> None:
        assert WhisperASREngine.modality == "asr"


# =========================================================================
# check_available tests
# =========================================================================


class TestWhisperASREngineCheckAvailable:
    """check_available() returns tuple[bool, str] with mocked shutil.which."""

    @patch("automedia.engines.implementations.asr_whisper.shutil.which")
    def test_returns_true_when_cli_found(self, mock_which: MagicMock) -> None:
        """shutil.which returns a path → available is True."""
        mock_which.return_value = "/usr/bin/whisper"
        engine = WhisperASREngine()
        available, msg = engine.check_available()
        assert available is True
        assert "found" in msg.lower()

    @patch("automedia.engines.implementations.asr_whisper.shutil.which")
    def test_returns_false_when_cli_not_found(self, mock_which: MagicMock) -> None:
        """shutil.which returns None → available is False."""
        mock_which.return_value = None
        engine = WhisperASREngine()
        available, msg = engine.check_available()
        assert available is False
        assert "not found" in msg.lower()


# =========================================================================
# Auto-registration tests
# =========================================================================


class TestWhisperASREngineAutoRegistration:
    """Engine auto-registers in EngineRegistry on module import."""

    def setup_method(self) -> None:
        """Ensure whisper is registered before each test.

        Other test files (e.g. ``test_image_comfyui``) clear the singleton
        registry in their teardown, so we must re-register here.
        """
        if "whisper" not in EngineRegistry():
            EngineRegistry().register("whisper", WhisperASREngine, modality="asr")

    def teardown_method(self) -> None:
        """Leave the registry clean with whisper registered."""
        EngineRegistry().clear()
        EngineRegistry().register("whisper", WhisperASREngine, modality="asr")

    def test_registered_after_import(self) -> None:
        """The engine is registered in EngineRegistry after import."""
        assert "whisper" in EngineRegistry()

    def test_clear_isolates(self) -> None:
        """EngineRegistry().clear() removes the engine."""
        assert "whisper" in EngineRegistry()
        EngineRegistry().clear()
        assert "whisper" not in EngineRegistry()


# =========================================================================
# Constructor tests
# =========================================================================


class TestWhisperASREngineConstructor:
    """Constructor with and without config dict."""

    def test_default_config_is_empty(self) -> None:
        """No-arg constructor stores empty dict."""
        engine = WhisperASREngine()
        assert engine._config == {}

    def test_with_config(self) -> None:
        """Constructor stores provided config."""
        config = {"model": "base", "language": "en"}
        engine = WhisperASREngine(engine_config=config)
        assert engine._config["model"] == "base"
        assert engine._config["language"] == "en"


# =========================================================================
# transcribe() functional tests
# =========================================================================


class TestWhisperASREngineTranscribe:
    """transcribe() — all paths with mocked subprocess."""

    @patch("automedia.engines.implementations.asr_whisper.subprocess.run")
    def test_calls_whisper_with_correct_args(self, mock_run: MagicMock, tmp_path: Any) -> None:
        """Verify the exact CLI command built by transcribe()."""
        audio_path = str(tmp_path / "test.mp3")
        _create_fake_audio(audio_path)
        json_path = str(tmp_path / "test.json")
        _write_fake_whisper_json(json_path)

        mock_run.return_value = _make_subprocess_result()
        engine = WhisperASREngine()
        result = engine.transcribe(audio_path, language="en")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "whisper"
        assert audio_path in args
        assert "--model" in args
        assert "tiny" in args  # default model
        assert "--language" in args
        assert "en" in args
        assert "--output_format" in args
        assert "json" in args
        assert "--output_dir" in args
        assert str(tmp_path) in args
        assert "text" in result
        assert "segments" in result

    @patch("automedia.engines.implementations.asr_whisper.subprocess.run")
    def test_returns_segments_from_json_file(self, mock_run: MagicMock, tmp_path: Any) -> None:
        """Transcription segments are parsed from the Whisper JSON output file."""
        audio_path = str(tmp_path / "audio.mp3")
        _create_fake_audio(audio_path)

        segments = [
            {"start": 0.0, "end": 3.0, "text": " First segment"},
            {"start": 3.5, "end": 6.0, "text": " Second segment"},
        ]
        json_path = str(tmp_path / "audio.json")
        _write_fake_whisper_json(json_path, segments)

        mock_run.return_value = _make_subprocess_result()
        engine = WhisperASREngine()
        result = engine.transcribe(audio_path)
        assert len(result["segments"]) == 2
        assert result["segments"][0]["text"] == " First segment"
        assert result["segments"][1]["text"] == " Second segment"
        assert result["text"] == "First segment Second segment"

    def test_file_not_found_raises(self) -> None:
        """Non-existent audio path raises FileNotFoundError."""
        engine = WhisperASREngine()
        with pytest.raises(FileNotFoundError, match="audio file not found"):
            engine.transcribe("/nonexistent/audio.mp3")

    @patch("automedia.engines.implementations.asr_whisper.subprocess.run")
    def test_failure_raises_called_process_error(self, mock_run: MagicMock, tmp_path: Any) -> None:
        """Non-zero returncode from whisper raises CalledProcessError."""
        audio_path = str(tmp_path / "test.mp3")
        _create_fake_audio(audio_path)

        mock_run.return_value = _make_subprocess_result(returncode=1, stderr="model error")
        engine = WhisperASREngine()
        with pytest.raises(subprocess.CalledProcessError):
            engine.transcribe(audio_path)

    @patch("automedia.engines.implementations.asr_whisper.subprocess.run")
    def test_default_language_from_config(self, mock_run: MagicMock, tmp_path: Any) -> None:
        """Language from config is used when parameter is None."""
        audio_path = str(tmp_path / "test.mp3")
        _create_fake_audio(audio_path)
        json_path = str(tmp_path / "test.json")
        _write_fake_whisper_json(json_path)

        mock_run.return_value = _make_subprocess_result()
        engine = WhisperASREngine(engine_config={"language": "ja"})
        engine.transcribe(audio_path)
        args = mock_run.call_args[0][0]
        lang_idx = args.index("--language") + 1
        assert args[lang_idx] == "ja"

    @patch("automedia.engines.implementations.asr_whisper.subprocess.run")
    def test_default_language_is_zh(self, mock_run: MagicMock, tmp_path: Any) -> None:
        """Built-in default language is 'zh' when neither param nor config provides one."""
        audio_path = str(tmp_path / "test.mp3")
        _create_fake_audio(audio_path)
        json_path = str(tmp_path / "test.json")
        _write_fake_whisper_json(json_path)

        mock_run.return_value = _make_subprocess_result()
        engine = WhisperASREngine()
        engine.transcribe(audio_path)
        args = mock_run.call_args[0][0]
        lang_idx = args.index("--language") + 1
        assert args[lang_idx] == "zh"

    @patch("automedia.engines.implementations.asr_whisper.subprocess.run")
    def test_fallback_to_stdout_json(self, mock_run: MagicMock, tmp_path: Any) -> None:
        """When JSON output file is missing, fall back to parsing stdout as JSON."""
        audio_path = str(tmp_path / "test.mp3")
        _create_fake_audio(audio_path)
        # Deliberately do NOT create the JSON file — test the stdout fallback
        stdout_json = json.dumps(
            {
                "text": "fallback text",
                "segments": [{"start": 0.0, "end": 1.0, "text": "fallback"}],
            }
        )
        mock_run.return_value = _make_subprocess_result(stdout=stdout_json)
        engine = WhisperASREngine()
        result = engine.transcribe(audio_path)
        assert result["text"] == "fallback text"
        assert len(result["segments"]) == 1

    @patch("automedia.engines.implementations.asr_whisper.subprocess.run")
    def test_fallback_to_stdout_text(self, mock_run: MagicMock, tmp_path: Any) -> None:
        """When JSON file is missing and stdout is not valid JSON, return raw text."""
        audio_path = str(tmp_path / "test.mp3")
        _create_fake_audio(audio_path)
        # Deliberately do NOT create the JSON file
        raw_text = "plain text transcription without json"
        mock_run.return_value = _make_subprocess_result(stdout=raw_text)
        engine = WhisperASREngine()
        result = engine.transcribe(audio_path)
        assert result["text"] == raw_text
        assert result["segments"] == []

    @patch("automedia.engines.implementations.asr_whisper.subprocess.run")
    def test_default_model_from_config(self, mock_run: MagicMock, tmp_path: Any) -> None:
        """Model from config overrides the default 'tiny'."""
        audio_path = str(tmp_path / "test.mp3")
        _create_fake_audio(audio_path)
        json_path = str(tmp_path / "test.json")
        _write_fake_whisper_json(json_path)

        mock_run.return_value = _make_subprocess_result()
        engine = WhisperASREngine(engine_config={"model": "base"})
        engine.transcribe(audio_path, language="en")
        args = mock_run.call_args[0][0]
        model_idx = args.index("--model") + 1
        assert args[model_idx] == "base"
