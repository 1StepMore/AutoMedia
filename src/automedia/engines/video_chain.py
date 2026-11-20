"""Video engine chain executor with retryable-only fallback (#576).

The video track used to resolve a single engine and render once: a transient
render failure (Remotion's WSL ``browser-connect timeout``) failed the whole
video track even when another engine in ``engines.video.chain`` could have
produced the file.  This module walks the configured chain in order and only
falls through on **retryable** failures:

- render error / timeout / non-zero engine subprocess exit → try the next
  engine in ``engines.video.chain``;
- deterministic failures (missing browser/binary, ``video_engine_unavailable``
  / ``FFmpeg not found``, invalid assets such as no storyboard, no audio, or a
  failed template validation) → fail immediately, never retry on another
  engine.

A single project also has a hard render budget of ``2 × single-engine
timeout``.  Once the cumulative wall-clock time of every attempt exceeds it,
the executor fails with the attempted-engine list and their durations instead
of relaying indefinitely.

Every fallback leaves a trace: the result carries ``engine_used`` (the engine
that actually produced the file), a human-readable ``fallback_reason`` naming
the failed engine, and a ``fallback_chain`` of per-attempt records.  A
single-engine success returns an empty chain so callers do not write fallback
fields into existing artifacts/snapshots.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from structlog import get_logger

from automedia.engines.base import BaseVideoEngine
from automedia.engines.errors import (
    EngineExecutionError,
    EngineNotFoundError,
    EngineUnavailableError,
)

log = get_logger(__name__)

_DEFAULT_ENGINE_TIMEOUT_S: float = 300.0
"""Fallback single-engine timeout when neither ``engines.video.timeout`` nor a
per-engine ``timeout`` is configured (matches the hyperframes default, #577)."""

_ERROR_SUMMARY_LIMIT = 300

_DETERMINISTIC_MARKERS: tuple[str, ...] = (
    "video_engine_unavailable",
    "ffmpeg not found",
    "hyperframes cli not found",
    "node not found",
    "not found on path",
    "not installed",
    "no images provided",
    "no images",
    "no audio",
    "requires a narration-aligned scene timeline",
    "scene timeline",
    "template validation failed",
    "invalid template",
    "does not match the target size",
    "browser launch failed",
    "browser executable",
    "missing browser",
    "chrome not found",
)
"""Failure markers that are deterministic: switching engines cannot fix them.

Matched case-insensitively against the exception message.  Timeouts and
non-zero renders deliberately do not appear here — those are retryable.
"""


class VideoRenderBudgetError(EngineExecutionError):
    """Raised when the cumulative render time exceeds ``2 × timeout``."""

    def __init__(
        self,
        *,
        total_s: float,
        budget_s: float,
        timeout_s: float,
        attempts: list[VideoChainAttempt],
    ) -> None:
        self.total_s = total_s
        self.budget_s = budget_s
        self.timeout_s = timeout_s
        self.attempts = attempts
        details = (
            f"video render budget exceeded: cumulative {total_s:.1f}s > "
            f"{budget_s:.1f}s (2 × single-engine timeout {timeout_s:.1f}s). "
            f"Attempted engines: {_attempts_summary(attempts)}"
        )
        super().__init__(engine_name="video-chain", details=details)


@dataclass(frozen=True)
class VideoChainAttempt:
    """One engine attempt in a chain run."""

    engine: str
    result: str
    duration_s: float
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "result": self.result,
            "duration_s": round(self.duration_s, 3),
            "error": self.error,
        }


@dataclass(frozen=True)
class VideoChainResult:
    """Outcome of a successful chain walk."""

    output_path: str
    engine_used: str
    attempts: tuple[VideoChainAttempt, ...] = ()
    fallback_reason: str = ""
    degraded: bool = False
    degraded_reason: str = ""

    @property
    def used_fallback(self) -> bool:
        return len(self.attempts) > 1

    @property
    def fallback_chain(self) -> list[dict[str, Any]]:
        """Per-attempt records; empty for a single-engine success (#576)."""
        if not self.used_fallback:
            return []
        return [attempt.as_dict() for attempt in self.attempts]


