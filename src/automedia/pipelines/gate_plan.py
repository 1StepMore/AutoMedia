"""The authoritative per-mode gate plan (issue #282).

Gate order used to be described three times: ``runner._MODE_MAP`` (what the
engine actually executed), ``dag.AUTO_GATE_DAG`` (exported and documented as
"canonical"), and ``GateRegistry`` (registration order).  The DAG was labelled
canonical in the CLI while execution read the mode map, so the label was a lie
and nothing forced the two to agree.

This module is now the ONE authority for "which gates run, in what order, for
mode X".  :mod:`automedia.pipelines.runner` executes it, and
:mod:`automedia.pipelines.dag` describes the dependency edges among the same
gates; a test asserts the DAG's topological order for every mode reproduces
these lists exactly.

Why the mode map, and not the DAG, is the authority: a preset is a PRODUCT
decision (what a text-only run owes), while the DAG is a structural fact
(which gate needs which).  Two gates can be orderable either way and still
belong to different presets; only the preset knows that.  Making the DAG the
execution source would push preset membership into a dependency graph that
cannot express "G4/G5 exist but no preset runs them".

Import-isolation: this module declares constants only — it imports nothing
from ``automedia``, so ``dag`` (which must not import ``runner``) can import it
freely and ``runner`` can import it without a cycle.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Per-mode gate lists — THE execution authority
# --------------------------------------------------------------------------- #

#: Full mixed pipeline: text track then video track, ending in human review.
_AUTO_GATE_NAMES: list[str] = [
    "pre-gate",
    "CW",
    "G0",
    "G1",
    "G2",
    "G3",
    "G6",
    "V0",
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
    "V6",
    "V7",
    "H0",
]

#: Text-only run: copy gates plus human review, no video.
_TEXT_ONLY_GATE_NAMES: list[str] = [
    "CW",
    "G0",
    "G1",
    "G2",
    "G3",
    "G6",
    "H0",
]

#: Video-only run: the video track alone (no copy gates).
_VIDEO_ONLY_GATE_NAMES: list[str] = [
    "V0",
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
    "V6",
    "V7",
]

#: Quality-assurance subset: the gates that judge an existing artifact.
_QA_ONLY_GATE_NAMES: list[str] = [
    "G0",
    "G2",
    "G3",
    "V1",
    "V6",
]

#: Image-carousel run: copy gates, no review, no video.
_IMAGE_CAROUSEL_GATE_NAMES: list[str] = [
    "CW",
    "G0",
    "G1",
    "G2",
    "G3",
    "G6",
]

#: Text run that also produces a cover image.
_TEXT_WITH_COVER_GATE_NAMES: list[str] = [
    "CW",
    "G0",
    "G1",
    "G2",
    "G3",
    "G6",
    "H0",
]

#: Social-thread run: copy gates only, published without the H0 review step.
_SOCIAL_THREAD_GATE_NAMES: list[str] = [
    "CW",
    "G0",
    "G1",
    "G2",
    "G3",
    "G6",
]

#: Short-video run: pre-flight through both tracks, ending in human review.
_SHORT_VIDEO_GATE_NAMES: list[str] = [
    "pre-gate",
    "CW",
    "G0",
    "G1",
    "G2",
    "G3",
    "G6",
    "V0",
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
    "V6",
    "V7",
    "H0",
]

#: Repurpose run: a full pipeline plus the P1-P4 sub-pipelines.
_REPURPOSE_GATE_NAMES: list[str] = [
    "pre-gate",
    "CW",
    "G0",
    "G1",
    "G2",
    "G3",
    "G6",
    "V0",
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
    "V6",
    "V7",
    "H0",
    "P1",
    "P2",
    "P3",
    "P4",
]

#: Every pipeline mode's ordered gate list.  The dict VALUES are the very list
#: objects declared above, so ``MODE_GATE_NAMES[mode] is _X_GATE_NAMES`` holds
#: and a caller can never mutate one without mutating the other.
MODE_GATE_NAMES: dict[str, list[str]] = {
    "auto": _AUTO_GATE_NAMES,
    "text_only": _TEXT_ONLY_GATE_NAMES,
    "text_with_cover": _TEXT_WITH_COVER_GATE_NAMES,
    "video_only": _VIDEO_ONLY_GATE_NAMES,
    "qa_only": _QA_ONLY_GATE_NAMES,
    "image-carousel": _IMAGE_CAROUSEL_GATE_NAMES,
    "social-thread": _SOCIAL_THREAD_GATE_NAMES,
    "short-video": _SHORT_VIDEO_GATE_NAMES,
    "repurpose": _REPURPOSE_GATE_NAMES,
}

#: Valid mode names, in declaration order.
VALID_MODES: tuple[str, ...] = tuple(MODE_GATE_NAMES)

#: Lifecycle gates.  Required where they apply and never removable through a
#: gate modifier (L1-L4 run from their own publish/archive/distribute/localize
#: commands rather than from a preset).
LIFECYCLE_GATE_NAMES: list[str] = ["L1", "L2", "L3", "L4"]


def gate_names_for_mode(mode: str) -> list[str]:
    """Return a COPY of *mode*'s gate list.

    A copy, because callers compose/modify it (platform modifiers, tier
    filtering) and must never mutate the declared plan.
    """
    try:
        return list(MODE_GATE_NAMES[mode])
    except KeyError:
        raise ValueError(
            f"Unknown pipeline mode {mode!r}. Choose from: {list(MODE_GATE_NAMES)}"
        ) from None


__all__ = [
    "LIFECYCLE_GATE_NAMES",
    "MODE_GATE_NAMES",
    "VALID_MODES",
    "_AUTO_GATE_NAMES",
    "_IMAGE_CAROUSEL_GATE_NAMES",
    "_QA_ONLY_GATE_NAMES",
    "_REPURPOSE_GATE_NAMES",
    "_SHORT_VIDEO_GATE_NAMES",
    "_SOCIAL_THREAD_GATE_NAMES",
    "_TEXT_ONLY_GATE_NAMES",
    "_TEXT_WITH_COVER_GATE_NAMES",
    "_VIDEO_ONLY_GATE_NAMES",
    "gate_names_for_mode",
]
