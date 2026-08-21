"""Run-record assertion matrix for the agent-tester validation layer (issue #86).

The review gap this closes: the matrix must be AutoInfo-style — a full
artifact-assertion matrix over what each scenario's assertions actually
PRODUCED (from run records), not just a static coverage grid over what the
scenarios DECLARE.  Pure functions, no new dependencies: consume only engine
suite records (``validation-runs/<stamp>/scenarios.json``) and the committed
baseline, and reuse ``automedia.validation.diff.diff_runs`` for the
four-way classification.

Two sections (both derived from the latest run record):

* ``report_cards`` — one director-readable digest per scenario IN THE LATEST
  RUN: status, hard flag, engine hard-safety violation, assertion counts
  (main steps only), per-step exit codes, first failure per step, missing
  artifacts, and the diff bucket the scenario fell into.
* ``assertions`` — the step-level truth table (the 04-MATRIX core): one row
  per MAIN step (recovery/cleanup excluded as rows — recovery failures stay
  in the step's ``failures``, cleanup is reported separately) with
  step_index, target, surface, name, check, standard, status, failures,
  exit_code (from ``output.exit_code`` when present), a per-step
  ``hard_safety`` cell (True when the step failed AND the scenario is hard),
  and collected artifact paths.

Honesty rules preserved: recovery never erases RED (a ``recovered`` step
keeps its failures); ``unconfigured`` scenarios carry empty assertions;
a scenario present in the latest run but absent from the baseline is
classified ``"new"``; no run record at all yields empty cards and a
``None`` diff (never a crash, never fabricated evidence).

Diff buckets (mapping of ``diff.diff_runs`` output, 1:1): new_passes →
``"new-pass"``, new_failures → ``"new-failure"``, regressed →
``"regressed"``, improved → ``"improved"``, stable → ``"stable"``,
other → ``"other"``; latest-only → ``"new"``.
"""

from __future__ import annotations

from typing import Any

from automedia.validation.diff import diff_runs

# Diff bucket → per-scenario classification label (1:1 with diff_runs keys).
_DIFF_LABELS: dict[str, str] = {
    "new_passes": "new-pass",
    "new_failures": "new-failure",
    "regressed": "regressed",
    "improved": "improved",
}

_MAIN_STEP_STATUSES: tuple[str, ...] = ("passed", "failed", "recovered")
"""Step statuses counted in a card's assertion totals (cleanup excluded)."""


def _suite_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    """The suite record's scenario rows; non-list garbage degrades to []."""
    rows = record.get("scenarios")
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _main_steps(row: dict[str, Any]) -> list[dict[str, Any]]:
    """The scenario row's main-step traces (cleanup excluded)."""
    steps = row.get("steps")
    return [s for s in steps if isinstance(s, dict)] if isinstance(steps, list) else []


def _exit_code(step: dict[str, Any]) -> int | None:
    """``output.exit_code`` when the step envelope carries one, else None."""
    output = step.get("output")
    if isinstance(output, dict) and isinstance(output.get("exit_code"), int):
        return output["exit_code"]
    return None


def _exit_codes(steps: list[dict[str, Any]]) -> dict[int, int]:
    """step_index → exit_code for the steps that carry one."""
    codes: dict[int, int] = {}
    for step in steps:
        idx = step.get("step_index")
        code = _exit_code(step)
        if isinstance(idx, int) and code is not None:
            codes[idx] = code
    return codes


def _artifact_paths(step: dict[str, Any]) -> list[str]:
    """Collected artifact paths from a step trace (``copied_to`` or source)."""
    paths: list[str] = []
    artifacts = step.get("artifacts")
    if not isinstance(artifacts, list):
        return paths
    for entry in artifacts:
        if isinstance(entry, dict):
            copied = entry.get("copied_to")
            path = entry.get("path")
            paths.append(str(copied or path or "?"))
    return paths


def _first_failures(step: dict[str, Any]) -> list[str]:
    """The step's expect failures; adapter errors name ``output.error``."""
    failures = step.get("failures")
    if isinstance(failures, list) and failures:
        return [str(f) for f in failures]
    output = step.get("output")
    if isinstance(output, dict) and output.get("error"):
        return [f"adapter error: {output['error']}"]
    return []


