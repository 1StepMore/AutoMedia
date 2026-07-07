"""Tests for audio pipeline — AudioPipeline TTS, ASR, SRT, and proofread."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

from automedia.pipelines.audio_pipeline import (
    AudioPipeline,
    DEFAULT_LANGUAGE,
    DEFAULT_VOICE,
    DEFAULT_WHISPER_MODEL,
    _levenshtein_distance,
    _is_similar,
)


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


def _write_srt(path: str, content: str) -> None:
    """Write SRT content to a file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


# =========================================================================
# AudioPipeline.generate_tts tests
# =========================================================================


class TestGenerateTts:
    """TTS generation via edge-tts subprocess."""

    @patch("automedia.pipelines.audio_pipeline.subprocess.run")
    def test_calls_edge_tts_with_correct_args(self, mock_run: MagicMock, tmp_path: Any) -> None:
        mock_run.return_value = _make_subprocess_result()
        output = str(tmp_path / "out.mp3")
        pipeline = AudioPipeline()
        result = pipeline.generate_tts("Hello", voice="en-US-GuyNeural", output_path=output)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "edge-tts"
        assert "--voice" in args
        assert "en-US-GuyNeural" in args
        assert "--text" in args
        assert "Hello" in args
        assert "--write-media" in args
        assert output in args
        assert os.path.isabs(result)

    @patch("automedia.pipelines.audio_pipeline.subprocess.run")
    def test_returns_absolute_path(self, mock_run: MagicMock, tmp_path: Any) -> None:
        mock_run.return_value = _make_subprocess_result()
        output = str(tmp_path / "subdir" / "tts.mp3")
        pipeline = AudioPipeline()
        result = pipeline.generate_tts("Test", output_path=output)
        assert os.path.isabs(result)
        assert result.endswith("tts.mp3")

    def test_empty_text_raises_value_error(self, tmp_path: Any) -> None:
        pipeline = AudioPipeline()
        with pytest.raises(ValueError, match="text must not be empty"):
            pipeline.generate_tts("", output_path=str(tmp_path / "out.mp3"))

    def test_empty_output_path_raises_value_error(self) -> None:
        pipeline = AudioPipeline()
        with pytest.raises(ValueError, match="output_path must not be empty"):
            pipeline.generate_tts("Hello", output_path="")

    @patch("automedia.pipelines.audio_pipeline.subprocess.run")
    def test_failure_raises_called_process_error(self, mock_run: MagicMock, tmp_path: Any) -> None:
        mock_run.return_value = _make_subprocess_result(returncode=1, stderr="voice not found")
        pipeline = AudioPipeline()
        with pytest.raises(subprocess.CalledProcessError):
            pipeline.generate_tts("Hello", output_path=str(tmp_path / "out.mp3"))

    @patch("automedia.pipelines.audio_pipeline.subprocess.run")
    def test_default_voice_used(self, mock_run: MagicMock, tmp_path: Any) -> None:
        mock_run.return_value = _make_subprocess_result()
        output = str(tmp_path / "out.mp3")
        pipeline = AudioPipeline()
        pipeline.generate_tts("Test", output_path=output)
        args = mock_run.call_args[0][0]
        voice_idx = args.index("--voice") + 1
        assert args[voice_idx] == DEFAULT_VOICE


# =========================================================================
# AudioPipeline.transcribe_audio tests
# =========================================================================


