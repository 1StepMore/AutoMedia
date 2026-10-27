"""Tests for the engine fallback chain.

Covers :func:`automedia.engines.resolve_engine_chain`: explicit ``chain``
ordering, de-duplication, skipped unavailable/unknown engines, legacy
``default`` + ``fallback`` compatibility, registration-order fallback, and the
``defaults.yaml`` chain declarations. Also covers pipeline integration: TTS/ASR
fall through to the next engine, and image generation uses the second engine
when the first is unavailable or fails.

Everything is monkeypatched — no network, no real ComfyUI, no real engines.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from PIL import Image

from automedia.engines import resolve_engine_chain
from automedia.engines.errors import EngineExecutionError, EngineUnavailableError
from automedia.engines.registry import EngineRegistry
from automedia.pipelines.audio_pipeline import AudioPipeline
from automedia.pipelines.image_pipeline import ImagePipeline


class _FakeEngine:
    """Minimal engine double recording calls."""

    def __init__(self, name: str, *, fail: Exception | None = None) -> None:
        self.engine_name = name
        self._fail = fail
        self.calls: list[tuple[Any, ...]] = []

    def check_available(self) -> tuple[bool, str]:
        return (self._fail is None, "" if self._fail is None else str(self._fail))

    def _maybe_fail(self) -> None:
        if self._fail is not None:
            raise self._fail


class _FakeTTSEngine(_FakeEngine):
    def synthesize(self, text: str, voice: str = "", output_path: str = "") -> str:
        self.calls.append((text, voice, output_path))
        self._maybe_fail()
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "wb") as fh:
            fh.write(b"fake-audio")
        return os.path.abspath(output_path)


class _FakeASREngine(_FakeEngine):
    def transcribe(self, audio_path: str, language: str | None = None) -> dict[str, Any]:
        self.calls.append((audio_path, language))
        self._maybe_fail()
        return {"text": "ok", "segments": [{"start": 0.0, "end": 1.0, "text": "ok"}]}


class _FakeImageEngine(_FakeEngine):
    def generate(self, prompt: str, width: int, height: int, output_path: str) -> str:
        self.calls.append((prompt, width, height, output_path))
        self._maybe_fail()
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        Image.new("RGB", (width, height), color=(10, 20, 30)).save(output_path, "PNG")
        return os.path.abspath(output_path)


def _cfg_chain(modality: str, chain: list[str]) -> dict[str, Any]:
    return {"engines": {modality: {"chain": chain}}}


def _cfg_fallback(modality: str, default: str, fallback: list[str]) -> dict[str, Any]:
    return {"engines": {modality: {"default": default, "fallback": fallback}}}


def _fake_resolve_from_default(modality: str, config: dict | None = None) -> Any:
    assert config is not None
    name = config["engines"][modality]["default"]
    return _FakeEngine(name)


class TestDefaultsYamlChains:
    def test_each_modality_declares_a_chain(self) -> None:
        defaults_path = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "automedia"
            / "manifests"
            / "defaults.yaml"
        )
        defaults = yaml.safe_load(defaults_path.read_text(encoding="utf-8"))
        engines = defaults["engines"]

        assert engines["tts"]["chain"] == ["piper", "edge-tts"]
        assert engines["asr"]["chain"] == ["whisper", "faster-whisper"]
        assert engines["image"]["chain"] == ["comfyui", "local"]

    def test_no_tmp_paths_in_engine_defaults(self) -> None:
        defaults_path = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "automedia"
            / "manifests"
            / "defaults.yaml"
        )
        assert "/tmp/" not in defaults_path.read_text(encoding="utf-8")


class TestResolveEngineChain:
    def test_explicit_chain_order_and_dedupe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[str] = []

        def _resolve(modality: str, config: dict | None = None) -> Any:
            assert config is not None
            name = config["engines"][modality]["default"]
            seen.append(name)
            return _FakeEngine(name)

        monkeypatch.setattr("automedia.engines.resolve_engine", _resolve)
        chain = resolve_engine_chain("tts", _cfg_chain("tts", ["piper", "edge-tts", "piper"]))

        assert [e.engine_name for e in chain] == ["piper", "edge-tts"]
        assert seen == ["piper", "edge-tts"]

    def test_chain_wins_over_default_and_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("automedia.engines.resolve_engine", _fake_resolve_from_default)
        config = {
            "engines": {
                "tts": {
                    "default": "piper",
                    "fallback": ["edge-tts"],
                    "chain": ["edge-tts"],
                }
            }
        }
        chain = resolve_engine_chain("tts", config)
        assert [e.engine_name for e in chain] == ["edge-tts"]

    def test_unavailable_engine_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _resolve(modality: str, config: dict | None = None) -> Any:
            assert config is not None
            name = config["engines"][modality]["default"]
            if name == "piper":
                raise EngineUnavailableError("piper", "model missing", "install piper")
            return _FakeEngine(name)

        monkeypatch.setattr("automedia.engines.resolve_engine", _resolve)
        chain = resolve_engine_chain("tts", _cfg_chain("tts", ["piper", "edge-tts"]))
        assert [e.engine_name for e in chain] == ["edge-tts"]

    def test_unknown_engine_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _resolve(modality: str, config: dict | None = None) -> Any:
            assert config is not None
            name = config["engines"][modality]["default"]
            if name == "bogus":
                raise KeyError(name)
            return _FakeEngine(name)

        monkeypatch.setattr("automedia.engines.resolve_engine", _resolve)
        chain = resolve_engine_chain("tts", _cfg_chain("tts", ["bogus", "edge-tts"]))
        assert [e.engine_name for e in chain] == ["edge-tts"]

    def test_empty_chain_returns_empty(self) -> None:
        assert resolve_engine_chain("tts", _cfg_chain("tts", [])) == []

    def test_legacy_default_plus_fallback_then_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("automedia.engines.resolve_engine", _fake_resolve_from_default)
        monkeypatch.setattr(
            "automedia.engines.EngineRegistry.list_by_modality_ordered",
            lambda self, modality: ["piper", "edge-tts"],
        )
        chain = resolve_engine_chain("tts", _cfg_fallback("tts", "piper", ["edge-tts"]))
        assert [e.engine_name for e in chain] == ["piper", "edge-tts"]

    def test_missing_chain_uses_default_then_registration_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = ["second-engine", "third-engine"]
        monkeypatch.setattr("automedia.engines.resolve_engine", _fake_resolve_from_default)
        monkeypatch.setattr(
            "automedia.engines.EngineRegistry.list_by_modality_ordered",
            lambda self, modality: names,
        )
        chain = resolve_engine_chain("tts", {"engines": {"tts": {"default": "first-engine"}}})
        assert [e.engine_name for e in chain] == [
            "first-engine",
            "second-engine",
            "third-engine",
        ]

    def test_all_unavailable_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(modality: str, config: dict | None = None) -> Any:
            raise EngineUnavailableError("x", "nah", "install")

        monkeypatch.setattr("automedia.engines.resolve_engine", _boom)
        assert resolve_engine_chain("asr", _cfg_chain("asr", ["faster-whisper"])) == []

    def test_non_dict_engine_config_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "automedia.engines.resolve_engine",
            lambda modality, config=None: _FakeEngine("solo"),
        )
        monkeypatch.setattr(
            "automedia.engines.EngineRegistry.list_by_modality_ordered",
            lambda self, modality: [],
        )
        assert [e.engine_name for e in resolve_engine_chain("tts", {"engines": {"tts": []}})] == [
            "solo"
        ]

    def test_default_config_reaches_local_when_comfyui_down(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from automedia.engines.implementations.image_comfyui import (
            ComfyUIImageEngine,
        )
        from automedia.engines.implementations.image_local import LocalImageEngine

        registry = EngineRegistry()
        if "comfyui" not in registry:
            registry.register("comfyui", ComfyUIImageEngine, modality="image")
        if "local" not in registry:
            registry.register("local", LocalImageEngine, modality="image")

        monkeypatch.setattr(ComfyUIImageEngine, "check_available", lambda self: (False, "down"))
        chain = resolve_engine_chain("image", {})
        assert [e.engine_name for e in chain] == ["local"]

    def test_missing_engines_section_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "automedia.engines.resolve_engine",
            lambda modality, config=None: _FakeEngine("solo"),
        )
        assert resolve_engine_chain("asr", {}) != []


class TestAudioPipelineChainFallback:
    def test_generate_tts_falls_through(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        first = _FakeTTSEngine("piper", fail=EngineExecutionError("piper", "boom"))
        second = _FakeTTSEngine("edge-tts")

        monkeypatch.setattr(
            "automedia.pipelines.audio_pipeline.resolve_engine_chain",
            lambda modality, config=None: [first, second],
        )
        output = str(tmp_path / "out.mp3")
        result = AudioPipeline().generate_tts("hello", output_path=output)

        assert result == os.path.abspath(output)
        assert len(first.calls) == 1
        assert len(second.calls) == 1
        assert os.path.getsize(output) > 0

    def test_generate_tts_raises_last_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        first = _FakeTTSEngine("piper", fail=EngineExecutionError("piper", "one"))
        second = _FakeTTSEngine("edge-tts", fail=EngineExecutionError("edge-tts", "two"))

        monkeypatch.setattr(
            "automedia.pipelines.audio_pipeline.resolve_engine_chain",
            lambda modality, config=None: [first, second],
        )
        with pytest.raises(EngineExecutionError, match="two"):
            AudioPipeline().generate_tts("hello", output_path=str(tmp_path / "out.mp3"))

    def test_transcribe_audio_falls_through(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        audio = str(tmp_path / "audio.mp3")
        with open(audio, "wb") as fh:
            fh.write(b"audio")
        first = _FakeASREngine("faster-whisper", fail=EngineExecutionError("faster-whisper", "x"))
        second = _FakeASREngine("whisper")

        monkeypatch.setattr(
            "automedia.pipelines.audio_pipeline.resolve_engine_chain",
            lambda modality, config=None: [first, second],
        )
        result = AudioPipeline().transcribe_audio(audio)
        assert result["text"] == "ok"
        assert len(second.calls) == 1

    def test_get_tts_engine_returns_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        first = _FakeTTSEngine("piper")
        second = _FakeTTSEngine("edge-tts")
        monkeypatch.setattr(
            "automedia.pipelines.audio_pipeline.resolve_engine_chain",
            lambda modality, config=None: [first, second],
        )
        pipeline = AudioPipeline()
        assert pipeline._get_tts_engine() is first
        assert pipeline._get_asr_engine is not None

    def test_empty_chain_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "automedia.pipelines.audio_pipeline.resolve_engine_chain",
            lambda modality, config=None: [],
        )
        pipeline = AudioPipeline()
        assert pipeline._get_tts_engine() is None
        assert pipeline._get_asr_engine() is None


class TestImagePipelineChainFallback:
    def test_uses_second_engine_when_first_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        first = _FakeImageEngine("comfyui", fail=EngineUnavailableError("comfyui", "down", "start"))
        second = _FakeImageEngine("local")

        monkeypatch.setattr(
            "automedia.engines.resolve_engine_chain",
            lambda modality, config=None: [first, second],
        )
        results = ImagePipeline().generate_covers("topic", "brand", str(tmp_path))

        assert len(results) == 4
        assert len(first.calls) == 4
        assert len(second.calls) == 4
        for path in results.values():
            assert os.path.isfile(path)

    def test_uses_second_engine_when_first_fails_execution(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        first = _FakeImageEngine("comfyui", fail=EngineExecutionError("comfyui", "timeout"))
        second = _FakeImageEngine("local")

        monkeypatch.setattr(
            "automedia.engines.resolve_engine_chain",
            lambda modality, config=None: [first, second],
        )
        path = ImagePipeline().generate_single_cover("topic", "brand", str(tmp_path))
        assert path and os.path.isfile(path)
        assert len(second.calls) == 1

    def test_all_engines_fail_returns_no_image(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        first = _FakeImageEngine("comfyui", fail=EngineUnavailableError("comfyui", "down", "x"))
        second = _FakeImageEngine("local", fail=EngineUnavailableError("local", "no PIL", "x"))

        monkeypatch.setattr(
            "automedia.engines.resolve_engine_chain",
            lambda modality, config=None: [first, second],
        )
        assert ImagePipeline().generate_covers("t", "b", str(tmp_path)) == {}

    def test_get_image_engine_raises_when_chain_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "automedia.engines.resolve_engine_chain",
            lambda modality, config=None: [],
        )
        pipeline = ImagePipeline()
        with pytest.raises(EngineUnavailableError):
            pipeline._get_image_engine()
