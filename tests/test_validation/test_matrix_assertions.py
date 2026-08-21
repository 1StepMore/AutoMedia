"""Unit tests for the run-record assertion matrix (issue #86 review gap).

Covers the AutoInfo-style artifact-assertion matrix: report cards (per
scenario digest), per-step assertion rows with exit_code and hard-safety
cells, and the diff four-way classification.  Synthetic engine-shaped suite
records only — never the real library or a real run record.
"""

from __future__ import annotations

from typing import Any

from automedia.validation.matrix_assertions import (
    build_assertion_matrix,
    scenario_report_cards,
)

TRACE = "11111111-2222-3333-4444-555555555555"


def _step(**overrides: Any) -> dict[str, Any]:
    """A step trace in the pinned engine shape, overridable per test."""
    base: dict[str, Any] = {
        "step_index": 1,
        "target": "health_check",
        "surface": "tool",
        "name": "call health_check",
        "passed": True,
        "status": "passed",
        "failures": [],
        "duration": 0.04,
        "trace_id": TRACE,
        "check": "server responds",
        "standard": "tool.contract",
        "output": {"success": True},
    }
    base.update(overrides)
    return base


def _cli_step(**overrides: Any) -> dict[str, Any]:
    """A cli-kind step with an exit_code in its output envelope."""
    base: dict[str, Any] = {
        "step_index": 2,
        "target": "automedia doctor",
        "surface": "cli",
        "name": "run doctor",
        "passed": True,
        "status": "passed",
        "failures": [],
        "duration": 0.1,
        "trace_id": TRACE,
        "check": "doctor lists deps",
        "standard": "cli.doctor",
        "output": {"success": True, "exit_code": 0},
    }
    base.update(overrides)
    return base


def _scenario_row(name: str, status: str, steps: list[dict], **overrides: Any) -> dict[str, Any]:
    """A scenario row in the pinned engine shape."""
    base: dict[str, Any] = {
        "scenario": name,
        "status": status,
        "summary": {"total": len(steps), "passed": 0, "failed": 0, "recovered": 0},
        "steps": steps,
        "cleanup": [],
        "trace_id": TRACE,
        "error_boundary": False,
        "hard": False,
        "hard_safety_violation": False,
    }
    base.update(overrides)
    return base


def _suite(rows: list[dict]) -> dict[str, Any]:
    """A suite record in the pinned engine shape."""
    return {"trace_id": TRACE, "generated_at": "2026-08-14T00:00:00+00:00", "scenarios": rows}


class TestReportCards:
    """The director-readable digest per scenario in the latest run."""

    def test_no_latest_record_yields_empty_cards_and_none_diff(self) -> None:
        cards, diff = scenario_report_cards(None, None)
        assert cards == []
        assert diff is None

    def test_card_carries_status_assertion_counts_and_diff_bucket(self) -> None:
        latest = _suite(
            [
                _scenario_row(
                    "alpha",
                    "passed",
                    [_step(), _cli_step()],
                )
            ]
        )
        cards, diff = scenario_report_cards(latest, None)
        assert diff is None  # no baseline -> no four-way classification
        (card,) = cards
        assert card["scenario"] == "alpha"
        assert card["status"] == "passed"
        assert card["assertions"] == {"total": 2, "passed": 2, "failed": 0, "recovered": 0}

    def test_card_exit_codes_map_step_index_to_output(self) -> None:
        latest = _suite([_scenario_row("alpha", "passed", [_step(), _cli_step()])])
        (card,) = scenario_report_cards(latest, None)[0]
        assert card["exit_codes"] == {2: 0}  # only the cli step carries exit_code

    def test_card_failures_first_per_step_only(self) -> None:
        latest = _suite(
            [
                _scenario_row(
                    "alpha",
                    "failed",
                    [_step(status="failed", passed=False, failures=["expect.success: no"])],
                )
            ]
        )
        (card,) = scenario_report_cards(latest, None)[0]
        assert card["failures"] == [
            "step 1 (call health_check): expect.success: no"
        ]

    def test_hard_failed_scenario_flags_violation_on_card(self) -> None:
        latest = _suite(
            [
                _scenario_row(
                    "risky",
                    "failed",
                    [_step(status="failed", passed=False, failures=["expect.success: no"])],
                    hard=True,
                    hard_safety_violation=True,
                )
            ]
        )
        (card,) = scenario_report_cards(latest, None)[0]
        assert card["hard"] is True
        assert card["hard_safety_violation"] is True


