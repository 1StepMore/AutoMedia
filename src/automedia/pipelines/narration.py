"""Narration hygiene — what the voice-over and subtitles are allowed to say.

The content writer produces a *script*: markdown headings for structure and
bracketed production cues such as ``[画面：对着镜头无奈叹气]`` or
``[音效：玻璃碎裂]``.  None of that is spoken.  Feeding the whole document to
TTS made the narrator read the cue aloud and pushed it into the SRT (#390).

Cleaning happens at the narration/subtitle boundary and nowhere else: the
draft on disk and whatever the gates validate stay untouched.

The implementation lives in :mod:`automedia.core.text_cleaning` — the image
track's publishable-copy boundary (#464) reuses the same ``#459`` structure
stripping, so the primitives are shared rather than duplicated.  This module
re-exports them unchanged; the video track's behaviour is byte-identical.
"""

from __future__ import annotations

from automedia.core.text_cleaning import (
    strip_emoji,
    strip_emphasis_markers,
    strip_narration_markup,
    strip_stage_directions,
    strip_structure_labels,
)

__all__ = [
    "strip_emoji",
    "strip_emphasis_markers",
    "strip_narration_markup",
    "strip_stage_directions",
    "strip_structure_labels",
]