def _error_summary(exc: BaseException) -> str:
    text = str(exc).replace("\n", " ").strip()
    return text[:_ERROR_SUMMARY_LIMIT]


def _attempts_summary(attempts: list[VideoChainAttempt]) -> str:
    if not attempts:
        return "none"
    return "; ".join(
        f"{attempt.engine} ({attempt.result}, {attempt.duration_s:.1f}s: {attempt.error})"
        for attempt in attempts
    )


def is_retryable_video_error(exc: BaseException) -> bool:
    """Return whether *exc* is a retryable video-engine failure (#576).

    Only :class:`EngineExecutionError` is considered retryable, and even then
    deterministic messages (missing binary/browser, invalid assets) win.
    :class:`EngineUnavailableError` / :class:`EngineNotFoundError` are always
    deterministic — an unavailable engine is not a transient render failure.
    """
    if isinstance(exc, (EngineUnavailableError, EngineNotFoundError)):
        return False
    if not isinstance(exc, EngineExecutionError):
        return False
    text = str(exc).lower()
    return not any(marker in text for marker in _DETERMINISTIC_MARKERS)


def _video_config(config: dict[str, Any] | None) -> dict[str, Any]:
    engines = (config or {}).get("engines")
    if not isinstance(engines, dict):
        return {}
    video = engines.get("video")
    return dict(video) if isinstance(video, dict) else {}


def _chain_names(config: dict[str, Any] | None) -> list[str]:
    """Ordered video engine names from ``engines.video.chain`` (no probing)."""
    from automedia.engines import _chain_plan
    from automedia.engines.registry import EngineRegistry

    names, _explicit = _chain_plan("video", _video_config(config), EngineRegistry())
    return names


def _resolve_candidate(name: str, config: dict[str, Any] | None) -> BaseVideoEngine:
    """Resolve *name* exactly as the chain would, including availability."""
    from automedia.engines import resolve_engine

    cfg: dict[str, Any] = dict(config or {})
    engines = dict(cfg.get("engines") or {})
    video = dict(engines.get("video") or {})
    video["default"] = name
    engines["video"] = video
    cfg["engines"] = engines
    return cast(BaseVideoEngine, resolve_engine("video", cfg))


def single_engine_timeout(config: dict[str, Any] | None, names: list[str]) -> float:
    """Resolve the single-engine timeout used for the project budget.

    Priority: ``engines.video.timeout`` (the #577-style shared setting), then
    the largest per-engine ``timeout`` in the chain, then 300 s.
    """
    video = _video_config(config)
    explicit = video.get("timeout")
    if explicit is not None:
        try:
            return max(0.001, float(explicit))
        except (TypeError, ValueError):
            pass
    values: list[float] = []
    for name in names:
        per_engine = video.get(name)
        if isinstance(per_engine, dict) and per_engine.get("timeout") is not None:
            try:
                values.append(float(per_engine["timeout"]))
            except (TypeError, ValueError):
                continue
    if values:
        return max(values)
    return _DEFAULT_ENGINE_TIMEOUT_S


def _budget_error(
    total_s: float,
    budget_s: float,
    timeout_s: float,
    attempts: list[VideoChainAttempt],
) -> VideoRenderBudgetError:
    return VideoRenderBudgetError(
        total_s=total_s,
        budget_s=budget_s,
        timeout_s=timeout_s,
        attempts=attempts,
    )


