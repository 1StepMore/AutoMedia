"""Report renderer for agent-tester validation runs (W4-T3, component C5).

Turns an engine suite record (pinned W1-T7 shape: ``{trace_id, generated_at,
scenarios: [...]}``) into the director-facing artifacts of guide §6: the
verdicts table, executive summary, regression failures, blockers, per-step
trace, GREEN→artifact links, and a sign-off block (W4-T5 note + unsigned-run
listing when a runs root is provided).

Surface:

- :func:`render_report` / :func:`render_report_text` — the full plain-text
  report (layout lives in ``report_text``; no ANSI, CLI-piping-safe).
- :func:`render_report_json` — the same content as a stable ordered dict
  (used by MCP/CLI JSON mode).

Determinism: output depends only on the record (plus, for the optional
unsigned listing, the runs root).  Scenarios are sorted by name in every
section, steps keep their recorded order, and widths derive from content —
the same record always renders byte-identical text.

Regression flags are NOT part of the pinned engine record, so
:func:`_regression_flags` resolves them record-first (a forward-compatible
``regression``/``regression_issue`` key on a scenario dict wins) and falls
back to the committed scenario library via ``loader.load_scenarios``; an
absent or broken library degrades to "no flags" — a report must never crash
because the library is unavailable, the run record is the source of truth.
"""

from __future__ import annotations

from pathlib import Path

from automedia.validation.loader import LoadError, load_scenarios
from automedia.validation.persist import list_runs
from automedia.validation.report_text import (
    artifacts_section,
    blockers_section,
    exec_summary_section,
    header_section,
    marker,
    regression_section,
    signoff_section,
    step_failure_lines,
    traces_section,
    verdict_summary,
    verdicts_section,
)


def _scenario_records(run_record: dict) -> list[dict]:
    """The suite's scenario records; non-list garbage degrades to []."""
    records = run_record.get("scenarios")
    return [r for r in records if isinstance(r, dict)] if isinstance(records, list) else []


def _steps(record: dict) -> list[dict]:
    """The record's main-step traces; non-list garbage degrades to []."""
    steps = record.get("steps")
    return [s for s in steps if isinstance(s, dict)] if isinstance(steps, list) else []


def _name(record: dict) -> str:
    """Stable sort key: the scenario name (determinism across section ordering)."""
    return str(record.get("scenario") or "")


def _counts(records: list[dict], flags: dict[str, tuple[bool, str | None]]) -> dict[str, int]:
    """Executive-summary counts: the 5 engine statuses + boundary-only + regression-failed."""
    statuses = [str(r.get("status") or "") for r in records]
    regression_failed = sum(
        1 for r in records if r.get("status") == "failed" and flags.get(_name(r), (False, None))[0]
    )
    return {
        "total": len(records),
        "passed": statuses.count("passed"),
        "failed": statuses.count("failed"),
        "unconfigured": statuses.count("unconfigured"),
        "partial_pass": statuses.count("partial-pass"),
        "recovered": statuses.count("recovered"),
        "boundary_only": sum(1 for r in records if r.get("error_boundary") is True),
        "regression_failed": regression_failed,
    }


def _regression_flags(records: list[dict]) -> dict[str, tuple[bool, str | None]]:
    """Scenario name -> (regression, regression_issue).

    Record-carried keys win (forward-compatible with the pinned shape); the
    committed library fills the rest via ``load_scenarios``, which the loader
    contract says raises :class:`LoadError` for a broken/absent handbook —
    degraded to no flags here (decoration, never a crash).
    """
    flags: dict[str, tuple[bool, str | None]] = {}
    for record in records:
        if "regression" in record:
            issue = record.get("regression_issue")
            flags[_name(record)] = (
                bool(record["regression"]),
                issue if isinstance(issue, str) else None,
            )
    try:
        scenarios = load_scenarios()
    except LoadError:
        return flags
    for scenario in scenarios:
        flags.setdefault(scenario.name, (scenario.regression, scenario.regression_issue))
    return flags


def _blockers(records: list[dict]) -> list[dict]:
    """Failed scenarios x failed steps x failures; every FAIL names the expect key."""
    blockers: list[dict] = []
    for record in sorted(records, key=_name):
        if record.get("status") != "failed":
            continue
        for step in _steps(record):
            if step.get("status") != "failed":
                continue
            for failure in step_failure_lines(step):
                blockers.append(
                    {
                        "scenario": _name(record),
                        "step_index": step.get("step_index"),
                        "step": step.get("name"),
                        "failure": failure,
                    }
                )
    return blockers


