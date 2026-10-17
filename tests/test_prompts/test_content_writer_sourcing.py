"""Deterministic tests for the generation-side sourcing constraint (#219).

Every ``content_writer.j2`` — the base template and each platform variant —
must carry the "no unsourced numbers" rule that mirrors Gate G0. The rule
lives in a single shared partial (``partials/no_unsourced_numbers.j2``) which
each template includes, so the constraint cannot drift between templates.

These tests render every template through the shipped loader
(:func:`automedia.prompts.load_prompt`) and assert on stable marker strings
rather than on free-form prose.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import automedia.prompts as prompts_mod
from automedia.prompts import load_prompt

PROMPTS_DIR = Path(prompts_mod.__file__).parent

# Stable markers emitted by partials/no_unsourced_numbers.j2.
_MARKER_NO_UNSOURCED = "NO_UNSOURCED_NUMBERS"
_MARKER_SOURCED_ONLY = "ONLY_USE_SOURCED_NUMBERS"


def _content_writer_variants() -> list[tuple[str, str | None]]:
    """Return ``(test_id, platform)`` for the base and every platform variant.

    ``platform=None`` selects the base ``content_writer.j2``; the platform
    names are derived from the ``platforms/<name>/content_writer.j2`` layout so
    a newly added platform variant is automatically covered.
    """
    variants: list[tuple[str, str | None]] = [("base", None)]
    variants.extend(
        (path.parent.name, path.parent.name)
        for path in sorted((PROMPTS_DIR / "platforms").glob("*/content_writer.j2"))
    )
    return variants


@pytest.fixture(autouse=True)
def _isolate_user_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the override dir at an empty path so rendering is deterministic.

    Without this, a developer's ``~/.automedia/overrides/prompts`` could shadow
    a built-in template and make the test depend on local machine state.
    """
    monkeypatch.setattr(prompts_mod, "_OVERRIDE_DIR", tmp_path / "no-overrides")


def test_all_content_writer_variants_are_discovered() -> None:
    """The base template plus at least one platform variant are exercised."""
    variants = _content_writer_variants()
    assert variants[0] == ("base", None)
    assert len(variants) >= 2


@pytest.mark.parametrize(
    ("test_id", "platform"),
    _content_writer_variants(),
    ids=[test_id for test_id, _ in _content_writer_variants()],
)
def test_content_writer_declares_no_unsourced_numbers(test_id: str, platform: str | None) -> None:
    """Each rendered content_writer prompt carries the sourcing constraint.

    The markers only become visible once the shared partial is resolved, so a
    rendered prompt containing them proves the template includes the partial.
    """
    rendered = load_prompt("content_writer", platform=platform, topic="t", brand="b")

    assert _MARKER_NO_UNSOURCED in rendered, (
        f"{test_id}: missing marker {_MARKER_NO_UNSOURCED!r} — did the "
        f"content_writer template drop its include of the shared partial?"
    )
    assert _MARKER_SOURCED_ONLY in rendered, (
        f"{test_id}: missing marker {_MARKER_SOURCED_ONLY!r} — the "
        f"'only use numbers found in the source material' rule is absent"
    )
