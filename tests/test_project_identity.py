"""Project-identity loading — ``Project.load`` and ``find_project_dir`` (issue #108).

These lock the two additions that let a parked project be re-identified by its
persisted ``project_id`` instead of minting a fresh one on resume.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from automedia.core.project import Project, find_project_dir

_INFO_FILENAME = "00_project_info.json"


def _write_info(project_dir: Path, payload: object) -> None:
    """Write a raw ``00_project_info.json`` payload into *project_dir*."""
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / _INFO_FILENAME).write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# Project.load
# ---------------------------------------------------------------------------


def test_load_round_trips_project_init(tmp_path: Path) -> None:
    """A project loaded from disk carries the identity init minted."""
    p = Project.init("topic", "brand", base_dir=str(tmp_path))
    loaded = Project.load(p.project_dir)
    assert loaded.project_id == p.project_id
    assert loaded.topic == p.topic
    assert loaded.brand == p.brand


def test_load_raises_on_missing_info_file(tmp_path: Path) -> None:
    """A directory without an info file is not a project."""
    empty = tmp_path / "not-a-project"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        Project.load(str(empty))


def test_load_raises_on_corrupt_info(tmp_path: Path) -> None:
    """Malformed JSON is surfaced as ValueError, not a JSONDecodeError leak."""
    _write_info(tmp_path / "corrupt", "{not valid json")
    with pytest.raises(ValueError):
        Project.load(str(tmp_path / "corrupt"))


def test_load_raises_when_project_id_absent(tmp_path: Path) -> None:
    """Valid JSON without project_id cannot identify a project."""
    _write_info(tmp_path / "no-id", {"topic": "t", "brand": "b"})
    with pytest.raises(ValueError):
        Project.load(str(tmp_path / "no-id"))


# ---------------------------------------------------------------------------
# find_project_dir
# ---------------------------------------------------------------------------


def test_find_project_dir_matches_by_id(tmp_path: Path) -> None:
    """A seeded project is found by its persisted id."""
    p = Project.init("topic", "brand", base_dir=str(tmp_path))
    found = find_project_dir(p.project_id, base_dir=str(tmp_path))
    assert found == p.project_dir


def test_find_project_dir_returns_none_for_unknown_id(tmp_path: Path) -> None:
    """An id that matches nothing yields None."""
    Project.init("topic", "brand", base_dir=str(tmp_path))
    assert find_project_dir("deadbeefcafe", base_dir=str(tmp_path)) is None


def test_find_project_dir_honours_base_dir(tmp_path: Path) -> None:
    """Only projects under base_dir are scanned; a same-id dir outside is skipped."""
    base = tmp_path / "base"
    p = Project.init("topic", "brand", base_dir=str(base))

    # A decoy with the exact same project_id living outside base_dir.
    decoy = tmp_path / "outside" / "20260101_topic"
    _write_info(
        decoy,
        {
            "project_id": p.project_id,
            "topic": "decoy",
            "brand": "brand",
            "tenant_id": "default",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    )

    found = find_project_dir(p.project_id, base_dir=str(base))
    assert found == p.project_dir
    assert found is not None
    assert Path(found).is_relative_to(base)


def test_find_project_dir_uses_env_var_when_base_dir_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no base_dir, AUTOMEDIA_PROJECTS_DIR drives the scan."""
    p = Project.init("topic", "brand", base_dir=str(tmp_path))
    monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(tmp_path))
    assert find_project_dir(p.project_id) == p.project_dir
