"""``automedia validate`` — run the agent-tester validation suite (plan W4-T1).

CLI surface for the validation framework: seven sub-commands.

* ``list`` — load the scenario library and list scenarios (load only, no
  engine run).  This is the NON-recursive meta command that covers the whole
  family for the coverage audit (Momus improvement #1: ``validate`` is the
  18th CLI command; the committed ``cli/validate-list-meta.yaml`` scenario
  asserts its output).
* ``run`` — run ONE named scenario (``--scenario``) through the engine
  against the real MCP server (``create_server()``), or the WHOLE library
  (``--all``) persisting one immutable suite record.  ``--scenario`` is the
  recursion bound (plan review fix M5): a single named scenario per
  invocation, and ``--all`` is mutually exclusive with it.
* ``report`` — render the run record for a run.  Delegates to W4-T3's
  renderer (``automedia.validation.report``) when present; a minimal text
  fallback (verdicts table + per-scenario status lines) ships until then.
  Final wiring lands in W4-T7.
* ``diff`` — diff the latest two runs.  Delegates to W4-T4's
  ``automedia.validation.diff`` when present; the minimal fallback prints the
  latest two run names.  Final wiring lands in W4-T7.
* ``coverage`` — run the deterministic coverage audit
  (``automedia.validation.coverage.coverage_audit``, W3-T7) and print the
  per-surface summary.
* ``matrix`` — render the per-scenario surface-coverage + last-run-status
  matrix (issue #86); non-recursive.
* ``sign`` — record the director's sign-off on a run
  (``automedia.validation.signoff.sign_run``): append a
  ``<timestamp> <signer> <verdict>`` line to the run's ``signed.txt``.  A
  missing or empty run name exits 1 (gap Tr-07).

Exit-code contract (typer conventions per ``doctor.py``): ``run`` exits 1
when the scenario status is ``failed``, 0 otherwise (passed / unconfigured /
partial-pass / recovered) with a clear status line; ``coverage`` exits 1 when
``missing`` is non-empty on ANY surface (mcp, cli, and — issue #78 — gates
and modes; boundary-only excluded); usage errors exit 2
(typer/click default).  ``--json`` switches every command to machine-readable
JSON via the shared ``--json`` global flag (``automedia.cli.output``).
"""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from automedia.cli.output import OutputMode, get_output_mode, output_error, output_json
from automedia.validation.engine import (
    make_adapters,
    run_validation_scenario,
    run_validation_suite,
)
from automedia.validation.loader import LoadError, load_scenarios
from automedia.validation.persist import (
    PersistError,
    latest_run,
    list_runs,
    persist_run,
    write_latest_pointer,
)
from automedia.validation.signoff import SignoffError, sign_run

app = typer.Typer(name="validate", help="Run the agent-tester validation suite.")

_ENV_GATE_CHOICES = ("report", "skip")


# ---------------------------------------------------------------------------
# validate list
# ---------------------------------------------------------------------------


@app.command("list")
def validate_list() -> None:
    """List all validation scenarios (load only — no engine run)."""
    try:
        scenarios = load_scenarios()
    except LoadError as exc:
        output_error(f"Failed to load scenarios: {exc}")
        return
    from automedia.validation.standards import StandardsRegistry

    unimplemented = sorted(StandardsRegistry.from_default().unimplemented_check_types())
    rows: list[tuple[str, str, str]] = []
    for scenario in scenarios:
        hint_parts: list[str] = []
        if scenario.requires_env:
            hint_parts.append("env-gated: " + ", ".join(scenario.requires_env))
        if scenario.error_boundary:
            hint_parts.append("boundary probe")
        if scenario.regression:
            hint_parts.append("regression")
        rows.append((scenario.name, scenario.category, "; ".join(hint_parts)))

    if get_output_mode() == OutputMode.JSON:
        output_json(
            {
                "total": len(rows),
                "unimplemented_check_types": unimplemented,
                "scenarios": [
                    {"name": name, "category": category, "hints": hints}
                    for name, category, hints in rows
                ],
            }
        )
        return

    typer.echo(f"Scenario list ({len(rows)} scenarios)")
    for name, category, hints in rows:
        typer.echo(f"  {name:<45} {category:<12} {hints}")
    typer.echo("")
    typer.echo(f"Unimplemented check-types: {len(unimplemented)}")
    typer.echo("Run one: automedia validate run --scenario <name>")


