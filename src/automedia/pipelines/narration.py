"""Narration hygiene — what the voice-over and subtitles are allowed to say.

The content writer produces a *script*: markdown headings for structure and
bracketed production cues such as ``[画面：对着镜头无奈叹气]`` or
``[音效：玻璃碎裂]``.  None of that is spoken.  Feeding the whole document to
TTS made the narrator read the cue aloud and pushed it into the SRT (#390).

Cleaning happens here — at the narration/subtitle boundary — and nowhere else:
the draft on disk and whatever the gates validate stay untouched.
"""

from __future__ import annotations

import re

#: Cue keywords that mark a bracket as a production note rather than prose.
#: ``切`` covers both ``[切]`` and the colonised ``[切：画面瞬间变得干净…]``
#: form the writer model emits (#455).
_CUE_KEYWORDS = (
    r"(?:画面|镜头|镜号|机位|构图|音效|配乐|音乐|bgm|字幕|花字|旁白|画外音|"
    r"切|转场|特效|特写|全景|中景|近景|远景|视觉|提示|"
    r"visual|sfx|vfx|cut\s*to|transition|shot)"
)

#: ``[画面：…]`` / ``（镜头：…）`` / ``【音效：…】`` — anything bracketed that
#: opens with a cue keyword.  The body may contain ``/``, ``、`` and colons;
#: only the matching bracket pair terminates it.
_BRACKETED_CUE_RE = re.compile(
    r"[\[【（(]\s*" + _CUE_KEYWORDS + r"[^\[\]【】（）()]{0,300}?[\]】）)]",
    re.IGNORECASE,
)

#: A cue whose closing bracket never arrives (truncated draft, or the closer
#: landed on the next line).  Runs to end of line only.
_DANGLING_CUE_RE = re.compile(
    r"[\[【（(]\s*" + _CUE_KEYWORDS + r"[^\[\]【】（）()\n]*$",
    re.IGNORECASE | re.MULTILINE,
)

_HSPACE_RUN_RE = re.compile(r"[ \t]{2,}")

#: Paired markdown emphasis markers (``**粗体**`` / ``__粗体__`` / ``*斜体*`` /
#: ``_斜体_``).  The narrator reads the markers themselves out loud ("星号星号",
#: issue #444), so only the emphasised words may survive.  Single underscores
#: inside a word (``a_b_c``) are not emphasis and stay untouched.
_EMPHASIS_PAIR_RES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\*\*(.+?)\*\*", re.DOTALL), r"\1"),
    (re.compile(r"__(.+?)__", re.DOTALL), r"\1"),
    (re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", re.DOTALL), r"\1"),
    (re.compile(r"(?<!\w)_(?!_)(.+?)(?<!_)_(?!\w)", re.DOTALL), r"\1"),
)

#: Stray runs left behind by unpaired markers (``**`` / ``__``).  Never prose,
#: always read aloud — drop them.
_STRAY_EMPHASIS_RE = re.compile(r"\*{2,}|_{2,}")

#: Labels that head a script-structure row (``主题：`` / ``品牌：…`` /
#: ``镜头2``) — they describe the script to a human editor, never the words a
#: narrator says (#455).
_STRUCTURE_LABEL = r"(?:主题|品牌|时长|风格|平台|bgm|音效|字幕|画面|运镜|机位|场景|转场|镜头\s*\d+)"

#: A row or ``｜``-separated segment that opens with a structure label.
_STRUCTURE_SEGMENT_RE = re.compile(rf"^{_STRUCTURE_LABEL}\s*[:：｜|]", re.IGNORECASE)

#: ``镜头1｜0:03-0:09`` — a shot header with its timecode (#455).
_SHOT_HEADER_RE = re.compile(
    r"镜头\s*\d+\s*(?:[｜|:：]\s*)?\d{1,2}:\d{2}\s*[-–—~至]\s*\d{1,2}:\d{2}\s*"
)

#: ``口播：`` / ``口播文案：`` mark the spoken part of the script; the label
#: itself is never spoken (#455).
_SPOKEN_PREFIX_RE = re.compile(r"口播(?:文案)?\s*[:：]\s*")