class TestDiffClassification:
    """The four-way classification against a baseline (review deliverable)."""

    def _records(self) -> tuple[dict, dict]:
        # Same scenario names across records: diff_runs classifies status
        # transitions per name (the honest four-way comparison).
        baseline = _suite(
            [
                _scenario_row("regressed-s", "failed", [_step(status="failed", passed=False)]),
                _scenario_row("newfail-s", "passed", [_step()]),
                _scenario_row("improved-s", "unconfigured", []),
                _scenario_row("stable-s", "passed", [_step()]),
            ]
        )
        latest = _suite(
            [
                _scenario_row("regressed-s", "failed", [_step(status="failed", passed=False)]),
                _scenario_row("newfail-s", "failed", [_step(status="failed", passed=False)]),
                _scenario_row("improved-s", "passed", [_step()]),
                _scenario_row("stable-s", "passed", [_step()]),
                _scenario_row("d-new", "passed", [_step()]),  # latest-only -> new
            ]
        )
        return baseline, latest

    def test_diff_buckets_map_to_card_labels(self) -> None:
        baseline, latest = self._records()
        cards, diff = scenario_report_cards(latest, baseline)
        assert diff is not None
        by_name = {c["scenario"]: c for c in cards}
        assert by_name["newfail-s"]["diff"] == "new-failure"
        assert by_name["regressed-s"]["diff"] == "regressed"
        assert by_name["improved-s"]["diff"] == "improved"
        assert by_name["stable-s"]["diff"] == "stable"
        assert by_name["d-new"]["diff"] == "new"


class TestAssertionRows:
    """The per-step truth table with exit_code / hard_safety / artifacts."""

    def test_step_row_carries_check_standard_exit_code(self) -> None:
        latest = _suite([_scenario_row("alpha", "passed", [_step(), _cli_step()])])
        matrix = build_assertion_matrix(latest, None)
        rows = matrix["assertions"]["alpha"]
        tool_row = next(r for r in rows if r["surface"] == "tool")
        cli_row = next(r for r in rows if r["surface"] == "cli")
        assert tool_row["check"] == "server responds"
        assert tool_row["standard"] == "tool.contract"
        assert tool_row["exit_code"] is None  # tool envelope has no exit_code
        assert cli_row["exit_code"] == 0

    def test_hard_safety_cell_true_when_hard_step_failed(self) -> None:
        latest = _suite(
            [
                _scenario_row(
                    "risky",
                    "failed",
                    [_step(status="failed", passed=False, failures=["expect.success: no"])],
                    hard=True,
                )
            ]
        )
        matrix = build_assertion_matrix(latest, None)
        (row,) = matrix["assertions"]["risky"]
        assert row["hard_safety"] is True

    def test_hard_safety_cell_false_for_passed_hard_step(self) -> None:
        latest = _suite(
            [_scenario_row("risky", "passed", [_step()], hard=True, hard_safety_violation=False)]
        )
        matrix = build_assertion_matrix(latest, None)
        (row,) = matrix["assertions"]["risky"]
        assert row["hard_safety"] is False

    def test_recovered_step_keeps_failures_and_status(self) -> None:
        latest = _suite(
            [
                _scenario_row(
                    "recovered-one",
                    "recovered",
                    [_step(status="recovered", passed=True, failures=["expect.success: no"])],
                )
            ]
        )
        matrix = build_assertion_matrix(latest, None)
        (row,) = matrix["assertions"]["recovered-one"]
        assert row["status"] == "recovered"
        assert row["failures"] == ["expect.success: no"]  # RED never erased

    def test_artifact_paths_collected(self) -> None:
        latest = _suite(
            [
                _scenario_row(
                    "alpha",
                    "passed",
                    [
                        _step(
                            artifacts=[
                                {"path": "draft.md", "copied_to": "artifacts/1-draft.md", "ok": True}
                            ]
                        )
                    ],
                )
            ]
        )
        matrix = build_assertion_matrix(latest, None)
        (row,) = matrix["assertions"]["alpha"]
        assert row["artifacts"] == ["artifacts/1-draft.md"]

    def test_unconfigured_scenario_has_no_assertion_rows(self) -> None:
        latest = _suite([_scenario_row("env-gated", "unconfigured", [])])
        matrix = build_assertion_matrix(latest, None)
        assert matrix["assertions"]["env-gated"] == []
        (card,) = matrix["report_cards"]
        assert card["status"] == "unconfigured"
        assert card["assertions"] == {"total": 0, "passed": 0, "failed": 0, "recovered": 0}
