"""V5 MP3 vs SRT Gate — structural + semantic subtitle/audio agreement (#469).

The retired criterion was a whole-string character similarity
(``SequenceMatcher.ratio() >= 0.80``).  Real Chinese ASR from
``faster-whisper-small`` carries homophone noise, so a *clean* film also scores
74–79% (#462) — the threshold was structurally unreachable — while same-source
pollution (SRT and narration generated from the same dirty text) pushed the
same metric past 80% and greened a broken film (#455).  A measurement that is
wrong in both directions is not a criterion.

Checks (each one can fail the gate on its own):
    1. cue_anchor_coverage   — every SRT cue has an anchor in the ASR transcript
    2. cue_order_consistency — cue order follows the ASR time order (block swap)
    3. uncovered_speech      — ASR speech that no cue covers (narration extra)
    4. structure_label_residue — no script-structure labels in SRT or whisper
       text (#455)
    5. srt_not_empty         — SRT file content is non-empty
    6. whisper_not_empty     — Whisper transcription is non-empty
    7. whisper_vs_srt_diff   — retired criterion, kept as an observation field
       only: always ``passed=True``, never drives the verdict
    8. semantic_consistency  — optional semantic layer; reports
       ``semantic: skipped(no key)`` when no judge is configured.  ``passed``
       stays ``True`` on the skip: an absent judge is not evidence of a bad
       film, and the three deterministic checks above still gate the verdict.

Anchor coverage, order and uncovered speech are judged on character sequences
after punctuation/whitespace normalisation.  The per-cue anchor is the longest
common substring between the cue and the ASR text; coverage is the share of the
cue matched inside a local window around that anchor, so scattered homophone
noise degrades the ratio gently instead of breaking the alignment.

Thresholds are calibrated from measured bad-vs-clean separation, not picked by
feel (numbers from the #469 run, whisper ``small``, zh):

* ``_CUE_COVERAGE_MIN = 0.45`` — clean film worst cue 0.53, a cue whose audio
  was not spoken 0.33, the bad film's label cue 0.08.
* ``_UNCOVERED_RUN_MIN = 8`` characters — clean film longest uncovered run 4,
  one extra narrated sentence 21.
* ``_ORDER_TOLERANCE = 4`` characters — clean film 0 backward steps, a swapped
  cue pair 10, the bad film 21.

failure_mode = "retry" — on failure, pipeline can retry/fix the gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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
    "cue_anchor_coverage",
    "cue_order_consistency",
    "uncovered_speech",
    "structure_label_residue",
    "srt_not_empty",
    "whisper_not_empty",
    "whisper_vs_srt_diff",
    "semantic_consistency",
]

#: Minimum share of a cue's characters that must be found in the ASR text
#: around the cue's anchor.  Calibrated in the module docstring.
_CUE_COVERAGE_MIN: float = 0.45

#: An ASR stretch of at least this many characters that no cue covers means the
#: narration says something the subtitles never show (多念一段).
_UNCOVERED_RUN_MIN: int = 8

#: How far a cue's anchor may move backwards before the order check fails.
#: Small alignment jitter from ASR noise is tolerated; a swapped block is not.
_ORDER_TOLERANCE: int = 4

#: Slack (characters) around the anchor position when measuring the local
#: alignment window.  Large enough for ASR to insert/drop a few characters,
#: small enough that the window cannot swallow a neighbouring cue.
_ANCHOR_MARGIN: int = 6

#: Script-structure patterns that must never survive into the narration audio
#: or the subtitles (#455).  ``strip_narration_markup`` removes them before
#: TTS/SRT, so a hit means structure leaked past the narration boundary.  A
#: similarity score cannot catch this — SRT and whisper derive from the same
#: cleaned text, so same-source pollution inflates similarity and would read as
#: "pass" — hence this check, judged on residue alone.
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

#: Everything that is not a word character or a CJK ideograph — dropped before
#: alignment.  ASR never reproduces SRT punctuation faithfully, and punctuation
#: differences are not evidence about what was spoken.
_NOISE_RE = re.compile(r"[^\w\u3400-\u4dbf\u4e00-\u9fff]+", re.UNICODE)

_SRT_TIMESTAMP_RE = re.compile(r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}")


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


@dataclass(frozen=True)
class _Cue:
    """One parsed subtitle cue: timing is kept, judgement uses ``text``."""

    index: int
    start: str
    end: str
    text: str


def _parse_srt_cues(srt_text: str) -> list[_Cue]:
    """Parse SRT blocks into cues, tolerating missing blank lines and CRLF.

    A cue starts at its timestamp line and collects text lines until the next
    timestamp line or a blank line that follows text.  Stray index lines are
    ignored.  HTML tags are stripped from the cue text (rendered markup is not
    speech).
    """
    cues: list[_Cue] = []
    start = end = ""
    collected: list[str] = []

    def flush() -> None:
        nonlocal start, end, collected
        text = re.sub(r"<[^>]+>", "", " ".join(collected)).strip()
        if text:
            cues.append(_Cue(index=len(cues) + 1, start=start, end=end, text=text))
        start = end = ""
        collected = []

    lines = (srt_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for position, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line.isdigit() and collected:
            # Next cue's index with no blank separator closes this cue.
            following = next((nxt.strip() for nxt in lines[position + 1 :] if nxt.strip()), "")
            if _SRT_TIMESTAMP_RE.search(following):
                flush()
                continue
        match = _SRT_TIMESTAMP_RE.search(line)
        if match:
            flush()
            ts = match.group(0)
            start, end = (part.strip() for part in ts.split("-->", 1))
            continue
        if not (start or collected):
            continue  # preamble / stray index before the first cue
        if not line:
            if collected:
                flush()
            continue
        if not collected and line.isdigit():
            continue  # index line directly above the next timestamp
        collected.append(line)
    flush()
    return cues


def _normalise(text: str) -> str:
    """Drop punctuation/whitespace and lowercase, keeping CJK and alphanumerics."""
    return _NOISE_RE.sub("", text or "").lower()


def _anchor(cue_norm: str, asr_norm: str) -> tuple[int, float, list[tuple[int, int]]]:
    """Locate *cue_norm* in *asr_norm*.

    Returns ``(anchor_start, coverage, matched_spans)`` where ``anchor_start``
    is the ASR offset of the cue's longest common substring with the
    transcription, ``coverage`` is the share of cue characters matched inside a
    local window around that anchor, and ``matched_spans`` are the ASR
    intervals covered by that cue (used for the uncovered-speech check).
    """
    if not cue_norm or not asr_norm:
        return 0, 0.0, []
    matcher = SequenceMatcher(None, cue_norm, asr_norm, autojunk=False)
    best = matcher.find_longest_match(0, len(cue_norm), 0, len(asr_norm))
    lo = max(0, best.b - _ANCHOR_MARGIN)
    hi = min(len(asr_norm), best.b + len(cue_norm) + _ANCHOR_MARGIN)
    window = asr_norm[lo:hi]
    blocks = SequenceMatcher(None, cue_norm, window, autojunk=False).get_matching_blocks()
    matched = sum(block.size for block in blocks)
    spans = [(lo + block.b, lo + block.b + block.size) for block in blocks if block.size]
    return best.b, matched / len(cue_norm), spans


@dataclass(frozen=True)
class _Alignment:
    """Everything the three structural checks need, computed once per run."""

    cue_count: int
    ratios: list[float]
    positions: list[int]
    uncovered_runs: list[tuple[int, int]]
    asr_norm: str


def _analyse_alignment(cues: list[_Cue], whisper_text: str) -> _Alignment:
    asr_norm = _normalise(whisper_text)
    ratios: list[float] = []
    positions: list[int] = []
    spans: list[tuple[int, int]] = []
    for cue in cues:
        cue_norm = _normalise(cue.text)
        if not cue_norm:
            continue
        position, ratio, cue_spans = _anchor(cue_norm, asr_norm)
        ratios.append(ratio)
        positions.append(position)
        spans.extend(cue_spans)

    runs: list[tuple[int, int]] = []
    covered = sorted(spans)
    cursor = 0
    for span_start, span_end in covered:
        if span_start > cursor:
            runs.append((cursor, span_start))
        cursor = max(cursor, span_end)
    if cursor < len(asr_norm):
        runs.append((cursor, len(asr_norm)))
    return _Alignment(
        cue_count=len(cues),
        ratios=ratios,
        positions=positions,
        uncovered_runs=runs,
        asr_norm=asr_norm,
    )


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_cue_anchor_coverage(alignment: _Alignment) -> CheckResult:
    """Check 1: every SRT cue is anchored in the ASR transcript (漏念一段)."""
    name = "cue_anchor_coverage"
    if alignment.cue_count == 0:
        return {"name": name, "passed": False, "detail": "no SRT cues parsed — nothing to verify"}
    if not alignment.asr_norm:
        return {"name": name, "passed": False, "detail": "empty ASR text — no anchor possible"}

    uncovered = [i + 1 for i, ratio in enumerate(alignment.ratios) if ratio < _CUE_COVERAGE_MIN]
    if uncovered:
        shown = "; ".join(f"cue #{i} coverage {alignment.ratios[i - 1]:.0%}" for i in uncovered[:3])
        more = f"; +{len(uncovered) - 3} more" if len(uncovered) > 3 else ""
        return {
            "name": name,
            "passed": False,
            "detail": (
                f"{len(uncovered)}/{alignment.cue_count} cues have no ASR anchor "
                f"(< {_CUE_COVERAGE_MIN:.0%}): {shown}{more}"
            ),
        }
    worst = min(alignment.ratios)
    return {
        "name": name,
        "passed": True,
        "detail": (
            f"all {alignment.cue_count} cues anchored in ASR "
            f"(worst cue coverage {worst:.0%} >= {_CUE_COVERAGE_MIN:.0%})"
        ),
    }


def _check_cue_order_consistency(alignment: _Alignment) -> CheckResult:
    """Check 2: cue anchors follow ASR time order (整段错位)."""
    name = "cue_order_consistency"
    positions = alignment.positions
    if len(positions) < 2:
        return {"name": name, "passed": True, "detail": "fewer than 2 cues — order not applicable"}

    inversions = [
        (i + 1, positions[i], i + 2, positions[i + 1])
        for i in range(len(positions) - 1)
        if positions[i + 1] < positions[i] - _ORDER_TOLERANCE
    ]
    if inversions:
        shown = "; ".join(
            f"cue #{left} anchors at {left_pos} before cue #{right} at {right_pos}"
            for left, left_pos, right, right_pos in inversions[:3]
        )
        more = f"; +{len(inversions) - 3} more" if len(inversions) > 3 else ""
        return {
            "name": name,
            "passed": False,
            "detail": f"cue order inverted versus ASR order: {shown}{more}",
        }
    return {
        "name": name,
        "passed": True,
        "detail": (
            f"cue anchors are monotonic in ASR order "
            f"({len(positions)} cues, tolerance {_ORDER_TOLERANCE} chars)"
        ),
    }


def _check_uncovered_speech(alignment: _Alignment) -> CheckResult:
    """Check 3: no ASR stretch left uncovered by the subtitles (多念一段)."""
    name = "uncovered_speech"
    long_runs = [
        (start, end) for start, end in alignment.uncovered_runs if end - start >= _UNCOVERED_RUN_MIN
    ]
    if long_runs:
        shown = "; ".join(
            f'{end - start} chars "{alignment.asr_norm[start:end][:24]}"'
            for start, end in long_runs[:3]
        )
        more = f"; +{len(long_runs) - 3} more" if len(long_runs) > 3 else ""
        return {
            "name": name,
            "passed": False,
            "detail": (
                f"{len(long_runs)} ASR stretch(es) with no subtitle coverage "
                f"(>= {_UNCOVERED_RUN_MIN} chars): {shown}{more}"
            ),
        }
    longest = max((end - start for start, end in alignment.uncovered_runs), default=0)
    return {
        "name": name,
        "passed": True,
        "detail": f"no uncovered ASR speech (longest uncovered run {longest} chars)",
    }


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
    timecodes) shows up on *both* sides.  This check fails on residue alone —
    a perfect anchor coverage cannot green a polluted film.
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
        "detail": "structure labels present (independent of alignment) — " + "; ".join(parts),
    }


def _check_srt_not_empty(srt_text: str) -> CheckResult:
    """Check 5: SRT file content is non-empty."""
    name = "srt_not_empty"
    if srt_text.strip():
        return {"name": name, "passed": True, "detail": "SRT text non-empty"}
    return {"name": name, "passed": False, "detail": "SRT text is empty"}


def _check_whisper_not_empty(whisper_text: str) -> CheckResult:
    """Check 6: Whisper transcription is non-empty."""
    name = "whisper_not_empty"
    if whisper_text.strip():
        return {"name": name, "passed": True, "detail": "Whisper text non-empty"}
    return {"name": name, "passed": False, "detail": "Whisper text is empty"}


def _check_whisper_vs_srt_diff(whisper_text: str, srt_text: str) -> CheckResult:
    """Check 7: retired character similarity, kept as an observation field.

    #469 retired ``ratio >= 0.80`` as a criterion: it is unreachable for a
    clean Chinese film under real ASR (74–79%, #462) and reachable by a
    same-source polluted film (#455).  The value is still reported so the
    report keeps a continuous history of it, but it never drives the verdict.
    """
    name = "whisper_vs_srt_diff"
    if not whisper_text.strip() or not srt_text.strip():
        return {
            "name": name,
            "passed": True,
            "detail": "observation only: similarity not computed (empty whisper or SRT text)",
        }
    clean_srt = _strip_srt_timestamps(srt_text)
    ratio = SequenceMatcher(None, whisper_text.strip().lower(), clean_srt.lower()).ratio()
    return {
        "name": name,
        "passed": True,
        "detail": f"observation only: similarity {ratio:.1%} (no longer a pass/fail criterion)",
    }


def _check_semantic_consistency() -> CheckResult:
    """Check 8: optional semantic layer — reports the honest skip without a judge.

    The deterministic trio (coverage + order + residue) already gates the
    verdict.  A semantic judge needs a model key; when none is configured the
    check says so instead of pretending to have judged anything.
    """
    return {
        "name": "semantic_consistency",
        "passed": True,
        "detail": "semantic: skipped(no key)",
    }


# ---------------------------------------------------------------------------
# V5Mp3VsSrt gate
# ---------------------------------------------------------------------------


class V5Mp3VsSrt(BaseGate):
    """V5 MP3 vs SRT Gate — structural agreement between audio and subtitles.

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
        # diff — reporting a failure here would be pure noise.
        skipped = missing_input_result("V5", gate_context, ("whisper_text", "srt_text"))
        if skipped is not None:
            return skipped

        whisper_text: str = gate_context.get("whisper_text", "")
        srt_text: str = gate_context.get("srt_text", "")
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        cues = _parse_srt_cues(srt_text)
        alignment = _analyse_alignment(cues, whisper_text)

        check_fns: list[tuple[str, Any]] = [
            ("cue_anchor_coverage", lambda: _check_cue_anchor_coverage(alignment)),
            ("cue_order_consistency", lambda: _check_cue_order_consistency(alignment)),
            ("uncovered_speech", lambda: _check_uncovered_speech(alignment)),
            (
                "structure_label_residue",
                lambda: _check_structure_label_residue(whisper_text, srt_text),
            ),
            ("srt_not_empty", lambda: _check_srt_not_empty(srt_text)),
            ("whisper_not_empty", lambda: _check_whisper_not_empty(whisper_text)),
            ("whisper_vs_srt_diff", lambda: _check_whisper_vs_srt_diff(whisper_text, srt_text)),
            ("semantic_consistency", _check_semantic_consistency),
        ]

        checks = apply_mock_overrides(check_fns, mock_results)

        return build_gate_result(checks, gate="V5", expected_suffix=".")
