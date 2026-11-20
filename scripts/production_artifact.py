#!/usr/bin/env python3
"""Locate the newest production artifact and pin it to a stable path.

Production runs write timestamped artifact filenames, so validation scenarios
cannot address them statically.  This locator searches every project directory
under ``<projects-dir>`` for a glob that is relative to the project root (for
example ``01_content/drafts/*_draft.md``), picks the match with the newest
modification time, and optionally links that file to a stable path the scenario
can then inspect.

Prefer ``--provenance`` for critical comparisons.  When several files match the
glob this tool **silently picks the newest**; that is convenient for locating
"the latest artifact" but wrong for content comparisons when a later rewrite
created a file the narrated run never read (AutoMedia#599).  Pass
``--provenance "04_audio/narration.provenance.json"`` to follow the pipeline's
own record of the source draft instead.

Usage::

    python3 scripts/production_artifact.py <projects-dir> <relative-glob> \\
        --link <stable-path> [--emit json|text] \\
        [--provenance <project-relative-provenance-json>]

Behaviour:

* ``--provenance`` reads ``source_draft`` (a project-relative path) from the
  newest matching provenance file and uses that exact file.  If the file is
  missing, unreadable, or names a path outside its project, the locator prints
  a warning to stderr and falls back to the glob — the fallback is convenient
  but can silently pick a newer draft, so scenarios must keep the warning
  visible.
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

    Note: multiple matches are resolved **silently** to the newest one.  A
    caller comparing content (not merely locating a fresh artifact) should use
    :func:`find_from_provenance` to name the exact file.
    """
    matches = [candidate for candidate in projects_dir.rglob(relative_glob) if candidate.is_file()]
    if not matches:
        return None

    newest = max(matches, key=lambda candidate: (candidate.stat().st_mtime, str(candidate)))
    relative = newest.relative_to(projects_dir)
    project = relative.parts[0] if len(relative.parts) > 1 else projects_dir.name
    return newest, project


def resolve_provenance(provenance_path: Path) -> Path | None:
    """Return the draft named by ``source_draft`` in a provenance JSON, or ``None``.

    ``provenance_path`` is ``<project>/04_audio/narration.provenance.json`` and
    ``source_draft`` is relative to ``<project>/``.  Any unreadable file,
    malformed JSON, missing path, or escape outside the project yields ``None``
    so the caller can fall back to the glob.
    """
    try:
        payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    source = payload.get("source_draft")
    if not isinstance(source, str) or not source.strip():
        return None

    project_root = provenance_path.parent.parent
    candidate = (project_root / source).resolve()
    try:
        candidate.relative_to(project_root.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def find_from_provenance(projects_dir: Path, provenance_rel: str) -> tuple[Path, str] | None:
    """Return ``(path, project_name)`` from the newest usable provenance file.

    Multiple provenance files are considered newest-first; the first one whose
    ``source_draft`` resolves inside its project wins.  ``None`` means no
    provenance was usable and the caller should fall back to the glob.
    """
    matches = [candidate for candidate in projects_dir.rglob(provenance_rel) if candidate.is_file()]
    if not matches:
        return None
    ordered = sorted(
        matches, key=lambda candidate: (candidate.stat().st_mtime, str(candidate)), reverse=True
    )
    for provenance in ordered:
        source = resolve_provenance(provenance)
        if source is None:
            continue
        try:
            relative = provenance.relative_to(projects_dir)
        except ValueError:
            continue
        project = relative.parts[0] if len(relative.parts) > 1 else projects_dir.name
        return source, project
    return None


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
        "--provenance",
        metavar="PROVENANCE_JSON",
        default=None,
        help=(
            "Project-relative provenance file (e.g. "
            '"04_audio/narration.provenance.json"). Its ``source_draft`` names '
            "the exact file to pin; when unavailable the locator falls back to "
            "the newest glob match."
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

    found = None
    if args.provenance is not None:
        found = find_from_provenance(projects_dir, args.provenance)
        if found is None:
            print(
                f"warning: no usable provenance at {args.provenance!r} under "
                f"{projects_dir}; falling back to the newest glob match "
                f"{args.relative_glob!r} (may pick a draft this run never read)",
                file=sys.stderr,
            )
    if found is None:
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
