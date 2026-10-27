"""Tests for PiperTTSEngine — local offline TTS via ``piper-tts``.

Unit tests are dependency-free. The end-to-end synthesis test is skipped
unless both the ``piper`` package and a voice model are present, plus ffmpeg
and ffprobe. The model path comes only from the environment
(``AUTOMEDIA_PIPER_MODEL_PATH`` / legacy ``AUTOMEDIA_PIPER_MODEL``) — tests
never hardcode a machine path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

import pytest

from automedia.core.env_overlay import env_lookup
from automedia.engines.errors import EngineExecutionError
from automedia.engines.implementations.tts_piper import (
    LEGACY_MODEL_ENV_VAR,
    MODEL_PATH_ENV_VAR,
    PiperTTSEngine,
)

_MODEL_PATH = env_lookup(MODEL_PATH_ENV_VAR) or env_lookup(LEGACY_MODEL_ENV_VAR) or ""

_HAS_PIPER = True
try:  # pragma: no cover - environment dependent
    import piper  # noqa: F401
except Exception:  # pragma: no cover - environment dependent
    _HAS_PIPER = False

_HAS_MODEL = bool(_MODEL_PATH) and os.path.isfile(_MODEL_PATH)
_HAS_FFMPEG = shutil.which("ffmpeg") is not None
_HAS_FFPROBE = shutil.which("ffprobe") is not None


@pytest.fixture()
def no_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force both model env vars (and the ``.env`` overlay) to resolve empty."""
    monkeypatch.setattr(
        "automedia.engines.implementations.tts_piper.env_lookup",
        lambda _key: "",
    )


class TestPiperAttributes:
    def test_engine_name(self) -> None:
        assert PiperTTSEngine.engine_name == "piper"

    def test_modality(self) -> None:
        assert PiperTTSEngine.modality == "tts"


class TestPiperValidateConfig:
    def test_missing_model_raises(self, tmp_path: Any) -> None:
        engine = PiperTTSEngine({"model_path": str(tmp_path / "absent.onnx")})
        with pytest.raises(ValueError, match="model_path"):
            engine.validate_config()


class TestPiperErrors:
    def test_empty_text_raises(self, tmp_path: Any) -> None:
        engine = PiperTTSEngine({"model_path": str(tmp_path / "voice.onnx")})
        with pytest.raises(ValueError, match="text must not be empty"):
            engine.synthesize("", output_path=str(tmp_path / "out.mp3"))

    def test_empty_output_path_raises(self, tmp_path: Any) -> None:
        engine = PiperTTSEngine({"model_path": str(tmp_path / "voice.onnx")})
        with pytest.raises(ValueError, match="output_path must not be empty"):
            engine.synthesize("你好", output_path="")

    def test_no_model_configured_raises(self, tmp_path: Any, no_model_env: None) -> None:
        engine = PiperTTSEngine({})
        with pytest.raises(ValueError, match="model_path"):
            engine.synthesize("你好", output_path=str(tmp_path / "out.mp3"))


@pytest.mark.skipif(not _HAS_PIPER, reason="piper not installed")
class TestPiperCheckAvailable:
    def test_configured_model_available(self, tmp_path: Any) -> None:
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"model")
        available, message = PiperTTSEngine({"model_path": str(model)}).check_available()
        assert available is True, message

    def test_missing_model_unavailable(self, tmp_path: Any) -> None:
        engine = PiperTTSEngine({"model_path": str(tmp_path / "absent.onnx")})
        available, message = engine.check_available()
        assert available is False
        assert "not found" in message.lower()

    def test_env_model_path_used(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"model")
        monkeypatch.setenv(MODEL_PATH_ENV_VAR, str(model))
        available, message = PiperTTSEngine({}).check_available()
        assert available is True, message

    def test_legacy_env_var_used(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        model = tmp_path / "voice.onnx"
        model.write_bytes(b"model")
        monkeypatch.setattr(
            "automedia.engines.implementations.tts_piper.env_lookup",
            lambda key: str(model) if key == LEGACY_MODEL_ENV_VAR else "",
        )
        available, message = PiperTTSEngine({}).check_available()
        assert available is True, message

    def test_no_model_configured_unavailable(self, no_model_env: None) -> None:
        available, message = PiperTTSEngine({}).check_available()
        assert available is False
        assert "no piper model configured" in message


@pytest.mark.skipif(
    not (_HAS_PIPER and _HAS_MODEL and _HAS_FFMPEG and _HAS_FFPROBE),
    reason="piper, a voice model (env), ffmpeg or ffprobe missing",
)
class TestPiperSynthesis:
    def test_synthesize_mp3_has_audio_stream(self, tmp_path: Any) -> None:
        output = str(tmp_path / "speech.mp3")
        engine = PiperTTSEngine(
            {
                "model_path": _MODEL_PATH,
                "speaker": 0,
                "length_scale": 1.0,
                "bitrate": 192,
                "sample_rate": 44100,
            }
        )
        result = engine.synthesize("你好，世界。", voice="", output_path=output)

        assert os.path.isabs(result)
        assert os.path.getsize(result) > 2000

        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                result,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert probe.returncode == 0, probe.stderr
        assert "mp3" in probe.stdout.lower()

    def test_synthesize_wav_kept_as_wav(self, tmp_path: Any) -> None:
        output = str(tmp_path / "speech.wav")
        result = PiperTTSEngine({"model_path": _MODEL_PATH}).synthesize(
            "你好。", output_path=output
        )
        assert result.endswith(".wav")
        assert os.path.getsize(result) > 0
        with open(result, "rb") as fh:
            assert fh.read(4) == b"RIFF"

    def test_invalid_model_raises_execution_error(self, tmp_path: Any) -> None:
        bogus = tmp_path / "bogus.onnx"
        bogus.write_bytes(b"not a model")
        engine = PiperTTSEngine({"model_path": str(bogus)})
        with pytest.raises(EngineExecutionError, match="piper synthesis failed"):
            engine.synthesize("你好", output_path=str(tmp_path / "out.wav"))