# ---------------------------------------------------------------------------
# validate run
# ---------------------------------------------------------------------------


@app.command("run")
def validate_run(
    scenario: str | None = typer.Option(
        None,
        "--scenario",
        help=(
            "Scenario name to run (the recursion bound: only one named "
            "scenario can be dispatched per invocation). Required unless "
            "--all is given."
        ),
    ),
    run_all: bool = typer.Option(
        False,
        "--all",
        help=(
            "Run the WHOLE scenario library and persist one immutable suite "
            "record (mutually exclusive with --scenario)."
        ),
    ),
    env_gate: str = typer.Option(
        "report",
        "--env-gate",
        help=(
            "'report' (default) shows unconfigured when required env vars are "
            "missing; 'skip' runs the scenario even when env vars are missing."
        ),
    ),
    runs_root: str = typer.Option(
        "validation-runs",
        "--runs-root",
        help="Directory for immutable run records (gitignored).",
    ),
) -> None:
    """Run ONE named scenario, or the whole library with ``--all``.

    Exit codes for a single run: 1 when the scenario status is ``failed`` OR
    the scenario is a hard-safety violation (``hard: true`` and not
    ``passed``); 0 otherwise.  ``--all`` exits 1 when any scenario ``failed``
    or the suite is hard-safety blocked.  Run from the repo root so relative
    artifact paths resolve.
    """
    if env_gate not in _ENV_GATE_CHOICES:
        raise typer.BadParameter(f"must be one of {', '.join(_ENV_GATE_CHOICES)}") from None
    root = Path(runs_root)
    if run_all:
        if scenario is not None:
            raise typer.BadParameter("--all and --scenario are mutually exclusive")
        _run_suite(root)
        return
    if scenario is None:
        raise typer.BadParameter("Missing option '--scenario' — pass --scenario <name> or --all")
    try:
        scenarios = load_scenarios()
    except LoadError as exc:
        output_error(f"Failed to load scenarios: {exc}")
        return
    by_name = {s.name: s for s in scenarios}
    target = by_name.get(scenario)
    if target is None:
        names = ", ".join(sorted(by_name)[:30])
        more = f", ... ({len(by_name)} total)" if len(by_name) > 30 else ""
        output_error(f"Unknown scenario {scenario!r}. Available scenarios: {names}{more}")
        return
    if env_gate == "skip" and target.requires_env:
        target = replace(target, requires_env=[])

    from automedia.mcp.server import create_server

    adapters = make_adapters(create_server())
    root = Path(runs_root)
    record = run_validation_scenario(target, adapters, run_root=root)
    run_record: dict[str, object] = {
        "trace_id": record["trace_id"],
        "generated_at": datetime.now(UTC).isoformat(),
        "scenarios": [record],
        "confidence": record.get("confidence", "real"),
    }
    try:
        record_path = persist_run(root, run_record)
        write_latest_pointer(root, record_path.parent.name)
    except PersistError as exc:
        output_error(f"Could not persist run record: {exc}")
        return

    status = str(record.get("status", "?"))
    hard_violation = bool(record.get("hard_safety_violation"))
    summary = record.get("summary")
    if isinstance(summary, dict):
        total = summary.get("total", "?")
        passed = summary.get("passed", 0)
    else:
        total = passed = "?"

    if get_output_mode() == OutputMode.JSON:
        raw_steps = record.get("steps")
        step_rows: list[dict[str, object]] = []
        if isinstance(raw_steps, list):
            step_rows.extend(
                {
                    "step_index": step.get("step_index"),
                    "name": step.get("name"),
                    "status": step.get("status"),
                    "passed": step.get("passed"),
                    "duration": step.get("duration"),
                    "failures": step.get("failures", []),
                }
                for step in raw_steps
                if isinstance(step, dict)
            )
        output_json(
            {
                "scenario": scenario,
                "status": status,
                "hard_safety_violation": hard_violation,
                "summary": summary if isinstance(summary, dict) else {},
                "reason": record.get("reason"),
                "run_dir": record_path.parent.name,
                "steps": step_rows,
            }
        )
    else:
        line = f"Scenario: {scenario}\nStatus: {status}"
        if hard_violation and status != "failed":
            line += " (HARD SAFETY VIOLATION)"
        if status == "unconfigured":
            line += f" ({record.get('reason')})"
        elif isinstance(summary, dict):
            line += f" ({passed}/{total} steps passed)"
        typer.echo(line)
        raw_steps = record.get("steps")
        if status == "failed" and isinstance(raw_steps, list):
            for step in raw_steps:
                if isinstance(step, dict) and not step.get("passed"):
                    failures = "; ".join(str(f) for f in step.get("failures", []))
                    typer.echo(
                        f"  step {step.get('step_index')} ({step.get('name')}): "
                        f"{step.get('status')} - {failures}"
                    )
        typer.echo(f"Run recorded: {record_path}")

    if status == "failed" or hard_violation:
        raise typer.Exit(code=1)


