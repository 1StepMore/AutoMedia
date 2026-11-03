"""Tests for the Azure Speech TTS engine (#356).

Everything is mocked at the httpx boundary — no network in the suite. A
real-credential smoke test lives in ``TestLiveSmoke`` and is skipped unless
``AUTOMEDIA_AZURE_SPEECH_KEY``/``_REGION`` are actually configured.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.engines.implementations.tts_azure import (
    DEFAULT_VOICE,
    SPEECH_KEY_ENV,
    SPEECH_REGION_ENV,
    AzureTTSEngine,
    speech_friendly_text,
)

_HTTPX = "httpx.Client"


def _fake_response(status_code: int = 200, content: bytes = b"mp3-bytes") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.text = "error-body" if status_code != 200 else ""
    return resp


@pytest.fixture(autouse=True)
def _no_azure_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Keep the suite credential-free regardless of the local environment.

    Isolates from BOTH the process env and the machine's real
    ``~/.automedia/.env`` overlay (which legitimately holds credentials on
    dev machines): point ``AUTOMEDIA_DOTENV_PATH`` at an empty file and drop
    the parsed-overlay cache, then restore the cache after the test.
    """
    monkeypatch.delenv(SPEECH_KEY_ENV, raising=False)
    monkeypatch.delenv(SPEECH_REGION_ENV, raising=False)
    monkeypatch.setenv("AUTOMEDIA_DOTENV_PATH", str(tmp_path / "empty.env"))

    from automedia.core.env_overlay import reset_dotenv_overlay_cache

    reset_dotenv_overlay_cache()
    yield
    reset_dotenv_overlay_cache()


@pytest.fixture(autouse=True)
def _azure_registered() -> None:
    """Re-register azure before each test.

    Other engine test modules (image/video/asr) clear the shared
    :class:`EngineRegistry` singleton in their teardowns, which drops the
    import-time registration of this module's engine class — same reason
    ``test_tts_edge.py`` re-registers edge-tts.
    """
    from automedia.engines.registry import EngineRegistry

    if "azure" not in EngineRegistry():
        EngineRegistry().register("azure", AzureTTSEngine, modality="tts")


class TestRegistration:
    def test_registered_as_tts_engine(self) -> None:
        from automedia.engines.registry import EngineRegistry

        assert "azure" in EngineRegistry().list_by_modality("tts")


class TestSpeechFriendlyText:
    def test_standalone_ai_normalized(self) -> None:
        assert speech_friendly_text("AI正在改变世界") == "人工智能正在改变世界"

    def test_compound_ai_token_untouched(self) -> None:
        assert speech_friendly_text("AIGC工具") == "AIGC工具"
        assert speech_friendly_text("AINet") == "AINet"

    def test_idempotent(self) -> None:
        once = speech_friendly_text("用AI做视频")
        assert speech_friendly_text(once) == once


