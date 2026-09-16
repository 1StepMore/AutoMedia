"""Shared L1 publish-log wiring for every publish path.

Resolves a publish target set, builds one ``publish_log`` entry per target from
real project data, validates each entry with :class:`L1PublishLogSchema`, and
writes the entries to ``06_publish/publish_log.json`` — all BEFORE any
``PublishEngine.publish_all`` call.  Keeping this in one place means the MCP
``publish_content`` flow, ``distribute_to_platforms``, and the cron runner
cannot drift apart.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from automedia.gates.publish_log_schema import (
    PUBLISH_PLATFORM_SET,
    PUBLISH_PLATFORMS,
    L1PublishLogSchema,
)

PUBLISH_LOG_RELPATH = ("06_publish", "publish_log.json")

_MEDIA_DIRS = ("02_images", "03_video", "04_subtitle")


class PublishLogGateError(RuntimeError):
    """Raised when L1 blocks a publish (empty target set or schema failure)."""


def resolve_target_platforms(declared: Iterable[str] | None) -> list[str]:
    """Intersect *declared* with the 19-platform constant.

    ``declared is None`` means "no declaration" and falls back to the full
    constant (the plan's brand-empty rule).  An explicit — possibly empty —
    iterable is intersected as-is, so callers that resolved their own targets
    (e.g. ``AdapterRegistry.list()``) do not silently gain the full set.
    """
    if declared is None:
        return list(PUBLISH_PLATFORMS)
    return [name for name in declared if name in PUBLISH_PLATFORM_SET]


def brand_declared_platforms(brand_name: str) -> list[str] | None:
    """Return *brand_name*'s declared platforms, or ``None`` when undeclared."""
    if not brand_name:
        return None
    from automedia.manifests.brand_profile_schema import load_brand_profiles

    profile = load_brand_profiles().get(brand_name)
    if profile is None or not profile.platforms:
        return None
    return list(profile.platforms)


def build_publish_log_entries(
    artifact_dir: str,
    topic: str,
    platforms: Sequence[str],
) -> list[dict[str, Any]]:
    """Build one entry per platform from the project's topic + draft + media."""
    root = Path(artifact_dir)
    content = _read_primary_draft(root)
    media_paths = _collect_media_paths(root)
    created_at = datetime.now(UTC).isoformat()
    return [
        {
            "topic": topic,
            "content": content,
            "media_paths": list(media_paths),
            "platform": platform,
            "created_at": created_at,
        }
        for platform in platforms
    ]


def prepare_publish_log(
    artifact_dir: str,
    topic: str,
    declared_platforms: Iterable[str] | None,
) -> list[dict[str, Any]]:
    """Resolve targets, build + validate entries, write ``06_publish/publish_log.json``.

    Raises :class:`PublishLogGateError` when the target-set intersection is
    empty (nothing publishable) or when any entry fails L1 while the gate's
    declared ``failure_mode`` is ``"stop"``.  Returns the written entries so
    callers can record the exact target set they gated on.
    """
    targets = resolve_target_platforms(declared_platforms)
    if not targets:
        raise PublishLogGateError(
            "no publishable target: declared platforms do not intersect the publish-platform set"
        )

    entries = build_publish_log_entries(artifact_dir, topic, targets)

    gate = L1PublishLogSchema()
    for entry in entries:
        result = gate.execute({"publish_log": entry})
        if not bool(result.get("passed", False)) and gate.failure_mode == "stop":
            raise PublishLogGateError(
                f"L1 publish_log validation failed for platform {entry.get('platform')!r}"
            )

    _write_publish_log(artifact_dir, entries)
    return entries


def _read_primary_draft(root: Path) -> str:
    drafts_dir = root / "01_content" / "drafts"
    if not drafts_dir.is_dir():
        return ""
    md_files = sorted(drafts_dir.glob("*.md"))
    if not md_files:
        return ""
    return md_files[0].read_text(encoding="utf-8")


def _collect_media_paths(root: Path) -> list[str]:
    paths: list[str] = []
    for subdir in _MEDIA_DIRS:
        base = root / subdir
        if not base.is_dir():
            continue
        paths.extend(str(p) for p in sorted(base.rglob("*")) if p.is_file())
    return paths


def _write_publish_log(artifact_dir: str, entries: Sequence[dict[str, Any]]) -> Path:
    target = Path(artifact_dir).joinpath(*PUBLISH_LOG_RELPATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
