"""Plain-text layout for validation reports (W4-T3, component C5).

Pure presentation: every function here turns precomputed facts (counts,
records, flags, blockers, artifact entries, unsigned runs) into the aligned
plain-text section blocks of guide §6.  No record parsing — the facts are
derived in ``automedia.validation.report``, which imports the section
builders from here.  No ANSI: statuses are fixed markers
(PASS/FAIL/UNCONF/RECOV/PARTIAL) so the report pipes cleanly through a CLI.

Determinism lives here too: all widths are derived from content and every
row follows the caller's already-sorted input, so the same facts always
render byte-identical text.
"""

from __future__ import annotations

_MARKERS: dict[str, str] = {
    "passed": "PASS",
    "failed": "FAIL",
    "unconfigured": "UNCONF",
    "recovered": "RECOV",
    "partial-pass": "PARTIAL",
}

_STANDARDS_SOURCE = "STANDARDS.md"
"""Citation appended to every per-step trace line (the plan's cite format)."""


def marker(status: str) -> str:
    """Plain-text status marker; unknown statuses fall back to upper-cased."""
    return _MARKERS.get(status, status.upper())


def step_failure_lines(step: dict) -> list[str]:
    """The step's expect failures; adapter errors name ``output.error`` instead."""
    failures = step.get("failures")
    if isinstance(failures, list) and failures:
        return [str(f) for f in failures]
    output = step.get("output")
    if isinstance(output, dict) and output.get("error"):
        return [f"adapter error: {output['error']}"]
    return ["step failed without a recorded expect failure"]


def header_section(run_record: dict) -> list[str]:
    """Report header: run trace_id + generated_at (plan W4-T3 section 1)."""
    return [
        f"Validation report — trace {run_record.get('trace_id') or '?'}",
        f"generated at {run_record.get('generated_at') or '?'}",
    ]


def exec_summary_section(counts: dict[str, int]) -> list[str]:
    """Totals line + boundary-only/regression line (guide §6.1 #2)."""
    return [
        "## Exec summary",
        f"total: {counts['total']} | passed: {counts['passed']} | "
        f"failed: {counts['failed']} | unconfigured: {counts['unconfigured']} | "
        f"partial-pass: {counts['partial_pass']} | recovered: {counts['recovered']}",
        "boundary-only: {boundary} | regression failed: {regression}".format(
            boundary=counts["boundary_only"], regression=counts["regression_failed"]
        ),
    ]


def verdicts_section(records: list[dict], flags: dict[str, tuple[bool, str | None]]) -> list[str]:
    """Aligned SCENARIO | STATUS | SUMMARY table; regression rows carry their issue."""
    rows = []
    for record in sorted(records, key=_name):
        summary = verdict_summary(record)
        regression, issue = flags.get(_name(record), (False, None))
        if regression:
            summary = f"{summary}; regression: {issue or 'flagged'}"
        rows.append((_name(record) or "?", marker(str(record.get("status") or "")), summary))
    name_width = max([len("SCENARIO")] + [len(row[0]) for row in rows])
    status_width = max([len("STATUS")] + [len(row[1]) for row in rows])
    lines = [
        "## Verdicts",
        f"{'SCENARIO'.ljust(name_width)} | {'STATUS'.ljust(status_width)} | SUMMARY",
    ]
    lines.append(f"{'-' * name_width}-+-{'-' * status_width}-+-{'-' * len('SUMMARY')}")
    lines.extend(
        f"{row[0].ljust(name_width)} | {row[1].ljust(status_width)} | {row[2]}" for row in rows
    )
    return lines


def blockers_section(blockers: list[dict]) -> list[str]:
    """Every failed scenario's failing steps; FAIL lines name the expect key (§4.7)."""
    if not blockers:
        return ["## Blockers", "none"]
    lines = ["## Blockers"]
    lines.extend(
        f"- {b['scenario']} step {b['step_index']} ({b['step']}): {b['failure']}" for b in blockers
    )
    return lines


