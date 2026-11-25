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
       text (#455); since #654 it also fails on any SRT cue carrying
       stage-direction residue (快切/贴纸/语速/空镜/``[画面：…]``… )
    5. srt_not_empty         — SRT file content is non-empty
    6. whisper_not_empty     — Whisper transcription is non-empty
    7. whisper_vs_srt_diff   — retired criterion, kept as an observation field
       only: always ``passed=True``, never drives the verdict
    8. semantic_consistency  — optional semantic layer (B26/C5).  When an LLM
       judge is available it decides whether the cues carry the same meaning
       as the ASR transcript: condensing/line-breaking is fine, added or
       changed facts/numbers are not.  When no verdict is available the check
       is reported as ``semantic_consistency_skipped`` (``passed=True``) —
       the *name* changes so a skip can never be read as a verified pass
       (same honesty rule as the V3 fix, #661).

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
from automedia.gates.llm_helpers import LLMCheckResult, llm_check_with_fallback

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

#: Prompt template used for the semantic judge (B26/C5).
_V5_JUDGE_PROMPT: str = "v5_semantic_consistency"

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
        # Anchored to the start of a line/cue (#671): ``场景：`` in ordinary
        # prose (``…经历过这样的场景：``) is not a metadata label, only a cue
        # that *begins* with one is scaffolding.
        "metadata_label",
        re.compile(
            r"^[ \t]*(?:主题|品牌|时长|风格|平台|BGM|音效|转场|字幕|画面|运镜|机位|场景)\s*[:：]",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "transition_tag",
        re.compile(r"\[(?:切|转场|切换|停顿|暂停|淡入|淡出|黑场|闪回|叠化|白闪|黑闪|分屏)\]"),
    ),
)

#: 舞台指示关键词（#654）。SRT 的**任意一条 cue 文本**命中即 fail，判据刻意
#: 从严：快切/贴纸/语速/空镜/推近这些词只出现在分镜说明里，不该出现在观众
#: 可见的字幕中——命中即说明结构化抽取（``extract_spoken_lines``）没跑到或
#: 漏了。只扫 SRT cue 文本，不扫 whisper（ASR 转写无此约束，普通叙述里出现
#: 「镜头」不构成缺陷）。
_STAGE_MARKER_RE = re.compile(
    r"\[(?:画面|音效|转场|切|镜头|特写|字幕|花字|旁白|视觉|bgm|sfx)\s*[:：\]]"
    r"|口播\s*[:：]|镜头|语速|贴纸|快切|特写|推近|空镜",
    re.IGNORECASE,
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


def _anchor(
    cue_norm: str,
    asr_norm: str,
    *,
    search_from: int = 0,
    search_len: int | None = None,
) -> tuple[int, float, list[tuple[int, int]]]:
    """Locate *cue_norm* in *asr_norm*.

    When ``search_len`` is given, the longest common substring is first looked
    for inside ``asr_norm[search_from:search_from + search_len]`` — the
    neighbourhood just after the previous cue's anchor (#672).  A phrase that
    repeats earlier in the transcript therefore no longer steals the anchor and
    fakes an order inversion.  The local anchor is only adopted when it matches
    a substring at least as long as the best whole-transcript match: a repeated
    phrase matches equally well nearby, while a genuinely displaced block only
    yields a short fragment locally — that case keeps the whole-transcript
    result, so real swaps still fail the order check.  With no local match the
    search also falls back to the whole transcript (the previous behaviour).

    Returns ``(anchor_start, coverage, matched_spans)`` where ``anchor_start``
    is the ASR offset of the cue's longest common substring with the
    transcription, ``coverage`` is the share of cue characters matched inside a
    local window around that anchor, and ``matched_spans`` are the ASR
    intervals covered by that cue (used for the uncovered-speech check).
    """
    if not cue_norm or not asr_norm:
        return 0, 0.0, []
    best = SequenceMatcher(None, cue_norm, asr_norm, autojunk=False).find_longest_match(
        0, len(cue_norm), 0, len(asr_norm)
    )
    anchor = best.b
    if search_len is not None and best.size and search_from < len(asr_norm):
        end = min(len(asr_norm), search_from + max(search_len, len(cue_norm)))
        local = SequenceMatcher(
            None, cue_norm, asr_norm[search_from:end], autojunk=False
        ).find_longest_match(0, len(cue_norm), 0, end - search_from)
        if local.size and local.size == best.size:
            anchor = search_from + local.b
    lo = max(0, anchor - _ANCHOR_MARGIN)
    hi = min(len(asr_norm), anchor + len(cue_norm) + _ANCHOR_MARGIN)
    window = asr_norm[lo:hi]
    blocks = SequenceMatcher(None, cue_norm, window, autojunk=False).get_matching_blocks()
    matched = sum(block.size for block in blocks)
    spans = [(lo + block.b, lo + block.b + block.size) for block in blocks if block.size]
    return anchor, matched / len(cue_norm), spans


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
    prev_anchor: int | None = None
    prev_len = 0
    for cue in cues:
        cue_norm = _normalise(cue.text)
        if not cue_norm:
            continue
        if prev_anchor is None:
            search_from, search_len = 0, None
        else:
            # #672：先在前一条 cue 的锚点之后、按两条 cue 长度给出的有限
            # 窗口里找；窗口内找不到才回退全篇搜索（_anchor 内部兜底）。
            search_from = prev_anchor
            search_len = prev_len + len(cue_norm) + 2 * _ANCHOR_MARGIN
        position, ratio, cue_spans = _anchor(
            cue_norm, asr_norm, search_from=search_from, search_len=search_len
        )
        ratios.append(ratio)
        positions.append(position)
        spans.extend(cue_spans)
        prev_anchor = position
        prev_len = len(cue_norm)

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


def _structure_residue_hits(text: str, *, skip: frozenset[str] = frozenset()) -> list[str]:
    """Count structure-label hits per pattern, e.g. ``["shot_label×2", ...]``.

    ``skip`` omits patterns whose anchoring makes them meaningless on flattened
    text — ``metadata_label`` is judged per SRT cue instead (#671).
    """
    hits: list[str] = []
    for name, pattern in _STRUCTURE_RESIDUE_RES:
        if name in skip:
            continue
        count = len(pattern.findall(text))
        if count:
            hits.append(f"{name}×{count}")
    return hits


def _metadata_label_cue_hits(cues: list[_Cue]) -> list[str]:
    """Return ``["metadata_label×N"]`` for cues that *begin* with a label (#671).

    A label word with a colon mid-sentence (``…经历过这样的场景：``) is ordinary
    prose; only a cue whose stripped text starts with ``主题：``/``场景：``/… is
    script scaffolding.  Flattening the SRT drops the line starts the anchored
    pattern needs, so it is evaluated cue by cue here.
    """
    pattern = dict(_STRUCTURE_RESIDUE_RES)["metadata_label"]
    count = sum(1 for cue in cues if pattern.match(cue.text.strip()))
    return [f"metadata_label×{count}"] if count else []


def _stage_marker_cue_hits(cues: list[_Cue]) -> list[str]:
    """Return ``cue N 混入舞台指示：<命中片段>`` for every cue that hits #654."""
    hits: list[str] = []
    for cue in cues:
        match = _STAGE_MARKER_RE.search(cue.text)
        if match:
            hits.append(f"cue {cue.index} 混入舞台指示：{match.group(0)}")
    return hits


def _check_structure_label_residue(
    whisper_text: str,
    srt_text: str,
    cues: list[_Cue],
) -> CheckResult:
    """Check 4: no script-structure labels or stage directions in SRT/whisper (#455, #654).

    SRT and whisper both derive from the cleaned narration, so shared
    pollution (``镜头1｜0:03-0:09`` / ``主题：`` / ``口播：`` / ``[切]`` /
    timecodes) shows up on *both* sides.  This check fails on residue alone —
    a perfect anchor coverage cannot green a polluted film.

    #654 adds one more fail path to the same check: any *cue* whose text hits
    the stage-direction regex (``快切`` / ``贴纸`` / ``语速`` / bare ``镜头`` /
    ``[画面：…]`` outside brackets…) fails the gate with the offending cue
    named.  The existing skipped/review semantics are untouched.
    """
    name = "structure_label_residue"
    # metadata_label 只在 cue 开头命中（#671）；扁平化后的 SRT 丢掉行首，
    # 所以从全量扫描里跳过、改由逐条 cue 判定。
    srt_hits = _structure_residue_hits(
        _strip_srt_timestamps(srt_text), skip=frozenset({"metadata_label"})
    )
    srt_hits.extend(_metadata_label_cue_hits(cues))
    whisper_hits = _structure_residue_hits(whisper_text)
    stage_hits = _stage_marker_cue_hits(cues)
    if not srt_hits and not whisper_hits and not stage_hits:
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
    if stage_hits:
        parts.append("; ".join(stage_hits))
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


def _llm_semantic_consistency(whisper_text: str, srt_text: str) -> dict[str, Any] | None:
    """Ask the LLM whether the subtitle cues carry the same meaning as the ASR.

    Parameters
    ----------
    whisper_text:
        The ASR transcript — what was actually spoken.
    srt_text:
        The subtitle file content — what the viewer reads.

    Returns
    -------
    dict[str, Any] | None
        ``{"passed": bool, "issues": [str, ...], "confidence": float,
        "structured_issues": [{"cue_text": str, "problem": str}, ...]}`` on a
        usable verdict.  ``None`` when no verdict exists — missing text, LLM
        failure/timeout, or a response that does not match the expected
        structure.  A ``None`` return is deliberately **not** a pass: the
        caller records the check as skipped (B26/C5, same contract as the
        V3 fix #661).
    """
    if not whisper_text.strip() or not srt_text.strip():
        return None

    def _unavailable(_text: str) -> LLMCheckResult:
        # Any LLM failure must surface as "not judged", never as a pass.
        return {"passed": False, "issues": ["llm unavailable"]}

    try:
        judged = llm_check_with_fallback(
            text=srt_text,
            check_type="audiosub_semantic",
            prompt_template_name=_V5_JUDGE_PROMPT,
            deterministic_fn=_unavailable,
            source_text=whisper_text,
        )
    except Exception:
        log.warning("V5 semantic judge failed", exc_info=True)
        return None

    # ``method != "llm"`` means the deterministic fallback ran: no verdict.
    if judged.get("method") != "llm":
        return None

    # G0CheckResult is the repo's only free-form structured slot; the prompt
    # puts one ``{cue_text, problem}`` entry per problem cue there.
    raw_issues = judged.get("structured_issues")
    if not isinstance(raw_issues, list):
        return None

    problems: list[dict[str, str]] = []
    for item in raw_issues:
        if not isinstance(item, dict):
            return None
        problems.append(
            {
                "cue_text": str(item.get("cue_text") or ""),
                "problem": str(item.get("problem") or ""),
            }
        )

    return {
        "passed": bool(judged.get("passed")),
        "issues": [str(issue) for issue in judged.get("issues", [])],
        "confidence": float(judged.get("confidence", 1.0)),
        "structured_issues": problems,
    }


def _check_semantic_consistency(whisper_text: str, srt_text: str) -> CheckResult:
    """Check 8: optional semantic layer — the honest skip without a judge.

    With a verdict, the check reports ``semantic_consistency`` and the judge
    decides; the detail names every problem cue (each quoted) so the failure
    is an evidence trail.  Without a verdict the check is reported as
    ``semantic_consistency_skipped`` — the *name* changes so no consumer can
    mistake "no judge" for "the semantic layer verified this pair".
    """
    if not whisper_text.strip() or not srt_text.strip():
        return {
            "name": "semantic_consistency_skipped",
            "passed": True,
            "detail": "not applicable (empty text)",
        }

    judge = _llm_semantic_consistency(whisper_text, srt_text)
    if judge is None:
        return {
            "name": "semantic_consistency_skipped",
            "passed": True,
            "detail": "not judged: no LLM judge available — semantic layer NOT verified",
        }

    problems: list[dict[str, str]] = judge.get("structured_issues") or []
    if judge["passed"]:
        confidence = float(judge.get("confidence", 1.0))
        return {
            "name": "semantic_consistency",
            "passed": True,
            "detail": (
                f"semantic judge: subtitle meaning matches ASR transcript "
                f"(confidence {confidence:.2f})"
            ),
        }

    parts = [f'cue "{item["cue_text"]}" — {item["problem"]}' for item in problems[:3]]
    if not parts:
        parts = [str(issue) for issue in judge.get("issues", [])[:3]]
    more = f"; +{len(problems) - 3} more" if len(problems) > 3 else ""
    return {
        "name": "semantic_consistency",
        "passed": False,
        "detail": f"semantic judge: {len(problems)} problem cue(s): " + "; ".join(parts) + more,
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

        # Gate-level marker (B26/C5): ``judged`` only when the semantic check
        # actually ran under its verified name.  A skip — or a ``_mock_results``
        # override, which bypasses the check entirely — must never advertise a
        # verified semantic layer, so the default stays ``"skipped"``.
        semantic_layer = "skipped"

        def _run_semantic_check() -> CheckResult:
            nonlocal semantic_layer
            result = _check_semantic_consistency(whisper_text, srt_text)
            semantic_layer = "judged" if result["name"] == "semantic_consistency" else "skipped"
            return result

        check_fns: list[tuple[str, Any]] = [
            ("cue_anchor_coverage", lambda: _check_cue_anchor_coverage(alignment)),
            ("cue_order_consistency", lambda: _check_cue_order_consistency(alignment)),
            ("uncovered_speech", lambda: _check_uncovered_speech(alignment)),
            (
                "structure_label_residue",
                lambda: _check_structure_label_residue(whisper_text, srt_text, cues),
            ),
            ("srt_not_empty", lambda: _check_srt_not_empty(srt_text)),
            ("whisper_not_empty", lambda: _check_whisper_not_empty(whisper_text)),
            ("whisper_vs_srt_diff", lambda: _check_whisper_vs_srt_diff(whisper_text, srt_text)),
            ("semantic_consistency", _run_semantic_check),
        ]

        checks = apply_mock_overrides(check_fns, mock_results)

        return build_gate_result(
            checks, gate="V5", expected_suffix=".", semantic_layer=semantic_layer
        )