class TestTranscribeAudio:
    """Whisper ASR transcription via subprocess."""

    @patch("automedia.pipelines.audio_pipeline.subprocess.run")
    def test_calls_whisper_with_correct_args(self, mock_run: MagicMock, tmp_path: Any) -> None:
        audio_path = str(tmp_path / "test.mp3")
        # Create audio file so os.path.isfile passes
        with open(audio_path, "wb") as f:
            f.write(b"fake audio")

        # Create expected JSON output
        json_path = str(tmp_path / "test.json")
        _write_fake_whisper_json(json_path)

        mock_run.return_value = _make_subprocess_result()
        pipeline = AudioPipeline()
        result = pipeline.transcribe_audio(audio_path, language="en")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "whisper"
        assert audio_path in args
        assert "--model" in args
        assert DEFAULT_WHISPER_MODEL in args
        assert "--language" in args
        assert "en" in args
        assert "--output_format" in args
        assert "json" in args
        assert "text" in result
        assert "segments" in result

    def test_file_not_found_raises(self) -> None:
        pipeline = AudioPipeline()
        with pytest.raises(FileNotFoundError, match="audio file not found"):
            pipeline.transcribe_audio("/nonexistent/audio.mp3")

    @patch("automedia.pipelines.audio_pipeline.subprocess.run")
    def test_failure_raises_called_process_error(self, mock_run: MagicMock, tmp_path: Any) -> None:
        audio_path = str(tmp_path / "test.mp3")
        with open(audio_path, "wb") as f:
            f.write(b"fake audio")

        mock_run.return_value = _make_subprocess_result(returncode=1, stderr="model error")
        pipeline = AudioPipeline()
        with pytest.raises(subprocess.CalledProcessError):
            pipeline.transcribe_audio(audio_path)

    @patch("automedia.pipelines.audio_pipeline.subprocess.run")
    def test_returns_segments_from_json(self, mock_run: MagicMock, tmp_path: Any) -> None:
        audio_path = str(tmp_path / "audio.mp3")
        with open(audio_path, "wb") as f:
            f.write(b"fake audio")

        segments = [
            {"start": 0.0, "end": 3.0, "text": " First segment"},
            {"start": 3.5, "end": 6.0, "text": " Second segment"},
        ]
        json_path = str(tmp_path / "audio.json")
        _write_fake_whisper_json(json_path, segments)

        mock_run.return_value = _make_subprocess_result()
        pipeline = AudioPipeline()
        result = pipeline.transcribe_audio(audio_path)
        assert len(result["segments"]) == 2
        assert result["segments"][0]["text"] == " First segment"

    @patch("automedia.pipelines.audio_pipeline.subprocess.run")
    def test_default_language_is_zh(self, mock_run: MagicMock, tmp_path: Any) -> None:
        audio_path = str(tmp_path / "test.mp3")
        with open(audio_path, "wb") as f:
            f.write(b"fake audio")
        json_path = str(tmp_path / "test.json")
        _write_fake_whisper_json(json_path)

        mock_run.return_value = _make_subprocess_result()
        pipeline = AudioPipeline()
        pipeline.transcribe_audio(audio_path)
        args = mock_run.call_args[0][0]
        lang_idx = args.index("--language") + 1
        assert args[lang_idx] == "zh"


# =========================================================================
# AudioPipeline.generate_srt tests
# =========================================================================


class TestGenerateSrt:
    """SRT generation from Whisper transcription."""

    def test_produces_valid_srt_content(self, tmp_path: Any) -> None:
        transcription = {
            "text": "Hello world this is a test",
            "segments": [
                {"start": 0.0, "end": 2.5, "text": "Hello world"},
                {"start": 3.0, "end": 5.0, "text": "this is a test"},
            ],
        }
        output_path = str(tmp_path / "output.srt")
        pipeline = AudioPipeline()
        result = pipeline.generate_srt(transcription, output_path)

        assert os.path.isfile(result)
        with open(result, "r", encoding="utf-8") as fh:
            content = fh.read()

        assert "1\n" in content
        assert "00:00:00,000 --> 00:00:02,500" in content
        assert "Hello world" in content
        assert "2\n" in content
        assert "00:00:03,000 --> 00:00:05,000" in content
        assert "this is a test" in content

    def test_empty_segments_produces_empty_srt(self, tmp_path: Any) -> None:
        transcription: dict[str, Any] = {"text": "", "segments": []}
        output_path = str(tmp_path / "empty.srt")
        pipeline = AudioPipeline()
        result = pipeline.generate_srt(transcription, output_path)

        assert os.path.isfile(result)
        with open(result, "r", encoding="utf-8") as fh:
            content = fh.read()
        assert content == ""

    def test_time_format_milliseconds(self, tmp_path: Any) -> None:
        transcription = {
            "segments": [
                {"start": 61.123, "end": 125.456, "text": "time test"},
            ],
        }
        output_path = str(tmp_path / "time.srt")
        pipeline = AudioPipeline()
        pipeline.generate_srt(transcription, output_path)

        with open(output_path, "r", encoding="utf-8") as fh:
            content = fh.read()

        assert "00:01:01,123 --> 00:02:05,456" in content

    def test_returns_absolute_path(self, tmp_path: Any) -> None:
        transcription: dict[str, Any] = {"segments": []}
        output_path = str(tmp_path / "test.srt")
        pipeline = AudioPipeline()
        result = pipeline.generate_srt(transcription, output_path)
        assert os.path.isabs(result)

    def test_seconds_to_srt_time_edge_cases(self) -> None:
        pipeline = AudioPipeline()
        assert pipeline._seconds_to_srt_time(0.0) == "00:00:00,000"
        assert pipeline._seconds_to_srt_time(1.5) == "00:00:01,500"
        assert pipeline._seconds_to_srt_time(3661.001) == "01:01:01,001"


