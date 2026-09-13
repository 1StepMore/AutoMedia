#!/usr/bin/env python3
"""Generate ``docs/doc-inventory.md`` — a deterministic inventory of the docs tree.

Walks ``docs/`` (EXCLUDING ``docs/archived/``) plus the root instruction
files (``AGENTS.md``, ``README.md``) and emits a markdown table listing every
walked file with its path, size in bytes, and type (``dir`` for directories,
``file`` for files).

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


def _walked_files() -> list[Path]:
    """Every walked file, sorted deterministically by POSIX path string.

    Directories under docs/ are included (sorted the same way) so the
    inventory shows the tree shape.  docs/archived/ is excluded per plan,
    and the output file itself (docs/doc-inventory.md) is excluded — its
    size would otherwise depend on its own contents (a self-referential
    feedback loop that breaks byte-determinism).
    """
    files: list[Path] = []
    docs_root = REPO_ROOT / "docs"
    archived = docs_root / "archived"
    for path in docs_root.rglob("*"):
        if archived in path.parents or path == archived:
            continue
        if path == _OUTPUT:
            continue
        files.append(path)
    for name in ("AGENTS.md", "README.md"):
        path = REPO_ROOT / name
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda p: p.as_posix())


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
