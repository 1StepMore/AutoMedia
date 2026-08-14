"""Unit tests for the run-to-run diff (W4-T4).

Synthetic engine suite records only — no engine, no server, no network.
Covers the pinned classification buckets (new_passes / new_failures /
regressed / improved / stable / other / unpaired), the quality trend
(drop flagged with scenario+step+key+before+after, raise, unchanged count,
missing-key and non-dict defensive paths, bool exclusion, deterministic
sorting), summary reconciliation, and ``diff_latest`` (baseline path vs
two-latest-runs path, ``None`` + warning when records are insufficient,
malformed/missing record errors).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from automedia.validation.diff import (
    STATUSES,
    DiffError,
    diff_latest,
    diff_runs,
)


def _step(step_index: int, output: object) -> dict[str, object]:
    """One engine step trace row; only the diff-relevant fields matter."""
    return {"step_index": step_index, "name": f"step {step_index}", "output": output}


def _scenario(
    name: str, status: str, steps: list[dict[str, object]] | None = None
) -> dict[str, object]:
    """One engine scenario row (engine.py record shape)."""
    row: dict[str, object] = {"scenario": name, "status": status, "error_boundary": False}
    if status != "unconfigured":
        row["summary"] = {"total": len(steps or []), "passed": 0, "failed": 0}
        row["steps"] = steps or []
        row["cleanup"] = []
    else:
        row["steps"] = []
        row["cleanup"] = []
        row["reason"] = "missing env: TEST"
    return row


def _suite(*rows: dict[str, object]) -> dict[str, object]:
    """One engine suite record wrapping scenario rows."""
    return {"trace_id": "t", "generated_at": "2026-08-14T00:00:00+00:00", "scenarios": list(rows)}


def _seed_run(root: Path, name: str, record: dict[str, object]) -> None:
    """Write a run dir + scenarios.json as the engine would (no overwrite)."""
    run_dir = root / name
    run_dir.mkdir(parents=True)
    (run_dir / "scenarios.json").write_text(json.dumps(record), encoding="utf-8")


class TestDiffRunsBuckets:
    def test_new_pass_failed_to_passed(self) -> None:
        before = _suite(_scenario("meta", "failed"))
        after = _suite(_scenario("meta", "passed"))
        result = diff_runs(before, after)
        assert result["new_passes"] == ["meta"]
        assert result["new_failures"] == []
        assert result["regressed"] == []
        assert result["improved"] == []

    def test_new_pass_recovered_and_partial_pass_to_passed(self) -> None:
        before = _suite(_scenario("rec", "recovered"), _scenario("pp", "partial-pass"))
        after = _suite(_scenario("rec", "passed"), _scenario("pp", "passed"))
        result = diff_runs(before, after)
        assert result["new_passes"] == ["pp", "rec"]

    def test_new_failure_passed_to_failed(self) -> None:
        before = _suite(_scenario("journey", "passed"))
        after = _suite(_scenario("journey", "failed"))
        result = diff_runs(before, after)
        assert result["new_failures"] == ["journey"]

    def test_new_failure_passed_to_unconfigured(self) -> None:
        before = _suite(_scenario("journey", "passed"))
        after = _suite(_scenario("journey", "unconfigured"))
        result = diff_runs(before, after)
        assert result["new_failures"] == ["journey"]

    def test_regressed_persistent_failure_not_in_stable(self) -> None:
        before = _suite(_scenario("meta", "failed"))
        after = _suite(_scenario("meta", "failed"))
        result = diff_runs(before, after)
        assert result["regressed"] == ["meta"]
        assert result["stable"]["failed"] == 0

    def test_improved_unconfigured_to_passed(self) -> None:
        before = _suite(_scenario("journey", "unconfigured"))
        after = _suite(_scenario("journey", "passed"))
        result = diff_runs(before, after)
        assert result["improved"] == ["journey"]
        assert result["new_passes"] == []

    def test_stable_counts_each_unchanged_status(self) -> None:
        before = _suite(
            _scenario("a", "passed"),
            _scenario("b", "unconfigured"),
            _scenario("c", "recovered"),
            _scenario("d", "partial-pass"),
        )
        after = _suite(
            _scenario("a", "passed"),
            _scenario("b", "unconfigured"),
            _scenario("c", "recovered"),
            _scenario("d", "partial-pass"),
        )
        result = diff_runs(before, after)
        assert result["stable"] == {
            "passed": 1,
            "failed": 0,
            "unconfigured": 1,
            "recovered": 1,
            "partial-pass": 1,
        }

    def test_other_unclassified_transition_is_counted(self) -> None:
        # failed -> unconfigured is neither a pass, a new failure, nor a
        # persistent failure: it must land in "other", never be dropped.
        before = _suite(_scenario("meta", "failed"))
        after = _suite(_scenario("meta", "unconfigured"))
        result = diff_runs(before, after)
        assert result["summary"]["other"] == 1
        assert result["summary"]["total"] == 1

    def test_unpaired_scenario_counted_not_classified(self) -> None:
        before = _suite(_scenario("only-before", "passed"))
        after = _suite(_scenario("only-after", "passed"))
        result = diff_runs(before, after)
        assert result["summary"]["unpaired"] == 2
        assert result["summary"]["total"] == 0
        assert result["new_passes"] == []

    def test_summary_counts_reconcile_with_buckets(self) -> None:
        before = _suite(
            _scenario("new-pass", "failed"),
            _scenario("new-fail", "passed"),
            _scenario("regress", "failed"),
            _scenario("improve", "unconfigured"),
            _scenario("stable-a", "passed"),
            _scenario("other-x", "failed"),
        )
        after = _suite(
            _scenario("new-pass", "passed"),
            _scenario("new-fail", "unconfigured"),
            _scenario("regress", "failed"),
            _scenario("improve", "passed"),
            _scenario("stable-a", "passed"),
            _scenario("other-x", "unconfigured"),
        )
        result = diff_runs(before, after)
        summary = result["summary"]
        assert summary["new_passes"] == 1
        assert summary["new_failures"] == 1
        assert summary["regressed"] == 1
        assert summary["improved"] == 1
        assert summary["stable"] == 1
        assert summary["other"] == 1
        assert summary["total"] == 6
        assert summary["total"] == (
            summary["new_passes"]
            + summary["new_failures"]
            + summary["regressed"]
            + summary["improved"]
            + summary["stable"]
            + summary["other"]
        )

    def test_lists_are_sorted(self) -> None:
        before = _suite(
            _scenario("zeta", "failed"),
            _scenario("alpha", "failed"),
            _scenario("mid", "passed"),
        )
        after = _suite(
            _scenario("zeta", "passed"),
            _scenario("alpha", "passed"),
            _scenario("mid", "failed"),
        )
        result = diff_runs(before, after)
        assert result["new_passes"] == ["alpha", "zeta"]
        assert result["new_failures"] == ["mid"]

    def test_malformed_record_raises(self) -> None:
        with pytest.raises(DiffError, match="not an engine suite record"):
            diff_runs({"scenarios": "nope"}, _suite())
        with pytest.raises(DiffError, match="not an engine suite record"):
            diff_runs([], _suite())
        with pytest.raises(DiffError, match="malformed scenario row"):
            diff_runs(_suite({"scenario": 1}), _suite())


class TestQualityTrend:
    def test_quality_drop_flagged_with_before_after(self) -> None:
        before = _suite(
            _scenario(
                "quality-draft-eval", "passed", [_step(2, {"success": True, "quality_score": 0.8})]
            )
        )
        after = _suite(
            _scenario(
                "quality-draft-eval", "passed", [_step(2, {"success": True, "quality_score": 0.6})]
            )
        )
        result = diff_runs(before, after)
        assert result["quality_trend"]["dropped"] == [
            {
                "scenario": "quality-draft-eval",
                "step": 2,
                "key": "quality_score",
                "before": 0.8,
                "after": 0.6,
            }
        ]
        assert result["quality_trend"]["raised"] == []
        assert result["quality_trend"]["unchanged"] == 0
        assert result["summary"]["quality_compared"] == 1

    def test_quality_raised(self) -> None:
        before = _suite(_scenario("q", "passed", [_step(2, {"quality_score": 0.5})]))
        after = _suite(_scenario("q", "passed", [_step(2, {"quality_score": 0.9})]))
        result = diff_runs(before, after)
        assert result["quality_trend"]["raised"] == [
            {"scenario": "q", "step": 2, "key": "quality_score", "before": 0.5, "after": 0.9}
        ]
        assert result["quality_trend"]["dropped"] == []

    def test_quality_unchanged_count(self) -> None:
        before = _suite(
            _scenario(
                "q", "passed", [_step(1, {"quality_score": 0.5}), _step(2, {"quality_score": 0.7})]
            )
        )
        after = _suite(
            _scenario(
                "q", "passed", [_step(1, {"quality_score": 0.5}), _step(2, {"quality_score": 0.7})]
            )
        )
        result = diff_runs(before, after)
        assert result["quality_trend"]["unchanged"] == 2
        assert result["summary"]["quality_compared"] == 2

    def test_quality_missing_score_key_on_one_side_no_entry(self) -> None:
        before = _suite(_scenario("q", "passed", [_step(2, {"quality_score": 0.5})]))
        after = _suite(_scenario("q", "passed", [_step(2, {"success": True})]))
        result = diff_runs(before, after)
        assert result["quality_trend"]["dropped"] == []
        assert result["summary"]["quality_compared"] == 0

    def test_quality_non_dict_output_skipped(self) -> None:
        before = _suite(_scenario("q", "passed", [_step(2, "not-a-dict")]))
        after = _suite(_scenario("q", "passed", [_step(2, {"quality_score": 0.5})]))
        result = diff_runs(before, after)
        assert result["quality_trend"]["dropped"] == []

    def test_quality_step_matched_by_index(self) -> None:
        before = _suite(
            _scenario(
                "q", "passed", [_step(1, {"quality_score": 0.9}), _step(2, {"quality_score": 0.4})]
            )
        )
        after = _suite(
            _scenario(
                "q", "passed", [_step(1, {"quality_score": 0.5}), _step(2, {"quality_score": 0.4})]
            )
        )
        result = diff_runs(before, after)
        assert result["quality_trend"]["dropped"] == [
            {"scenario": "q", "step": 1, "key": "quality_score", "before": 0.9, "after": 0.5}
        ]
        assert result["quality_trend"]["unchanged"] == 1

    def test_quality_bool_and_unrelated_keys_excluded(self) -> None:
        before = _suite(
            _scenario(
                "q", "passed", [_step(2, {"score": True, "max_tokens": 100, "quality_score": 0.7})]
            )
        )
        after = _suite(
            _scenario(
                "q", "passed", [_step(2, {"score": False, "max_tokens": 200, "quality_score": 0.7})]
            )
        )
        result = diff_runs(before, after)
        # bool under "score" excluded; "max_tokens" has no "score"; the
        # real quality_score is unchanged.
        assert result["quality_trend"]["dropped"] == []
        assert result["quality_trend"]["unchanged"] == 1

    def test_quality_entries_sorted(self) -> None:
        before = _suite(
            _scenario(
                "b-q",
                "passed",
                [_step(1, {"quality_score": 0.9}), _step(2, {"quality_score": 0.9})],
            ),
            _scenario("a-q", "passed", [_step(1, {"quality_score": 0.9})]),
        )
        after = _suite(
            _scenario(
                "b-q",
                "passed",
                [_step(1, {"quality_score": 0.1}), _step(2, {"quality_score": 0.1})],
            ),
            _scenario("a-q", "passed", [_step(1, {"quality_score": 0.1})]),
        )
        result = diff_runs(before, after)
        entries = result["quality_trend"]["dropped"]
        assert [entry["scenario"] for entry in entries] == ["a-q", "b-q", "b-q"]
        assert [entry["step"] for entry in entries] == [1, 1, 2]


class TestDiffLatest:
    def test_baseline_path_diffs_latest_against_baseline(self, tmp_path: Path) -> None:
        baseline = _suite(_scenario("meta", "failed"), _scenario("journey", "unconfigured"))
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        runs = tmp_path / "runs"
        _seed_run(runs, "20260814-000000-000001", _suite(_scenario("meta", "passed")))
        result = diff_latest(runs, baseline_path=baseline_path)
        assert result is not None
        assert result["new_passes"] == ["meta"]
        assert result["summary"]["unpaired"] == 1  # journey not in the new run

    def test_baseline_path_requires_at_least_one_run(self, tmp_path: Path) -> None:
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps(_suite()), encoding="utf-8")
        with pytest.warns(UserWarning, match="no recorded runs"):
            assert diff_latest(tmp_path / "empty-runs", baseline_path=baseline_path) is None

    def test_two_runs_required_without_baseline(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        _seed_run(runs, "20260814-000000-000001", _suite())
        with pytest.warns(UserWarning, match="at least two recorded runs"):
            assert diff_latest(runs) is None
        with pytest.warns(UserWarning, match="at least two recorded runs"):
            assert diff_latest(tmp_path / "missing-runs") is None

    def test_diffs_second_newest_against_newest(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        _seed_run(runs, "20260814-000000-000001", _suite(_scenario("meta", "failed")))
        _seed_run(runs, "20260814-000000-000002", _suite(_scenario("meta", "passed")))
        result = diff_latest(runs)
        assert result is not None
        assert result["new_passes"] == ["meta"]

    def test_missing_baseline_file_raises(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        _seed_run(runs, "20260814-000000-000001", _suite())
        with pytest.raises(DiffError, match="run record not found"):
            diff_latest(runs, baseline_path=tmp_path / "nope.json")

    def test_malformed_run_record_raises(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        run_dir = runs / "20260814-000000-000001"
        run_dir.mkdir(parents=True)
        (run_dir / "scenarios.json").write_text("not json", encoding="utf-8")
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps(_suite()), encoding="utf-8")
        with pytest.raises(DiffError, match="not valid JSON"):
            diff_latest(runs, baseline_path=baseline_path)

    def test_baseline_record_must_be_suite_shaped(self, tmp_path: Path) -> None:
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps({"scenarios": []}), encoding="utf-8")
        runs = tmp_path / "runs"
        _seed_run(runs, "20260814-000000-000001", _suite(_scenario("a", "passed")))
        # {"scenarios": []} is a valid empty suite — diff succeeds with zero pairs.
        result = diff_latest(runs, baseline_path=baseline_path)
        assert result is not None
        assert result["summary"]["total"] == 0


def test_statuses_cover_engine_verdicts() -> None:
    """The stable dict keys are exactly the engine's five statuses."""
    assert STATUSES == ("passed", "failed", "unconfigured", "recovered", "partial-pass")
