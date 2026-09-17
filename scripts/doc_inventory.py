#!/usr/bin/env python3
"""Generate ``docs/doc-inventory.md`` — a deterministic inventory of the docs tree.

Inventories the **git-tracked** files under ``docs/`` (EXCLUDING
``docs/archived/``) plus the root instruction files (``AGENTS.md``,
``README.md``), and emits a markdown table listing each with its path, size in
bytes, and type (``dir`` for directories, ``file`` for files).

Tracked, not on-disk: the inventory is a COMMITTED artifact and ``--check``
runs on a clean CI clone.  An on-disk walk also counted untracked drafts and
gitignored files that do not exist in the clone, so the gate compared "this
working directory" against "the committed tree" and flipped red/green
depending on whose scratch files happened to be present.  Listing the tracked
set makes both sides describe the same thing; ``git add`` a new doc and
regenerate to include it.

Deterministic: the walk order is sorted by POSIX path string
(``sorted(..., key=lambda p: p.as_posix())``), so two runs produce
byte-identical output.  The first line is exactly the AUTO-GENERATED marker
(byte-identical to the ``MARKER`` constant in ``tests/test_doc_consistency.py``
and the checker's ``_INVENTORY_MARKER``).

``--check`` mode regenerates the inventory in memory and diffs it against the
committed file: exit 0 on a byte match, exit 1 on any difference.

MANUAL-ONLY regeneration, CI-CHECKED drift: the ``--check`` mode is wired into
CI (``.github/workflows/ci.yml``, T-13) so a stale committed inventory fails the
build; ``automedia``-runs the file only changes when someone means it to
(regenerate with ``python3 scripts/doc_inventory.py``).  The marker check on
the committed file also runs inside ``scripts/check-doc-consistency.py`` (the
one doc-consistency step).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Exact first line of the generated file.  Must be byte-identical to the
# ``MARKER`` in tests/test_doc_consistency.py.
MARKER = (
    "<!-- AUTO-GENERATED: docs/doc-inventory.md — do not edit manually. "
    "Regenerate: python scripts/doc_inventory.py -->"
)

_OUTPUT = REPO_ROOT / "docs" / "doc-inventory.md"

# Walked roots, in this order: the docs tree (excluding archived/) then the
# two root instruction files.
_WALK_ROOTS: tuple[Path, ...] = (REPO_ROOT / "docs",)

#: ``git ls-files`` pathspecs covering the inventory's scope.
_TRACKED_PATHSPECS: tuple[str, ...] = ("docs", "AGENTS.md", "README.md")

_DOCS_ROOT = REPO_ROOT / "docs"
_ARCHIVED_ROOT = _DOCS_ROOT / "archived"

_INSTRUCTION_FILES: tuple[str, ...] = ("AGENTS.md", "README.md")


def _git_tracked_files() -> list[Path] | None:
    """Repo-absolute paths of every git-tracked file in the inventory's scope.

    Returns ``None`` when git cannot be consulted (no ``.git``, git not
    installed), so :func:`_walked_files` can fall back to a filesystem walk.
    """
    git = shutil.which("git")
    if git is None:
        return None
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell, no user input
            [git, "-C", str(REPO_ROOT), "ls-files", "-z", "--", *_TRACKED_PATHSPECS],
            capture_output=True,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    names = proc.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    return [REPO_ROOT / name for name in names if name]


def _filesystem_files() -> list[Path]:
    """On-disk fallback; only reached without a git checkout (see _walked_files)."""
    on_disk = [path for path in _DOCS_ROOT.rglob("*") if path != _DOCS_ROOT]
    on_disk.extend(path for path in (REPO_ROOT / n for n in _INSTRUCTION_FILES) if path.is_file())
    return on_disk


def _is_inventoried(path: Path) -> bool:
    if path == _OUTPUT:
        return False
    if path == _ARCHIVED_ROOT or _ARCHIVED_ROOT in path.parents:
        return False
    return path != _DOCS_ROOT


def _with_ancestor_dirs(files: list[Path]) -> list[Path]:
    """The files plus every directory strictly under ``docs/`` containing one.

    Directory rows show the tree shape.  They are derived from the file set
    rather than from ``rglob`` because git tracks no empty directories — a row
    for one would not exist in a clean clone.
    """
    dirs: set[Path] = set()
    for path in files:
        if _DOCS_ROOT not in path.parents:
            continue
        for parent in path.parents:
            if parent == _DOCS_ROOT:
                break
            dirs.add(parent)
    return [*files, *dirs]


def _walked_files() -> list[Path]:
    """Every inventoried path, sorted deterministically by POSIX path string.

    ``docs/archived/`` is excluded per plan, and the output file itself
    (``docs/doc-inventory.md``) is excluded — its size would otherwise depend
    on its own contents (a self-referential feedback loop that breaks
    byte-determinism).
    """
    tracked = _git_tracked_files()
    if tracked is None:
        print(
            "WARNING: git unavailable — falling back to a filesystem walk; the "
            "inventory may include untracked files (see _git_tracked_files).",
            file=sys.stderr,
        )
        candidates = _filesystem_files()
    else:
        candidates = [path for path in tracked if path.is_file()]
    files = [path for path in candidates if _is_inventoried(path)]
    return sorted(_with_ancestor_dirs(files), key=lambda p: p.as_posix())


def _rel_label(path: Path) -> str:
    """The inventory label for a path: repo-relative when under the repo
    root, else the POSIX path string (never happens today)."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def generate() -> str:
    """Build the inventory markdown in memory (deterministic)."""
    lines = [MARKER, "", "## Doc Inventory", ""]
    lines.append("| Path | Size (bytes) | Type |")
    lines.append("|------|-------------:|------|")
    for path in _walked_files():
        label = _rel_label(path)
        if path.is_dir():
            lines.append(f"| {label} | — | dir |")
        else:
            lines.append(f"| {label} | {path.stat().st_size} | file |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Generate the inventory; ``--check`` exits 1 when the committed file differs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in memory and diff against the committed file; "
        "exit 1 on any difference, 0 on a byte match.",
    )
    args = parser.parse_args(argv)

    generated = generate()
    if args.check:
        try:
            committed = _OUTPUT.read_text(encoding="utf-8")
        except OSError:
            print(f"FAIL: {_OUTPUT} is missing (run python scripts/doc_inventory.py)")
            return 1
        if committed == generated:
            print(f"OK: {_OUTPUT} matches the generated inventory")
            return 0
        print(
            f"FAIL: {_OUTPUT} differs from the generated inventory "
            f"(run python scripts/doc_inventory.py)"
        )
        return 1

    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(generated, encoding="utf-8")
    print(f"Wrote {_OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
