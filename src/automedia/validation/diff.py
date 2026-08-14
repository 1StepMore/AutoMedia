"""Run-to-run diff for agent-tester validation (W4-T4).

The director's drift detector (guide §5.4 + §6.5): compare two engine suite
records and report what changed — new passes, new failures, regressions —
plus the quality trend: per-step numeric score keys extracted from step
outputs, with any decrease flagged as ``dropped``.

Record shapes (engine.py, W1-T7): a suite record is ``{trace_id,
generated_at, scenarios: [...]}``; each scenario row carries ``scenario``
(name) and ``status`` (passed / failed / unconfigured / recovered /
partial-pass); each step trace carries ``step_index`` (1-based; 0 =
cleanup) and ``output``.  The W2-T4 committed baseline
(``scenarios/baseline/2026-08-14-preflight.json``) is exactly such a
record with a ``baseline: true`` marker — ``diff_latest(..., baseline_path=...)``
diffs the latest recorded run against it, which is how later waves prove
their RED→GREEN turns.

Classification: the buckets are disjoint and partition every compared pair.

- ``new_passes``: before failed/recovered/partial-pass → after passed
- ``new_failures``: before passed → after anything else (incl. unconfigured)
- ``regressed``: before failed → after failed (persistent failures)
- ``improved``: before unconfigured → after passed
- ``stable``: before == after, per-status counts — persistent failures are
  reported in ``regressed`` and excluded here so the buckets partition the
  compared set
- ``other``: any remaining transition (never silently dropped)

Quality trend: numeric values under score-named keys (key contains
"score"; bools excluded) are extracted from step outputs of scenarios
present in BOTH records, matched by ``step_index``.  A score key present on
one side only is not compared (missing score keys = no trend entry for
that step).  Any decrease is flagged ``dropped``.  The known score key is
``quality_score`` (W3-T4: ``evaluate_content_quality`` output — verified
in ``mcp/tools/quality.py`` + ``decision/pydantic.py``
``ContentQualityOutput``; error envelopes also carry ``quality_score:
0.0``, so a step whose LLM call failed is honestly compared as a drop).
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

from automedia.validation.persist import list_runs

STATUSES: tuple[str, ...] = (
    "passed",
    "failed",
    "unconfigured",
    "recovered",
    "partial-pass",
)


class DiffError(ValueError):
    """A suite record or run file could not be read as diffable evidence."""


def _suite_scenarios(record: object, label: str) -> dict[str, dict[str, object]]:
    """Validate an engine suite record and index its rows by scenario name."""
    if not isinstance(record, dict) or not isinstance(record.get("scenarios"), list):
        raise DiffError(
            f"{label} is not an engine suite record (expected a dict carrying a 'scenarios' list)"
        )
    index: dict[str, dict[str, object]] = {}
    for row in record["scenarios"]:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("scenario"), str)
            or not isinstance(row.get("status"), str)
            or not row["status"]
        ):
            raise DiffError(
                f"{label} has a malformed scenario row "
                "(expected {{scenario: str, status: str, ...}})"
            )
        index[str(row["scenario"])] = row
    return index


def _extract_scores(output: object) -> dict[str, float]:
    """Numeric score keys from a step output envelope (flat scan).

    A key counts as a score when its name contains "score" (lowercased) and
    its value is a number — bools are excluded (bool is an int subclass).
    Non-dict outputs (or non-numeric values) contribute nothing.
    """
    if not isinstance(output, dict):
        return {}
    scores: dict[str, float] = {}
    for key, value in output.items():
        if not isinstance(key, str) or "score" not in key.lower():
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        scores[key] = float(value)
    return scores


def _quality_trend(
    before_idx: dict[str, dict[str, object]],
    after_idx: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], int]:
    """Compare per-step score keys of scenarios present in both records.

    Returns ``(dropped, raised, unchanged)`` — a tuple so the caller never
    has to re-narrow dict values.
    """
    dropped: list[dict[str, object]] = []
    raised: list[dict[str, object]] = []
    unchanged = 0
    for name in sorted(before_idx.keys() & after_idx.keys()):
        before_steps = before_idx[name].get("steps")
        after_steps = after_idx[name].get("steps")
        if not isinstance(before_steps, list) or not isinstance(after_steps, list):
            continue
        after_by_index = {
            int(step["step_index"]): step
            for step in after_steps
            if isinstance(step, dict) and isinstance(step.get("step_index"), int)
        }
        for step in before_steps:
            if not isinstance(step, dict) or not isinstance(step.get("step_index"), int):
                continue
            after_step = after_by_index.get(int(step["step_index"]))
            if after_step is None:
                continue
            before_scores = _extract_scores(step.get("output"))
            after_scores = _extract_scores(after_step.get("output"))
            for key in sorted(before_scores.keys() & after_scores.keys()):
                before_value = before_scores[key]
                after_value = after_scores[key]
                if before_value > after_value:
                    dropped.append(
                        {
                            "scenario": name,
                            "step": int(step["step_index"]),
                            "key": key,
                            "before": before_value,
                            "after": after_value,
                        }
                    )
                elif before_value < after_value:
                    raised.append(
                        {
                            "scenario": name,
                            "step": int(step["step_index"]),
                            "key": key,
                            "before": before_value,
                            "after": after_value,
                        }
                    )
                else:
                    unchanged += 1
    return dropped, raised, unchanged


def diff_runs(before: dict, after: dict) -> dict:
    """Diff two engine suite records; return the run-to-run change report.

    ``before``/``after`` are suite records in the engine shape
    (``{trace_id, generated_at, scenarios: [...]}``).  The report is
    deterministic: every scenario list is sorted; ``stable`` carries the
    five statuses in canonical order (persistent failures live in
    ``regressed``, so the buckets partition the compared set).
    """
    before_idx = _suite_scenarios(before, "before record")
    after_idx = _suite_scenarios(after, "after record")

    new_passes: list[str] = []
    new_failures: list[str] = []
    regressed: list[str] = []
    improved: list[str] = []
    other: list[str] = []
    stable: dict[str, int] = {status: 0 for status in STATUSES}
    unpaired = 0
    for name in sorted(before_idx.keys() | after_idx.keys()):
        before_row = before_idx.get(name)
        after_row = after_idx.get(name)
        if before_row is None or after_row is None:
            unpaired += 1
            continue
        before_status = str(before_row["status"])
        after_status = str(after_row["status"])
        if before_status == after_status:
            if before_status == "failed":
                regressed.append(name)
            else:
                stable[before_status] += 1
        elif after_status == "passed":
            if before_status == "unconfigured":
                improved.append(name)
            else:
                new_passes.append(name)
        elif before_status == "passed":
            new_failures.append(name)
        else:
            other.append(name)

    quality_dropped, quality_raised, quality_unchanged = _quality_trend(before_idx, after_idx)
    compared = len(before_idx.keys() & after_idx.keys())
    return {
        "new_passes": new_passes,
        "new_failures": new_failures,
        "regressed": regressed,
        "improved": improved,
        "stable": stable,
        "quality_trend": {
            "dropped": quality_dropped,
            "raised": quality_raised,
            "unchanged": quality_unchanged,
        },
        "summary": {
            "total": compared,
            "new_passes": len(new_passes),
            "new_failures": len(new_failures),
            "regressed": len(regressed),
            "improved": len(improved),
            "stable": sum(stable.values()),
            "other": len(other),
            "unpaired": unpaired,
            "quality_compared": quality_unchanged + len(quality_dropped) + len(quality_raised),
        },
    }


def _load_record(path: Path) -> dict:
    """Read one engine suite record from disk; :class:`DiffError` on failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise DiffError(f"run record not found: {path}") from None
    try:
        record = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DiffError(f"run record is not valid JSON: {path}: {exc}") from None
    if not isinstance(record, dict):
        raise DiffError(f"run record is not a JSON object: {path}")
    return record


