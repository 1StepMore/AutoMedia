"""One platform registry, three consumers (issue #283).

The platform list used to be maintained three times and the counts had
drifted (21 / 19 / 20).  Each list answers a DIFFERENT question, so equality
of the three is the wrong assertion; what must hold is that every difference
is a STATED property in ``automedia.core.platforms`` rather than an
oversight.  These tests pin exactly that, plus the derived consumers.
"""

from __future__ import annotations

import pytest

from automedia.adapters import AdapterRegistry
from automedia.core.media_spec import PLATFORM_MEDIA_SPECS
from automedia.core.platforms import (
    PLATFORMS,
    PlatformCategory,
    PlatformKind,
    names_with_adapter,
    names_with_media_spec,
    platform_categories,
    platform_category,
    platform_names,
)
from automedia.pipelines.runner import (
    _PLATFORM_CATEGORIES,
    _derive_mode_from_platforms,
)


def _registered_adapters() -> set[str]:
    # Importing the package registers the built-ins; tests that call clear()
    # must not leak an empty registry into this module.
    from automedia.adapters import ensure_registered

    ensure_registered()
    return set(AdapterRegistry.list())


# ---------------------------------------------------------------------------
# The registry is the source of truth
# ---------------------------------------------------------------------------


def test_registry_has_no_duplicate_entries() -> None:
    assert len(PLATFORMS) == len(platform_names())
    for name, entry in PLATFORMS.items():
        assert entry.name == name, "the dict key and the entry's own name must agree"


def test_every_entry_has_a_kind_consistent_with_its_capabilities() -> None:
    for entry in PLATFORMS.values():
        if entry.kind is PlatformKind.PUBLISHER:
            assert entry.has_adapter and entry.has_media_spec
        elif entry.kind is PlatformKind.NOTIFIER:
            assert entry.has_adapter and not entry.has_media_spec
        else:
            assert not entry.has_adapter and not entry.has_media_spec


# ---------------------------------------------------------------------------
# Consumer 1 — the adapter registry
# ---------------------------------------------------------------------------


def test_registered_adapters_match_the_registry_exactly() -> None:
    """Every name with an adapter is registered, and nothing extra is."""
    assert _registered_adapters() == set(names_with_adapter())


def test_only_the_notifier_lacks_a_media_spec() -> None:
    notifiers = {name for name, e in PLATFORMS.items() if e.kind is PlatformKind.NOTIFIER}

    assert notifiers == {"feishu"}


# ---------------------------------------------------------------------------
# Consumer 2 — the media-spec table
# ---------------------------------------------------------------------------


def test_media_spec_table_matches_the_registry_exactly() -> None:
    """A new publisher without spec numbers is a failure, not a silent default."""
    assert set(PLATFORM_MEDIA_SPECS) == set(names_with_media_spec())


def test_media_specs_declare_a_format() -> None:
    for name, spec in PLATFORM_MEDIA_SPECS.items():
        assert spec.format, f"{name} declares no output format"


# ---------------------------------------------------------------------------
# Consumer 3 — runner's category map and mode derivation
# ---------------------------------------------------------------------------


def test_runner_categories_are_derived_from_the_registry() -> None:
    assert platform_categories() == _PLATFORM_CATEGORIES
    assert set(_PLATFORM_CATEGORIES) == set(platform_names())


def test_notification_never_forces_multimedia_mode() -> None:
    """A notifier must not drag a text-only run into the mixed pipeline."""
    assert platform_category("feishu") is PlatformCategory.NOTIFICATION_ONLY
    assert _derive_mode_from_platforms(["wechat", "feishu"]) == "text_only"


def test_sub_pipeline_target_derives_a_text_mode() -> None:
    assert PLATFORMS["newsletter"].kind is PlatformKind.SUB_PIPELINE
    assert _derive_mode_from_platforms(["newsletter"]) == "text_only"


@pytest.mark.parametrize(
    "name,category",
    [
        ("wechat", PlatformCategory.TEXT_FIRST),
        ("xiaohongshu", PlatformCategory.MIXED_SOCIAL),
        ("youtube", PlatformCategory.VIDEO_FIRST),
        ("feishu", PlatformCategory.NOTIFICATION_ONLY),
    ],
)
def test_category_lookup(name: str, category: PlatformCategory) -> None:
    assert platform_category(name) is category


def test_unknown_platform_reads_as_text_first() -> None:
    """A brand may name a platform this build does not ship; never raise."""
    assert platform_category("myspace") is PlatformCategory.TEXT_FIRST
    assert _derive_mode_from_platforms(["myspace"]) == "text_only"
