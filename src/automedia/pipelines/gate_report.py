"""Gate-report writer — renders a per-run gate report from ALREADY-captured data.

Design constraints (productization-roadmap-20260902 todo 4 / roadmap P0-1):

- **No new persistent gate store.**  Renders ONLY from
  :class:`~automedia.pipelines.gate_engine.GateLogEntry` rows (the pipeline's
  own gates log) plus optional in-memory per-gate result dicts (the dicts
  produced by ``GateEngine._run`` / ``gates._result.build_gate_result``).
- **Vocabulary mapping.**  Internal gate status ``passed|failed|error`` maps to
  the report vocabulary ``pass|fail|review`` (``error`` → ``review``: a gate
  that crashed needs human attention, it did not "fail" on content).
- **H0 / HITL honesty.**  ``_hitl_approved`` lives only in transient result
  dicts — it is ABSENT from gates_log rows.  A live render (``gate_results``
  given) may mark H0 as reviewed based on that key; an offline render
  (persisted rows only) marks H0 as ``review`` ONLY when the caller asserts
  the run's director/hitl mode via ``hitl_mode=True``.  It never guesses from
  persisted data alone.
- **Output.**  ``write_gate_report`` writes a human-readable Markdown file and
  a structured JSON file to
  ``<project_dir>/05_review/gate-report/gate-report-<UTC-ISO-ts>.{md,json}``,
  creating the parent directory.  Nothing else in the project layout is
  touched.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from structlog import get_logger

from automedia.pipelines.gate_engine import GateLogEntry

log = get_logger(__name__)

__all__ = ["render_gate_report", "write_gate_report"]

#: Report directory relative to the project root (layout: core/project.py).
REPORT_SUBDIR = Path("05_review") / "gate-report"
#: Report filename stem (timestamp is appended at write time).
REPORT_STEM = "gate-report"

#: Report vocabulary — what each internal status maps to.
_VERDICT_MAP: dict[str, str] = {
    "passed": "pass",
    "failed": "fail",
    "error": "review",
}

#: Per-check remediation keys produced by
#: :func:`automedia.gates._result._enrich_failing_checks` (failing checks
#: only).  Preserved verbatim when present; never synthesized in this module.
_CHECK_REMEDIATION_KEYS = ("check_name", "actual_value", "threshold", "suggestion")


class GateReportRow(TypedDict, total=False):
    """One per-gate row in the report (JSON-serializable)."""

    gate: str
    status: str  # internal: passed|failed|error
    verdict: str  # report vocabulary: pass|fail|review
    verdict_source: str  # "log" (persisted) | "result" (live in-memory)
    reviewed: bool  # True only when HITL involvement is a fact, not a guess
    duration_s: float
    error: str | None
    checks: list[dict[str, Any]] | None  # per-check detail (live renders only)
    expected_vs_actual: dict[str, Any] | None
    output_path: str | None


class GateReport(TypedDict):
    """Top-level report dict returned by :func:`render_gate_report`."""

    project_dir: str
    generated_at: str  # UTC ISO-8601
    gates: list[GateReportRow]
    summary: dict[str, Any]
    blocked_by_gate: str | None
    blocked_by: str  # human-readable "blocked by" sentence
    markdown: str


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _verdict_for_row(
    entry: GateLogEntry,
    result: dict[str, Any] | None,
    hitl_mode: bool,
) -> tuple[str, str, bool]:
    """Compute ``(verdict, verdict_source, reviewed)`` for one gate row.

    H0 special-casing per the plan's OFFLINE/ONLINE contract:

    - LIVE (``result`` given): ``_hitl_approved=True`` → the human approved;
      the gate had been "review" and resolved to ``pass`` (recorded as
      reviewed).  ``_hitl_approved=False`` → human rejected → ``fail``.
      ``status == "awaiting_hitl"`` → still under review → ``review``.
    - OFFLINE (no result): H0 maps to ``review`` ONLY when the caller asserts
      the run's hitl/director mode via ``hitl_mode``; otherwise ``pass``.
      Persisted rows carry no ``_hitl_approved`` — never guessed.
    """
    verdict = _VERDICT_MAP.get(entry.status, "review")
    source = "log"
    reviewed = False

    if entry.gate_name == "H0":
        if result is not None:
            source = "result"
            if result.get("_hitl_approved") is False:
                return "fail", source, True
            if result.get("_hitl_approved") is True:
                return "pass", source, True
            if result.get("status") == "awaiting_hitl":
                return "review", source, True
        elif hitl_mode:
            return "review", source, True

    return verdict, source, reviewed


def _build_row(
    entry: GateLogEntry,
    result: dict[str, Any] | None,
    hitl_mode: bool,
) -> GateReportRow:
    """Build one report row from a log entry plus optional live result dict."""
    verdict, source, reviewed = _verdict_for_row(entry, result, hitl_mode)

    row = GateReportRow(
        gate=entry.gate_name,
        status=entry.status,
        verdict=verdict,
        verdict_source=source,
        reviewed=reviewed,
        duration_s=round(float(entry.duration_s), 4),
        error=entry.error,
    )

    if result is not None:
        # Per-check detail where present (live in-memory result dicts only).
        checks = result.get("checks")
        if isinstance(checks, list):
            normalized: list[dict[str, Any]] = []
            for c in checks:
                if not isinstance(c, dict):
                    continue
                check: dict[str, Any] = {
                    "name": c.get("name", ""),
                    "passed": bool(c.get("passed", False)),
                    "detail": c.get("detail", ""),
                }
                # Keep the remediation fields already derived for failing
                # checks (suggestion/threshold/actual_value/check_name).
                # Passing checks carry none, so none are invented here.
                for key in _CHECK_REMEDIATION_KEYS:
                    if key in c:
                        check[key] = c[key]
                normalized.append(check)
            row["checks"] = normalized
        eva = result.get("expected_vs_actual")
        if isinstance(eva, dict) and eva:
            row["expected_vs_actual"] = eva
        output_path = result.get("output_path")
        if isinstance(output_path, str) and output_path:
            row["output_path"] = output_path
    else:
        row["checks"] = None  # per-check detail unavailable from persisted rows

    return row


def _match_result(
    entry: GateLogEntry,
    gate_results: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Find the in-memory result dict for *entry* by gate name (last wins —
    the engine replaces ``results[-1]`` on quality retries)."""
    if not gate_results:
        return None
    matched: dict[str, Any] | None = None
    for r in gate_results:
        if isinstance(r, dict) and r.get("gate") == entry.gate_name:
            matched = r
    return matched


