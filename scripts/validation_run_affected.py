#!/usr/bin/env python3
"""Validation run driver for CI (plan W5-T3): affected-area subset + full suite.

Reads the scenario subset from argv and runs it through the real engine
(``make_adapters(create_server())`` — tool-kind steps dispatch through the
live MCP dispatcher, cli/file steps through subprocesses).  Consumed by:

* ``ci.yml`` job ``validation-affected`` (PRs): ``--all`` marker or the
  mapper's output (scenario file paths relative to the scenarios dir)
* ``nightly.yml`` job ``validation-full-suite``: ``--all``
* ``nightly.yml`` job ``validation-draft-publish``: one scenario path

EXIT POLICY (PINNED, plan W5-T3 — duplicated in the workflow comments):
any scenario status ``failed`` → exit 1; everything else (``passed``,
``unconfigured``, ``recovered``, ``partial-pass``) → exit 0.  An
all-unconfigured run is a green run: the env gate (W1-T5) short-circuits
before any dispatch, so LLM-gated scenarios never call out on a clean env.

SAFETY (pinned in the plan): no LLM calls in CI — the job environments
carry no credentials, so every env-gated scenario reports ``unconfigured``
with its missing-var list; no real publish — the publish scenarios are
dry-run/stub/draft-only by design (W3-T5), and the draft-only scenario
targets a manual-level platform the engine always skips; no persisted state
(save=False, no runs root) — the meta scenario's own ``validation-runs/``
is self-cleaned by its cleanup step.

Usage:
    python3 scripts/validation_run_affected.py --all
    python3 scripts/validation_run_affected.py surface/health/engine-health-alias.yaml
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from automedia.mcp.server import create_server
from automedia.validation.engine import make_adapters, run_validation_scenario
from automedia.validation.loader import default_scenarios_dir, load_scenarios
from automedia.validation.schema import Scenario

REPO_ROOT = Path(__file__).resolve().parents[1]


def _path_to_name(scenarios_dir: Path) -> dict[str, str]:
    """Scenario file path (relative to the scenarios dir) -> scenario name.

    The engine's ``Scenario`` carries no file path (loader drops it), so the
    path→name map is rebuilt by re-globbing the ``name:`` field — the same
    scan regression.py uses, inverted.
    """
    mapping: dict[str, str] = {}
    for path in sorted(scenarios_dir.rglob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        name = doc.get("name") if isinstance(doc, dict) else None
        if isinstance(name, str):
            mapping[str(path.relative_to(scenarios_dir))] = name
    return mapping


def _select(scenarios_dir: Path, paths: Sequence[str]) -> list[str]:
    """Scenario names for the requested subset; unknown paths warn loudly.

    An empty selection with a non-empty request is an error (running nothing
    would be a silent green gate).
    """
    by_path = _path_to_name(scenarios_dir)
    unknown = sorted(set(paths) - set(by_path))
    if unknown:
        print(f"WARNING: {len(unknown)} requested path(s) not in the library "
              f"(skipped): {', '.join(unknown)}", file=sys.stderr)
    selected = sorted(by_path[path] for path in paths if path in by_path)
    if not selected:
        print("ERROR: nothing to run — pass `--all` or scenario file paths "
              "(see the module docstring)", file=sys.stderr)
        sys.exit(1)
    return selected


def _load_library(scenarios_dir: Path) -> dict[str, Scenario]:
    """Load the library; a broken library is a loud gate failure (never a crash)."""
    try:
        return {s.name: s for s in load_scenarios(scenarios_dir)}
    except Exception as exc:  # noqa: BLE001 — LoadError carries the file context
        print(f"ERROR: library failed to load: {exc}", file=sys.stderr)
        sys.exit(1)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected scenarios; exit per the pinned policy."""
    args = list(argv) if argv is not None else sys.argv[1:]
    scenarios_dir = default_scenarios_dir()

    if "AUTOMEDIA_LLM_API_KEY" in os.environ:
        print("WARNING: AUTOMEDIA_LLM_API_KEY is set — LLM-gated scenarios will "
              "execute for real. CI must run credential-free (unset it).",
              file=sys.stderr)

    if args and args[0] == "--all":
        print("full suite")
        selected = [s.name for s in _load_library(scenarios_dir).values()]
    else:
        selected = _select(scenarios_dir, args)

    library = _load_library(scenarios_dir)
    adapters = make_adapters(create_server())
    records = [
        run_validation_scenario(
            library[name],
            adapters,
            run_root=None,  # save=False: no persisted state
            cwd=REPO_ROOT,  # fixture paths + expect artifact checks align (W3-T4)
        )
        for name in selected
    ]
    return _report(records)


def _report(records: Sequence[dict[str, object]]) -> int:
    """Print per-scenario status lines + summary; apply the pinned exit policy."""
    statuses: dict[str, int] = {}
    failed: list[str] = []
    for record in records:
        name = str(record["scenario"])
        status = str(record["status"])
        statuses[status] = statuses.get(status, 0) + 1
        detail = ""
        if status == "unconfigured":
            detail = f"  ({record.get('reason', '')})"
        elif status != "passed":
            summary = record.get("summary")
            if isinstance(summary, dict):
                detail = f"  (summary {summary})"
        print(f"{name}: {status}{detail}")
        if status == "failed":
            failed.append(name)

    order = ("passed", "failed", "recovered", "partial-pass", "unconfigured")
    summary_line = ", ".join(f"{s}: {statuses.get(s, 0)}" for s in order)
    print(f"\nsummary: {summary_line}")
    if failed:
        print(f"FAIL: {len(failed)} scenario(s) failed — exit 1", file=sys.stderr)
        return 1
    print("OK: no failures — exit 0 (unconfigured-only runs are green by policy)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
