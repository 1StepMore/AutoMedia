"""The honest producer behind V0's ``lint_result`` (#470).

V0 declared three criteria but nothing in the pipeline ever wrote
``lint_result``, so the gate reported ``skipped`` forever (capability debt
#448).  This executor makes V0's three *objective* checks real — stdlib only:

1. **SRT/cue structure** — block indexes increase by one, the timing line
   matches ``HH:MM:SS,mmm --> HH:MM:SS,mmm``, and every cue carries the
   ``-->`` separator.  Failures name the offending cue.
2. **Subtitle time monotonicity** — every cue starts at or after the previous
   cue's end.  Overlaps name both cues.
3. **Script field completeness** — every timeline scene carries non-empty
   spoken text (口播) and a positive duration.  Missing fields name the
   scene.

Result shape (consumed by ``gates/lint.py`` unchanged):
``{"errors": int, "warnings": int, "syntax_ok": bool, ...}`` plus forensic
``problems`` / ``warnings_detail`` lists for the gate report.  ``problems``
and ``warnings_detail`` are capped — a clean run stays silent (zero warnings,
zero errors).
"""

from __future__ import annotations

import re
from typing import Any

#: Upper bound on recorded warnings — a clean or near-clean run must not turn
#: into warning noise (contract DoD 4).
_MAX_RECORDED_WARNINGS: int = 10

#: ``00:00:01,240 --> 00:00:04,880`` — the only cue timing line shape.
_SRT_TIME_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*$"
)

#: A cue's display text must not be empty once markup is gone.
_CUE_TEXT_MIN_CHARS: int = 1


def _parse_srt_timestamp(match: re.Match[str], half: int) -> float:
    base = 1 if half == 0 else 5
    hours, minutes, seconds, millis = (int(match.group(base + i)) for i in range(4))
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def _lint_srt_structure(srt_text: str) -> tuple[list[str], bool]:
    """Check cue indexes, the ``-->`` timing line shape and text presence.

    Returns ``(problems, syntax_ok)``; every problem names its cue.
    """
    problems: list[str] = []
    blocks = [b for b in re.split(r"\n\s*\n", srt_text.strip()) if b.strip()]
    if not blocks:
        return ["SRT is empty — no cues to inspect"], False

    previous_index: int | None = None
    saw_timing = False
    for block_no, block in enumerate(blocks, start=1):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        position = f"cue {block_no}"
        # Index line: strictly increasing integers.
        index_line = lines[0].strip()
        if not index_line.isdigit():
            problems.append(f"{position}: index line {index_line!r} is not a number")
            index = -1
        else:
            index = int(index_line)
            if previous_index is not None and index != previous_index + 1:
                problems.append(f"{position}: cue index {index} does not follow {previous_index}")
            previous_index = index
        # Timing line with the --> separator.
        timing = lines[1].strip() if len(lines) > 1 else ""
        if "-->" not in timing:
            problems.append(f"{position}: missing '-->' timing line")
        else:
            saw_timing = True
            if not _SRT_TIME_RE.match(timing):
                problems.append(
                    f"{position}: timing line {timing!r} is not 'HH:MM:SS,mmm --> HH:MM:SS,mmm'"
                )
        # Display text.
        text = " ".join(lines[2:]).strip()
        if len(text) < _CUE_TEXT_MIN_CHARS:
            problems.append(f"{position}: cue has no display text")
    return problems, saw_timing


def _lint_srt_monotonic(srt_text: str) -> list[str]:
    """Check that cue times are monotonic and non-overlapping.

    Returns problems, each naming both offending cues.
    """
    problems: list[str] = []
    prev_end: float | None = None
    prev_index: int | None = None
    for block_no, block in enumerate(
        [b for b in re.split(r"\n\s*\n", srt_text.strip()) if b.strip()], start=1
    ):
        lines = [line for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        match = _SRT_TIME_RE.match(lines[1].strip())
        if match is None:
            continue
        start = _parse_srt_timestamp(match, 0)
        end = _parse_srt_timestamp(match, 1)
        index = int(lines[0].strip()) if lines[0].strip().isdigit() else block_no
        if end < start:
            problems.append(f"cue {index}: end {end:.3f}s is before start {start:.3f}s")
        if prev_end is not None and start < prev_end:
            problems.append(
                f"cue {index}: start {start:.3f}s overlaps previous cue "
                f"{prev_index} (ends {prev_end:.3f}s)"
            )
        prev_end, prev_index = max(prev_end or 0.0, end), index
    return problems


def _lint_script_fields(scenes: list[dict[str, Any]]) -> tuple[list[str], bool]:
    """Check every timeline scene carries spoken text and a positive duration.

    Returns ``(problems, checked)`` — ``checked=False`` means the run had no
    scene timeline at all (legacy single-track path); the caller records that
    as a check-level skip naming what is missing, never as a pass.
    """
    if not scenes:
        return [], False
    problems: list[str] = []
    for scene in scenes:
        sid = scene.get("id") or f"index {scene.get('index')}"
        if not str(scene.get("text") or "").strip():
            problems.append(f"scene {sid}: missing spoken text (口播)")
        duration = scene.get("duration")
        if not isinstance(duration, (int, float)) or duration <= 0:
            problems.append(f"scene {sid}: missing positive duration (时长)")
    return problems, True


def run_lint(gate_context: dict[str, Any]) -> dict[str, Any] | None:
    """Produce V0's ``lint_result`` from the run's real artifacts (#470).

    Reads the SRT (``srt_text`` / ``subtitles_path``) and the scene timeline
    (``video_timeline_scenes``).  Returns ``None`` when the run produced no
    SRT at all — the caller then leaves ``lint_result`` unwritten and V0
    reports its honest skip as before.
    """
    srt_text = str(gate_context.get("srt_text") or "")
    if not srt_text:
        subtitles_path = str(gate_context.get("subtitles_path") or "")
        if subtitles_path:
            try:
                with open(subtitles_path, encoding="utf-8") as fh:
                    srt_text = fh.read()
            except OSError:
                return None
    if not srt_text.strip():
        return None

    structure_problems, syntax_ok = _lint_srt_structure(srt_text)
    monotonic_problems = _lint_srt_monotonic(srt_text)
    scene_problems, scenes_checked = _lint_script_fields(
        list(gate_context.get("video_timeline_scenes") or [])
    )

    problems = structure_problems + monotonic_problems + scene_problems
    warnings_detail: list[str] = []
    if not scenes_checked:
        warnings_detail.append(
            "script-field check skipped: no scene timeline in this run "
            "(legacy single-track path) — 分镜/口播/时长 fields unavailable"
        )

    return {
        "errors": len(problems),
        "warnings": min(len(warnings_detail), _MAX_RECORDED_WARNINGS),
        "syntax_ok": syntax_ok,
        "problems": problems[:50],
        "warnings_detail": warnings_detail[:_MAX_RECORDED_WARNINGS],
        "checks": {
            "srt_structure": "passed" if not structure_problems else "failed",
            "time_monotonic": "passed" if not monotonic_problems else "failed",
            "script_fields": (
                "passed"
                if scenes_checked and not scene_problems
                else ("failed" if scenes_checked else "skipped")
            ),
        },
    }


__all__ = ["run_lint"]