def _render_markdown(report: GateReport) -> str:
    """Render the human-readable Markdown view of the report dict."""
    lines: list[str] = []
    lines.append("# Gate Report")
    lines.append("")
    lines.append(f"- Project: `{report['project_dir']}`")
    lines.append(f"- Generated (UTC): {report['generated_at']}")
    summary = report["summary"]
    lines.append(
        f"- Gates: {summary['total']} "
        f"(pass {summary['passed']} / fail {summary['failed']} / "
        f"review {summary['errored']})"
    )
    if report["blocked_by_gate"]:
        lines.append(f"- **Blocked by**: {report['blocked_by']}")
    lines.append("")

    if not report["gates"]:
        lines.append(
            "_No gate executions were recorded for this run (empty gates log) — nothing to report._"
        )
        lines.append("")
        return "\n".join(lines)

    lines.append("| Gate | Verdict | Duration (s) | Reason |")
    lines.append("|------|---------|--------------|--------|")
    for row in report["gates"]:
        verdict = row["verdict"]
        if row.get("reviewed"):
            verdict += " (reviewed)"
        reason = row.get("error") or ""
        lines.append(f"| {row['gate']} | {verdict} | {row.get('duration_s', 0.0)} | {reason} |")
    lines.append("")

    # Per-check detail sections for rows that carry them (live renders).
    for row in report["gates"]:
        checks = row.get("checks")
        eva = row.get("expected_vs_actual")
        output_path = row.get("output_path")
        has_detail = bool(checks) or bool(eva) or bool(output_path)
        if not has_detail:
            continue
        lines.append(f"## {row['gate']} — details")
        lines.append("")
        if output_path:
            lines.append(f"- Output: `{output_path}`")
        if eva:
            lines.append(f"- Expected: {eva.get('expected', '')}")
            lines.append(f"- Actual: {eva.get('actual', '')}")
        if checks:
            lines.append("")
            lines.append("| Check | Passed | Detail |")
            lines.append("|-------|--------|--------|")
            lines.extend(
                f"| {c.get('name', '')} | {'yes' if c.get('passed') else 'no'} "
                f"| {c.get('detail', '')} |"
                for c in checks
            )
        lines.append("")

    return "\n".join(lines)


