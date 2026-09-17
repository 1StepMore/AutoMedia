"""AX metrics emitted per validation suite run (gap Tr-02).

Six formulas, computed from one suite record and written as ``metrics.json``
beside ``scenarios.json`` (and embedded under the record's ``metrics`` key so
``validate report`` renders them):

* ``task_completion_rate`` — passed real runs / runnable real runs, where
  real excludes ``unconfigured`` and mock-confidence records.
* ``tool_call_accuracy`` — passed primary steps / attempted primary steps over
  the real-confidence scenarios.
* ``recovery_success_rate`` — recovered / attempted recoveries.
* ``doc_freshness`` — ``scripts/doc_inventory.py --check`` exit 0 ? 1 : 0.
* ``token_usage`` — sum of reported token counts; ``null`` until
  instrumentation exists (no writer ships yet).
* ``error_recovery_time_s`` — median failed→recovery seconds; ``null`` when
  there are no recoveries.

Null semantics are explicit: a metric with no denominator is ``null`` plus a
reason, never ``0``.  An all-unconfigured run therefore writes
``task_completion_rate: null`` and ``unproven: true``.
"""

from __future__ import annotations

import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

METRIC_KEYS: tuple[str, ...] = (
    "task_completion_rate",
    "tool_call_accuracy",
    "recovery_success_rate",
    "doc_freshness",
    "token_usage",
    "error_recovery_time_s",
)
"""The six Tr-02 metric keys, in report order."""

_NO_USAGE_INSTRUMENTATION_REASON = "no token instrumentation yet"


def _confidence(record: dict[str, Any]) -> str:
    """A record's confidence: ``mock`` or ``real`` (absent = real)."""
    value = record.get("confidence")
    return value if value in ("real", "mock") else "real"


def _repo_root() -> Path:
    """Repo root from this module's location (same trick as the loader)."""
    return Path(__file__).resolve().parents[3]


def doc_freshness(repo_root: Path | None = None) -> int | None:
    """1 when ``doc_inventory.py --check`` exits 0, else 0; None when absent."""
    root = _repo_root() if repo_root is None else repo_root
    script = root / "scripts" / "doc_inventory.py"
    if not script.is_file():
        return None
    try:
        proc = subprocess.run(  # noqa: S603 — trusted committed script
            [sys.executable, str(script), "--check"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    return 1 if proc.returncode == 0 else 0


def _primary_steps(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every primary step trace across the given scenario records."""
    steps: list[dict[str, Any]] = []
    for record in records:
        raw = record.get("steps")
        if isinstance(raw, list):
            steps.extend(step for step in raw if isinstance(step, dict))
    return steps


def _recovery_stats(records: list[dict[str, Any]]) -> tuple[int, int, list[float]]:
    """``(attempted, recovered, durations)`` over the record's primary steps."""
    attempted = 0
    recovered = 0
    durations: list[float] = []
    for step in _primary_steps(records):
        recovery = step.get("recovery")
        if not isinstance(recovery, list) or not recovery:
            continue
        attempted += 1
        entries = [entry for entry in recovery if isinstance(entry, dict)]
        if step.get("status") == "recovered" or any(
            entry.get("passed") is True for entry in entries
        ):
            recovered += 1
            total = sum(
                entry.get("duration", 0.0)
                for entry in entries
                if isinstance(entry.get("duration"), (int, float))
            )
            durations.append(float(total))
    return attempted, recovered, durations


def build_metrics(
    run_record: dict[str, Any], *, doc_freshness_value: int | None = None
) -> dict[str, Any]:
    """Compute the six Tr-02 metrics from a suite record.

    ``doc_freshness_value`` injects the doc check result (tests, callers that
    already ran it); otherwise it is computed here.  Every absent denominator
    yields ``null`` with a reason, never ``0``.
    """
    raw = run_record.get("scenarios")
    records = [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []
    real = [r for r in records if _confidence(r) == "real" and r.get("status") != "unconfigured"]
    runnable = len(real)
    passed = sum(1 for r in real if r.get("status") == "passed")
    task_completion_rate = round(passed / runnable, 4) if runnable else None

    steps = _primary_steps(real)
    attempted_steps = len(steps)
    passed_steps = sum(1 for step in steps if step.get("passed") is True)
    tool_call_accuracy = round(passed_steps / attempted_steps, 4) if attempted_steps else None

    attempted_recoveries, recovered, durations = _recovery_stats(records)
    recovery_success_rate = (
        round(recovered / attempted_recoveries, 4) if attempted_recoveries else None
    )
    error_recovery_time_s = round(statistics.median(durations), 4) if durations else None

    freshness = doc_freshness() if doc_freshness_value is None else doc_freshness_value

    reasons: dict[str, str] = {}
    if task_completion_rate is None:
        reasons["task_completion_rate"] = "no runnable real runs (all unconfigured or mock-only)"
    if tool_call_accuracy is None:
        reasons["tool_call_accuracy"] = "no primary steps recorded"
    if recovery_success_rate is None:
        reasons["recovery_success_rate"] = "no attempted recoveries"
    if freshness is None:
        reasons["doc_freshness"] = "doc_inventory --check unavailable"
    reasons["token_usage"] = _NO_USAGE_INSTRUMENTATION_REASON
    if error_recovery_time_s is None:
        reasons["error_recovery_time_s"] = "no recoveries"

    return {
        "task_completion_rate": task_completion_rate,
        "tool_call_accuracy": tool_call_accuracy,
        "recovery_success_rate": recovery_success_rate,
        "doc_freshness": freshness,
        "token_usage": None,
        "error_recovery_time_s": error_recovery_time_s,
        "unproven": task_completion_rate is None,
        "runs": {
            "runnable_real": runnable,
            "passed_real": passed,
            "attempted_steps": attempted_steps,
            "passed_steps": passed_steps,
            "attempted_recoveries": attempted_recoveries,
            "recovered": recovered,
        },
        "reasons": reasons,
    }
