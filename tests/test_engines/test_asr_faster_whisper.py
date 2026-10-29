"""Tests for FasterWhisperASREngine — local offline ASR.

Unit tests need only the ``faster-whisper`` package. The end-to-end test
additionally needs a local model directory (``AUTOMEDIA_FASTER_WHISPER_MODEL``)
and synthesizes a speech WAV with Piper; it is skipped when either side is
missing. No network is used.
"""

from __future__ import annotations

import os
import sys
import types
import wave
from pathlib import Path
from typing import Any, ClassVar

import pytest

from automedia.core.env_overlay import env_lookup
from automedia.engines.implementations.asr_faster_whisper import (
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    MODEL_ENV_VAR,
    FasterWhisperASREngine,
)
from automedia.pipelines.audio_pipeline import AudioPipeline

_MODEL_DIR = env_lookup(MODEL_ENV_VAR) or ""
_PIPER_MODEL = env_lookup("AUTOMEDIA_PIPER_MODEL_PATH") or env_lookup("AUTOMEDIA_PIPER_MODEL") or ""

_HAS_FASTER_WHISPER = True
try:  # pragma: no cover - environment dependent
    import faster_whisper
except Exception:  # pragma: no cover - environment dependent
    _HAS_FASTER_WHISPER = False

_HAS_MODEL_DIR = bool(_MODEL_DIR) and os.path.isdir(_MODEL_DIR)
_HAS_PIPER = True
try:  # pragma: no cover - environment dependent
    import piper  # noqa: F401
except Exception:  # pragma: no cover - environment dependent
    _HAS_PIPER = False
_HAS_PIPER_MODEL = bool(_PIPER_MODEL) and os.path.isfile(_PIPER_MODEL)


def _make_speech_wav(path: str) -> bool:
    """Synthesize Chinese speech with Piper; return False when unavailable."""
    if not (_HAS_PIPER and _HAS_PIPER_MODEL):
        return False
    from piper import PiperVoice

    voice = PiperVoice.load(_PIPER_MODEL)
    with wave.open(path, "wb") as wav_file:
        voice.synthesize_wav("今天天气很好，我们出去散步吧。", wav_file)
    return os.path.getsize(path) > 0


class _FakeSegment:
    def __init__(self, start: float, end: float, text: str) -> None:
        self.start = start
        self.end = end
        self.text = text


class _FakeWhisperModel:
    instances: ClassVar[list[_FakeWhisperModel]] = []
    transcribe_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, model_name: str, **kwargs: Any) -> None:
        self.model_name = model_name
        self.kwargs = kwargs
        _FakeWhisperModel.instances.append(self)

    def transcribe(self, audio_path: str, **kwargs: Any) -> tuple[Any, Any]:
        _FakeWhisperModel.transcribe_kwargs = {"audio_path": audio_path, **kwargs}
        segments = [
            _FakeSegment(0.0, 0.8, " 你好。"),
            _FakeSegment(0.8, 1.6, " 世界。"),
        ]
        return iter(segments), {"language": "zh"}


class TestFasterWhisperAttributes:
    def test_engine_name(self) -> None:
        assert FasterWhisperASREngine.engine_name == "faster-whisper"

    def test_modality(self) -> None:
        assert FasterWhisperASREngine.modality == "asr"


class TestFasterWhisperConstants:
    def test_default_model(self) -> None:
        assert DEFAULT_MODEL == "tiny"

    def test_default_language(self) -> None:
        assert DEFAULT_LANGUAGE == "zh"