def render_gate_report(
    project_dir: str,
    gates_log: list[GateLogEntry],
    gate_results: list[dict[str, Any]] | None = None,
    *,
    hitl_mode: bool = False,
) -> GateReport:
    """Render a per-run gate report from already-captured pipeline data.

    Parameters
    ----------
    project_dir:
        Project root directory (recorded in the report; not read from).
    gates_log:
        The pipeline's per-gate log entries (``PipelineResult.gates_log``).
        Required input; may be empty.
    gate_results:
        Optional in-memory per-gate result dicts (the dicts produced by gate
        execution).  When given ("LIVE" render), rows are enriched with
        per-check detail, ``expected_vs_actual``, and ``output_path``, and H0
        rows may reflect ``_hitl_approved``.  When omitted ("OFFLINE" render,
        e.g. from persisted history rows), per-check detail is marked
        unavailable and H0 is never guessed as "review".
    hitl_mode:
        OFFLINE-only context flag: set ``True`` when the run's director/hitl
        mode was active so the H0 row renders as ``review``.  Ignored when
        ``gate_results`` are present.

    Returns
    -------
    GateReport
        JSON-serializable report dict; ``report["markdown"]`` holds the
        human-readable Markdown rendering.
    """
    rows: list[GateReportRow] = []
    for entry in gates_log:
        result = _match_result(entry, gate_results)
        rows.append(_build_row(entry, result, hitl_mode))

    blocked_gate: str | None = None
    for row in rows:
        if row["verdict"] == "fail":
            blocked_gate = row["gate"]
            break

    blocked_by = ""
    if blocked_gate:
        blocked_row = next(r for r in rows if r["gate"] == blocked_gate)
        reason = blocked_row.get("error") or "no reason recorded"
        blocked_by = f"Run blocked by gate {blocked_gate}: {reason}"

    verdicts = [r["verdict"] for r in rows]
    total_duration = round(sum(r.get("duration_s", 0.0) for r in rows), 4)
    summary = {
        "total": len(rows),
        "passed": verdicts.count("pass"),
        "failed": verdicts.count("fail"),
        "errored": verdicts.count("review"),
        "total_duration_s": total_duration,
    }

    report: GateReport = {
        "project_dir": project_dir,
        "generated_at": datetime.now(UTC).isoformat(),
        "gates": rows,
        "summary": summary,
        "blocked_by_gate": blocked_gate,
        "blocked_by": blocked_by,
        "markdown": "",
    }
    report["markdown"] = _render_markdown(report)
    return report


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _timestamp_for_filename() -> str:
    """UTC ISO timestamp safe for filenames (``:`` replaced)."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace(":", "")


def write_gate_report(project_dir: str, report: dict[str, Any]) -> tuple[Path, Path]:
    """Write the report as Markdown + JSON under ``05_review/gate-report/``.

    Creates the parent directory.  Returns ``(markdown_path, json_path)``.

    Note: the plan text types the return as ``Path``; both files are written
    as one pair, so the concrete contract here returns the 2-tuple — callers
    that need a single path can take either element.
    """
    out_dir = Path(project_dir) / REPORT_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = f"{REPORT_STEM}-{_timestamp_for_filename()}"
    md_path = out_dir / f"{stem}.md"
    json_path = out_dir / f"{stem}.json"

    markdown = report.get("markdown")
    if not isinstance(markdown, str) or not markdown:
        # Re-render if the caller passed a report without the markdown view.
        markdown = _render_markdown(report)  # type: ignore[arg-type]

    md_path.write_text(markdown, encoding="utf-8")

    payload = {k: v for k, v in report.items() if k != "markdown"}
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    log.debug(
        "gate_report written",
        markdown=str(md_path),
        json=str(json_path),
        project_dir=project_dir,
    )
    return md_path, json_path