def _run_suite(root: Path) -> None:
    """Run the whole library, persist one suite record, and report it.

    Delegates to the engine's suite core (gap R-09): one exclusive-create run
    directory holds ``scenarios.json`` plus any collected artifacts, and
    ``latest.txt`` is refreshed.  Exit 1 when any scenario ``failed`` or the
    suite carries a hard-safety violation.
    """
    from automedia.mcp.server import create_server

    try:
        record = run_validation_suite(create_server(), runs_root=root)
    except LoadError as exc:
        output_error(f"Failed to load scenarios: {exc}")
        raise typer.Exit(code=1) from None
    except PersistError as exc:
        output_error(f"Could not persist suite record: {exc}")
        raise typer.Exit(code=1) from None
    run_name = latest_run(root)
    raw_scenarios = record.get("scenarios")
    scenario_rows = (
        [
            {"scenario": entry.get("scenario"), "status": entry.get("status")}
            for entry in raw_scenarios
            if isinstance(entry, dict)
        ]
        if isinstance(raw_scenarios, list)
        else []
    )
    statuses: dict[str, int] = {}
    for row in scenario_rows:
        key = str(row["status"])
        statuses[key] = statuses.get(key, 0) + 1
    failed = statuses.get("failed", 0)
    blocked = bool(record.get("blocked")) or bool(record.get("hard_safety_violations"))

    if get_output_mode() == OutputMode.JSON:
        output_json(
            {
                "trace_id": record.get("trace_id"),
                "generated_at": record.get("generated_at"),
                "run_dir": run_name,
                "blocked": blocked,
                "hard_safety_violations": record.get("hard_safety_violations", []),
                "counts": statuses,
                "scenarios": scenario_rows,
            }
        )
    else:
        typer.echo(f"Suite run: {run_name}")
        for row in scenario_rows:
            typer.echo(f"  {row['scenario']}: {row['status']}")
        order = ("passed", "failed", "recovered", "partial-pass", "unconfigured")
        summary = ", ".join(f"{name}: {statuses.get(name, 0)}" for name in order)
        typer.echo(f"summary: {summary}")
        typer.echo(f"Run recorded: {root / str(run_name) / 'scenarios.json'}")

    if failed or blocked:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# validate report
# ---------------------------------------------------------------------------


@app.command("report")
def validate_report(
    run: str = typer.Option(
        "latest",
        "--run",
        help="Run directory name, or 'latest' (the latest.txt pointer).",
    ),
    runs_root: str = typer.Option(
        "validation-runs",
        "--runs-root",
        help="Directory of immutable run records (gitignored).",
    ),
) -> None:
    """Render the report for a run (W4-T3 renderer, minimal fallback)."""
    root = Path(runs_root)
    run_name = latest_run(root) if run == "latest" else run
    if run_name is None:
        output_error(f"No runs recorded under {root} (no latest.txt pointer).")
        return
    record_path = root / run_name / "scenarios.json"
    if not record_path.is_file():
        output_error(f"No run record at {record_path}.")
        return
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if get_output_mode() == OutputMode.JSON:
        output_json(_render_report_json(record))
        return
    typer.echo(_render_report(record, run_name=run_name, runs_root=root))


