"""Validate matrix for the agent-tester validation layer (issue #86).

Two honest halves in one deterministic artifact:

* STATIC half (declarative, from ``automedia.validation.coverage``): for each
  of the four surfaces (``mcp``/``cli``/``gates``/``modes``) the audit's
  verbatim declared/covered/missing/phantom/boundary-only lists; per scenario
  its declarative metadata plus the last recorded engine status; one ``rows``
  table where each cell answers "does this scenario exercise this surface?".
* ASSERTION half (dynamic, from run records — the AutoInfo 04-MATRIX gap the
  #86 review demanded): ``report_cards`` (per-scenario digest: status, hard
  safety, assertion counts, exit codes, failures, artifacts, diff bucket),
  ``assertions`` (the per-step truth table with exit_code / hard_safety /
  artifacts cells), and ``diff`` (the diff_runs four-way classification
  against the committed baseline).  Built by
  :func:`automedia.validation.matrix_assertions.build_assertion_matrix`.

The surfaces + summary + missing flags come straight from
:func:`coverage_audit` — never re-extracted here.  Only the per-scenario
row cells require step-level scanning, and they mirror the audit's own
extraction rules (tool-kind steps incl. recovery/cleanup; cli-kind
``automedia <sub>`` commands; declarative ``proves_gates``/``proves_modes``).

``last_status`` and the assertion half are best-effort: the latest run
record named by ``latest.txt`` under ``runs_root`` is read, indexed by
scenario name; a missing runs root, missing record, or corrupt JSON yields
``None``/empty — never a crash.

Run it directly::

    python -m automedia.validation.matrix   # prints deterministic JSON
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from automedia.validation.coverage import _cli_subcommand, coverage_audit
from automedia.validation.loader import load_scenarios
from automedia.validation.matrix_assertions import build_assertion_matrix
from automedia.validation.persist import latest_run
from automedia.validation.schema import Scenario, Step

_SURFACES: tuple[str, ...] = ("mcp", "cli", "gates", "modes")
_SURFACE_KEYS: tuple[str, ...] = (
    "declared",
    "covered",
    "missing",
    "phantom",
    "boundary_only",
)
"""The five audit-derived lists carried per surface (audit key = key + _surface)."""


def _status_hint(scenario: Scenario) -> str:
    """Static hint derived from the scenario's own metadata (issue #86)."""
    if scenario.requires_env:
        return f"requires-env: {', '.join(scenario.requires_env)}"
    if scenario.error_boundary:
        return "error-boundary probe"
    if scenario.hard:
        return "hard"
    return "ready"


def _walk_steps(scenario: Scenario) -> list[Step]:
    """Every step a scenario declares: primary + cleanup, recursing recovery."""
    walked: list[Step] = []

    def collect(step: Step) -> None:
        walked.append(step)
        for recovery in step.recovery_steps:
            collect(recovery)

    for step in [*scenario.steps, *scenario.cleanup_steps]:
        collect(step)
    return walked


def _uses_mcp(scenario: Scenario) -> bool:
    """True when any declared step (incl. recovery/cleanup) is tool-kind."""
    return any(step.kind == "tool" for step in _walk_steps(scenario))


def _uses_cli(scenario: Scenario) -> bool:
    """True when any cli-kind step invokes an ``automedia <sub>`` command."""
    return any(
        step.kind == "cli"
        and step.command is not None
        and _cli_subcommand(step.command) is not None
        for step in _walk_steps(scenario)
    )