def _artifact_entries(records: list[dict]) -> list[dict]:
    """GREEN→artifact links: collect_artifacts copies + file-kind inspected paths.

    collect entries print ``copied_to`` (or the source path when the copy
    failed, marked missing); a passed file-kind step without collection names
    its inspected path (the trace ``target`` = command) so every GREEN shows
    an artifact (guide §4.7).
    """
    entries: list[dict] = []
    for record in sorted(records, key=_name):
        for step in _steps(record):
            artifacts = step.get("artifacts")
            collected = False
            if isinstance(artifacts, list):
                collected = True
                for entry in artifacts:
                    if not isinstance(entry, dict):
                        continue
                    copied = entry.get("copied_to")
                    path = entry.get("path")
                    entries.append(
                        {
                            "scenario": _name(record),
                            "step_index": step.get("step_index"),
                            "step": step.get("name"),
                            "artifact": str(copied or path or "?"),
                            "ok": entry.get("ok") is True,
                        }
                    )
            if step.get("surface") == "file" and step.get("status") == "passed" and not collected:
                entries.append(
                    {
                        "scenario": _name(record),
                        "step_index": step.get("step_index"),
                        "step": step.get("name"),
                        "artifact": str(step.get("target") or "?"),
                        "ok": True,
                    }
                )
    return entries


def _unsigned_runs(runs_root: Path | None) -> list[str] | None:
    """Run dirs lacking ``signed.txt`` (W4-T5 sign-off); None = no root provided."""
    if runs_root is None:
        return None
    return [
        name for name in list_runs(runs_root) if not (runs_root / name / "signed.txt").is_file()
    ]


def render_report_text(run_record: dict, *, runs_root: Path | None = None) -> str:
    """Render the full plain-text report; ``runs_root`` enables the unsigned listing."""
    records = _scenario_records(run_record)
    flags = _regression_flags(records)
    sections = [
        header_section(run_record),
        exec_summary_section(_counts(records, flags)),
        verdicts_section(records, flags),
        blockers_section(_blockers(records)),
        regression_section(records, flags),
        traces_section(records),
        artifacts_section(_artifact_entries(records)),
        signoff_section(_unsigned_runs(runs_root)),
    ]
    return "\n".join(line for section in sections for line in section) + "\n"


def render_report(run_record: dict, *, runs_root: Path | None = None) -> str:
    """Alias of :func:`render_report_text` (the CLI-friendly entry point)."""
    return render_report_text(run_record, runs_root=runs_root)


def render_report_json(run_record: dict) -> dict:
    """The report as a stable ordered dict (MCP/CLI JSON mode)."""
    records = _scenario_records(run_record)
    flags = _regression_flags(records)
    verdicts = []
    for record in sorted(records, key=_name):
        regression, issue = flags.get(_name(record), (False, None))
        verdicts.append(
            {
                "scenario": _name(record),
                "status": record.get("status"),
                "marker": marker(str(record.get("status") or "")),
                "summary": verdict_summary(record),
                "regression": regression,
                "regression_issue": issue,
                "error_boundary": record.get("error_boundary") is True,
            }
        )
    regression_failures = [
        {"scenario": _name(r), "issue": flags.get(_name(r), (False, None))[1]}
        for r in sorted(records, key=_name)
        if r.get("status") == "failed" and flags.get(_name(r), (False, None))[0]
    ]
    traces = {
        _name(record) or "?": [
            {
                "step_index": step.get("step_index"),
                "target": step.get("target"),
                "surface": step.get("surface"),
                "name": step.get("name"),
                "check": step.get("check"),
                "standard": step.get("standard"),
                "status": step.get("status"),
                "duration": step.get("duration"),
                "failures": step.get("failures"),
            }
            for step in _steps(record)
        ]
        for record in sorted(records, key=_name)
    }
    return {
        "trace_id": run_record.get("trace_id"),
        "generated_at": run_record.get("generated_at"),
        "summary": _counts(records, flags),
        "verdicts": verdicts,
        "blockers": _blockers(records),
        "regression_failures": regression_failures,
        "traces": traces,
        "artifacts": _artifact_entries(records),
    }