def _render_report(record: dict[str, Any], *, run_name: str, runs_root: Path) -> str:
    """Render a run record to text: W4-T3 renderer when present, else the
    minimal fallback (verdicts table + per-scenario status lines).  W4-T7
    wires the final renderer contract."""
    try:
        from automedia.validation.report import render_report  # W4-T3 (parallel task)
    except ImportError:
        return _fallback_report(record, run_name=run_name)
    if callable(render_report):
        try:
            rendered = render_report(record, runs_root=runs_root)
            if isinstance(rendered, str) and rendered:
                return rendered
        except Exception:  # noqa: S110 - renderer contract wired finally in W4-T7; fallback is pinned interim behavior
            pass
    return _fallback_report(record, run_name=run_name)


def _render_report_json(record: dict[str, Any]) -> dict[str, Any]:
    """W4-T3's JSON projection when present, else the raw record."""
    try:
        from automedia.validation.report import render_report_json  # W4-T3
    except ImportError:
        return record
    if callable(render_report_json):
        try:
            rendered = render_report_json(record)
            if isinstance(rendered, dict):
                return rendered
        except Exception:  # noqa: S110 - renderer contract wired finally in W4-T7; raw record is pinned interim behavior
            pass
    return record


def _fallback_report(record: dict[str, Any], *, run_name: str) -> str:
    """Minimal report: verdict counts + one status line per scenario."""
    lines = [f"Run: {run_name}"]
    generated = record.get("generated_at")
    if generated:
        lines.append(f"Generated at: {generated}")
    trace = record.get("trace_id")
    if trace:
        lines.append(f"Trace ID: {trace}")
    scenarios = record.get("scenarios")
    if not isinstance(scenarios, list):
        lines.append("(no scenarios in record)")
        return "\n".join(lines)
    verdicts: dict[str, int] = {}
    for entry in scenarios:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", "unknown"))
        verdicts[status] = verdicts.get(status, 0) + 1
    lines.append("")
    lines.append("Verdicts:")
    lines.extend(f"  {status:<13} {verdicts[status]}" for status in sorted(verdicts))
    lines.append("")
    lines.append("Scenarios:")
    for entry in scenarios:
        if not isinstance(entry, dict):
            continue
        name = entry.get("scenario", "?")
        status = entry.get("status", "?")
        detail = ""
        if status == "unconfigured":
            detail = f" ({entry.get('reason')})"
        elif isinstance(entry.get("summary"), dict):
            summary = entry["summary"]
            detail = f" ({summary.get('passed')}/{summary.get('total')} steps passed)"
        lines.append(f"  [{status:<12}] {name}{detail}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# validate diff
# ---------------------------------------------------------------------------


@app.command("diff")
def validate_diff(
    baseline: str | None = typer.Option(
        None,
        "--baseline",
        help="Baseline run record path (JSON) to diff against.",
    ),
    runs_root: str = typer.Option(
        "validation-runs",
        "--runs-root",
        help="Directory of immutable run records (gitignored).",
    ),
) -> None:
    """Diff the latest two runs (W4-T4 module when present, minimal fallback)."""
    root = Path(runs_root)
    if baseline is None:
        baseline = _default_baseline_path(root)
    runs = list_runs(root)
    if not runs:
        output_error(f"No runs recorded under {root}.")
        return
    payload: dict[str, Any] = {"runs": runs[:2], "baseline": baseline}
    diff_result, diff_error = _compute_diff(root, baseline)
    if diff_result is not None:
        payload["diff"] = diff_result
    if diff_error is not None:
        payload["diff_error"] = diff_error
    if get_output_mode() == OutputMode.JSON:
        output_json(payload)
        return
    typer.echo("Latest two runs:")
    for name in runs[:2]:
        typer.echo(f"  {name}")
    if baseline:
        typer.echo(f"Baseline: {baseline}")
    if diff_result is not None:
        typer.echo("Diff summary:")
        typer.echo(_render_diff_text(diff_result))
    elif diff_error is not None:
        typer.echo(f"Diff unavailable: {diff_error}")


def _compute_diff(
    runs_root: Path, baseline: str | None
) -> tuple[dict[str, Any] | None, str | None]:
    """W4-T4's diff when present; ``(None, None)`` when the module is absent
    (the minimal fallback prints the latest two run names only).  W4-T7
    wires the final diff contract."""
    try:
        diff_mod: Any = importlib.import_module("automedia.validation.diff")
    except ImportError:
        return None, None
    diff_latest = getattr(diff_mod, "diff_latest", None)
    if not callable(diff_latest):
        return None, None
    diff_error_cls: Any = getattr(diff_mod, "DiffError", ValueError)
    baseline_path = Path(baseline) if baseline is not None else None
    try:
        result = diff_latest(runs_root, baseline_path=baseline_path)
    except diff_error_cls as exc:
        return None, str(exc)
    if isinstance(result, dict):
        return result, None
    return None, None


def _default_baseline_path(runs_root: Path) -> str | None:
    """Best-effort resolve of the committed baseline record.

    The default ``--runs-root validation-runs`` sits at the repo root, so the
    parent of the runs root IS the repo root — where the committed W2-T4
    baseline (``scenarios/baseline/2026-08-14-preflight.json``) lives.
    ``None`` when the file is absent, letting the two-latest-runs behavior
    take over.
    """
    candidate = runs_root.resolve().parent / "scenarios" / "baseline" / "2026-08-14-preflight.json"
    if candidate.is_file():
        return str(candidate)
    return None


def _render_diff_text(diff_result: dict[str, Any]) -> str:
    """Render a diff result as a sectioned plain-text report (no ANSI)."""
    lines = ["## Diff"]
    for bucket in ("new_passes", "new_failures", "regressed", "improved"):
        names = diff_result.get(bucket) or []
        lines.append(f"## {bucket}")
        if names:
            lines.append(", ".join(str(name) for name in names))
        else:
            lines.append("(none)")
    trend = diff_result.get("quality_trend") or {}
    lines.append("## quality_trend")
    lines.append(
        f"dropped: {len(trend.get('dropped', []) or [])}, "
        f"raised: {len(trend.get('raised', []) or [])}, "
        f"unchanged: {trend.get('unchanged', 0)}"
    )
    stable = diff_result.get("stable") or {}
    lines.append("## stable")
    lines.extend(f"  {status}: {stable[status]}" for status in sorted(stable))
    summary = diff_result.get("summary") or {}
    lines.append("## summary")
    lines.extend(f"  {key}: {summary[key]}" for key in sorted(summary))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# validate coverage
# ---------------------------------------------------------------------------


@app.command("coverage")
def validate_coverage() -> None:
    """Run the coverage audit over the scenario library.

    Exit 1 when ``missing`` is non-empty on any surface (MCP tools, CLI
    commands, and — issue #78 — gates and modes), excluding boundary-only
    probes which are listed loudly instead.
    """
    from automedia.validation.coverage import coverage_audit

    try:
        audit = coverage_audit()
    except (LoadError, OSError) as exc:
        output_error(f"Coverage audit failed: {exc}")
        return
    summary = audit.get("summary", {})
    missing_mcp = list(audit.get("missing_mcp", []))
    missing_cli = list(audit.get("missing_cli", []))
    missing_gates = list(audit.get("missing_gates", []))
    missing_modes = list(audit.get("missing_modes", []))

    if get_output_mode() == OutputMode.JSON:
        output_json(audit)
    else:
        typer.echo("Coverage audit")
        typer.echo(
            "  CLI: "
            f"declared={summary.get('cli_declared')} "
            f"used={summary.get('cli_used')} "
            f"covered={summary.get('cli_covered')} "
            f"missing={summary.get('cli_missing')} "
            f"boundary_only={summary.get('cli_boundary_only')} "
            f"phantom={summary.get('cli_phantom')}"
        )
        typer.echo(
            "  MCP: "
            f"declared={summary.get('mcp_declared')} "
            f"used={summary.get('mcp_used')} "
            f"covered={summary.get('mcp_covered')} "
            f"missing={summary.get('mcp_missing')} "
            f"boundary_only={summary.get('mcp_boundary_only')} "
            f"phantom={summary.get('mcp_phantom')}"
        )
        typer.echo(
            "  Gates: "
            f"declared={summary.get('gates_declared')} "
            f"used={summary.get('gates_used')} "
            f"covered={summary.get('gates_covered')} "
            f"missing={summary.get('gates_missing')} "
            f"boundary_only={summary.get('gates_boundary_only')} "
            f"phantom={summary.get('gates_phantom')}"
        )
        typer.echo(
            "  Modes: "
            f"declared={summary.get('modes_declared')} "
            f"used={summary.get('modes_used')} "
            f"covered={summary.get('modes_covered')} "
            f"missing={summary.get('modes_missing')} "
            f"boundary_only={summary.get('modes_boundary_only')} "
            f"phantom={summary.get('modes_phantom')}"
        )
        if missing_mcp:
            typer.echo(f"  Missing MCP tools (declared, not covered): {', '.join(missing_mcp)}")
        if missing_cli:
            typer.echo(f"  Missing CLI commands (declared, not covered): {', '.join(missing_cli)}")
        if missing_gates:
            typer.echo(f"  Missing gates (declared, not covered): {', '.join(missing_gates)}")
        if missing_modes:
            typer.echo(f"  Missing modes (declared, not covered): {', '.join(missing_modes)}")
        if not (missing_mcp or missing_cli or missing_gates or missing_modes):
            typer.echo("  missing = 0 (excluding boundary-only, listed above)")

    if missing_mcp or missing_cli or missing_gates or missing_modes:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# validate matrix
# ---------------------------------------------------------------------------


@app.command("matrix")
def validate_matrix(
    runs_root: str = typer.Option(
        "validation-runs",
        "--runs-root",
        help="Directory of immutable run records (gitignored).",
    ),
) -> None:
    """Render the validation matrix: coverage grid + run-record assertion
    cards + diff classification (issue #86).  Non-recursive like ``list`` —
    no scenario argument."""
    from automedia.validation.matrix import build_matrix

    matrix = build_matrix(runs_root=runs_root)
    if get_output_mode() == OutputMode.JSON:
        output_json(matrix)
        return
    _render_matrix_text(matrix)


def _render_matrix_text(matrix: dict[str, Any]) -> None:
    """Plain deterministic text rendering (no ANSI) of the matrix."""
    typer.echo("Validation matrix")
    for surface in ("mcp", "cli", "gates", "modes"):
        s = matrix["surfaces"].get(surface, {})
        typer.echo(
            f"  {surface}: "
            f"declared={len(s.get('declared', []))} "
            f"covered={len(s.get('covered', []))} "
            f"missing={len(s.get('missing', []))} "
            f"phantom={len(s.get('phantom', []))} "
            f"boundary_only={len(s.get('boundary_only', []))}"
        )
    typer.echo("Scenarios:")
    for row in matrix.get("rows", []):
        surface_cells = " ".join(
            f"{name}:{'✓' if row.get(name) else '✗'}" for name in ("mcp", "cli", "gates", "modes")
        )
        hard = "yes" if row.get("hard") else "no"
        last = str(row.get("last_status") or "-")
        typer.echo(f"  {row.get('scenario', '?')} [{surface_cells}] hard={hard} last={last}")
    hard_names = matrix.get("flags", {}).get("hard", []) or []
    hard_line = ", ".join(str(name) for name in hard_names) if hard_names else "(none)"
    typer.echo(f"Hard-safety scenarios: {hard_line}")

    _render_assertion_section(matrix)


def _render_assertion_section(matrix: dict[str, Any]) -> None:
    """The run-record assertion half: report cards + per-step truth table +
    diff four-way classification (AutoInfo 04-MATRIX, issue #86)."""
    cards = matrix.get("report_cards") or []
    assertions = matrix.get("assertions") or {}
    diff = matrix.get("diff")

    typer.echo("")
    typer.echo("## Report cards (latest run)")
    if not cards:
        typer.echo("  (no run record yet — run scenarios to produce evidence)")
    for card in sorted(cards, key=lambda c: str(c.get("scenario") or "")):
        name = card.get("scenario", "?")
        status = card.get("status", "?")
        hard = "HARD" if card.get("hard_safety_violation") else "ok"
        counts = card.get("assertions") or {}
        diff_label = card.get("diff", "-")
        typer.echo(
            f"  {name} [{status} {hard} "
            f"steps={counts.get('passed', 0)}/{counts.get('total', 0)} "
            f"diff={diff_label}]"
        )
        for failure in card.get("failures", []):
            typer.echo(f"    ! {failure}")
        for idx, code in (card.get("exit_codes") or {}).items():
            typer.echo(f"    exit[{idx}]={code}")

    typer.echo("")
    typer.echo("## Assertions (per step)")
    for name in sorted(assertions):
        typer.echo(f"  {name}:")
        for step in assertions[name]:
            status = step.get("status", "?")
            hard = " HARD" if step.get("hard_safety") else ""
            exit_code = step.get("exit_code")
            exit_part = f" exit={exit_code}" if exit_code is not None else ""
            typer.echo(
                f"    {step.get('step_index')}. {step.get('target') or step.get('name')} "
                f"[{step.get('surface')}] {status}{hard}{exit_part}"
            )
            for failure in step.get("failures", []):
                typer.echo(f"      ! {failure}")

    if diff is None:
        typer.echo("")
        typer.echo("## Diff: (no baseline or fewer than two runs to compare)")
        return
    typer.echo("")
    typer.echo("## Diff")
    for bucket in ("new_passes", "new_failures", "regressed", "improved"):
        names = diff.get(bucket) or []
        label = ", ".join(str(n) for n in names) if names else "(none)"
        typer.echo(f"  {bucket}: {label}")


# ---------------------------------------------------------------------------
# validate sign
# ---------------------------------------------------------------------------


@app.command("sign")
def validate_sign(
    run: str = typer.Argument(
        "",
        help="Run directory name to sign (required — a missing/empty name exits 1).",
    ),
    verdict: str = typer.Option(
        "approved",
        "--verdict",
        help="Free-form single-line sign-off verdict (e.g. approved, rejected).",
    ),
    signer: str = typer.Option(
        "director",
        "--signer",
        help="Signer name recorded on the sign-off line.",
    ),
    runs_root: str = typer.Option(
        "validation-runs",
        "--runs-root",
        help="Directory of immutable run records (gitignored).",
    ),
) -> None:
    """Record the director's sign-off on a run (appends to ``signed.txt``).

    Delegates to :func:`automedia.validation.signoff.sign_run`: a missing run
    directory, an empty run name, or an empty/multi-line verdict exits 1 with
    a clear error.  Sign-offs append and are never overwritten.
    """
    name = run.strip()
    if not name:
        output_error("A run name is required: automedia validate sign <run-name>")
        raise typer.Exit(code=1)
    root = Path(runs_root)
    try:
        signed_path = sign_run(root, name, verdict, signer=signer)
    except SignoffError as exc:
        output_error(f"Sign-off failed: {exc}")
        raise typer.Exit(code=1) from None
    if get_output_mode() == OutputMode.JSON:
        output_json(
            {
                "run": name,
                "signed": str(signed_path),
                "verdict": verdict,
                "signer": signer,
            }
        )
        return
    typer.echo(f"Signed {name}: {verdict} ({signer})")
    typer.echo(f"Sign-off recorded: {signed_path}")
