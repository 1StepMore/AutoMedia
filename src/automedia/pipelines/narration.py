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
_CUE_KEYWORDS = (
    r"(?:画面|镜头|镜号|机位|构图|音效|配乐|音乐|bgm|字幕|花字|旁白|画外音|"
    r"转场|特效|特写|全景|中景|近景|远景|视觉|提示|"
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


def strip_stage_directions(text: str) -> str:
    """Remove bracketed production cues, keeping the prose around them."""
    if not text:
        return ""
    cleaned = _BRACKETED_CUE_RE.sub("", text)
    cleaned = _DANGLING_CUE_RE.sub("", cleaned)
    lines = [_HSPACE_RUN_RE.sub(" ", line).strip() for line in cleaned.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def strip_narration_markup(text: str) -> str:
    """Drop markdown structure and production cues from narrated text.

    Headings are section labels, not sentences; bullet markers are scaffolding;
    bracketed cues are notes for whoever edits the video.  Only the words a
    person would actually say survive.
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
    return strip_stage_directions("\n".join(lines))