def render_video_with_fallback(
    assets: dict[str, Any],
    output_path: str,
    config: dict[str, Any] | None = None,
    *,
    clock: Callable[[], float] | None = None,
) -> VideoChainResult:
    """Render *assets* through the video chain, falling back only when safe.

    Parameters
    ----------
    assets:
        Engine asset dictionary (images/audio/scenes/...).
    output_path:
        Destination mp4 path passed to every engine.
    config:
        Merged pipeline configuration; ``engines.video.chain`` is the order.
    clock:
        Monotonic clock injection point (tests use a deterministic fake).

    Returns
    -------
    VideoChainResult
        The first successful render plus trace fields.

    Raises
    ------
    VideoRenderBudgetError
        Cumulative render time exceeded ``2 × single-engine timeout``.
    EngineExecutionError
        Every candidate failed, or a deterministic failure stopped the chain.
    """
    now = clock or time.monotonic
    names = _chain_names(config)
    if not names:
        raise EngineExecutionError(
            engine_name="video-chain",
            details="No video engine candidates configured in engines.video.chain.",
        )

    timeout_s = single_engine_timeout(config, names)
    budget_s = 2 * timeout_s
    started = now()
    attempts: list[VideoChainAttempt] = []

    for index, name in enumerate(names):
        elapsed = now() - started
        if elapsed > budget_s:
            raise _budget_error(elapsed, budget_s, timeout_s, attempts)

        attempt_started = now()
        try:
            engine = _resolve_candidate(name, config)
        except (EngineUnavailableError, EngineNotFoundError) as exc:
            duration = max(0.0, now() - attempt_started)
            attempts.append(
                VideoChainAttempt(
                    engine=name,
                    result="deterministic",
                    duration_s=duration,
                    error=_error_summary(exc),
                )
            )
            raise EngineExecutionError(
                engine_name=name,
                details=(
                    f"deterministic failure — not retrying another engine: "
                    f"{_error_summary(exc)}. Attempted engines: {_attempts_summary(attempts)}"
                ),
                cause=exc,
            ) from exc
        except Exception as exc:
            duration = max(0.0, now() - attempt_started)
            attempts.append(
                VideoChainAttempt(
                    engine=name,
                    result="deterministic",
                    duration_s=duration,
                    error=_error_summary(exc),
                )
            )
            raise EngineExecutionError(
                engine_name=name,
                details=(
                    f"deterministic failure — not retrying another engine: "
                    f"{_error_summary(exc)}. Attempted engines: {_attempts_summary(attempts)}"
                ),
                cause=exc,
            ) from exc

        try:
            rendered = engine.render(assets, output_path)
            duration = max(0.0, now() - attempt_started)
            attempts.append(
                VideoChainAttempt(
                    engine=name,
                    result="success",
                    duration_s=duration,
                )
            )
            total = now() - started
            if total > budget_s:
                raise _budget_error(total, budget_s, timeout_s, attempts)

            failed = [attempt for attempt in attempts if attempt.result != "success"]
            reason = "; ".join(
                f"{attempt.engine}: {attempt.error}" for attempt in failed
            )
            return VideoChainResult(
                output_path=str(rendered or output_path),
                engine_used=name,
                attempts=tuple(attempts),
                fallback_reason=reason,
                degraded=bool(getattr(engine, "last_render_degraded", False)),
                degraded_reason=str(getattr(engine, "last_render_reason", "") or "")[:300],
            )
        except VideoRenderBudgetError:
            raise
        except Exception as exc:
            duration = max(0.0, now() - attempt_started)
            retryable = is_retryable_video_error(exc)
            attempts.append(
                VideoChainAttempt(
                    engine=name,
                    result="retryable" if retryable else "deterministic",
                    duration_s=duration,
                    error=_error_summary(exc),
                )
            )
            total = now() - started
            if total > budget_s:
                raise _budget_error(total, budget_s, timeout_s, attempts) from exc

            if not retryable:
                raise EngineExecutionError(
                    engine_name=name,
                    details=(
                        f"deterministic failure — not retrying another engine: "
                        f"{_error_summary(exc)}. Attempted engines: "
                        f"{_attempts_summary(attempts)}"
                    ),
                    cause=exc,
                ) from exc

            log.warning(
                "engines.video.retryable_failure",
                engine=name,
                duration_s=round(duration, 3),
                error=_error_summary(exc),
                remaining=list(names[index + 1 :]),
            )
            if index == len(names) - 1:
                raise EngineExecutionError(
                    engine_name=name,
                    details=(
                        f"all video engines failed. Attempted engines: "
                        f"{_attempts_summary(attempts)}"
                    ),
                    cause=exc,
                ) from exc

    raise EngineExecutionError(  # pragma: no cover - loop always returns or raises
        engine_name="video-chain",
        details=f"no engine produced a video. Attempted engines: {_attempts_summary(attempts)}",
    )


__all__ = [
    "VideoChainAttempt",
    "VideoChainResult",
    "VideoRenderBudgetError",
    "is_retryable_video_error",
    "render_video_with_fallback",
    "single_engine_timeout",
]
