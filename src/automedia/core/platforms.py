"""The single source of truth for platform identity.

Three lists used to describe "the platforms" independently, and they had
drifted apart (issue #283):

* ``pipelines.runner._PLATFORM_CATEGORIES`` — 21 names, mapped to a content
  category for auto-deriving the pipeline mode.
* ``core.media_spec.PLATFORM_MEDIA_SPECS`` — 19 names, each with real
  width/height/format numbers.
* ``adapters.AdapterRegistry`` — 20 names, the adapters that can actually
  publish or notify.

The counts differed because the three lists answered three different
questions, and nothing recorded WHY a name was in one and not the others.
This module records the answer once: every platform is an entry with a
:class:`PlatformKind` and a :class:`PlatformCategory`, so a missing media
spec or a missing adapter is a stated property, not an oversight.

The two names that used to look like drift are both deliberate:

* ``feishu`` is a NOTIFIER (``notification-only``); it has an adapter but no
  media spec, because a notification has no width or aspect ratio.
* ``newsletter`` is a SUB_PIPELINE target served by the P3 repurpose gate
  (``04_repurpose/newsletter/``); it has neither an adapter nor a media
  spec, because it is not distributed through the platform registry.

No I/O, no imports from ``adapters`` or ``pipelines``: this module is a leaf
so every consumer can depend on it without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PlatformKind(StrEnum):
    """What a platform name can be used for."""

    PUBLISHER = "publisher"
    """Distributes finished content; has an adapter and a media spec."""

    NOTIFIER = "notifier"
    """Sends a notification (no media); has an adapter, no media spec."""

    SUB_PIPELINE = "sub-pipeline"
    """A repurpose target, not a distribution channel: no adapter, no spec."""


class PlatformCategory(StrEnum):
    """Content shape a platform expects, used to auto-derive the pipeline mode."""

    TEXT_FIRST = "text-first"
    MIXED_SOCIAL = "mixed-social"
    VIDEO_FIRST = "video-first"
    NOTIFICATION_ONLY = "notification-only"


@dataclass(frozen=True)
class PlatformEntry:
    """One platform, with everything the rest of the code needs to know about it."""

    name: str
    category: PlatformCategory
    kind: PlatformKind

    @property
    def has_adapter(self) -> bool:
        """True when ``AdapterRegistry`` must hold an adapter for this name."""
        return self.kind is not PlatformKind.SUB_PIPELINE

    @property
    def has_media_spec(self) -> bool:
        """True when ``PLATFORM_MEDIA_SPECS`` must carry a spec for this name."""
        return self.kind is PlatformKind.PUBLISHER


def _entry(name: str, category: PlatformCategory, kind: PlatformKind) -> tuple[str, PlatformEntry]:
    return name, PlatformEntry(name=name, category=category, kind=kind)


_TEXT = PlatformCategory.TEXT_FIRST
_SOCIAL = PlatformCategory.MIXED_SOCIAL
_VIDEO = PlatformCategory.VIDEO_FIRST
_NOTIFY = PlatformCategory.NOTIFICATION_ONLY

_PUB = PlatformKind.PUBLISHER
_NOTIF = PlatformKind.NOTIFIER
_SUB = PlatformKind.SUB_PIPELINE

#: Every platform AutoMedia knows about, keyed by its canonical name.
PLATFORMS: dict[str, PlatformEntry] = dict(
    (
        _entry("wechat", _TEXT, _PUB),
        _entry("zhihu", _TEXT, _PUB),
        _entry("xiaohongshu", _SOCIAL, _PUB),
        _entry("feishu", _NOTIFY, _NOTIF),
        _entry("youtube", _VIDEO, _PUB),
        _entry("twitter", _TEXT, _PUB),
        _entry("bilibili", _VIDEO, _PUB),
        _entry("tiktok", _VIDEO, _PUB),
        _entry("linkedin", _TEXT, _PUB),
        _entry("medium", _TEXT, _PUB),
        _entry("newsletter", _TEXT, _SUB),
        _entry("douyin", _VIDEO, _PUB),
        _entry("wordpress", _TEXT, _PUB),
        _entry("reddit", _TEXT, _PUB),
        _entry("baijiahao", _TEXT, _PUB),
        _entry("juejin", _TEXT, _PUB),
        _entry("toutiao", _TEXT, _PUB),
        _entry("facebook", _SOCIAL, _PUB),
        _entry("instagram", _SOCIAL, _PUB),
        _entry("weibo", _TEXT, _PUB),
        _entry("kuaishou", _VIDEO, _PUB),
    )
)


def platform_names() -> list[str]:
    """Every known platform name, sorted."""
    return sorted(PLATFORMS)


def names_with_adapter() -> list[str]:
    """Platform names that must be registered in ``AdapterRegistry``, sorted."""
    return sorted(name for name, entry in PLATFORMS.items() if entry.has_adapter)


def names_with_media_spec() -> list[str]:
    """Platform names that must carry a ``PLATFORM_MEDIA_SPECS`` entry, sorted."""
    return sorted(name for name, entry in PLATFORMS.items() if entry.has_media_spec)


def platform_category(name: str) -> PlatformCategory:
    """Return *name*'s category; unknown names read as ``text-first``.

    Unknown names deliberately do not raise: a brand profile may name a
    platform this build does not ship, and the pipeline-mode derivation must
    still produce a sane answer (the previous dict's ``.get(p, "text-first")``
    fallback behaved the same way).
    """
    entry = PLATFORMS.get(name)
    return entry.category if entry is not None else PlatformCategory.TEXT_FIRST


def platform_categories() -> dict[str, str]:
    """The name -> category mapping, as plain strings.

    Derived from :data:`PLATFORMS`; callers that need the historical dict
    shape (including tests) can use this instead of maintaining their own copy.
    """
    return {name: str(entry.category) for name, entry in PLATFORMS.items()}


__all__ = [
    "PLATFORMS",
    "PlatformCategory",
    "PlatformEntry",
    "PlatformKind",
    "names_with_adapter",
    "names_with_media_spec",
    "platform_categories",
    "platform_category",
    "platform_names",
]
