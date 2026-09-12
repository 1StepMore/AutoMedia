"""6-phase scenario executor for agent-tester validation (W1-T7).

Composes the W1 modules into the guide's §3.1 engine contract: load
(``loader.load_scenarios``), dispatch (adapter table, §3.2), assert
(``expects.evaluate_expect``), aggregate (``expects.aggregate_status``),
trace (per-step records), persist (``persist.persist_run`` + latest.txt).

Async core (plan fix C3): the step executor is async — ToolAdapter's
``run_async`` is the real path.  The sync wrappers use ``asyncio.run`` and
are CLI/test-only; the long-lived MCP server (W4) must call the
``*_async`` cores from its running loop.  In-process isolation (plan
assumption): MCP-driven runs share server state (GateRegistry, active
pipelines), so mutating scenarios should prefer the CLI surface
(subprocess isolation) — and ``server=None`` makes tool-kind steps fail
loudly, never fabricate.

Records: scenario ``{scenario, status, summary, steps, cleanup, trace_id,
error_boundary, hard_safety_violation, confidence}``; unconfigured ``{...,
status: "unconfigured", steps: [], cleanup: [], reason: "missing env: [...]",
hard_safety_violation: scenario.hard, confidence}``; suite ``{trace_id,
generated_at, scenarios, hard_safety_violations, blocked, confidence}`` — ONE
UUID per run threaded into every step (§3.1 phase 5).  ``confidence`` is
``"real"`` for a shipped-provider run and ``"mock"`` when ``AUTOMEDIA_FAKE_LLM``
selects the deterministic mock LLM (gap T-22): a mock pass proves plumbing
only and never satisfies real-surface coverage.  Step trace: ``step_index`` (1-based; 0 =
cleanup), target, surface, name, arguments (REDACTED), passed, status,
failures, duration (``time.monotonic``, 3 decimals), trace_id, check,
standard, output (redacted).

Timeouts (§2.2/§2.4): tool steps run under ``asyncio.wait_for`` with
``step.timeout_seconds or DEFAULT_TIMEOUT_SECONDS``; timeout -> failed
("timed out after Ns").  CLI steps time out inside CLIAdapter — never
double-wrapped.

error_boundary probes assert the error occurs: they PASS when the call
raised, the output reports ``success: false``, or the expect failed
(status "passed" + ``note: "error_boundary: true"``; failures document how
the error manifested) and FAIL only on full success ("boundary probe
expected an error, got success").  Recovery never applies to probes; the
scenario-level flag is copied into the record (W3-T7 audit reads it).

Recovery/cleanup (§2.6): recovery runs only after a primary failure; only
a passing recovery converts the record to "recovered" — the failure stays
in ``failures`` (RED never erased).  Cleanup runs best-effort after the
main steps under ``cleanup`` and never influences status.

Artifacts (§4.4): GREEN steps with ``collect_artifacts`` copy their
artifacts into the exclusive per-run dir's ``artifacts/`` via
``persist.collect_artifacts`` (entries in the trace; required-missing
surfaced loudly in ``summary.artifacts_missing``).  The run dir is created
first (``persist.prepare_run_dir``) so artifacts and ``scenarios.json``
share one immutable directory — evidence can never be overwritten by a later
run (gap T-16).  A ``save=False`` suite collects nothing.

Redaction (plan fix m8): :func:`_redact` lazily imports ``_redact_secrets``
from ``automedia.mcp.tools._shared`` (NOT config_loader), falling back to
a local keyword redactor only if the import fails.

SIZE_OK: this module deliberately exceeds the 250-line guideline — the
plan pins the whole six-phase executor in one file (guide §3.3: "the whole
engine fits in one file") and must not touch the other validation modules.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from automedia.validation.adapters import (
    Adapter,
    CLIAdapter,
    FileAdapter,
    ToolAdapter,
    ToolCallable,
)
from automedia.validation.env_gate import check_env, fake_mode_active
from automedia.validation.expects import (
    SimpleRecord,
    aggregate_status,
    apply_recovery,
    evaluate_expect,
)
from automedia.validation.loader import load_scenarios
from automedia.validation.metrics import build_metrics
from automedia.validation.persist import (
    collect_artifacts,
    persist_run,
    prepare_run_dir,
    write_latest_pointer,
    write_metrics,
)
from automedia.validation.schema import DEFAULT_TIMEOUT_SECONDS, Scenario, Step

# Keyword set of the local fallback redactor — mirrors (and slightly
# widens) ``mcp/tools/_shared.py``'s ``_SECRET_KEYWORDS``.
_FALLBACK_SECRET_KEYWORDS: tuple[str, ...] = (
    "key",
    "secret",
    "password",
    "token",
    "credential",
    "auth",
    "cookie",
)


class Adapters:
    """Dispatch table (guide §3.2): step kind -> surface adapter."""

    def __init__(self, table: Mapping[str, Adapter]) -> None:
        self._table: dict[str, Adapter] = dict(table)

    def get(self, kind: str) -> Adapter | None:
        """Return the adapter registered for ``kind``, or None."""
        return self._table.get(kind)


def make_adapters(server: ToolCallable | None = None) -> Adapters:
    """Build the dispatch table for the three shipped surfaces.

    cli/file adapters are always registered; the tool adapter is registered
    only when a FastMCP instance is injected — ``server=None`` makes
    tool-kind steps fail loudly at dispatch (see module docstring).
    """
    table: dict[str, Adapter] = {"cli": CLIAdapter(), "file": FileAdapter()}
    if server is not None:
        table["tool"] = ToolAdapter(server)
    return Adapters(table)


def _confidence() -> str:
    """Run-record confidence (gap T-22): ``"mock"`` under fake mode, else ``"real"``."""
    return "mock" if fake_mode_active() else "real"


def _redact(value: object) -> object:
    """Recursively replace secret values with ``***REDACTED***``.

    Lazily imports ``_redact_secrets`` from ``automedia.mcp.tools._shared``
    (the util verified by the plan review — NOT config_loader); the local
    fallback applies only when that import fails (defense in depth).
    """
    try:
        from automedia.mcp.tools._shared import _redact_secrets
    except ImportError:
        return _local_redact(value)
    return _redact_secrets(value)


def _local_redact(value: object) -> object:
    """Fallback redactor: values under secret-keyword dict keys -> marker."""
    if not isinstance(value, dict):
        return value
    return {
        key: (
            "***REDACTED***"
            if isinstance(key, str) and any(kw in key.lower() for kw in _FALLBACK_SECRET_KEYWORDS)
            else _local_redact(val)
        )
        for key, val in value.items()
    }


async def _dispatch(step: Step, adapters: Adapters) -> tuple[dict[str, object], bool]:
    """Phase 2: turn one step into one real call; never raises.

    Returns ``(output, ok)``.  Tool steps go through the async adapter path
    wrapped in ``asyncio.wait_for`` (timeout -> failed); cli/file steps run
    synchronously — CLIAdapter enforces its own timeout.
    """
    adapter = adapters.get(step.kind)
    if adapter is None:
        if step.kind == "tool":
            reason = (
                "no MCP server instance (server=None): tool-kind steps cannot "
                "dispatch; pass the FastMCP instance or use cli-kind steps"
            )
        else:
            reason = f"no adapter registered for step kind {step.kind!r}"
        return {"success": False, "error": reason}, False
    timeout = step.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
    if step.kind == "tool" and isinstance(adapter, ToolAdapter):
        try:
            result = await asyncio.wait_for(adapter.run_async(step), timeout)
        except TimeoutError:  # asyncio.TimeoutError == builtin TimeoutError (3.11+)
            return {"success": False, "error": f"timed out after {timeout:g}s"}, False
        return result.output, result.ok
    result = adapter.run(step)
    return result.output, result.ok


async def _execute_step(
    step: Step,
    adapters: Adapters,
    trace_id: str,
    step_index: int,
    *,
    cwd: Path,
) -> tuple[dict[str, object], bool]:
    """Phases 2+3+5 for one step: dispatch, wall-clock, assert, trace.

    Returns the trace plus the adapter's ``ok`` flag (the boundary grader
    inverts on it).  A call that raised is never ``passed`` even when the
    expect block is empty (an aborted call is not evidence).
    """
    start = time.monotonic()
    output, ok = await _dispatch(step, adapters)
    duration = round(time.monotonic() - start, 3)
    expect_result = evaluate_expect(step.expect, output, step=step, cwd=cwd)
    passed = ok and expect_result.passed
    return (
        {
            "step_index": step_index,
            "target": step.tool or step.command,
            "surface": step.kind,
            "name": step.name,
            "arguments": _redact(step.arguments or {}),
            "passed": passed,
            "status": "passed" if passed else "failed",
            "failures": list(expect_result.failures),
            "duration": duration,
            "trace_id": trace_id,
            "check": step.check,
            "standard": step.standard,
            "output": _redact(output),
        },
        ok,
    )


def _apply_boundary(trace: dict[str, object], ok: bool) -> dict[str, object]:
    """Grade an ``error_boundary`` probe (semantics in module docstring).

    The probe passes when ANY error signal fired: the call raised
    (``ok`` False), the output reports ``success: false``, or the expect
    block failed.  Only a fully successful step fails the probe.
    """
    output = trace["output"]
    output_success = isinstance(output, dict) and output.get("success") is not False
    fully_succeeded = ok and output_success and not bool(trace["failures"])
    if fully_succeeded:
        return {
            **trace,
            "passed": False,
            "status": "failed",
            "failures": ["boundary probe expected an error, got success"],
        }
    return {**trace, "passed": True, "status": "passed", "note": "error_boundary: true"}


async def _run_primary_step(
    step: Step,
    adapters: Adapters,
    trace_id: str,
    step_index: int,
    *,
    cwd: Path,
    run_root: Path | None,
) -> dict[str, object]:
    """One main step: execute, boundary-grade, recover, collect artifacts."""
    trace, ok = await _execute_step(step, adapters, trace_id, step_index, cwd=cwd)
    if step.error_boundary:
        return _apply_boundary(trace, ok)
    if not bool(trace["passed"]) and step.recovery_steps:
        recovery = [
            (await _execute_step(r, adapters, trace_id, step_index, cwd=cwd))[0]
            for r in step.recovery_steps
        ]
        trace["recovery"] = recovery
        status = apply_recovery(False, [bool(r["passed"]) for r in recovery])
        if status == "recovered":
            trace["passed"] = True
            trace["status"] = "recovered"
    if bool(trace["passed"]) and step.collect_artifacts and run_root is not None:
        trace["artifacts"] = collect_artifacts(step, step_index, run_root, cwd=cwd)
    return trace


def _summarize(steps: list[dict[str, object]]) -> dict[str, object]:
    """Per-scenario roll-up: status counts + loud required-artifact misses."""
    statuses = [str(step["status"]) for step in steps]
    missing: list[str] = []
    for step in steps:
        artifacts = step.get("artifacts")
        if not isinstance(artifacts, list):
            continue
        for entry in artifacts:
            if not isinstance(entry, dict):
                continue
            if entry.get("required") and not entry.get("ok"):
                missing.append(
                    f"step {step['step_index']} ({step['name']}): required artifact "
                    f"{entry.get('path')!r} {entry.get('reason') or 'unavailable'}"
                )
    return {
        "total": len(steps),
        "passed": statuses.count("passed"),
        "failed": statuses.count("failed"),
        "recovered": statuses.count("recovered"),
        "artifacts_missing": missing,
    }


async def run_validation_scenario_async(
    scenario: Scenario,
    adapters: Adapters,
    *,
    run_root: Path | None = None,
    cwd: Path | None = None,
    trace_id: str | None = None,
) -> dict[str, object]:
    """Phase 4 orchestration for ONE scenario (guide §3.3).

    Env gate first — an unconfigured scenario short-circuits before any
    dispatch (never a pass/fail); then main steps (with recovery and
    artifact collection per GREEN step), best-effort cleanup, aggregation.
    ``trace_id`` threads the run-wide UUID (§3.1 phase 5); a standalone
    call with ``None`` generates a fresh one.
    """
    base = Path.cwd() if cwd is None else Path(cwd)
    trace_id = trace_id or str(uuid.uuid4())
    gate = check_env(scenario.requires_env, requires_real_llm=scenario.requires_real_llm)
    if not gate.configured:
        return {
            "scenario": scenario.name,
            "status": "unconfigured",
            "steps": [],
            "cleanup": [],
            "trace_id": trace_id,
            "reason": f"missing env: {', '.join(gate.missing)}",
            "error_boundary": scenario.error_boundary,
            "hard_safety_violation": scenario.hard,
            "confidence": _confidence(),
        }
    steps = [
        await _run_primary_step(step, adapters, trace_id, index, cwd=base, run_root=run_root)
        for index, step in enumerate(scenario.steps, 1)
    ]
    cleanup = [
        (await _execute_step(cleanup_step, adapters, trace_id, 0, cwd=base))[0]
        for cleanup_step in scenario.cleanup_steps
    ]
    status = aggregate_status(
        scenario,
        [SimpleRecord(passed=bool(step["passed"]), status=str(step["status"])) for step in steps],
    )
    return {
        "scenario": scenario.name,
        "status": status,
        "summary": _summarize(steps),
        "steps": steps,
        "cleanup": cleanup,
        "trace_id": trace_id,
        "error_boundary": scenario.error_boundary,
        "hard_safety_violation": scenario.hard and status != "passed",
        "confidence": _confidence(),
    }


def run_validation_scenario(
    scenario: Scenario,
    adapters: Adapters,
    *,
    run_root: Path | None = None,
    cwd: Path | None = None,
    trace_id: str | None = None,
) -> dict[str, object]:
    """Sync wrapper of :func:`run_validation_scenario_async` (CLI/test only).

    ``asyncio.run`` cannot run inside a running loop — the MCP server must
    call the async core (in-process isolation, see module docstring).
    """
    return asyncio.run(
        run_validation_scenario_async(
            scenario, adapters, run_root=run_root, cwd=cwd, trace_id=trace_id
        )
    )


async def run_validation_suite_async(
    server: ToolCallable | None,
    scenarios_dir: str | Path | None = None,
    *,
    runs_root: Path | None = None,
    save: bool = True,
    cwd: Path | None = None,
) -> dict[str, object]:
    """Load the library, run every scenario, persist one immutable run record.

    ``server`` is the FastMCP instance for the ToolAdapter (``None`` makes
    tool-kind steps fail loudly).  ``save=True`` requires ``runs_root``;
    the exclusive per-run dir is created up front so artifacts are collected
    beside the record, then the record is persisted via ``persist_run`` and
    ``latest.txt`` is refreshed (guide §3.1 phase 6).  Load failures
    propagate loudly
    (:class:`~automedia.validation.loader.LoadError`).
    """
    scenarios = load_scenarios(scenarios_dir)
    adapters = make_adapters(server)
    trace_id = str(uuid.uuid4())
    base = Path.cwd() if cwd is None else Path(cwd)
    # One exclusive per-run dir holds both the artifacts and the record, so
    # evidence is immutable and two runs can never collide (gap T-16); the
    # save=False path creates nothing and leaves the runs root untouched.
    root: Path | None = None
    run_root: Path | None = None
    if save:
        if runs_root is None:
            raise ValueError("save=True requires runs_root (directory for immutable run records)")
        root = runs_root
        run_root = prepare_run_dir(root)
    records = [
        await run_validation_scenario_async(
            scenario, adapters, run_root=run_root, cwd=base, trace_id=trace_id
        )
        for scenario in scenarios
    ]
    violations = sorted(str(r["scenario"]) for r in records if r.get("hard_safety_violation"))
    record: dict[str, object] = {
        "trace_id": trace_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "scenarios": records,
        "hard_safety_violations": violations,
        "blocked": bool(violations),
        "confidence": _confidence(),
    }
    record["metrics"] = build_metrics(record)
    if save and root is not None:
        record_path = persist_run(root, record, run_dir=run_root)
        if run_root is not None:
            write_metrics(run_root, record["metrics"])  # type: ignore[arg-type]
        write_latest_pointer(root, record_path.parent.name)
    return record


def run_validation_suite(
    server: ToolCallable | None,
    scenarios_dir: str | Path | None = None,
    *,
    runs_root: Path | None = None,
    save: bool = True,
    cwd: Path | None = None,
) -> dict[str, object]:
    """Sync wrapper of :func:`run_validation_suite_async` (CLI path only).

    The MCP server must call the async core from its running loop
    (in-process isolation, see module docstring).
    """
    return asyncio.run(
        run_validation_suite_async(server, scenarios_dir, runs_root=runs_root, save=save, cwd=cwd)
    )
