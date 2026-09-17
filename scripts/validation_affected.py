#!/usr/bin/env python3
"""Affected-area mapper for the agent-tester validation CI gate (plan W5-T3).

The executable machinery of the affected-area gate: maps a set of changed
repo-relative file paths (``git diff --name-only`` output) to the scenario
subset whose behavior they may affect.  ``impact_map`` in
docs/dev/project-validation-framework.md is DOC-ONLY (plan review fix m4) —
this script is what CI actually runs.

OUTPUT CONTRACT: prints one scenario FILE PATH per line, relative to the
scenarios directory (``AUTOMEDIA_VALIDATION_SCENARIOS_DIR`` else repo-root
``scenarios/``) — paths, not names, so each output line traces directly to
the change that produced it (the runner re-globs path → name, the same
name→path scan regression.py uses).  Ambiguity and the ``--all`` flag print
the single line ``--all``, the full-suite marker.

MAPPING RULES (conservative, first match per changed path, union over
paths; any ambiguous path makes the whole result ``--all``):

* ``src/automedia/mcp/**``     → scenarios/surface/**   (the MCP tool surface)
* ``src/automedia/cli/**``     → scenarios/cli/**       (the CLI command surface)
* ``src/automedia/gates/**``   → scenarios/journeys/** + scenarios/quality/**
* ``src/automedia/adapters/**`` → scenarios/publish/**
* ``scenarios/**`` (a *.yaml)  → that scenario file + scenarios/regression/**
  (conservative: the changed scenario itself, plus the regression pins —
  a library edit can flip a pinned status).  A changed file that no longer
  exists (deletion) contributes only the regression pins.
* ``src/automedia/core/**`` or ``src/automedia/validation/**`` → AMBIGUOUS
  (core is depended on by everything; the validation framework is the
  engine that runs everything) → ``--all``.
* anything else (unmatched)    → FALLBACK: the deterministic root batch
  (``scenarios/*.yaml``) + ALL env-free scenarios (``requires_env`` absent
  or empty — read from the YAMLs; env-gated scenarios need credentials the
  PR job never has, so the safe net is exactly the credential-free set).
* empty changed list (no diff) → ``--all`` (cannot scope → full suite).
* empty result after all rules → the fallback set (conservative net).

The fallback is deliberately generous: unmatched paths (pipelines,
accounts, pyproject.toml, docs, ...) could affect almost anything, so the
gate runs the cheap deterministic net instead of guessing.

CLI: ``python3 scripts/validation_affected.py [--all] <changed-file...>``

Deterministic: every output list is sorted; no network, no LLM, no side
effects.  Stdlib + PyYAML only (no automedia import — the scenarios-dir
resolution mirrors loader.default_scenarios_dir).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

# Rule table: changed-path prefix -> scenario subdirs relative to the
# scenarios root whose entire contents are affected.
_RULE_SUBDIRS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("src/automedia/mcp/", ("surface",)),
    ("src/automedia/cli/", ("cli",)),
    ("src/automedia/gates/", ("journeys", "quality")),
    ("src/automedia/adapters/", ("publish",)),
)

# Prefixes everything depends on — any hit forces the full suite.
_AMBIGUOUS_PREFIXES: tuple[str, ...] = (
    "src/automedia/core/",
    "src/automedia/validation/",
)


def default_scenarios_dir() -> Path:
    """Resolve the scenarios directory exactly like loader.default_scenarios_dir."""
    override = os.environ.get("AUTOMEDIA_VALIDATION_SCENARIOS_DIR")
    if override:
        return Path(override).expanduser()
    return REPO_ROOT / "scenarios"


def map_affected(
    changed_paths: Sequence[str], *, scenarios_dir: str | Path | None = None
) -> list[str]:
    """Map changed repo-relative paths to affected scenario paths.

    Returns scenario file paths relative to the scenarios dir, sorted, or
    the singleton ``["--all"]`` (full-suite marker) when any change is
    ambiguous or the list is empty.  Pure and deterministic — no I/O beyond
    reading the scenario tree under ``scenarios_dir``.
    """
    root = Path(scenarios_dir) if scenarios_dir is not None else default_scenarios_dir()
    if not changed_paths:
        return ["--all"]

    selected: set[str] = set()
    fallback = False
    for changed in changed_paths:
        if any(changed.startswith(prefix) for prefix in _AMBIGUOUS_PREFIXES):
            return ["--all"]
        for prefix, subdirs in _RULE_SUBDIRS:
            if changed.startswith(prefix):
                for subdir in subdirs:
                    selected |= _yaml_relpaths(root, root / subdir)
                break
        else:
            if changed.startswith("scenarios/") and changed.endswith(".yaml"):
                rel = changed[len("scenarios/") :]
                if (root / rel).is_file():
                    selected.add(rel)
                # A library edit may flip a pinned regression status.
                selected |= _yaml_relpaths(root, root / "regression")
            else:
                fallback = True

    if fallback or not selected:
        selected |= _fallback_set(root)
    return sorted(selected)


def _yaml_relpaths(root: Path, directory: Path) -> set[str]:
    """All ``*.yaml`` files under ``directory``, relative to the scenarios root."""
    if not directory.is_dir():
        return set()
    return {str(path.relative_to(root)) for path in directory.rglob("*.yaml")}


def _scan_yamls(root: Path) -> list[tuple[str, object]]:
    """(relpath, parsed doc) for every ``*.yaml`` under the scenarios root.

    Parse failures are skipped (tolerant of non-scenario YAML); the
    runner's load_scenarios is the authoritative schema gate.
    """
    entries: list[tuple[str, object]] = []
    if not root.is_dir():
        return entries
    for path in sorted(root.rglob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        entries.append((str(path.relative_to(root)), doc))
    return entries


def _is_env_free(doc: object) -> bool:
    """A scenario needs no environment when ``requires_env`` is absent/empty.

    Shape-checked (dict with ``name`` str and ``steps`` list) so non-scenario
    YAML under the tree is never counted as an env-free scenario.
    """
    if not isinstance(doc, dict):
        return False
    if not isinstance(doc.get("name"), str) or not isinstance(doc.get("steps"), list):
        return False
    requires_env = doc.get("requires_env")
    return not requires_env


def _fallback_set(root: Path) -> set[str]:
    """Deterministic root batch + every env-free scenario (the safe net).

    The batch is the non-recursive root glob (``scenarios/*.yaml`` — the
    deterministic W2 batch); the env-free scan is library-wide.
    """
    batch = {str(path.relative_to(root)) for path in root.glob("*.yaml")}
    env_free = {rel for rel, doc in _scan_yamls(root) if _is_env_free(doc)}
    return batch | env_free


def main(argv: Sequence[str] | None = None) -> int:
    """Print the affected scenario paths (or ``--all``); exit 0 always."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="print the full-suite marker --all (ambiguity escape hatch)",
    )
    parser.add_argument(
        "changed",
        nargs="*",
        help="repo-relative changed file paths (git diff --name-only output)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = ["--all"] if args.all else map_affected(args.changed)
    for line in result:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
