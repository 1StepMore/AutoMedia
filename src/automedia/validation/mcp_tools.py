"""MCP tool handlers for the agent-tester validation surface (plan W4-T2).

The four handlers registered by ``automedia.mcp.server.create_server()``
expose the validation layer to MCP clients: scenario-library listing,
single-scenario execution, run-record reporting, and the static coverage
audit.  They wrap the W1/W3 engine cores and follow the server's flat-envelope
convention (``success_response``/``error_response`` — no nested ``data``).

**In-process isolation (documented, plan requirement):** an MCP-driven
scenario run executes inside the long-lived server process and shares its
state (GateRegistry, active pipelines), unlike the CLI surface which runs in
a subprocess.  Mutating scenarios therefore prefer the CLI surface; this
module never runs the whole library — suite runs are CLI-only.

**Recursion bound (review fix M5):** :func:`run_validation_scenario`
REQUIRES a ``scenario_name`` — the name filter.  An empty or unknown name is
rejected before any dispatch, so a scenario step that invokes this tool must
carry a static name (bounded: a finite library, no dynamic recursion).  The
meta scenario ``list-validation-scenarios-meta`` calls
:func:`list_validation_scenarios`, which takes no name and never recurses.
There is deliberately no suite-run tool in the MCP surface: the engine's
``run_validation_suite_async`` cannot be reached without going through the
name-filtered single-scenario path.

No allowlist involvement: all four tools do plain file I/O only
(``mcp_allowlist.yaml`` untouched — Red Line 3).

This module must NOT import ``automedia.mcp.server`` (the engine adapters
already pin that rule; importing server here would be circular with W4).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context

from automedia.mcp.mcp_error import (
    MCPErrorCode,
    error_response,
    success_response,
)
from automedia.validation.engine import make_adapters, run_validation_scenario_async
from automedia.validation.loader import LoadError, load_scenarios
from automedia.validation.persist import (
    PersistError,
    latest_run,
    list_runs,
    persist_run,
    write_latest_pointer,
)
from automedia.validation.schema import Scenario

DEFAULT_RUNS_ROOT = "validation-runs"
"""Default runs root shared by the run/report tools (CLI parity)."""


def _status_hint(scenario: Scenario) -> str:
    """Static, metadata-derived hint about a scenario's likely run status.

    Derived only from the scenario's own fields — never a runtime probe: an
    env-gated scenario short-circuits to ``unconfigured`` (the engine checks
    the env gate before any dispatch), an ``error_boundary`` scenario probes
    the dispatcher, everything else is runnable.
    """
    if scenario.requires_env:
        return f"requires-env: {', '.join(scenario.requires_env)}"
    if scenario.error_boundary:
        return "error-boundary probe"
    return "ready"


def _load_library() -> tuple[list[Scenario], dict[str, Any] | None]:
    """Load the scenario library; ``(scenarios, None)`` or ``([], error)``."""
    try:
        return load_scenarios(), None
    except LoadError as exc:
        return [], error_response(
            MCPErrorCode.VALIDATION_ERROR,
            f"scenario library failed to load: {exc}",
            (
                "Fix the offending scenario file(s) or point "
                "AUTOMEDIA_VALIDATION_SCENARIOS_DIR at a valid library"
            ),
        )


def list_validation_scenarios() -> dict[str, Any]:
    """List the agent-tester validation scenario library.

    Loads every committed scenario (``AUTOMEDIA_VALIDATION_SCENARIOS_DIR``
    when set, else the repo ``scenarios/`` directory) and returns one entry
    per scenario with ``name``, ``description``, ``category``, and a static
    ``status_hint`` (``ready`` / ``requires-env: <names>`` /
    ``error-boundary probe`` — never a runtime probe).  A missing directory
    yields an empty list (loader phase-0 semantics, not an error).

    Returns
    -------
    dict
        ``{"success": true, "scenarios": [...], "count": N}``.
    """
    scenarios, error = _load_library()
    if error is not None:
        return error
    entries = [
        {
            "name": scenario.name,
            "description": scenario.description,
            "category": scenario.category,
            "status_hint": _status_hint(scenario),
        }
        for scenario in scenarios
    ]
    return success_response({"scenarios": entries, "count": len(entries)})


async def run_validation_scenario(
    scenario_name: str,
    runs_root: str = DEFAULT_RUNS_ROOT,
    save: bool = False,
    context: Context | None = None,
) -> dict[str, Any]:
    """Run ONE named validation scenario in-process against this server.

    ``scenario_name`` is REQUIRED — the name filter is the recursion bound
    (review fix M5): an empty name is rejected before any dispatch, and an
    unknown name errors with the available scenarios listed.  The run uses
    the engine's async core and dispatches tool-kind steps back through this
    server instance (in-process isolation — see module docstring).  With
    ``save=True`` the run record is persisted immutably under ``runs_root``
    (default ``validation-runs/``, created on demand) as a suite-shaped
    ``scenarios.json`` plus a ``latest.txt`` pointer, readable via
    ``get_validation_report``.

    Returns
    -------
    dict
        The scenario run record flattened under ``success``:
        ``{"scenario", "status", "summary", "steps", "cleanup", "trace_id",
        "error_boundary"}`` (or the ``unconfigured`` record shape).
    """
    name = scenario_name.strip()
    if not name:
        return error_response(
            MCPErrorCode.INVALID_PARAM,
            (
                "scenario_name is required — the name filter bounds recursion: "
                "a step invoking this tool must name a scenario"
            ),
            "Pass a scenario name from list_validation_scenarios",
        )
    scenarios, error = _load_library()
    if error is not None:
        return error
    by_name = {scenario.name: scenario for scenario in scenarios}
    scenario = by_name.get(name)
    if scenario is None:
        available = ", ".join(sorted(by_name)) or "(no scenarios loaded)"
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"unknown scenario {name!r}",
            f"Available scenarios: {available}",
        )
    server = context.fastmcp if context is not None else None
    adapters = make_adapters(server)
    run_root = Path(runs_root) if save else None
    record = await run_validation_scenario_async(scenario, adapters, run_root=run_root)
    if save and run_root is not None:
        suite: dict[str, object] = {
            "trace_id": record["trace_id"],
            "generated_at": datetime.now(UTC).isoformat(),
            "scenarios": [record],
        }
        try:
            record_path = persist_run(run_root, suite)
        except PersistError as exc:
            return error_response(
                MCPErrorCode.UNKNOWN,
                f"could not persist run record under {run_root}: {exc}",
                "Choose a runs_root with no colliding run directory",
            )
        write_latest_pointer(run_root, record_path.parent.name)
    return success_response(record)


def get_validation_report(run_dir: str | None = None) -> dict[str, Any]:
    """Read a persisted validation run record.

    Reads ``validation-runs/<run_dir>/scenarios.json``; with no ``run_dir``
    (or an empty one) the latest run named by ``latest.txt`` is read.  The
    record is the suite shape ``{trace_id, generated_at, scenarios}``; a
    single-scenario save from :func:`run_validation_scenario` is stored in
    the same shape with one entry.  No run record found → error envelope
    naming what exists under the runs root.

    Returns
    -------
    dict
        ``{"success": true, "run_dir": <dir read>, "trace_id": ...,
        "generated_at": ..., "scenarios": [...]}``.
    """
    root = Path(DEFAULT_RUNS_ROOT)
    target = run_dir.strip() if run_dir else None
    name = target or latest_run(root)
    if name is None:
        existing = list_runs(root)
        resolution = (
            "no runs yet — run_validation_scenario(save=True) or the CLI "
            "suite (automedia validate run)"
            if not existing
            else f"existing runs under {root}: {', '.join(existing)}"
        )
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"no validation run record found under {root}",
            resolution,
        )
    record_path = root / name / "scenarios.json"
    if not record_path.is_file():
        existing = list_runs(root)
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"no run record at {record_path}",
            f"existing runs under {root}: {', '.join(existing) or '(none)'}",
        )
    try:
        record: dict[str, Any] = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return error_response(
            MCPErrorCode.UNKNOWN,
            f"could not read run record {record_path}: {exc}",
            "Inspect or remove the corrupt run directory",
        )
    return success_response({"run_dir": name, **record})


def validation_coverage_audit() -> dict[str, Any]:
    """Run the static coverage audit over the scenario library.

    Wraps ``automedia.validation.coverage.coverage_audit`` (imported lazily
    so a missing module surfaces as an error envelope, never an import-time
    crash): declared/used/covered/missing/phantom/boundary-only sets for the
    MCP and CLI surfaces plus a numeric ``summary``.  Deterministic — the
    audit is regex/parse only, no runtime probes.

    Returns
    -------
    dict
        The audit dict flattened under ``success`` (``declared_mcp``,
        ``used_mcp``, ``covered_mcp``, ..., ``summary``).
    """
    try:
        from automedia.validation.coverage import coverage_audit
    except ImportError as exc:
        return error_response(
            MCPErrorCode.IMPORT_ERROR,
            f"coverage audit module unavailable: {exc}",
            "Reinstall the automedia package",
        )
    try:
        audit = coverage_audit()
    except LoadError as exc:
        return error_response(
            MCPErrorCode.VALIDATION_ERROR,
            f"coverage audit failed: {exc}",
            "Fix the scenario library first (see list_validation_scenarios)",
        )
    return success_response(audit)


def validation_matrix() -> dict[str, Any]:
    """Run the validation matrix: per-scenario surface coverage + last-run status.

    Wraps ``automedia.validation.matrix.build_matrix`` (lazy import so a
    missing module surfaces as an error envelope, never an import-time
    crash): surfaces (mcp/cli/gates/modes coverage sets), per-scenario
    rows with surface cells and last-run status, hard-safety flags.
    Non-recursive: takes no scenario name.

    Returns
    -------
    dict
        The matrix dict flattened under ``success``.
    """
    try:
        from automedia.validation.matrix import build_matrix
    except ImportError as exc:
        return error_response(
            MCPErrorCode.IMPORT_ERROR,
            f"validation matrix module unavailable: {exc}",
            "Reinstall the automedia package",
        )
    try:
        matrix = build_matrix()
    except Exception as exc:  # envelope, never crash the server
        return error_response(
            MCPErrorCode.VALIDATION_ERROR,
            f"validation matrix failed: {exc}",
            "Fix the scenario library first (see list_validation_scenarios)",
        )
    return success_response(matrix)


__all__ = [
    "DEFAULT_RUNS_ROOT",
    "get_validation_report",
    "list_validation_scenarios",
    "run_validation_scenario",
    "validation_coverage_audit",
    "validation_matrix",
]
