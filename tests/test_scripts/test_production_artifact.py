"""Tests for ``scripts/production_artifact.py``.

The locator pins timestamped production artifacts to a stable path for
validation scenarios.  These tests build synthetic project trees in
``tmp_path`` and drive the script through a subprocess with the current
interpreter, which also proves it works when invoked by absolute path from an
unrelated working directory.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "production_artifact.py"
DRAFT_GLOB = "01_content/drafts/*_draft.md"


def _write_artifact(project: Path, name: str, content: str, mtime: float) -> Path:
    path = project / "01_content" / "drafts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def _run(*args: str | Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        check=False,
    )


def test_picks_newest_artifact_and_reports_metadata(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    _write_artifact(projects / "proj-old", "old_draft.md", "old draft\n", 1_000_000)
    newer_content = "new draft body\nwith two lines\n"
    newer = _write_artifact(projects / "proj-new", "new_draft.md", newer_content, 2_000_000)

    result = _run(projects, DRAFT_GLOB, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "path": str(newer.resolve()),
        "size": len(newer_content.encode("utf-8")),
        "project": "proj-new",
    }


def test_equal_mtimes_break_on_lexicographically_largest_path(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    _write_artifact(projects / "proj-a", "a_draft.md", "a\n", 1_500_000)
    winner = _write_artifact(projects / "proj-b", "b_draft.md", "b\n", 1_500_000)

    result = _run(projects, DRAFT_GLOB, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["path"] == str(winner.resolve())
    assert payload["project"] == "proj-b"


def test_missing_match_exits_one(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()

    result = _run(projects, DRAFT_GLOB, cwd=tmp_path)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "no file matched" in result.stderr


def test_missing_projects_dir_exits_one(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    result = _run(missing, DRAFT_GLOB, cwd=tmp_path)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "not found" in result.stderr


def test_link_creates_readable_stable_path(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    _write_artifact(projects / "proj-old", "old_draft.md", "old\n", 1_000_000)
    content = "stable content\n"
    source = _write_artifact(projects / "proj-new", "new_draft.md", content, 2_000_000)
    stable = tmp_path / "stable" / "nested" / "article.md"

    result = _run(projects, DRAFT_GLOB, "--link", stable, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert stable.is_file()
    assert stable.read_text(encoding="utf-8") == content
    assert json.loads(result.stdout)["path"] == str(source.resolve())


def test_link_replaces_existing_stable_path(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    content = "fresh content\n"
    _write_artifact(projects / "proj", "ts_draft.md", content, 2_000_000)
    stable = tmp_path / "article.md"
    stable.write_text("stale content\n", encoding="utf-8")

    result = _run(projects, DRAFT_GLOB, "--link", stable, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert stable.read_text(encoding="utf-8") == content


def test_emit_text_prints_content_not_json(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    content = "# Heading\n\nBody paragraph.\n"
    _write_artifact(projects / "proj", "ts_draft.md", content, 2_000_000)

    result = _run(projects, DRAFT_GLOB, "--emit", "text", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == content
    assert not result.stdout.startswith("{")