def regression_section(records: list[dict], flags: dict[str, tuple[bool, str | None]]) -> list[str]:
    """Failed regression scenarios with their issue references (guide §6.1 #3)."""
    failed = [
        r
        for r in sorted(records, key=_name)
        if r.get("status") == "failed" and flags.get(_name(r), (False, None))[0]
    ]
    if not failed:
        return ["## Regression failures", "none"]
    lines = ["## Regression failures"]
    for record in failed:
        _, issue = flags[_name(record)]
        lines.append(f"- {_name(record)}: {issue or 'regression scenario failed'}")
    return lines


def _trace_line(step: dict) -> str:
    """``step→check→standard(cite)→result`` — the plan's per-step format."""
    duration = step.get("duration")
    clock = f"{duration:.2f}s" if isinstance(duration, (int, float)) else "?"
    return (
        f"{step.get('step_index') or '?'}. {step.get('target') or step.get('name') or '?'} "
        f"→ {step.get('check') or '?'} → {step.get('standard') or '?'} "
        f"({_STANDARDS_SOURCE}) → {step.get('status') or '?'} ({clock})"
    )


def traces_section(records: list[dict]) -> list[str]:
    """Per-scenario step traces; failed steps append their failures (guide §6.1 #5)."""
    lines = ["## Per-step traces"]
    for record in sorted(records, key=_name):
        lines.append(f"### {_name(record) or '?'}")
        if record.get("status") == "unconfigured":
            lines.append(f"unconfigured: {record.get('reason') or 'no reason recorded'}")
            continue
        steps = _steps(record)
        if not steps:
            lines.append("(no steps)")
        for step in steps:
            lines.append(_trace_line(step))
            # Failure evidence only for non-passed steps; recovered keeps its
            # primary failure (RED is never erased).
            if step.get("status") != "passed":
                lines.extend(f"  {f}" for f in step_failure_lines(step))
    return lines


def artifacts_section(entries: list[dict]) -> list[str]:
    """GREEN→artifact links: ``artifact: <copied_to or path>`` per entry (§4.7)."""
    if not entries:
        return ["## Artifacts", "(no artifacts collected)"]
    lines = ["## Artifacts"]
    for entry in entries:
        missing = " (missing)" if not entry["ok"] else ""
        lines.append(
            f"- {entry['scenario']} step {entry['step_index']} ({entry['step']}): "
            f"artifact: {entry['artifact']}{missing}"
        )
    return lines


def signoff_section(unsigned: list[str] | None) -> list[str]:
    """Sign-off note (W4-T5) + the unsigned-run listing when a runs root exists."""
    lines = [
        "## Sign-off",
        "Directors append the run name, date, and verdict to signed.txt in the "
        "run directory (W4-T5).",
    ]
    if unsigned is None:
        return lines
    if unsigned:
        lines.append("Unsigned runs:")
        lines.extend(f"- {name}" for name in unsigned)
    else:
        lines.append("Unsigned runs: none (all signed)")
    return lines


def _steps(record: dict) -> list[dict]:
    """The record's main-step traces; non-list garbage degrades to []."""
    steps = record.get("steps")
    return [s for s in steps if isinstance(s, dict)] if isinstance(steps, list) else []


def _name(record: dict) -> str:
    """Stable sort key: the scenario name (determinism across section ordering)."""
    return str(record.get("scenario") or "")


def verdict_summary(record: dict) -> str:
    """The SUMMARY cell: step counts, loud artifact misses, or the reason.

    Shared by the verdicts table and the JSON render (which carries the
    regression tag in its own keys, not in this cell).
    """
    if record.get("status") == "unconfigured":
        return str(record.get("reason") or "unconfigured")
    summary = record.get("summary")
    if not isinstance(summary, dict):
        return str(record.get("status") or "?")
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    recovered = summary.get("recovered", 0)
    text = f"{passed}/{total} steps passed"
    if failed:
        text += f", {failed} failed"
    if recovered:
        text += f", {recovered} recovered"
    missing = summary.get("artifacts_missing")
    if isinstance(missing, list) and missing:
        text += f"; {len(missing)} required artifact(s) missing"
    return text
