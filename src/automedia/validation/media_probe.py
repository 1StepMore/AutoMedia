"""Read-only media/artifact probes for validation expectations.

Every probe is a pure read: it inspects one file and returns a plain dict with
an ``ok`` flag plus the observed facts.  Probes **never raise** — a missing
file, an unreadable image, a malformed subtitle, or a broken subprocess all
come back as ``ok: False`` with an ``error`` string, because an expectation
must be able to fail loudly, never crash the grader and never silently pass.

Media inspection delegates to ``ffprobe`` (a subprocess); image inspection uses
Pillow; text/SRT/glob inspection is pure stdlib.  This module deliberately
imports nothing from :mod:`automedia.validation.schema` or
:mod:`automedia.validation.expects` so the evaluator can depend on it without a
cycle.  It also never opens a network connection.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

_FFPROBE_TIMEOUT_SECONDS = 20.0
"""Wall-clock ceiling for one ffprobe invocation."""

_SRT_TIMING_RE: re.Pattern[str] = re.compile(
    r"(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})"
)
"""One SRT cue timing line: ``HH:MM:SS,mmm --> HH:MM:SS,mmm``."""

_FENCE_PREFIXES: tuple[str, ...] = ("```", "~~~")
"""Markdown code-fence openers; fenced blocks never count as paragraphs."""

_SENTENCE_TERMINATORS: frozenset[str] = frozenset("。！？.!?")
"""Sentence-ending punctuation counted by :func:`probe_text`."""

_IMAGE_SUFFIXES: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
)
"""Image suffixes used as a fallback when the step check type is generic."""

_NON_UNIFORM_STDDEV: float = 3.0
"""Grayscale stddev at or above which an image counts as non-uniform.

