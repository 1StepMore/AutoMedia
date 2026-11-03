"""Narration-aligned scene timeline for the video track (#351).

Implements the promo kit's 时间轴-旁白分段对齐法
(``promo/docs/时间轴-旁白分段对齐法.md``):

1. Split the narration into scenes at sentence boundaries.
2. Synthesize each segment separately (engines.tts chain — Azure leads when
   configured, Piper/edge-tts fall through).
3. Measure each segment's real duration with ``ffprobe``.
4. Scene cut points = the accumulated segment durations (a cut lands on a
   sentence end); total DUR = the sum; per-scene frames = duration × fps.

Degradation is honest and logged: when per-segment TTS or ffprobe is
unavailable, :func:`build_scene_timeline` falls back to the legacy shape
(one narration track, scenes evenly split over the measured total) and says
so in the returned ``timeline_mode`` — callers surface that in the
gate-report media_stage block.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Protocol

from structlog import get_logger

logger = get_logger(__name__)

#: Cap on scene count — 30–60s videos read best at 3–6 scenes.
MAX_SCENES: int = 6

#: Segments shorter than this are flash-cut bait (e.g. "好！") and get
#: merged into the previous sentence; full short sentences survive.
_MIN_SEGMENT_CHARS: int = 6

_SENTENCE_RE = re.compile(r"[^。！？!?；;。\n]+[。！？!?；;。\n]?")

_SEGMENT_FILE_TEMPLATE = "narration-segment-{i:02d}.mp3"

_PROBE_TIMEOUT: int = 30
_CONCAT_TIMEOUT: int = 120


class _TTSSynthesizer(Protocol):
    """The slice of AudioPipeline the timeline builder needs."""

    def generate_tts(self, text: str, voice: str = "", output_path: str = "") -> str: ...


def split_narration(text: str, max_scenes: int = MAX_SCENES) -> list[str]:
    """Split *text* into 1..*max_scenes* sentence-aligned segments.

    Splits on sentence-ending punctuation (。！？!?；;). Segments shorter
    than ``_MIN_SEGMENT_CHARS`` are merged into the previous one; when the
    result still exceeds *max_scenes*, the longest segments are merged
    pairwise until it fits. Text without sentence punctuation yields one
    segment (the whole text).
    """
    text = (text or "").strip()
    if not text:
        return []

    raw = [m.group(0).strip() for m in _SENTENCE_RE.finditer(text)]
    segments = [s for s in raw if s]
    if not segments:
        return [text]

    # Merge tiny fragments (true exclamations) into their predecessor.
    merged: list[str] = []
    for seg in segments:
        if merged and len(seg) < _MIN_SEGMENT_CHARS:
            merged[-1] = merged[-1] + seg
        else:
            merged.append(seg)

    # Too many scenes → merge the shortest neighbours pairwise.
    while len(merged) > max_scenes:
        shortest = min(range(len(merged) - 1), key=lambda i: len(merged[i]) + len(merged[i + 1]))
        merged[shortest] = merged[shortest] + merged[shortest + 1]
        del merged[shortest + 1]

    return merged


def probe_audio_duration(
    audio_path: str,
    ffprobe_cmd: str | list[str] = "ffprobe",
    timeout: int = _PROBE_TIMEOUT,
) -> float | None:
    """Return the audio duration in seconds via ``ffprobe`` (None on failure).

    ``ffprobe`` may live on a different machine than this Python process
    (restricted-hardware setups render inside WSL); callers on such hosts
    pass a WSL-wrapped command prefix, e.g. ``["wsl", "-e", "ffprobe"]``.
    """
    prefix = [ffprobe_cmd] if isinstance(ffprobe_cmd, str) else list(ffprobe_cmd)
    try:
        result = subprocess.run(  # noqa: S603 — fixed argv, internal
            [
                *prefix,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return max(0.0, float(result.stdout.strip()))
    except ValueError:
        return None


def synthesize_scene_narration(
    segments: list[str],
    audio_pipeline: _TTSSynthesizer,
    audio_dir: str,
) -> list[str]:
    """Synthesize each segment via the TTS chain; return the segment paths.

    Raises whatever the synthesizer raises on the first failed segment —
    the caller degrades to the legacy path and logs the reason. Any files
    written before the failure are left for forensics but not returned.
    """
    paths: list[str] = []
    for i, seg in enumerate(segments, start=1):
        # Forward slashes: valid on both Windows and (WSL-)Linux — the same
        # relative path is written by the local TTS and read by WSL-wrapped
        # ffprobe/ffmpeg, so backslash-escape surprises cannot happen.
        seg_base = audio_dir.rstrip("/\\")
        out = f"{seg_base}/{_SEGMENT_FILE_TEMPLATE.format(i=i)}"
        audio_pipeline.generate_tts(seg, output_path=out)
        if not os.path.isfile(out) or os.path.getsize(out) == 0:
            raise RuntimeError(f"segment TTS produced no audio: {out}")
        paths.append(out)
    return paths


def concat_audio(
    files: list[str],
    output_path: str,
    ffmpeg_cmd: str | list[str] = "ffmpeg",
    timeout: int = _CONCAT_TIMEOUT,
) -> str | None:
    """Concatenate audio segments with the ffmpeg concat demuxer.

    Returns *output_path* on success, ``None`` when ffmpeg is unavailable or
    the concat fails (caller keeps the legacy single-track narration).
    """
    if not files:
        return None
    if len(files) == 1 and os.path.abspath(files[0]) == os.path.abspath(output_path):
        return output_path

    if len(files) == 1:
        import shutil as _shutil

        _shutil.copy2(files[0], output_path)
        return output_path

    ffmpeg_prefix = [ffmpeg_cmd] if isinstance(ffmpeg_cmd, str) else list(ffmpeg_cmd)
    listing = output_path + ".concat.txt"
    try:
        with open(listing, "w", encoding="utf-8") as fh:
            for f in files:
                # The concat demuxer resolves relative entries against the
                # LISTING's own directory — write basenames (all segments
                # live in the same dir), escaping single quotes.
                entry = os.path.basename(f)
                fh.write("file '" + entry.replace("'", "'" * 2) + "'\n")
        result = subprocess.run(  # noqa: S603 — fixed argv, internal
            [
                *ffmpeg_prefix,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                listing,
                "-c",
                "copy",
                output_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        if os.path.exists(listing):
            os.remove(listing)
    if result.returncode != 0 or not os.path.isfile(output_path):
        logger.warning("timeline.concat_failed", returncode=result.returncode)
        return None
    return output_path


def build_scene_timeline(
    text: str,
    *,
    audio_pipeline: _TTSSynthesizer,
    audio_dir: str,
    ffprobe_cmd: str | list[str] = "ffprobe",
    ffmpeg_cmd: str | list[str] = "ffmpeg",
    legacy_audio_path: str = "",
) -> dict[str, Any]:
    """Build the narration-aligned scene timeline; degrade honestly.

    Returns one of:

    - ``{"timeline_mode": "narration_aligned", "scenes": [...],
      "narration_path": ..., "total_duration": float}`` — per-scene TTS,
      ffprobe-measured cut points (the promo-kit method).
    - ``{"timeline_mode": "fallback_proportional", "scenes": [...],
      "narration_path": ..., "total_duration": float, "reason": str}`` —
      one narration track, scenes evenly split over the measured duration
      (per-scene text kept; only the cut points are approximate).
    - ``{"timeline_mode": "unavailable", "scenes": [], "reason": str}`` —
      no narration could be produced at all; the caller skips the video
      track with an explicit reason.

    Scene dicts carry ``id / index / start / duration / name / text /
    audio_path`` and are consumed by the hyperframes project provisioning
    (``assets["scenes"]``).
    """
    os.makedirs(audio_dir, exist_ok=True)
    segments = split_narration(text)
    if not segments:
        return {"timeline_mode": "unavailable", "scenes": [], "reason": "empty narration"}

    mode = "narration_aligned"
    segment_files: list[str] = []
    reason = ""
    try:
        segment_files = synthesize_scene_narration(segments, audio_pipeline, audio_dir)
    except Exception as exc:
        mode = "fallback_proportional"
        reason = f"per-segment TTS failed ({exc}); using single-track narration"
        logger.warning("timeline.per_segment_tts_failed", error=str(exc))

    durations: list[float] = []
    narration_path = ""
    if segment_files:
        durations = [probe_audio_duration(f, ffprobe_cmd) or 0.0 for f in segment_files]
        if any(d <= 0 for d in durations):
            mode = "fallback_proportional"
            reason = reason or "ffprobe unavailable — cut points are approximate"
            logger.warning("timeline.ffprobe_unavailable", hint="durations fall back to even split")
        narration_target = audio_dir.rstrip("/\\") + "/narration.mp3"
        narration_path = concat_audio(segment_files, narration_target, ffmpeg_cmd) or ""

    if not narration_path:
        # Legacy single-track path (also covers: per-segment TTS failed, or
        # concat unavailable but a legacy track already exists).
        if legacy_audio_path and os.path.isfile(legacy_audio_path):
            narration_path = legacy_audio_path
        else:
            try:
                narration_path = audio_pipeline.generate_tts(
                    text, output_path=audio_dir.rstrip("/\\") + "/narration.mp3"
                )
            except Exception as exc:
                return {
                    "timeline_mode": "unavailable",
                    "scenes": [],
                    "reason": f"TTS failed: {exc}",
                }
        mode = mode if mode == "fallback_proportional" else "fallback_proportional"
        reason = reason or "concat unavailable — using single-track narration"

    total = probe_audio_duration(narration_path, ffprobe_cmd)
    n = len(segments)
    if not total or total <= 0:
        # No measurable duration: even split over the default scene length.
        total = n * 10.0
        mode = "fallback_proportional"
        reason = reason or "audio duration unmeasurable — default scene length used"

    scenes: list[dict[str, Any]] = []
    if mode == "narration_aligned":
        start = 0.0
        for i, (seg, dur) in enumerate(zip(segments, durations, strict=False), start=1):
            dur = dur if dur > 0 else total / n
            scenes.append(
                {
                    "id": f"scene-{i}",
                    "index": i,
                    "name": f"Scene {i}",
                    "start": round(start, 3),
                    "duration": round(dur, 3),
                    "text": seg,
                    "audio_path": segment_files[i - 1],
                }
            )
            start += dur
    else:
        per = total / n
        start = 0.0
        for i, seg in enumerate(segments, start=1):
            scenes.append(
                {
                    "id": f"scene-{i}",
                    "index": i,
                    "name": f"Scene {i}",
                    "start": round(start, 3),
                    "duration": round(per, 3),
                    "text": seg,
                    "audio_path": "",
                }
            )
            start += per

    return {
        "timeline_mode": mode,
        "scenes": scenes,
        "narration_path": narration_path,
        "total_duration": round(total, 3),
        **({"reason": reason} if reason else {}),
    }