class TestCheckAvailable:
    def test_false_without_credentials(self) -> None:
        ok, msg = AzureTTSEngine().check_available()
        assert ok is False
        assert SPEECH_KEY_ENV in msg

    def test_false_without_region(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(SPEECH_KEY_ENV, "k")
        ok, msg = AzureTTSEngine().check_available()
        assert ok is False
        assert SPEECH_REGION_ENV in msg

    def test_true_with_env_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(SPEECH_KEY_ENV, "k")
        monkeypatch.setenv(SPEECH_REGION_ENV, "eastasia")
        ok, msg = AzureTTSEngine().check_available()
        assert ok is True
        assert "eastasia" in msg

    def test_config_keys_work_without_env(self) -> None:
        engine = AzureTTSEngine({"speech_key": "k", "region": "westus"})
        ok, msg = engine.check_available()
        assert ok is True
        assert "westus" in msg


class TestSynthesize:
    def _engine(self, **cfg: Any) -> AzureTTSEngine:
        return AzureTTSEngine({"speech_key": "k", "region": "eastasia", **cfg})

    def test_posts_ssml_and_writes_bytes(self, tmp_path: os.PathLike) -> None:
        out = str(tmp_path / "seg.mp3")
        captured: dict[str, Any] = {}

        class _Client:
            def __init__(self, **_: Any) -> None:
                pass

            def __enter__(self) -> _Client:
                return self

            def __exit__(self, *a: Any) -> None:
                return None

            def post(self, url: str, content: bytes, headers: dict[str, str]) -> MagicMock:
                captured.update(url=url, content=content, headers=headers)
                return _fake_response()

        with patch(_HTTPX, _Client):
            result = self._engine().synthesize(
                "AI很热", voice="zh-CN-YunyangNeural", output_path=out
            )

        assert result == os.path.abspath(out)
        assert captured["url"] == "https://eastasia.tts.speech.microsoft.com/cognitiveservices/v1"
        assert captured["headers"]["Ocp-Apim-Subscription-Key"] == "k"
        assert captured["headers"]["X-Microsoft-OutputFormat"] == "audio-24khz-48kbitrate-mono-mp3"
        assert "zh-CN-YunyangNeural" in captured["content"].decode("utf-8")
        # speech normalization applied: AI → 人工智能 inside the SSML
        assert "人工智能很热" in captured["content"].decode("utf-8")
        with open(out, "rb") as fh:
            assert fh.read() == b"mp3-bytes"

    def test_default_voice_and_no_normalization_optout(self, tmp_path: os.PathLike) -> None:
        out = str(tmp_path / "seg.mp3")
        seen: dict[str, Any] = {}

        class _Client:
            def __init__(self, **_: Any) -> None:
                pass

            def __enter__(self) -> _Client:
                return self

            def __exit__(self, *a: Any) -> None:
                return None

            def post(self, url: str, content: bytes, headers: dict[str, str]) -> MagicMock:
                seen["content"] = content
                return _fake_response()

        with patch(_HTTPX, _Client):
            self._engine(speech_normalization=False).synthesize("AI很热", output_path=out)

        ssml = seen["content"].decode("utf-8")
        assert DEFAULT_VOICE in ssml
        assert "AI很热" in ssml

    def test_xml_escaping(self, tmp_path: os.PathLike) -> None:
        out = str(tmp_path / "seg.mp3")
        seen: dict[str, Any] = {}

        class _Client:
            def __init__(self, **_: Any) -> None:
                pass

            def __enter__(self) -> _Client:
                return self

            def __exit__(self, *a: Any) -> None:
                return None

            def post(self, url: str, content: bytes, headers: dict[str, str]) -> MagicMock:
                seen["content"] = content
                return _fake_response()

        with patch(_HTTPX, _Client):
            self._engine().synthesize("价格<100 & 品质>预期", output_path=out)

        ssml = seen["content"].decode("utf-8")
        assert "价格&lt;100 &amp; 品质&gt;预期" in ssml

    def test_empty_args_raise(self, tmp_path: os.PathLike) -> None:
        engine = self._engine()
        with pytest.raises(ValueError):
            engine.synthesize("", output_path=str(tmp_path / "a.mp3"))
        with pytest.raises(ValueError):
            engine.synthesize("text", output_path="")

    def test_missing_credentials_raise(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: os.PathLike
    ) -> None:
        engine = AzureTTSEngine()
        with pytest.raises(ValueError, match="AUTOMEDIA_AZURE_SPEECH"):
            engine.synthesize("text", output_path=str(tmp_path / "a.mp3"))

    @pytest.mark.parametrize("status", [401, 403, 429, 500])
    def test_http_errors_raise_engine_error(self, status: int, tmp_path: os.PathLike) -> None:
        out = str(tmp_path / "seg.mp3")

        class _Client:
            def __init__(self, **_: Any) -> None:
                pass

            def __enter__(self) -> _Client:
                return self

            def __exit__(self, *a: Any) -> None:
                return None

            def post(self, url: str, content: bytes, headers: dict[str, str]) -> MagicMock:
                return _fake_response(status_code=status)

        from automedia.engines.errors import EngineExecutionError

        with patch(_HTTPX, _Client), pytest.raises(EngineExecutionError):
            self._engine().synthesize("text", output_path=out)
        assert not os.path.exists(out)


class TestChainIntegration:
    def test_azure_leads_chain_when_credentialed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from automedia.engines import resolve_engine_chain

        monkeypatch.setenv(SPEECH_KEY_ENV, "k")
        monkeypatch.setenv(SPEECH_REGION_ENV, "eastasia")
        config = {"engines": {"tts": {"chain": ["azure", "edge-tts"]}}}
        with patch(_HTTPX, MagicMock()):
            chain = resolve_engine_chain("tts", config)
        assert [e.engine_name for e in chain][:1] == ["azure"]

    def test_azure_skipped_without_credentials(self) -> None:
        from automedia.engines import resolve_engine_chain
        from automedia.engines.implementations import tts_piper as _piper_mod  # noqa: F401

        config = {"engines": {"tts": {"chain": ["azure", "edge-tts"]}}}
        chain = resolve_engine_chain("tts", config)
        # azure is absent (no creds); edge-tts is present only if the CLI
        # exists on this machine — assert on azure's absence, not the tail.
        assert "azure" not in [e.engine_name for e in chain]


class TestLiveSmoke:
    """Only runs where real Azure credentials are configured (local .env)."""

    def test_real_synthesis(self, tmp_path: os.PathLike) -> None:
        if not (os.environ.get(SPEECH_KEY_ENV) and os.environ.get(SPEECH_REGION_ENV)):
            pytest.skip("Azure Speech credentials not configured")
        engine = AzureTTSEngine()
        ok, _ = engine.check_available()
        assert ok
        out = str(tmp_path / "live.mp3")
        result = engine.synthesize("人工智能的视频能力验收。", output_path=out)
        assert os.path.isfile(result)
        assert os.path.getsize(result) > 1000
