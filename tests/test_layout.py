"""The project layout has one source of truth (issue #284).

Before this module, ``Project.init()`` created six directories while the code
wrote to thirteen; six of those were never created.  Two numbered directories
also both meant "publish".  These tests pin the fix:

* every directory the code writes into is declared in ``core.layout``;
* ``Project.init()`` creates all of them;
* the retired ``05_publish`` still resolves for existing projects, and new
  writes never create it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from automedia.core import layout
from automedia.core.project import Project

_SRC = Path(__file__).resolve().parent.parent / "src" / "automedia"

# Any quoted "<two digits>_<name>" or "research_data" literal in the source is
# a candidate layout directory.  Collecting them from the tree is what catches
# a NEW writer that invents a directory instead of declaring it.
_DIR_LITERAL_RE = re.compile(r'"(0[0-9]_[a-z_]+|research_data)"')
_COVERED_RE = re.compile(r"^\d\d_[a-z_]+$|^research_data$")


def _directories_referenced_in_source() -> set[str]:
    found: set[str] = set()
    for path in _SRC.rglob("*.py"):
        if path == _SRC / "core" / "layout.py":
            continue  # the declaration site itself
        found.update(_DIR_LITERAL_RE.findall(path.read_text(encoding="utf-8")))
    return found


def _declared_directories() -> set[str]:
    """Every top-level directory name the layout declares, including parents."""
    declared: set[str] = set()
    for rel in layout.PROJECT_SUBDIRS:
        declared.add(rel.split("/")[0])
    # Constants that name a top-level directory without being in PROJECT_SUBDIRS.
    for value in layout.__all__:
        candidate = getattr(layout, value)
        if isinstance(candidate, str) and _COVERED_RE.match(candidate):
            declared.add(candidate.split("/")[0])
    return {name for name in declared if _COVERED_RE.match(name)}


# ---------------------------------------------------------------------------
# One declaration covers every writer
# ---------------------------------------------------------------------------


def test_every_directory_written_by_the_code_is_declared() -> None:
    """A new hardcoded directory must be declared in core.layout first."""
    declared = _declared_directories()
    undeclared = _directories_referenced_in_source() - declared

    assert undeclared == set(), (
        "these directories are written by the code but not declared in "
        f"automedia.core.layout: {sorted(undeclared)}"
    )


def test_project_init_creates_every_declared_directory(tmp_path: Path) -> None:
    """The regression #284 names: writes to a directory Project.init forgot."""
    project = Project.init(topic_slug="layout test", brand="TestBrand", base_dir=str(tmp_path))
    root = Path(project.project_dir)

    missing = [sub for sub in layout.PROJECT_SUBDIRS if not (root / sub).is_dir()]
    assert missing == [], f"Project.init did not create: {missing}"


def test_derived_media_directories_do_not_collide_with_numbering() -> None:
    """Two directories must never share a number prefix."""
    tops = {rel.split("/")[0] for rel in layout.PROJECT_SUBDIRS}

    assert len(tops) == len(set(tops))


# ---------------------------------------------------------------------------
# 05_publish / 06_publish: one publish directory, with a legacy read path
# ---------------------------------------------------------------------------


def test_publish_is_the_only_publish_directory(tmp_path: Path) -> None:
    assert layout.PUBLISH == "06_publish"
    assert layout.LEGACY_PATHS == {"05_publish": layout.PUBLISH}


def test_new_publish_path_is_canonical_when_nothing_exists(tmp_path: Path) -> None:
    resolved = layout.publish_dir(tmp_path, "en")

    assert resolved == tmp_path / "06_publish" / "en"
    assert not (tmp_path / "05_publish").exists()


def test_existing_legacy_publish_directory_still_resolves(tmp_path: Path) -> None:
    """A project created before #284 keeps finding its localized content."""
    legacy = tmp_path / "05_publish" / "ja"
    legacy.mkdir(parents=True)
    (legacy / "article.md").write_text("legacy", encoding="utf-8")

    resolved = layout.publish_dir(tmp_path, "ja")

    assert resolved == legacy
    assert (resolved / "article.md").read_text(encoding="utf-8") == "legacy"


def test_canonical_wins_when_both_exist(tmp_path: Path) -> None:
    (tmp_path / "05_publish").mkdir()
    (tmp_path / "06_publish").mkdir()

    assert layout.publish_dir(tmp_path, "en") == tmp_path / "06_publish" / "en"


@pytest.mark.parametrize("lang", ["en", "ja", "zh-CN"])
def test_omni_output_paths_land_under_06_publish(tmp_path: Path, lang: str) -> None:
    from automedia.omni.artifact_mapping import ol_output_path, orf_output_path

    assert ol_output_path(tmp_path, lang, mkdir=True) == tmp_path.resolve() / "06_publish" / lang
    assert (
        orf_output_path(tmp_path, lang, mkdir=True)
        == tmp_path.resolve() / "06_publish" / lang / "deliverables"
    )


def test_writers_never_create_the_legacy_directory(tmp_path: Path) -> None:
    from automedia.omni.artifact_mapping import ol_output_path, orf_output_path

    ol_output_path(tmp_path, "en", mkdir=True)
    orf_output_path(tmp_path, "en", mkdir=True)

    assert not (tmp_path / "05_publish").exists()
