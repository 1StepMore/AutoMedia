"""Contract tests for ``scripts/doc_inventory.py`` and its committed artifact.

Regression lock: the inventory must describe the git-TRACKED docs tree.  It
used to walk the filesystem, so untracked drafts (which do not exist in a CI
clone) were listed and the ``--check`` gate flipped red/green depending on
which scratch files happened to be present — it was comparing a working
directory against a committed file.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INVENTORY = REPO_ROOT / "docs" / "doc-inventory.md"
SCRIPT = REPO_ROOT / "scripts" / "doc_inventory.py"


def _listed_rows() -> list[tuple[str, str]]:
    """``(path, kind)`` for every inventory table row, header/separator dropped."""
    rows: list[tuple[str, str]] = []
    for line in INVENTORY.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 3:
            continue
        path, _size, kind = cells
        if path == "Path" or set(path) <= set("-: "):
            continue
        rows.append((path, kind))
    return rows


def _tracked_paths() -> set[str]:
    git = shutil.which("git")
    assert git is not None, "git is required to verify the docs inventory"
    out = subprocess.run(  # noqa: S603 — fixed argv, no shell, no user input
        [git, "-C", str(REPO_ROOT), "ls-files", "-z", "--", "docs", "AGENTS.md", "README.md"],
        capture_output=True,
        check=True,
    ).stdout
    return {name for name in out.decode("utf-8", "surrogateescape").split("\0") if name}


def test_inventory_lists_only_tracked_paths() -> None:
    tracked = _tracked_paths()

    bad_files = [path for path, kind in _listed_rows() if kind == "file" and path not in tracked]
    assert not bad_files, f"inventory lists untracked files: {bad_files}"

    listed_dirs = [path for path, kind in _listed_rows() if kind == "dir"]
    bad_dirs = [d for d in listed_dirs if not any(t.startswith(f"{d}/") for t in tracked)]
    assert not bad_dirs, f"inventory lists directories holding no tracked file: {bad_dirs}"


def test_check_mode_reports_no_drift() -> None:
    proc = subprocess.run(  # noqa: S603 — fixed argv, no shell, no user input
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