def diff_latest(runs_root: Path, *, baseline_path: Path | None = None) -> dict | None:
    """Diff the latest recorded run — against the baseline, or two latest runs.

    With ``baseline_path`` (the PRIMARY use case — the committed W2-T4
    baseline ``scenarios/baseline/2026-08-14-preflight.json``), the latest
    run in ``runs_root`` is diffed against that record; this is how later
    waves prove the baseline's RED/unconfigured rows turned GREEN.
    Without it, the two latest runs (``persist.list_runs``, newest-first)
    are diffed oldest→newest.

    Returns ``None`` with a clear ``UserWarning`` when fewer than two
    records are available (no runs at all, or only one run without a
    baseline).
    """
    names = list_runs(runs_root)
    if baseline_path is not None:
        if not names:
            warnings.warn(
                f"no recorded runs under {runs_root}: cannot diff against baseline {baseline_path}",
                UserWarning,
                stacklevel=2,
            )
            return None
        before = _load_record(Path(baseline_path))
        after_name = names[0]
    else:
        if len(names) < 2:
            warnings.warn(
                f"need at least two recorded runs under {runs_root} to diff; found {len(names)}",
                UserWarning,
                stacklevel=2,
            )
            return None
        before_name, after_name = names[1], names[0]
        before = _load_record(runs_root / before_name / "scenarios.json")
    after = _load_record(runs_root / after_name / "scenarios.json")
    return diff_runs(before, after)