@pytest.mark.skipif(not _HAS_FASTER_WHISPER, reason="faster-whisper not installed")
class TestFasterWhisperCheckAvailable:
    def test_bare_model_name_available(self) -> None:
        engine = FasterWhisperASREngine({"model_path": "tiny"})
        available, message = engine.check_available()
        assert available is True, message

    def test_default_available(self) -> None:
        available, message = FasterWhisperASREngine().check_available()
        assert available is True, message

    def test_missing_local_model_dir_unavailable(self, tmp_path: Any) -> None:
        engine = FasterWhisperASREngine({"model_path": str(tmp_path / "absent-model")})
        available, message = engine.check_available()
        assert available is False
        assert "not found" in message.lower()

    def test_existing_local_model_dir_available(self, tmp_path: Any) -> None:
        engine = FasterWhisperASREngine({"model_path": str(tmp_path)})
        available, message = engine.check_available()
        assert available is True, message

    def test_env_model_dir_used(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(MODEL_ENV_VAR, str(tmp_path))
        available, message = FasterWhisperASREngine({}).check_available()
        assert available is True, message


class TestFasterWhisperDecodeProbe:
    def test_incompatible_av_reports_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = types.ModuleType("faster_whisper")

        def _boom(_audio: object) -> None:
            raise TypeError("open() got an unexpected keyword argument 'metadata_errors'")

        module.decode_audio = _boom  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "faster_whisper", module)
        available, message = FasterWhisperASREngine({}).check_available()
        assert available is False
        assert "cannot decode audio" in message

    def test_missing_decode_audio_reports_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = types.ModuleType("faster_whisper")
        monkeypatch.setitem(sys.modules, "faster_whisper", module)
        available, message = FasterWhisperASREngine({}).check_available()
        assert available is False
        assert "decode_audio" in message

    def test_successful_decode_stays_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = types.ModuleType("faster_whisper")
        seen: list[object] = []

        def _decode(audio: object) -> None:
            seen.append(audio)

        module.decode_audio = _decode  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "faster_whisper", module)
        available, message = FasterWhisperASREngine({}).check_available()
        assert available is True, message
        assert len(seen) == 1


class TestFasterWhisperTranscribeErrors:
    def test_missing_audio_raises(self) -> None:
        engine = FasterWhisperASREngine({"model_path": "tiny"})
        with pytest.raises(FileNotFoundError, match="audio file not found"):
            engine.transcribe("/nonexistent/audio.wav")


@pytest.mark.skipif(not _HAS_FASTER_WHISPER, reason="faster-whisper not installed")
class TestFasterWhisperTranscribeContract:
    def test_transcribe_shape_and_srt(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(faster_whisper, "WhisperModel", _FakeWhisperModel)
        _FakeWhisperModel.instances.clear()
        audio = tmp_path / "audio.wav"
        audio.write_bytes(b"RIFF-fake")

        engine = FasterWhisperASREngine(
            {"model_path": "tiny", "language": "zh", "compute_type": "int8"}
        )
        result = engine.transcribe(str(audio))

        assert result["text"] == "你好。 世界。"
        assert [seg["text"] for seg in result["segments"]] == ["你好。", "世界。"]
        assert result["segments"][0] == {"start": 0.0, "end": 0.8, "text": "你好。"}
        assert _FakeWhisperModel.transcribe_kwargs["language"] == "zh"
        assert _FakeWhisperModel.transcribe_kwargs["vad_filter"] is True
        assert _FakeWhisperModel.instances[0].kwargs["compute_type"] == "int8"

        srt_path = AudioPipeline().generate_srt(result, str(tmp_path / "out.srt"))
        assert os.path.isfile(srt_path)
        content = Path(srt_path).read_text(encoding="utf-8")
        assert "你好。" in content
        assert "00:00:00,000 --> 00:00:00,800" in content


@pytest.mark.skipif(
    not (_HAS_FASTER_WHISPER and _HAS_MODEL_DIR and _HAS_PIPER and _HAS_PIPER_MODEL),
    reason="faster-whisper, model dir, piper voice or piper model missing",
)
class TestFasterWhisperTranscribe:
    def test_transcribes_speech(self, tmp_path: Any) -> None:
        wav_path = str(tmp_path / "speech.wav")
        if not _make_speech_wav(wav_path):
            pytest.skip("piper could not synthesize the speech fixture")

        engine = FasterWhisperASREngine(
            {
                "model_path": _MODEL_DIR,
                "language": "zh",
                "compute_type": "int8",
                "device": "cpu",
            }
        )
        result = engine.transcribe(wav_path)

        assert isinstance(result["text"], str)
        assert result["text"].strip()
        assert isinstance(result["segments"], list)
        assert result["segments"]
        first = result["segments"][0]
        assert isinstance(first["start"], float)
        assert isinstance(first["end"], float)
        assert isinstance(first["text"], str)
        assert first["end"] >= first["start"]
