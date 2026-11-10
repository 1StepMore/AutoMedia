"""V5 MP3 vs SRT Gate — Whisper transcription diff vs SRT text ≥80%.

Checks:
    1. whisper_vs_srt_diff    — diff ratio between Whisper output and SRT text
    2. srt_not_empty          — SRT file content is non-empty
    3. whisper_not_empty      — Whisper transcription is non-empty
    4. structure_label_residue — no script-structure labels in SRT or whisper
       text (#455)

failure_mode = "retry" — on failure, pipeline can retry/fix the gate.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from structlog import get_logger

from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result, missing_input_result
from automedia.gates.base import BaseGate
from automedia.gates.helpers import apply_mock_overrides

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "whisper_vs_srt_diff",
    "srt_not_empty",
    "whisper_not_empty",
    "structure_label_residue",
]

_MIN_DIFF_RATIO: float = 0.80

#: Script-structure patterns that must never survive into the narration audio
#: or the subtitles (#455).  ``strip_narration_markup`` removes them before
#: TTS/SRT, so a hit means structure leaked past the narration boundary.  The
#: diff ratio cannot catch this — SRT and whisper derive from the same
#: cleaned text, so same-source pollution inflates similarity past the
#: threshold and would read as "pass" — hence this check, judged on residue
#: alone and independent of the ratio.
_STRUCTURE_RESIDUE_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("shot_label", re.compile(r"镜头\s*\d+")),
    ("timecode", re.compile(r"\d{1,2}:\d{2}\s*[-–—~至]\s*\d{1,2}:\d{2}")),
    ("spoken_prefix", re.compile(r"口播\s*[:：]")),
    (
        "metadata_label",
        re.compile(
            r"(?:主题|品牌|时长|风格|平台|BGM|音效|转场|字幕|画面|运镜|机位|场景)\s*[:：]",
            re.IGNORECASE,
        ),
    ),
    (
        "transition_tag",
        re.compile(r"\[(?:切|转场|切换|停顿|暂停|淡入|淡出|黑场|闪回|叠化|白闪|黑闪|分屏)\]"),
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_srt_timestamps(srt_text: str) -> str:
    """Strip SRT timestamps and sequence numbers, leaving only dialogue text."""
    # Remove sequence numbers (lines that are just digits)
    lines = re.sub(r"^\d+\s*$", "", srt_text, flags=re.MULTILINE)
    # Remove timestamp lines (00:00:00,000 --> 00:00:01,000)
    lines = re.sub(r"\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}", "", lines)
    # Remove HTML tags
    lines = re.sub(r"<[^>]+>", "", lines)
    # Collapse whitespace
    lines = re.sub(r"\s+", " ", lines).strip()
    return lines


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_whisper_vs_srt_diff(whisper_text: str, srt_text: str) -> CheckResult:
    """Check 1: diff ratio between Whisper output and SRT text ≥80%."""
    name = "whisper_vs_srt_diff"
    if not whisper_text.strip() or not srt_text.strip():
        return {"name": name, "passed": False, "detail": "empty whisper or SRT text"}

    clean_srt = _strip_srt_timestamps(srt_text)
    ratio = SequenceMatcher(None, whisper_text.strip().lower(), clean_srt.lower()).ratio()
    if ratio >= _MIN_DIFF_RATIO:
        return {
            "name": name,
            "passed": True,
            "detail": f"similarity {ratio:.1%} >= {_MIN_DIFF_RATIO:.0%}",
        }
    return {
        "name": name,
        "passed": False,
        "detail": f"similarity {ratio:.1%} < {_MIN_DIFF_RATIO:.0%}",
    }


def _check_srt_not_empty(srt_text: str) -> CheckResult:
    """Check 2: SRT file content is non-empty."""
    name = "srt_not_empty"
    if srt_text.strip():
        return {"name": name, "passed": True, "detail": "SRT text non-empty"}
    return {"name": name, "passed": False, "detail": "SRT text is empty"}


def _structure_residue_hits(text: str) -> list[str]:
    """Count structure-label hits per pattern, e.g. ``["shot_label×2", ...]``."""
    hits: list[str] = []
    for name, pattern in _STRUCTURE_RESIDUE_RES:
        count = len(pattern.findall(text))
        if count:
            hits.append(f"{name}×{count}")
    return hits


def _check_structure_label_residue(whisper_text: str, srt_text: str) -> CheckResult:
    """Check 4: no script-structure labels in SRT or whisper text (#455).

    SRT and whisper both derive from the cleaned narration, so shared
    pollution (``镜头1｜0:03-0:09`` / ``主题：`` / ``口播：`` / ``[切]`` /
    timecodes) shows up on *both* sides and the diff ratio stays high.  This
    check fails on residue alone — a perfect similarity score cannot green a
    polluted film.
    """
    name = "structure_label_residue"
    srt_hits = _structure_residue_hits(_strip_srt_timestamps(srt_text))
    whisper_hits = _structure_residue_hits(whisper_text)
    if not srt_hits and not whisper_hits:
        return {
            "name": name,
            "passed": True,
            "detail": "no structure labels in SRT or whisper text",
        }
    parts: list[str] = []
    if srt_hits:
        parts.append("srt: " + ", ".join(srt_hits))
    if whisper_hits:
        parts.append("whisper: " + ", ".join(whisper_hits))
    return {
        "name": name,
        "passed": False,
        "detail": "structure labels present (independent of diff ratio) — " + "; ".join(parts),
    }


def _check_whisper_not_empty(whisper_text: str) -> CheckResult:
    """Check 3: Whisper transcription is non-empty."""
    name = "whisper_not_empty"
    if whisper_text.strip():
        return {"name": name, "passed": True, "detail": "Whisper text non-empty"}
    return {"name": name, "passed": False, "detail": "Whisper text is empty"}


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# V5Mp3VsSrt gate
# ---------------------------------------------------------------------------


class V5Mp3VsSrt(BaseGate):
    """V5 MP3 vs SRT Gate — Whisper transcription diff vs SRT text ≥80%.

    ``gate_context`` expected keys:
        - ``whisper_text``: str — Whisper transcription output
        - ``srt_text``: str — SRT subtitle file content
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing.

    failure_mode = "retry" — on failure, pipeline can retry the gate.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error``.
    """

    _gate_name = "V5"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run V5 MP3 vs SRT checks and return structured result."""
        if not gate_context.get("hyperframes_available", True):
            return {
                "passed": True,
                "gate": "V5",
                "status": "skipped",
                "reason": "HyperFrames not installed — video QA skipped",
            }

        # ``whisper_text`` + ``srt_text`` are produced by the transcription and
        # subtitle stages.  Absent means there is no audio/subtitle pair to
        # diff — reporting a diff failure here would be pure noise.
        skipped = missing_input_result("V5", gate_context, ("whisper_text", "srt_text"))
        if skipped is not None:
            return skipped

        whisper_text: str = gate_context.get("whisper_text", "")
        srt_text: str = gate_context.get("srt_text", "")
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            ("whisper_vs_srt_diff", lambda: _check_whisper_vs_srt_diff(whisper_text, srt_text)),
            ("srt_not_empty", lambda: _check_srt_not_empty(srt_text)),
            ("whisper_not_empty", lambda: _check_whisper_not_empty(whisper_text)),
            (
                "structure_label_residue",
                lambda: _check_structure_label_residue(whisper_text, srt_text),
            ),
        ]

        checks = apply_mock_overrides(check_fns, mock_results)

        return build_gate_result(checks, gate="V5", expected_suffix=".")
