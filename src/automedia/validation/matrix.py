"""Validate matrix for the agent-tester validation layer (issue #86).

Combines the static coverage audit (``automedia.validation.coverage``) with
a per-scenario surface/status grid into one deterministic artifact: for
each of the four surfaces (``mcp``/``cli``/``gates``/``modes``) the audit's
verbatim declared/covered/missing/phantom/boundary-only lists; per scenario
its declarative metadata plus the last recorded engine status; and one
``rows`` table where each cell answers "does this scenario exercise this
surface?".

The surfaces + summary + missing flags come straight from
:func:`coverage_audit` — never re-extracted here.  Only the per-scenario
row cells require step-level scanning, and they mirror the audit's own
extraction rules (tool-kind steps incl. recovery/cleanup; cli-kind
``automedia <sub>`` commands; declarative ``proves_gates``/``proves_modes``).

``last_status`` is best-effort: the latest run record named by
``latest.txt`` under ``runs_root`` is read, indexed by scenario name; a
missing runs root, missing record, or corrupt JSON yields ``None`` — never
a crash.

Run it directly::

    python -m automedia.validation.matrix   # prints deterministic JSON
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from automedia.validation.coverage import _cli_subcommand, coverage_audit
from automedia.validation.loader import load_scenarios
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


def build_matrix(
    scenarios_dir: str | Path | None = None,
    runs_root: str | Path = "validation-runs",
) -> dict[str, Any]:
    """Deterministic validate matrix over the scenario library (issue #86).

    ``scenarios_dir`` defaults to the loader's default (env override
    ``AUTOMEDIA_VALIDATION_SCENARIOS_DIR`` else repo-root ``scenarios/``);
    a missing directory is an empty library (loader phase-0 semantics).
    ``runs_root`` is where run records live (default ``validation-runs``,
    gitignored); the latest run's statuses are merged best-effort.

    Returns the matrix dict: ``surfaces`` (audit lists verbatim per
    surface), ``scenarios`` (per-scenario declarative metadata +
    ``status_hint`` + ``last_status``), ``rows`` (bool surface cells per
    scenario), ``flags`` (hard / boundary_only / missing), and ``summary``
    (the audit's summary verbatim).
    """
    audit = coverage_audit(scenarios_dir)
    scenarios = load_scenarios(scenarios_dir)
    statuses = _read_last_statuses(runs_root)

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

    return {
        "surfaces": surfaces,
        "scenarios": scenario_rows,
        "rows": rows,
        "flags": flags,
        "summary": audit["summary"],
    }


def main() -> None:
    """Print the matrix as deterministic JSON (``python -m
    automedia.validation.matrix``)."""
    print(json.dumps(build_matrix(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