def _read_last_statuses(runs_root: str | Path) -> dict[str, str]:
    """Scenario name → last recorded status from the latest run, best-effort."""
    root = Path(runs_root)
    run_name = latest_run(root)
    if run_name is None:
        return {}
    try:
        record = json.loads((root / run_name / "scenarios.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    statuses: dict[str, str] = {}
    for row in record.get("scenarios", []) if isinstance(record, dict) else []:
        name = row.get("scenario") if isinstance(row, dict) else None
        status = row.get("status") if isinstance(row, dict) else None
        if isinstance(name, str) and isinstance(status, str):
            statuses[name] = status
    return statuses


def _load_latest_record(runs_root: str | Path) -> dict[str, Any] | None:
    """The latest engine suite record, best-effort; None when unavailable.

    Reads ``<runs_root>/<latest.txt>/scenarios.json``; a missing runs root,
    missing pointer, or corrupt JSON yields None — never a crash (mirrors
    ``_read_last_statuses``'s tolerance).
    """
    root = Path(runs_root)
    run_name = latest_run(root)
    if run_name is None:
        return None
    try:
        record = json.loads((root / run_name / "scenarios.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return record if isinstance(record, dict) else None


def _default_baseline_path(runs_root: str | Path) -> Path | None:
    """Best-effort resolve of the committed baseline record (validate-diff parity).

    The default ``--runs-root validation-runs`` sits at the repo root, so the
    parent of the runs root IS the repo root — where the committed W2-T4
    baseline (``scenarios/baseline/2026-08-14-preflight.json``) lives.
    ``None`` when the file is absent.
    """
    candidate = (
        Path(runs_root).resolve().parent / "scenarios" / "baseline" / "2026-08-14-preflight.json"
    )
    return candidate if candidate.is_file() else None


def _load_record(path: str | Path) -> dict[str, Any] | None:
    """Read one engine suite record from a path, best-effort."""
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return record if isinstance(record, dict) else None


def build_matrix(
    scenarios_dir: str | Path | None = None,
    runs_root: str | Path = "validation-runs",
    baseline_path: str | Path | None = None,
) -> dict[str, Any]:
    """Deterministic validate matrix over the scenario library (issue #86).

    ``scenarios_dir`` defaults to the loader's default (env override
    ``AUTOMEDIA_VALIDATION_SCENARIOS_DIR`` else repo-root ``scenarios/``);
    a missing directory is an empty library (loader phase-0 semantics).
    ``runs_root`` is where run records live (default ``validation-runs``,
    gitignored); the latest run's statuses + assertions are merged best-effort.
    ``baseline_path`` is the committed baseline record for the diff
    four-way classification; when ``None`` it auto-resolves to
    ``scenarios/baseline/2026-08-14-preflight.json`` under the repo root
    (the same default the CLI ``validate diff`` uses); ``None`` when absent.

    Returns the matrix dict: ``surfaces`` (audit lists verbatim per
    surface), ``scenarios`` (per-scenario declarative metadata +
    ``status_hint`` + ``last_status``), ``rows`` (bool surface cells per
    scenario), ``flags`` (hard / boundary_only / missing), ``summary``
    (the audit's summary verbatim), plus the assertion half:
    ``report_cards``, ``assertions``, and ``diff`` (run-record-derived).
    """
    audit = coverage_audit(scenarios_dir)
    scenarios = load_scenarios(scenarios_dir)
    statuses = _read_last_statuses(runs_root)
    latest = _load_latest_record(runs_root)
    baseline = None
    if baseline_path is not None:
        baseline = _load_record(baseline_path)
    else:
        default = _default_baseline_path(runs_root)
        if default is not None:
            baseline = _load_record(default)

    surfaces: dict[str, dict[str, list[str]]] = {}
    for surface in _SURFACES:
        surfaces[surface] = {key: audit[f"{key}_{surface}"] for key in _SURFACE_KEYS}

    scenario_rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        name = scenario.name
        last_status = statuses.get(name)
        scenario_rows.append(
            {
                "name": name,
                "category": scenario.category,
                "hard": scenario.hard,
                "status_hint": _status_hint(scenario),
                "proves_gates": list(scenario.proves_gates),
                "proves_modes": list(scenario.proves_modes),
                "last_status": last_status,
            }
        )

    rows = [
        {
            "scenario": scenario.name,
            "mcp": _uses_mcp(scenario),
            "cli": _uses_cli(scenario),
            "gates": bool(scenario.proves_gates),
            "modes": bool(scenario.proves_modes),
            "hard": scenario.hard,
            "last_status": statuses.get(scenario.name),
        }
        for scenario in scenarios
    ]

    flags: dict[str, Any] = {
        "hard": [scenario.name for scenario in scenarios if scenario.hard],
        "boundary_only": audit["error_boundary_scenarios"],
        "missing": {surface: audit[f"missing_{surface}"] for surface in _SURFACES},
    }

    assertion = build_assertion_matrix(latest, baseline)

    return {
        "surfaces": surfaces,
        "scenarios": scenario_rows,
        "rows": rows,
        "flags": flags,
        "summary": audit["summary"],
        "report_cards": assertion["report_cards"],
        "assertions": assertion["assertions"],
        "diff": assertion["diff"],
    }


def main() -> None:
    """Print the matrix as deterministic JSON (``python -m
    automedia.validation.matrix``)."""
    print(json.dumps(build_matrix(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
