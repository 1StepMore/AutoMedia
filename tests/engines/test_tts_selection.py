"""TTS engine selection tests (#630): azure-tts preferred, edge-tts fallback.

All engines are faked at the ``synthesize`` boundary; availability is driven
through ``check_available`` and the credential env vars. No network request is
made anywhere in this module.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from structlog.testing import capture_logs

from automedia.engines.implementations.tts_azure import (
    DEFAULT_OUTPUT_FORMAT,
    SPEECH_KEY_ENV,
    SPEECH_REGION_ENV,
    AzureTTSEngine,
)
from automedia.engines.implementations.tts_edge import EdgeTTSEngine
from automedia.engines.implementations.tts_piper import PiperTTSEngine
from automedia.engines.registry import EngineRegistry
from automedia.pipelines.audio_pipeline import AudioPipeline


def _fake_synthesize(engine_name: str) -> Any:
    """Build a ``synthesize`` replacement that writes a name-tagged payload."""

    def _synthesize(self: Any, text: str, voice: str = "", output_path: str = "") -> str:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "wb") as fh:
            fh.write(f"{engine_name}-audio".encode())
        return os.path.abspath(output_path)

    return _synthesize


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Keep the suite credential-free: no env vars, no ~/.automedia/.env overlay."""
    monkeypatch.delenv(SPEECH_KEY_ENV, raising=False)
    monkeypatch.delenv(SPEECH_REGION_ENV, raising=False)
    monkeypatch.setenv("AUTOMEDIA_DOTENV_PATH", str(tmp_path / "empty.env"))

    from automedia.core.env_overlay import reset_dotenv_overlay_cache

    reset_dotenv_overlay_cache()
    yield
    reset_dotenv_overlay_cache()


@pytest.fixture(autouse=True)
def _engines_registered() -> None:
    """Re-register the TTS engines (other modules clear the shared registry)."""
    registry = EngineRegistry()
    if "azure-tts" not in registry:
        registry.register("azure-tts", AzureTTSEngine, modality="tts")
    if "edge-tts" not in registry:
        registry.register("edge-tts", EdgeTTSEngine, modality="tts")


@pytest.fixture(autouse=True)
def _deterministic_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Edge always available; piper always unavailable — isolate the azure/edge axis."""
    monkeypatch.setattr(
        EdgeTTSEngine, "check_available", lambda self: (True, "edge-tts CLI found on PATH")
    )
    monkeypatch.setattr(EdgeTTSEngine, "synthesize", _fake_synthesize("edge-tts"))
    monkeypatch.setattr(
        PiperTTSEngine, "check_available", lambda self: (False, "piper model missing")
    )


def test_prefers_azure_when_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(SPEECH_KEY_ENV, "k")
    monkeypatch.setenv(SPEECH_REGION_ENV, "eastasia")
    monkeypatch.setattr(AzureTTSEngine, "synthesize", _fake_synthesize("azure-tts"))

    out = str(tmp_path / "narration.mp3")
    pipeline = AudioPipeline()
    result = pipeline.generate_tts("hello", output_path=out)

    assert result == os.path.abspath(out)
    assert pipeline.last_engine_name == "azure-tts"
    assert pipeline.last_output_format == DEFAULT_OUTPUT_FORMAT
    assert Path(out).read_bytes() == b"azure-tts-audio"


def test_falls_back_to_edge_when_azure_unavailable(tmp_path: Path) -> None:
    # No credentials (fixture): azure check_available returns (False, ...) —
    # selection must degrade to edge-tts without raising.
    out = str(tmp_path / "narration.mp3")
    pipeline = AudioPipeline()
    with capture_logs() as logs:
        result = pipeline.generate_tts("hello", output_path=out)

    assert result == os.path.abspath(out)
    assert pipeline.last_engine_name == "edge-tts"
    assert pipeline.last_output_format == EdgeTTSEngine.output_format
    assert Path(out).read_bytes() == b"edge-tts-audio"

    warnings = [entry for entry in logs if entry["log_level"] == "warning"]
    assert any(
        "azure-tts" in entry["event"]
        and "AUTOMEDIA_AZURE_SPEECH_KEY" in " ".join(str(v) for v in entry.values())
        for entry in warnings
    )


def test_falls_back_when_azure_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(SPEECH_KEY_ENV, "k")
    monkeypatch.setenv(SPEECH_REGION_ENV, "eastasia")

    from automedia.engines.errors import EngineExecutionError

    def _boom(self: Any, text: str, voice: str = "", output_path: str = "") -> str:
        raise EngineExecutionError(engine_name="azure-tts", details="boom")

    monkeypatch.setattr(AzureTTSEngine, "synthesize", _boom)

    out = str(tmp_path / "narration.mp3")
    pipeline = AudioPipeline()
    with caplog.at_level("WARNING", logger="automedia.pipelines.audio_pipeline"):
        result = pipeline.generate_tts("hello", output_path=out)

    assert result == os.path.abspath(out)
    assert pipeline.last_engine_name == "edge-tts"
    assert Path(out).read_bytes() == b"edge-tts-audio"
    assert any(
        "azure-tts" in record.getMessage() and "trying next engine" in record.getMessage()
        for record in caplog.records
    )


def test_provenance_records_engine(tmp_path: Path) -> None:
    from automedia.pipelines.runner import _write_narration_provenance

    draft = tmp_path / "01_content" / "drafts" / "x_draft.md"
    draft.parent.mkdir(parents=True)
    draft.write_text("draft text", encoding="utf-8")
    audio_dir = tmp_path / "04_audio"
    gate_context: dict[str, Any] = {
        "project_dir": str(tmp_path),
        "output_files": [{"type": "article", "path": str(draft)}],
    }

    _write_narration_provenance(
        gate_context,
        audio_dir=str(audio_dir),
        narration_text="narration",
        tts_meta={
            "engine": "azure-tts",
            "output_format": DEFAULT_OUTPUT_FORMAT,
            "voice": "zh-CN-YunjianNeural",
        },
    )

    payload = json.loads((audio_dir / "narration.provenance.json").read_text(encoding="utf-8"))
    assert payload["engine"] == "azure-tts"
    assert payload["output_format"] == DEFAULT_OUTPUT_FORMAT
    assert payload["voice"] == "zh-CN-YunjianNeural"
    # Credentials never land in provenance: only the known fields exist.
    assert set(payload) <= {
        "source_draft",
        "source_sha256",
        "narration_chars",
        "generated_at",
        "engine",
        "output_format",
        "voice",
    }

    # Without tts_meta the pre-#630 shape is preserved (no empty fields written).
    _write_narration_provenance(
        gate_context,
        audio_dir=str(audio_dir),
        narration_text="narration",
        tts_meta=None,
    )
    legacy = json.loads((audio_dir / "narration.provenance.json").read_text(encoding="utf-8"))
    assert "engine" not in legacy and "output_format" not in legacy and "voice" not in legacy
