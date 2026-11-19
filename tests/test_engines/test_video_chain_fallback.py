"""Video engine chain fallback (#576).

The executor may only fall through on retryable failures, must stop on
deterministic failures, must enforce ``2 × single-engine timeout`` as a
project-wide budget, and must not pollute a single-engine success with
fallback fields.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from automedia.engines.errors import EngineExecutionError, EngineUnavailableError
from automedia.engines.video_chain import (
    VideoRenderBudgetError,
    render_video_with_fallback,
)


class _Clock:
    """Deterministic monotonic clock advanced by fake engine renders."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _FakeChainVideoEngine:
    """Video engine double that records calls and optionally fails."""

    def __init__(
        self,
        name: str,
        *,
        error: Exception | None = None,
        advance: float = 0.0,
        clock: _Clock | None = None,
        degraded: bool = False,
        degraded_reason: str = "",
    ) -> None:
        self.engine_name = name
        self._error = error
        self._advance = advance
        self._clock = clock
        self.calls = 0
        self.last_render_degraded = degraded
        self.last_render_reason = degraded_reason

    def check_available(self) -> tuple[bool, str]:
        return True, "ok"

    def render(self, assets: dict[str, Any], output_path: str) -> str:
        self.calls += 1
        if self._clock is not None:
            self._clock.advance(self._advance)
        if self._error is not None:
            raise self._error
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-mp4")
        return os.path.abspath(output_path)


def _config(chain: list[str], *, timeout: float | None = None) -> dict[str, Any]:
    video: dict[str, Any] = {"chain": chain}
    if timeout is not None:
        video["timeout"] = timeout
    return {"engines": {"video": video}}


def _install_engines(
    monkeypatch: pytest.MonkeyPatch, engines: dict[str, _FakeChainVideoEngine]
) -> None:
    def _resolve(modality: str, config: dict[str, Any] | None = None) -> Any:
        assert modality == "video"
        name = ((config or {}).get("engines") or {}).get("video", {}).get("default")
        return engines[name]

    monkeypatch.setattr("automedia.engines.resolve_engine", _resolve)


def test_retryable_failure_falls_back_to_next_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clock = _Clock()
    first = _FakeChainVideoEngine(
        "remotion",
        error=EngineExecutionError(
            "remotion", "remotion render timed out after 25s (browser-connect timeout)"
        ),
        advance=25.0,
        clock=clock,
    )
    second = _FakeChainVideoEngine("hyperframes", advance=5.0, clock=clock)
    _install_engines(monkeypatch, {"remotion": first, "hyperframes": second})

    result = render_video_with_fallback(
        {"images": ["a.png"], "audio": "a.mp3"},
        str(tmp_path / "out.mp4"),
        _config(["remotion", "hyperframes"], timeout=100),
        clock=clock,
    )

    assert result.engine_used == "hyperframes"
    assert "remotion" in result.fallback_reason
    assert "timed out" in result.fallback_reason
    assert result.used_fallback is True
    assert [item["engine"] for item in result.fallback_chain] == ["remotion", "hyperframes"]
    assert result.fallback_chain[0]["result"] == "retryable"
    assert result.fallback_chain[-1]["result"] == "success"
    assert os.path.isfile(result.output_path)
    assert first.calls == 1 and second.calls == 1


def test_deterministic_failure_does_not_try_next_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clock = _Clock()
    first = _FakeChainVideoEngine(
        "remotion",
        error=EngineExecutionError("remotion", "FFmpeg not found on PATH"),
        advance=2.0,
        clock=clock,
    )
    second = _FakeChainVideoEngine("hyperframes", clock=clock)
    _install_engines(monkeypatch, {"remotion": first, "hyperframes": second})

    with pytest.raises(EngineExecutionError, match="deterministic failure") as excinfo:
        render_video_with_fallback(
            {"images": ["a.png"], "audio": "a.mp3"},
            str(tmp_path / "out.mp4"),
            _config(["remotion", "hyperframes"], timeout=100),
            clock=clock,
        )

    assert "FFmpeg not found" in str(excinfo.value)
    assert first.calls == 1
    assert second.calls == 0


def test_unavailable_engine_is_deterministic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clock = _Clock()
    second = _FakeChainVideoEngine("hyperframes", clock=clock)

    def _resolve(modality: str, config: dict[str, Any] | None = None) -> Any:
        name = ((config or {}).get("engines") or {}).get("video", {}).get("default")
        if name == "remotion":
            raise EngineUnavailableError("remotion", "node not found on PATH", "install node")
        return second

    monkeypatch.setattr("automedia.engines.resolve_engine", _resolve)

    with pytest.raises(EngineExecutionError, match="deterministic failure"):
        render_video_with_fallback(
            {"images": ["a.png"], "audio": "a.mp3"},
            str(tmp_path / "out.mp4"),
            _config(["remotion", "hyperframes"], timeout=100),
            clock=clock,
        )

    assert second.calls == 0


def test_cumulative_budget_fails_with_attempt_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clock = _Clock()
    first = _FakeChainVideoEngine(
        "remotion",
        error=EngineExecutionError("remotion", "remotion render timed out after 15s"),
        advance=15.0,
        clock=clock,
    )
    second = _FakeChainVideoEngine(
        "hyperframes",
        error=EngineExecutionError("hyperframes", "hyperframes render timed out after 10s"),
        advance=10.0,
        clock=clock,
    )
    _install_engines(monkeypatch, {"remotion": first, "hyperframes": second})

    with pytest.raises(VideoRenderBudgetError, match="budget exceeded") as excinfo:
        render_video_with_fallback(
            {"images": ["a.png"], "audio": "a.mp3"},
            str(tmp_path / "out.mp4"),
            _config(["remotion", "hyperframes"], timeout=10),
            clock=clock,
        )

    message = str(excinfo.value)
    assert "remotion" in message and "15.0s" in message
    assert "hyperframes" in message and "10.0s" in message
    assert first.calls == 1 and second.calls == 1


def test_single_engine_success_has_no_fallback_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clock = _Clock()
    only = _FakeChainVideoEngine("hyperframes", advance=3.0, clock=clock)
    _install_engines(monkeypatch, {"hyperframes": only})

    result = render_video_with_fallback(
        {"images": ["a.png"], "audio": "a.mp3"},
        str(tmp_path / "out.mp4"),
        _config(["hyperframes"], timeout=100),
        clock=clock,
    )

    assert result.engine_used == "hyperframes"
    assert result.used_fallback is False
    assert result.fallback_chain == []
    assert result.fallback_reason == ""
    assert only.calls == 1
