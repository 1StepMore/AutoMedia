"""``resolve_video_engine`` — chain fallback for a stale default (#476).

``engines.video.default`` pointing at an unregistered name (a stale override
such as the removed ``ffmpeg``) used to hard-fail the render with the chain
never consulted; the run then presented as a clean ``awaiting_review`` with no
mp4.  The helper falls back to the configured chain with an explicit warning;
an empty chain re-raises; a *registered* default that is unavailable still
raises ``EngineUnavailableError`` (the #414 fail-loudly path).
"""

from __future__ import annotations

import pytest

from automedia.engines import (
    EngineNotFoundError,
    EngineRegistry,
    EngineUnavailableError,
    resolve_video_engine,
)
from automedia.engines.base import BaseVideoEngine


class _FakeVideoEngine(BaseVideoEngine):
    """A registered-but-shallow video engine double."""

    engine_name = "fake-video"

    def __init__(self, engine_config: dict | None = None) -> None:
        self._config = engine_config or {}

    def check_available(self) -> tuple[bool, str]:
        if self._config.get("unavailable"):
            return False, "engine unavailable (test double)"
        return True, "ok"

    def render(self, assets, output_path: str, **kwargs) -> str:  # type: ignore[no-untyped-def]
        return output_path


@pytest.fixture()
def fake_video_registry():
    """Register the fake video engine, restoring the registry afterwards."""
    registry = EngineRegistry()
    had_entry = "fake-video" in registry._registry
    previous_entry = registry._registry.get("fake-video")
    previous_modality = set(registry._modality_map.get("video", set()))
    registry.register("fake-video", _FakeVideoEngine, modality="video")
    yield registry
    if had_entry:
        registry._registry["fake-video"] = previous_entry
    else:
        registry._registry.pop("fake-video", None)
    registry._modality_map["video"] = previous_modality


def _cfg(default: str, **extra) -> dict:
    section = {"default": default}
    section.update(extra)
    return {"engines": {"video": section}}


class TestResolveVideoEngine:
    def test_normal_engine_returned(self, fake_video_registry) -> None:
        engine = resolve_video_engine(_cfg("fake-video"))
        assert engine.engine_name == "fake-video"

    def test_unregistered_default_falls_back_to_chain(self, fake_video_registry, caplog) -> None:
        """Stale default (unregistered) → chain's first available engine + warning."""
        cfg = _cfg("ffmpeg", chain=["fake-video"])
        engine = resolve_video_engine(cfg)
        assert engine.engine_name == "fake-video"

    def test_unregistered_default_and_empty_chain_raises(self, fake_video_registry) -> None:
        """No fallback available → the original EngineNotFoundError propagates."""
        with pytest.raises(EngineNotFoundError) as excinfo:
            resolve_video_engine(_cfg("ffmpeg", chain=[]))
        assert "ffmpeg" in str(excinfo.value)

    def test_registered_but_unavailable_default_raises_loudly(self, fake_video_registry) -> None:
        """A *registered* default that fails check_available does NOT silently
        fall back — explicit failure is the #414 contract."""
        cfg = _cfg("fake-video", **{"fake-video": {"unavailable": True}})
        with pytest.raises(EngineUnavailableError):
            resolve_video_engine(cfg)

    def test_fallback_skips_unavailable_chain_entries(self, fake_video_registry) -> None:
        """The chain walk honours per-engine availability."""
        cfg = _cfg(
            "ffmpeg",
            chain=["nonexistent", "fake-video"],
        )
        engine = resolve_video_engine(cfg)
        assert engine.engine_name == "fake-video"
