#!/usr/bin/env python3
"""Locate the newest production artifact and pin it to a stable path.

Production runs write timestamped artifact filenames, so validation scenarios
cannot address them statically.  This locator searches every project directory
under ``<projects-dir>`` for a glob that is relative to the project root (for
example ``01_content/drafts/*_draft.md``), picks the match with the newest
modification time, and optionally links that file to a stable path the scenario
can then inspect.

Usage::

    python3 scripts/production_artifact.py <projects-dir> <relative-glob> \\
        --link <stable-path> [--emit json|text]

Behaviour:

* ``--link`` creates the target's parent directories, replaces any existing
  file/link at the target, and creates a symlink to the chosen source.  When
  symlinks are unavailable (for example Windows without the symlink privilege)
  it falls back to ``shutil.copy2``.  The stable path is always readable as a
  normal file afterwards.
* ``--emit json`` (default) prints a single JSON object::

      {"path": "<resolved source path>", "size": <bytes>, "project": "<dir name>"}

* ``--emit text`` prints the chosen file's UTF-8 content instead of JSON.
* No match or a missing ``<projects-dir>`` prints an error to stderr and exits 1.

Examples::

    python3 scripts/production_artifact.py /tmp/automedia/prod-article \\
        "01_content/drafts/*_draft.md" \\
        --link /tmp/automedia/prod-article/article.md

    python3 scripts/production_artifact.py /tmp/automedia/prod-article \\
        "01_content/drafts/*_draft.md" --emit text

Standard library only; safe to run from any working directory.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_FAILURE = 1


def find_newest(projects_dir: Path, relative_glob: str) -> tuple[Path, str] | None:
    """Return ``(path, project_name)`` for the newest match, or ``None``.

    ``relative_glob`` is interpreted under each project directory, which is why
    the search runs from ``projects_dir`` (``rglob`` matches the glob at any
    depth) and the project name is the first component of the relative path.
    The newest match wins; equal mtimes are broken by the lexicographically
    largest absolute path so the choice is deterministic.
    """
    matches = [candidate for candidate in projects_dir.rglob(relative_glob) if candidate.is_file()]
    if not matches:
        return None

    newest = max(matches, key=lambda candidate: (candidate.stat().st_mtime, str(candidate)))
    relative = newest.relative_to(projects_dir)
    project = relative.parts[0] if len(relative.parts) > 1 else projects_dir.name
    return newest, project


def pin_artifact(source: Path, stable_path: Path) -> None:
    """Make ``stable_path`` a readable alias of ``source``.

    A symlink is preferred; any ``OSError`` (notably a Windows install without
    the symlink privilege) falls back to a full copy.  An existing file or link
    at the target is removed first, and the source itself is never deleted.
    """
    resolved_source = source.resolve()
    stable_path.parent.mkdir(parents=True, exist_ok=True)

    if os.path.abspath(stable_path) == os.path.abspath(resolved_source):
        return  # The target already is the source; nothing to pin.

    if os.path.lexists(stable_path):
        stable_path.unlink()

    try:
        stable_path.symlink_to(resolved_source)
    except OSError:
        shutil.copy2(resolved_source, stable_path)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser with self-documenting help text."""
    parser = argparse.ArgumentParser(
        prog="production_artifact.py",
        description=(
            "Find the newest artifact matching a project-relative glob across all "
            "project directories, then optionally pin it to a stable path."
        ),
        epilog=(
            "Examples:\n"
            "  python3 scripts/production_artifact.py /tmp/automedia/prod-article \\\n"
            '      "01_content/drafts/*_draft.md" \\\n'
            "      --link /tmp/automedia/prod-article/article.md\n"
            "  python3 scripts/production_artifact.py /tmp/automedia/prod-article \\\n"
            '      "01_content/drafts/*_draft.md" --emit text\n\n'
            "Exit status: 0 on success, 1 when no artifact matches or the projects "
            "directory is missing."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "projects_dir",
        metavar="PROJECTS_DIR",
        help="Directory whose immediate subdirectories are project directories.",
    )
    parser.add_argument(
        "relative_glob",
        metavar="RELATIVE_GLOB",
        help=(
            "Glob relative to each project directory, e.g. "
            '"01_content/drafts/*_draft.md" or "02_images/body/*.png".'
        ),
    )
    parser.add_argument(
        "--link",
        metavar="STABLE_PATH",
        default=None,
        help=(
            "Stable path to create (parent directories included). A symlink is used, "
            "with a copy fallback when symlinks are unavailable."
        ),
    )
    parser.add_argument(
        "--emit",
        choices=("json", "text"),
        default="json",
        help=(
            "Output format: 'json' (default) prints path/size/project metadata; "
            "'text' prints the artifact's UTF-8 content."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the locator and return the process exit code."""
    args = build_parser().parse_args(argv)
    projects_dir = Path(args.projects_dir)

    if not projects_dir.is_dir():
        print(f"error: projects directory not found: {projects_dir}", file=sys.stderr)
        return EXIT_FAILURE

    found = find_newest(projects_dir, args.relative_glob)
    if found is None:
        print(
            f"error: no file matched {args.relative_glob!r} under {projects_dir}",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    source, project = found

    if args.link is not None:
        try:
            pin_artifact(source, Path(args.link))
        except OSError as exc:
            print(f"error: could not create stable path {args.link}: {exc}", file=sys.stderr)
            return EXIT_FAILURE

    if args.emit == "text":
        sys.stdout.write(source.read_text(encoding="utf-8"))
    else:
        payload = {
            "path": str(source.resolve()),
            "size": source.stat().st_size,
            "project": project,
        }
        print(json.dumps(payload))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