# =========================================================================
# AudioPipeline.proofread_srt tests
# =========================================================================


class TestProofreadSrt:
    """SRT proofreading — brand name spelling check."""

    def test_correct_brand_name_passes(self, tmp_path: Any) -> None:
        srt_content = (
            "1\n00:00:01,000 --> 00:00:03,000\n"
            "Welcome to AutoMedia\n\n"
            "2\n00:00:03,500 --> 00:00:05,000\n"
            "AutoMedia is great\n"
        )
        srt_path = str(tmp_path / "test.srt")
        _write_srt(srt_path, srt_content)

        pipeline = AudioPipeline()
        assert pipeline.proofread_srt(srt_path, "AutoMedia") is True

    def test_misspelled_brand_name_fails(self, tmp_path: Any) -> None:
        srt_content = (
            "1\n00:00:01,000 --> 00:00:03,000\n"
            "Welcome to AutoMedai\n"
        )
        srt_path = str(tmp_path / "test.srt")
        _write_srt(srt_path, srt_content)

        pipeline = AudioPipeline()
        assert pipeline.proofread_srt(srt_path, "AutoMedia") is False

    def test_no_brand_mention_passes(self, tmp_path: Any) -> None:
        srt_content = (
            "1\n00:00:01,000 --> 00:00:03,000\n"
            "Hello world\n"
        )
        srt_path = str(tmp_path / "test.srt")
        _write_srt(srt_path, srt_content)

        pipeline = AudioPipeline()
        assert pipeline.proofread_srt(srt_path, "SomeBrand") is True

    def test_file_not_found_returns_false(self, tmp_path: Any) -> None:
        pipeline = AudioPipeline()
        assert pipeline.proofread_srt(str(tmp_path / "nonexistent.srt"), "Brand") is False

    def test_empty_brand_name_passes(self, tmp_path: Any) -> None:
        srt_content = "1\n00:00:01,000 --> 00:00:03,000\nHello\n"
        srt_path = str(tmp_path / "test.srt")
        _write_srt(srt_path, srt_content)

        pipeline = AudioPipeline()
        assert pipeline.proofread_srt(srt_path, "") is True

    def test_short_brand_misspelling_detected(self, tmp_path: Any) -> None:
        # Brand "ABC" (3 chars) — "ABD" is 1 edit away, max_dist=1
        srt_content = "1\n00:00:01,000 --> 00:00:03,000\nThe ABD brand\n"
        srt_path = str(tmp_path / "test.srt")
        _write_srt(srt_path, srt_content)

        pipeline = AudioPipeline()
        assert pipeline.proofread_srt(srt_path, "ABC") is False


# =========================================================================
# AudioPipeline.generate_all tests
# =========================================================================