def _diff_classification(diff: dict[str, Any] | None, name: str, baseline_names: set[str]) -> str:
    """Map a scenario name to its diff bucket, or ``"new"`` when latest-only.

    ``diff`` is the verbatim ``diff_runs`` output; ``baseline_names`` is the
    set of scenario names in the baseline record.  The four buckets partition
    the COMPARED set; a scenario present in the latest run but absent from
    the baseline appears in none of them and is classified ``"new"``.
    ``diff is None`` (no baseline) also yields ``"new"`` — every scenario in
    the latest run is unproven against a baseline.
    """
    if diff is None:
        return "new"
    for key, label in _DIFF_LABELS.items():
        if name in (diff.get(key) or []):
            return label
    if name not in baseline_names:
        return "new"
    return "stable"


def scenario_report_cards(
    latest: dict[str, Any] | None, baseline: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Build the per-scenario report cards + the diff over the two records.

    ``latest`` is the newest engine suite record (or None when no run exists);
    ``baseline`` is the committed baseline record (or None).  The diff is
    computed by ``diff_runs`` when BOTH records are present, else None.

    Returns ``(cards, diff)`` where each card carries: scenario, status,
    hard, hard_safety_violation, assertions {total, passed, failed,
    recovered}, exit_codes {step_index: exit_code}, failures (first failure
    per step, truncated list), artifacts_missing (from summary), diff bucket.
    Cards are sorted by scenario name.
    """
    if latest is None:
        return [], None

    diff = diff_runs(baseline, latest) if baseline is not None else None
    baseline_names = (
        {str(r.get("scenario")) for r in _suite_rows(baseline)} if baseline is not None else set()
    )
    cards: list[dict[str, Any]] = []
    for row in _suite_rows(latest):
        name = str(row.get("scenario") or "")
        if not name:
            continue
        steps = _main_steps(row)
        statuses = [str(s.get("status")) for s in steps]
        cards.append(
            {
                "scenario": name,
                "status": str(row.get("status") or "?"),
                "hard": bool(row.get("hard")),
                "hard_safety_violation": bool(row.get("hard_safety_violation")),
                "assertions": {
                    "total": len(steps),
                    "passed": statuses.count("passed"),
                    "failed": statuses.count("failed"),
                    "recovered": statuses.count("recovered"),
                },
                "exit_codes": _exit_codes(steps),
                "failures": [
                    f"step {s.get('step_index')} ({s.get('name')}): {_first_failures(s)[0]}"
                    for s in steps
                    if s.get("status") != "passed" and _first_failures(s)
                ][:5],
                "artifacts_missing": list(row.get("summary", {}).get("artifacts_missing") or [])
                if isinstance(row.get("summary"), dict)
                else [],
                "diff": _diff_classification(diff, name, baseline_names),
            }
        )
    return sorted(cards, key=lambda c: str(c["scenario"])), diff


def build_assertion_matrix(
    latest: dict[str, Any] | None, baseline: dict[str, Any] | None
) -> dict[str, Any]:
    """The assertion half of the matrix: report_cards + step truth table + diff.

    Returns ``{"report_cards": [...], "assertions": {name: [step rows]},
    "diff": <diff_runs output or None>}``.  Each step row: step_index,
    target, surface, name, check, standard, status, failures, exit_code,
    hard_safety (True when the step failed AND the scenario is hard),
    artifacts.  Both cards and assertion rows are sorted by scenario name.
    """
    cards, diff = scenario_report_cards(latest, baseline)
    assertions: dict[str, list[dict[str, Any]]] = {}
    if latest is not None:
        hard_by_name = {str(r.get("scenario")): bool(r.get("hard")) for r in _suite_rows(latest)}
        for card in cards:
            name = str(card["scenario"])
            row = next((r for r in _suite_rows(latest) if str(r.get("scenario")) == name), None)
            assertions[name] = (
                [
                    {
                        "step_index": s.get("step_index"),
                        "target": s.get("target"),
                        "surface": s.get("surface"),
                        "name": s.get("name"),
                        "check": s.get("check"),
                        "standard": s.get("standard"),
                        "status": s.get("status"),
                        "failures": _first_failures(s),
                        "exit_code": _exit_code(s),
                        "hard_safety": bool(s.get("passed")) is False
                        and hard_by_name.get(name, False),
                        "artifacts": _artifact_paths(s),
                    }
                    for s in _main_steps(row)
                ]
                if row is not None
                else []
            )
    return {"report_cards": cards, "assertions": assertions, "diff": diff}


__all__ = [
    "build_assertion_matrix",
    "scenario_report_cards",
]