A flat fill has stddev 0.0; real photographic content is far above 3.0.  The
threshold is intentionally low so a gradient/photo passes and a solid card
fails.
"""


def probe_image(path: str | Path) -> dict[str, Any]:
    """Inspect one image file with Pillow.

    Returns ``{"ok", "width", "height", "mode", "format", "size_bytes",
    "non_uniform", "stddev", "error"}``.  ``stddev`` is the grayscale
    ``ImageStat`` standard deviation; ``non_uniform`` is True when it reaches
    :data:`_NON_UNIFORM_STDDEV` (a solid fill is False).  Non-image or missing
    files yield ``ok: False``.
    """
    result: dict[str, Any] = {
        "ok": False,
        "width": None,
        "height": None,
        "mode": None,
        "format": None,
        "size_bytes": 0,
        "non_uniform": False,
        "stddev": None,
        "error": None,
    }
    target = Path(path)
    if not target.is_file():
        result["error"] = f"file not found: {target}"
        return result
    try:
        result["size_bytes"] = target.stat().st_size
    except OSError as exc:
        result["error"] = f"cannot stat image: {exc}"
        return result
    try:
        from PIL import Image, ImageStat
    except ImportError as exc:  # pragma: no cover - Pillow is a core dependency
        result["error"] = f"Pillow unavailable: {exc}"
        return result
    try:
        with Image.open(target) as image:
            width, height = image.size
            mode = image.mode
            image_format = image.format
            gray = image.convert("L")
            stats = ImageStat.Stat(gray)
            stddev = float(stats.stddev[0]) if stats.stddev else 0.0
        result.update(
            ok=True,
            width=int(width),
            height=int(height),
            mode=mode,
            format=image_format,
            stddev=stddev,
            non_uniform=stddev >= _NON_UNIFORM_STDDEV,
        )
    except Exception as exc:
        result["error"] = f"not a readable image: {exc}"
    return result


def probe_media(path: str | Path) -> dict[str, Any]:
    """Inspect one audio/video file with ``ffprobe``.

    Returns ``{"ok", "duration_s", "width", "height", "bitrate_kbps", "codec",
    "decodable", "has_video", "has_audio", "size_bytes", "format", "error"}``.
    ``decodable`` is True only when ``ffprobe`` exits 0 and reports a
    ``format`` or ``streams`` block.  An audio-only file reports width/height
    0 and still carries its codec/bitrate.  A missing ``ffprobe`` is a hard
    failure (``ok: False``) — never a silent pass.
    """
    result: dict[str, Any] = {
        "ok": False,
        "duration_s": None,
        "bitrate_kbps": None,
        "width": 0,
        "height": 0,
        "codec": None,
        "decodable": False,
        "has_video": False,
        "has_audio": False,
        "size_bytes": 0,
        "format": None,
        "error": None,
    }
    target = Path(path)
    if not target.is_file():
        result["error"] = f"file not found: {target}"
        return result
    try:
        result["size_bytes"] = target.stat().st_size
    except OSError as exc:
        result["error"] = f"cannot stat media: {exc}"
        return result
    ffprobe = _find_ffprobe()
    if ffprobe is None:
        result["error"] = "ffprobe not found"
        return result
    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(target),
    ]
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, local file
            command,
            capture_output=True,
            text=True,
            timeout=_FFPROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        result["error"] = f"ffprobe failed: {exc}"
        return result
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip() or f"exit {proc.returncode}"
        result["error"] = f"ffprobe error: {detail}"
        return result
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        result["error"] = f"ffprobe output not JSON: {exc}"
        return result
    if not isinstance(parsed, dict):
        result["error"] = f"ffprobe output is {type(parsed).__name__}, not an object"
        return result
    fmt = parsed.get("format")
    raw_streams = parsed.get("streams")
    streams = raw_streams if isinstance(raw_streams, list) else []
    if not isinstance(fmt, dict) and not streams:
        result["error"] = "ffprobe reported no format or stream block"
        return result
    fmt_dict = fmt if isinstance(fmt, dict) else {}
    video_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "video"
    ]
    audio_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "audio"
    ]
    codec_stream = (
        video_streams[0] if video_streams else (audio_streams[0] if audio_streams else None)
    )
    result.update(
        ok=True,
        decodable=True,
        format=_str_or_none(fmt_dict.get("format_name")),
        duration_s=_media_duration(fmt_dict, streams),
        bitrate_kbps=_media_bitrate_kbps(fmt_dict, streams),
        codec=_str_or_none(codec_stream.get("codec_name")) if codec_stream else None,
        has_video=bool(video_streams),
        has_audio=bool(audio_streams),
    )
    if video_streams:
        result["width"] = _int_or_zero(video_streams[0].get("width"))
        result["height"] = _int_or_zero(video_streams[0].get("height"))
    return result


def probe_video_thumbnail(path: str | Path) -> dict[str, Any]:
    """Return ``ffprobe``-derived width/height for one video (thumbnail facts).

    This intentionally delegates to :func:`probe_media`; the validation layer
    only needs the frame dimensions, and one probe keeps the observed facts
    consistent with the rest of the media assertions.
    """
    return probe_media(path)


def probe_text(path: str | Path) -> dict[str, Any]:
    """Inspect one Markdown/text artifact.

    ``paragraphs`` counts blank-line-separated non-empty blocks, excluding
    heading lines (starting with ``#``) and fenced code blocks.  ``headings``
    counts ATX heading lines; ``has_heading`` is True when any line starts with
    ``"# "``.  ``sentences`` counts ``。！？.!?`` terminators; ``chars`` is the
    stripped text length.
    """
    result: dict[str, Any] = {
        "ok": False,
        "paragraphs": 0,
        "headings": 0,
        "chars": 0,
        "has_heading": False,
        "sentences": 0,
        "error": None,
    }
    target = Path(path)
    if not target.is_file():
        result["error"] = f"file not found: {target}"
        return result
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result["error"] = f"cannot read text: {exc}"
        return result
    paragraphs = 0
    headings = 0
    in_block = False
    in_fence = False
    has_heading = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(_FENCE_PREFIXES):
            if in_block:
                paragraphs += 1
                in_block = False
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped:
            if in_block:
                paragraphs += 1
                in_block = False
            continue
        if stripped.startswith("#"):
            headings += 1
            if stripped.startswith("# "):
                has_heading = True
            if in_block:
                paragraphs += 1
                in_block = False
            continue
        in_block = True
    if in_block:
        paragraphs += 1
    result.update(
        ok=True,
        paragraphs=paragraphs,
        headings=headings,
        chars=len(text.strip()),
        has_heading=has_heading,
        sentences=sum(1 for char in text if char in _SENTENCE_TERMINATORS),
    )
    return result


def probe_srt(path: str | Path) -> dict[str, Any]:
    """Parse one SRT subtitle file.

    ``cues`` counts blocks with a valid timestamp line; ``monotonic`` is True
    iff every cue starts at or after the previous cue's end (1 ms tolerance),
    which is the no-overlap contract.  ``first_start_s``/``last_end_s`` are the
    first cue's start and the final cue's end in seconds.
    """
    result: dict[str, Any] = {
        "ok": False,
        "cues": 0,
        "monotonic": True,
        "first_start_s": None,
        "last_end_s": None,
        "error": None,
    }
    target = Path(path)
    if not target.is_file():
        result["error"] = f"file not found: {target}"
        return result
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result["error"] = f"cannot read subtitle: {exc}"
        return result
    cues = 0
    monotonic = True
    first_start: float | None = None
    last_end: float | None = None
    previous_end: float | None = None
    for line in text.splitlines():
        match = _SRT_TIMING_RE.search(line)
        if match is None:
            continue
        start = _srt_seconds(match.groups()[:4])
        end = _srt_seconds(match.groups()[4:])
        cues += 1
        if first_start is None:
            first_start = start
        if start > end:
            monotonic = False
        if previous_end is not None and start < previous_end - 0.001:
            monotonic = False
        previous_end = end
        last_end = end
    result.update(
        ok=True,
        cues=cues,
        monotonic=monotonic,
        first_start_s=first_start,
        last_end_s=last_end,
    )
    return result


def glob_artifacts(root: str | Path, pattern: str) -> list[str]:
    """Every absolute path under ``root`` matching ``pattern``, sorted.

    The return type is a list of strings (absolute paths) so adapter facts are
    JSON-serialisable.  A bad pattern or unreadable tree yields ``[]`` rather
    than an exception.
    """
    try:
        base = Path(root).expanduser()
        matches = sorted(base.rglob(pattern), key=str)
        return [str(path.resolve()) for path in matches]
    except (OSError, ValueError, NotImplementedError):
        return []


# --- helpers ---------------------------------------------------------------


def _find_ffprobe() -> str | None:
    """Prefer ``ffprobe`` on PATH, fall back to ``~/.local/bin/ffprobe``."""
    found = shutil.which("ffprobe")
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / "ffprobe"
    if candidate.is_file():
        return str(candidate)
    return None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_or_zero(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _media_duration(fmt: dict[str, Any], streams: list[Any]) -> float | None:
    duration = _float_or_none(fmt.get("duration"))
    if duration is not None:
        return duration
    for stream in streams:
        if isinstance(stream, dict):
            duration = _float_or_none(stream.get("duration"))
            if duration is not None:
                return duration
    return None


def _media_bitrate_kbps(fmt: dict[str, Any], streams: list[Any]) -> int | None:
    """Prefer a stream ``bit_rate``, else the container ``bit_rate`` (kbps)."""
    bits: float | None = None
    for stream in streams:
        if isinstance(stream, dict):
            bits = _float_or_none(stream.get("bit_rate"))
            if bits is not None:
                break
    if bits is None:
        bits = _float_or_none(fmt.get("bit_rate"))
    return None if bits is None else round(bits / 1000.0)


def _srt_seconds(groups: tuple[str, ...]) -> float:
    hours, minutes, seconds, millis = (int(part) for part in groups)
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def is_image_path(path: str | Path) -> bool:
    """True when the suffix looks like a still image (probe-selection fallback)."""
    return Path(path).suffix.lower() in _IMAGE_SUFFIXES
