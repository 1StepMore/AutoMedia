"""The project directory layout, in one place (issue #284).

``Project.init()`` created six directories while the code wrote to thirteen
different paths, six of which it never created: a fresh project had to grow
its own folders at write time or fail.  Worse, TWO numbered directories meant
"publish": ``05_publish/{lang}/`` for Omni's localized output and
``06_publish/`` for the publish log — with ``05_`` already taken by
``05_review``.  Directory numbers are part of the interface: agent prompts,
user scripts and ``asset_library/ingest.py``'s phase table all key off them.

This module is the single source of truth.  Rules:

* Every top-level directory a project can contain is declared here.
* Numbered families are grouped by what the CONTENT is, not by the stage that
  produced it: ``04_*`` holds derived media and text artifacts, ``05_review``
  holds human/agent review output, ``06_publish`` holds everything that ships.
* :data:`LEGACY_PATHS` records the renamed paths so an existing project keeps
  working; readers resolve a legacy path when the canonical one is absent, and
  nothing ever writes a legacy path again.

There is no I/O beyond the small helpers below, and no imports from
``pipelines``/``adapters``/``omni``: this is a leaf module, so any writer can
depend on it without creating a cycle.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------- #
# Top-level directories
# --------------------------------------------------------------------------- #

CONTENT = "01_content"
"""Source content: ``drafts/`` and the pipeline's written copy."""

IMAGES = "02_images"
"""Generated imagery: ``cover/``, ``body/``, ``fallback/``."""

VIDEO = "03_video"
"""Rendered video output."""

SUBTITLE = "04_subtitle"
"""Subtitle files (SRT/VTT) rendered from audio."""

AUDIO = "04_audio"
"""TTS narration and its transcription (``narration.mp3`` / ``.srt``)."""

DISTRIBUTION = "04_distribution"
"""Per-platform distribution rewrites, one subdirectory per platform (D1-D7)."""

REPURPOSE = "04_repurpose"
"""Per-platform repurpose output from the P-gate sub-pipelines."""

RESEARCH_DATA = "research_data"
"""Omni OPP extraction output, one subdirectory per source document."""

REVIEW = "05_review"
"""Gate reports and review artifacts."""

PUBLISH = "06_publish"
"""Everything about publishing: ``{lang}/`` localized content and
``publish_log.json`` records.  ONE publish directory: the former
``05_publish`` was merged in here (issue #284)."""

# --------------------------------------------------------------------------- #
# Nested paths that more than one writer must agree on
# --------------------------------------------------------------------------- #

DRAFTS = f"{CONTENT}/drafts"
COVER = f"{IMAGES}/cover"
COVER_FILE = f"{IMAGES}/cover/cover.png"
BODY_IMAGES = f"{IMAGES}/body"
FALLBACK_IMAGES = f"{IMAGES}/fallback"
GATE_REPORT = f"{REVIEW}/gate-report"
PUBLISH_LOG = f"{PUBLISH}/publish_log.json"

#: Every top-level directory :func:`automedia.core.project.Project.init` creates.
#: A regression test asserts this covers every directory the code writes into,
#: so "writes to a directory the project never made" cannot come back.
PROJECT_SUBDIRS: tuple[str, ...] = (
    DRAFTS,
    COVER,
    VIDEO,
    SUBTITLE,
    AUDIO,
    DISTRIBUTION,
    REPURPOSE,
    RESEARCH_DATA,
    REVIEW,
    PUBLISH,
)

# --------------------------------------------------------------------------- #
# Legacy path support
# --------------------------------------------------------------------------- #

#: Mapping of a retired path to its canonical replacement.  A legacy path is
#: READ when the canonical one does not exist, so projects created before
#: issue #284 keep resolving their localized content.  Nothing writes these.
LEGACY_PATHS: dict[str, str] = {
    "05_publish": PUBLISH,
}


def publish_dir(project_dir: str | Path, *parts: str) -> Path:
    """Resolve *parts* under the publish directory, honoring the legacy name.

    This is what every publish-path consumer should call.  ``05_publish`` was
    the Omni layer's own publish directory before it merged into
    ``06_publish``; an existing project keeps resolving its files, and new
    writes always land in the canonical location.
    """
    return resolve_path(project_dir, "05_publish", *parts)


def resolve_path(project_dir: str | Path, legacy: str, *parts: str) -> Path:
    """Resolve *parts* under the canonical replacement for *legacy*.

    Returns the canonical path even when it does not exist yet — the caller
    decides whether to create it.  When the canonical path is missing but the
    legacy one exists, the legacy path is returned instead, so reads of an old
    project still find their files.
    """
    root = Path(project_dir)
    canonical = root / LEGACY_PATHS.get(legacy, legacy)
    for part in parts:
        canonical = canonical / part
    if canonical.exists():
        return canonical
    old = root / legacy
    for part in parts:
        old = old / part
    return old if old.exists() else canonical


__all__ = [
    "AUDIO",
    "BODY_IMAGES",
    "CONTENT",
    "COVER",
    "COVER_FILE",
    "DISTRIBUTION",
    "DRAFTS",
    "FALLBACK_IMAGES",
    "GATE_REPORT",
    "IMAGES",
    "LEGACY_PATHS",
    "PROJECT_SUBDIRS",
    "PUBLISH",
    "PUBLISH_LOG",
    "REPURPOSE",
    "RESEARCH_DATA",
    "REVIEW",
    "SUBTITLE",
    "VIDEO",
    "publish_dir",
    "resolve_path",
]