class TestGenerateAll:
    """One-stop TTS → ASR → SRT pipeline."""

    @patch("automedia.pipelines.audio_pipeline.subprocess.run")
    def test_orchestrates_full_pipeline(self, mock_run: MagicMock, tmp_path: Any) -> None:
        # First call: edge-tts (success)
        # Second call: whisper (success)
        # After whisper, we need to create the JSON file
        def side_effect(cmd, **kwargs):
            if cmd[0] == "edge-tts":
                # Create the mp3 file that edge-tts would produce
                write_media_idx = cmd.index("--write-media") + 1
                mp3_path = cmd[write_media_idx]
                os.makedirs(os.path.dirname(mp3_path), exist_ok=True)
                with open(mp3_path, "wb") as f:
                    f.write(b"fake mp3 audio data")
                return _make_subprocess_result()
            elif cmd[0] == "whisper":
                # Create the whisper JSON output
                audio_path = cmd[1]
                json_path = audio_path.rsplit(".", 1)[0] + ".json"
                _write_fake_whisper_json(json_path)
                return _make_subprocess_result()
            return _make_subprocess_result()

        mock_run.side_effect = side_effect
        output_dir = str(tmp_path / "output")
        pipeline = AudioPipeline()
        results = pipeline.generate_all("Hello world", voice="en-US-GuyNeural", output_dir=output_dir)

        assert "mp3" in results
        assert "json" in results
        assert "srt" in results
        assert os.path.isfile(results["mp3"])
        assert os.path.isfile(results["json"])
        assert os.path.isfile(results["srt"])
        assert mock_run.call_count == 2

    def test_empty_output_dir_raises_value_error(self) -> None:
        pipeline = AudioPipeline()
        with pytest.raises(ValueError, match="output_dir must not be empty"):
            pipeline.generate_all("Hello", output_dir="")

    @patch("automedia.pipelines.audio_pipeline.subprocess.run")
    def test_srt_contains_segments(self, mock_run: MagicMock, tmp_path: Any) -> None:
        segments = [
            {"start": 0.0, "end": 2.0, "text": " Hello"},
            {"start": 2.5, "end": 4.0, "text": " World"},
        ]

        def side_effect(cmd, **kwargs):
            if cmd[0] == "edge-tts":
                write_media_idx = cmd.index("--write-media") + 1
                mp3_path = cmd[write_media_idx]
                os.makedirs(os.path.dirname(mp3_path), exist_ok=True)
                with open(mp3_path, "wb") as f:
                    f.write(b"fake mp3")
                return _make_subprocess_result()
            elif cmd[0] == "whisper":
                audio_path = cmd[1]
                json_path = audio_path.rsplit(".", 1)[0] + ".json"
                _write_fake_whisper_json(json_path, segments)
                return _make_subprocess_result()
            return _make_subprocess_result()

        mock_run.side_effect = side_effect
        output_dir = str(tmp_path / "out")
        pipeline = AudioPipeline()
        results = pipeline.generate_all("Test", output_dir=output_dir)

        with open(results["srt"], "r", encoding="utf-8") as fh:
            srt_content = fh.read()
        assert "Hello" in srt_content
        assert "World" in srt_content
        assert "00:00:00,000 --> 00:00:02,000" in srt_content


# =========================================================================
# Helper function tests
# =========================================================================


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_levenshtein_identical_strings(self) -> None:
        assert _levenshtein_distance("hello", "hello") == 0

    def test_levenshtein_single_insertion(self) -> None:
        assert _levenshtein_distance("hello", "helllo") == 1

    def test_levenshtein_single_substitution(self) -> None:
        assert _levenshtein_distance("hello", "hallo") == 1

    def test_levenshtein_empty_strings(self) -> None:
        assert _levenshtein_distance("", "") == 0
        assert _levenshtein_distance("abc", "") == 3

    def test_is_similar_within_distance(self) -> None:
        assert _is_similar("AutoMedai", "AutoMedia", max_dist=2) is True

    def test_is_similar_exact_match(self) -> None:
        assert _is_similar("AutoMedia", "AutoMedia", max_dist=0) is True

    def test_is_similar_too_far(self) -> None:
        assert _is_similar("xyz", "AutoMedia", max_dist=2) is False

    def test_is_similar_length_diff_exceeds_max(self) -> None:
        assert _is_similar("AB", "ABCDEFG", max_dist=2) is False