#: ``0:03-0:09`` / ``（0:00-0:03）`` — production timing.  Never narration:
#: a TTS-ready script writes durations in words, so a colon timecode span is
#: scaffolding wherever it sits (parenthesised section headers included).
_TIMECODE_SPAN_RE = re.compile(r"[（(]?\s*\d{1,2}:\d{2}\s*[-–—~至]\s*\d{1,2}:\d{2}\s*[）)]?")

#: Short uncolonised production tags — ``[切]`` / ``[转场]`` / ``[停顿]``.
#: Deliberately an allowlist: ordinary bracketed prose must survive (#455).
_SHORT_CUE_TAG_RE = re.compile(
    r"\[(?:切|转场|切换|停顿|暂停|淡入|淡出|黑场|闪回|叠化|白闪|黑闪|分屏)\]"
)

#: Segments inside a metadata row are separated by full-width or ASCII bars.
_SEGMENT_SPLIT_RE = re.compile(r"\s*[｜|]\s*")


def strip_emphasis_markers(text: str) -> str:
    """Unwrap markdown emphasis so only the spoken words remain (#444).

    ``**主题**：先跑通流程`` becomes ``主题：先跑通流程``.  Paired markers are
    unwrapped first; whatever run of ``**``/``__`` survives is an unpaired
    marker, which is still unreadable aloud and is removed.  A single
    underscore inside a word (``a_b_c``) is not emphasis and is preserved.
    """
    cleaned = text or ""
    for pattern, replacement in _EMPHASIS_PAIR_RES:
        cleaned = pattern.sub(replacement, cleaned)
    return _STRAY_EMPHASIS_RE.sub("", cleaned)


def strip_stage_directions(text: str) -> str:
    """Remove bracketed production cues, keeping the prose around them."""
    if not text:
        return ""
    cleaned = _BRACKETED_CUE_RE.sub("", text)
    cleaned = _DANGLING_CUE_RE.sub("", cleaned)
    lines = [_HSPACE_RUN_RE.sub(" ", line).strip() for line in cleaned.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def strip_structure_labels(text: str) -> str:
    """Drop script structure — metadata rows, shot headers, spoken prefixes.

    ``strip_narration_markup`` feeds TTS and the SRT, so labels such as
    ``主题：`` / ``镜头1｜0:03-0:09`` / ``口播：`` / ``[切]`` would be read
    aloud (#455).  Rows and ``｜``-segments that open with a structure label
    are removed; a shot header or ``口播：`` prefix on a spoken line is peeled
    off and the prose kept.  Bracketed tags outside the production vocabulary
    are left alone.
    """
    kept_lines: list[str] = []
    for line in (text or "").splitlines():
        line = _SHORT_CUE_TAG_RE.sub("", line)
        line = _SHOT_HEADER_RE.sub("", line)
        line = _TIMECODE_SPAN_RE.sub("", line)
        line = _SPOKEN_PREFIX_RE.sub("", line)
        segments = [seg for seg in _SEGMENT_SPLIT_RE.split(line) if seg]
        structured = "".join(
            seg for seg in segments if not _STRUCTURE_SEGMENT_RE.match(seg.strip())
        ).strip()
        if structured:
            kept_lines.append(structured)
    return "\n".join(kept_lines).strip()


def strip_narration_markup(text: str) -> str:
    """Drop markdown structure and production cues from narrated text.

    Headings are section labels, not sentences; bullet markers are scaffolding;
    bracketed cues are notes for whoever edits the video; script structure rows
    and shot headers are notes for the editor (#455).  Only the words a person
    would actually say survive.
    """
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Horizontal rules and empty bullet scaffolding carry no words.
        if not line.strip("-*_ "):
            continue
        line = re.sub(r"^(?:[-*>]\s*)+", "", line).strip()
        if line:
            lines.append(line)
    cleaned = strip_emphasis_markers("\n".join(lines))
    # Cues are stripped before structure rows so ``[画面：…]主题：…`` is still
    # recognised as a metadata row (#455).
    cleaned = strip_stage_directions(cleaned)
    return strip_structure_labels(cleaned)
