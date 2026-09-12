"""Unit tests for the validation report renderer (W4-T3, component C5).

Synthetic engine-shaped suite records only (pinned W1-T7 shapes — scenario
``{scenario, status, summary, steps, cleanup, trace_id, error_boundary}``,
unconfigured ``{..., steps: [], reason, ...}``, step trace
``{step_index, target, surface, name, passed, status, failures, duration,
trace_id, check, standard, output}``, suite ``{trace_id, generated_at,
scenarios}``).  Covers: all eight report sections, verdicts-table alignment,
blockers naming expect key + observed value, regression failure resolution
(record keys AND the committed-library fallback), the step→check→standard
(cite)→result trace format, GREEN→artifact links (collect copies + file-kind
inspected paths + missing markers), the sign-off block incl. unsigned-run
listing, byte-identical determinism under record reordering, the JSON render,
and the ``render_report`` alias.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from automedia.validation.report import (
    render_report,
    render_report_json,
    render_report_text,
)

_STANDARDS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "synth"
    / "standards"
    / "standards_fixture.md"
)

TRACE_ID = "11111111-2222-3333-4444-555555555555"
GENERATED_AT = "2026-08-14T12:00:00+00:00"

REGRESSION_YAML = """\
name: regression-probe
description: pinned fix probe
intent: prove the report resolves regression flags from the committed library
regression: true
regression_issue: "#1234"
steps:
  - name: probe
    kind: cli
    check: command runs
    standard: founder-expectations.F01
    command: "python3 -c 'print(1)'"
    expect:
      success: true
"""


def step_trace(**overrides: object) -> dict:
    """A step trace matching the pinned engine shape, overridable per test."""
    base: dict = {
        "step_index": 1,
        "target": "health_check",
        "surface": "tool",
        "name": "call health_check",
        "arguments": {},
        "passed": True,
        "status": "passed",
        "failures": [],
        "duration": 0.04,
        "trace_id": TRACE_ID,
        "check": "server responds",
        "standard": "tool.contract",
        "output": {"success": True},
    }
    base.update(overrides)
    return base


def scenario_record(name: str, status: str, steps: list[dict], **overrides: object) -> dict:
    """A scenario record matching the pinned engine shape."""
    base: dict = {
        "scenario": name,
        "status": status,
        "summary": {
            "total": len(steps),
            "passed": sum(1 for s in steps if s["status"] == "passed"),
            "failed": sum(1 for s in steps if s["status"] == "failed"),
            "recovered": sum(1 for s in steps if s["status"] == "recovered"),
            "artifacts_missing": [],
        },
        "steps": steps,
        "cleanup": [],
        "trace_id": TRACE_ID,
        "error_boundary": False,
    }
    base.update(overrides)
    return base


def unconfigured_record(name: str, reason: str = "missing env: AUTOMEDIA_LLM_API_KEY") -> dict:
    """An unconfigured record with the pinned shape (steps always [])."""
    return {
        "scenario": name,
        "status": "unconfigured",
        "steps": [],
        "cleanup": [],
        "trace_id": TRACE_ID,
        "reason": reason,
        "error_boundary": False,
    }


def suite_record(scenarios: list[dict]) -> dict:
    """A suite record in the pinned engine shape."""
    return {"trace_id": TRACE_ID, "generated_at": GENERATED_AT, "scenarios": scenarios}


@pytest.fixture
def no_library(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the loader at a missing library: regression flags resolve to none.

    ``load_scenarios`` raises LoadError for an absent STANDARDS.md handbook
    (resolved BEFORE the missing-dir early return), which the report degrades
    to "no flags" — the record is the source of truth.
    """
    monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", "/nonexistent-report-test-scenarios")


def mixed_suite() -> dict:
    """A suite exercising every engine status: passed, failed, unconfigured,
    partial-pass, recovered, and a boundary-only probe."""
    return suite_record(
        [
            scenario_record(
                "scenario-recovered",
                "recovered",
                [
                    step_trace(
                        step_index=1,
                        status="recovered",
                        passed=True,
                        failures=["expect.success: expected True, observed False"],
                        name="recoverable call",
                        duration=0.11,
                    )
                ],
                summary={
                    "total": 1,
                    "passed": 0,
                    "failed": 0,
                    "recovered": 1,
                    "artifacts_missing": [],
                },
            ),
            scenario_record(
                "scenario-failed",
                "failed",
                [
                    step_trace(
                        status="failed",
                        passed=False,
                        failures=["expect.success: expected True, observed False"],
                        name="failing call",
                        target="broken_tool",
                        duration=0.21,
                    )
                ],
            ),
            scenario_record(
                "scenario-passed",
                "passed",
                [step_trace(target="health_check", name="health check", duration=0.04)],
            ),
            scenario_record(
                "scenario-partial",
                "partial-pass",
                [
                    step_trace(target="ok_tool", name="ok call", duration=0.03),
                    step_trace(
                        step_index=2,
                        target="bad_tool",
                        name="bad call",
                        status="failed",
                        passed=False,
                        failures=["expect.success: expected True, observed False"],
                        duration=0.17,
                    ),
                ],
                summary={
                    "total": 2,
                    "passed": 1,
                    "failed": 1,
                    "recovered": 0,
                    "artifacts_missing": [],
                },
            ),
            unconfigured_record("scenario-unconf"),
            scenario_record(
                "scenario-boundary",
                "passed",
                [step_trace(status="passed", note="error_boundary: true", duration=0.02)],
                error_boundary=True,
            ),
        ]
    )


class TestHeaderAndSummary:
    def test_header_names_trace_and_generated_at(self, no_library: None) -> None:
        text = render_report(suite_record([]))
        assert f"Validation report — trace {TRACE_ID}" in text
        assert f"generated at {GENERATED_AT}" in text

    def test_exec_summary_counts_all_six_statuses_and_boundary(self, no_library: None) -> None:
        text = render_report(mixed_suite())
        assert (
            "total: 6 | passed: 2 | failed: 1 | unconfigured: 1 | partial-pass: 1 | "
            "recovered: 1" in text
        )
        assert "boundary-only: 1 | regression failed: 0" in text

    def test_empty_suite_renders_zero_counts(self, no_library: None) -> None:
        text = render_report(suite_record([]))
        assert (
            "total: 0 | passed: 0 | failed: 0 | unconfigured: 0 | "
            "partial-pass: 0 | recovered: 0" in text
        )
        assert "boundary-only: 0 | regression failed: 0" in text
        assert "(no artifacts collected)" in text

    def test_sections_render_in_pinned_order(self, no_library: None) -> None:
        text = render_report(mixed_suite())
        heads = [line for line in text.splitlines() if line.startswith("## ")]
        assert heads == [
            "## Exec summary",
            "## Verdicts",
            "## Hard Safety",
            "## Blockers",
            "## Regression failures",
            "## Per-step traces",
            "## Artifacts",
            "## Sign-off",
        ]


class TestVerdictsTable:
    def test_aligned_columns_with_plain_markers(self, no_library: None) -> None:
        text = render_report(
            suite_record(
                [
                    scenario_record("cc", "unconfigured", [], reason="missing env: X"),
                    scenario_record(
                        "bbbbbb", "failed", [step_trace(status="failed", passed=False)]
                    ),
                    scenario_record("aa", "passed", [step_trace()]),
                ]
            )
        )
        expected = "\n".join(
            [
                "SCENARIO | STATUS | SUMMARY",
                "---------+--------+--------",
                "aa       | PASS   | 1/1 steps passed",
                "bbbbbb   | FAIL   | 0/1 steps passed, 1 failed",
                "cc       | UNCONF | missing env: X",
            ]
        )
        assert expected in text
        assert "PASS" in text and "FAIL" in text and "UNCONF" in text

    def test_recovered_and_partial_markers(self, no_library: None) -> None:
        text = render_report(mixed_suite())
        assert "RECOV" in text and "PARTIAL" in text


class TestBlockers:
    def test_blocker_names_scenario_step_and_expect_key(self, no_library: None) -> None:
        text = render_report(mixed_suite())
        assert (
            "- scenario-failed step 1 (failing call): "
            "expect.success: expected True, observed False" in text
        )

    def test_blockers_absent_when_nothing_failed(self, no_library: None) -> None:
        text = render_report(suite_record([scenario_record("ok", "passed", [step_trace()])]))
        assert "## Blockers\nnone" in text

    def test_adapter_error_step_names_output_error(self, no_library: None) -> None:
        """A step that failed with no expect failure names output.error (engine puts
        adapter errors there, never in failures)."""
        record = suite_record(
            [
                scenario_record(
                    "no-server",
                    "failed",
                    [
                        step_trace(
                            status="failed",
                            passed=False,
                            failures=[],
                            output={
                                "success": False,
                                "error": "no MCP server instance (server=None)",
                            },
                        )
                    ],
                )
            ]
        )
        text = render_report(record)
        assert "adapter error: no MCP server instance (server=None)" in text


class TestRegressionFailures:
    def test_record_flagged_regression_listed_with_issue(self, no_library: None) -> None:
        record = suite_record(
            [
                scenario_record(
                    "pinned-bug",
                    "failed",
                    [step_trace(status="failed", passed=False)],
                    regression=True,
                    regression_issue="#42",
                )
            ]
        )
        text = render_report(record)
        assert "## Regression failures\n- pinned-bug: #42" in text
        assert "regression failed: 1" in text
        assert "regression: #42" in text  # verdicts table row tagged

    def test_regression_failures_none_when_none_flagged(self, no_library: None) -> None:
        text = render_report(mixed_suite())
        assert "## Regression failures\nnone" in text

    def test_flags_fall_back_to_committed_library(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Engine records carry no regression key — the report reads the library."""
        root = tmp_path / "scenarios"
        root.mkdir()
        shutil.copy2(_STANDARDS_FIXTURE, root / "STANDARDS.md")
        (root / "regression.yaml").write_text(REGRESSION_YAML, encoding="utf-8")
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(root))
        record = suite_record(
            [
                scenario_record(
                    "regression-probe",
                    "failed",
                    [step_trace(status="failed", passed=False)],
                )
            ]
        )
        text = render_report(record)
        assert "## Regression failures\n- regression-probe: #1234" in text

    def test_record_key_wins_over_library(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = tmp_path / "scenarios"
        root.mkdir()
        shutil.copy2(_STANDARDS_FIXTURE, root / "STANDARDS.md")
        (root / "regression.yaml").write_text(REGRESSION_YAML, encoding="utf-8")
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(root))
        record = suite_record(
            [
                scenario_record(
                    "regression-probe",
                    "failed",
                    [step_trace(status="failed", passed=False)],
                    regression=False,
                )
            ]
        )
        text = render_report(record)
        assert "## Regression failures\nnone" in text


class TestPerStepTraces:
    def test_trace_line_is_step_check_standard_result(self, no_library: None) -> None:
        text = render_report(suite_record([scenario_record("ok", "passed", [step_trace()])]))
        assert (
            "### ok\n"
            "1. health_check → server responds → tool.contract (STANDARDS.md) "
            "→ passed (0.04s)" in text
        )

    def test_failed_step_appends_failure_lines(self, no_library: None) -> None:
        text = render_report(mixed_suite())
        assert (
            "1. broken_tool → server responds → tool.contract (STANDARDS.md) → failed (0.21s)\n"
            "  expect.success: expected True, observed False" in text
        )

    def test_recovered_step_keeps_primary_failure(self, no_library: None) -> None:
        """RED is never erased: a recovered step still shows its failure in the trace."""
        text = render_report(mixed_suite())
        assert (
            "1. health_check → server responds → tool.contract (STANDARDS.md) → recovered (0.11s)\n"
            "  expect.success: expected True, observed False" in text
        )

    def test_unconfigured_scenario_shows_reason(self, no_library: None) -> None:
        text = render_report(mixed_suite())
        assert "### scenario-unconf\nunconfigured: missing env: AUTOMEDIA_LLM_API_KEY" in text


class TestArtifacts:
    def test_collect_entries_print_copied_to_and_missing(self, no_library: None) -> None:
        record = suite_record(
            [
                scenario_record(
                    "with-artifacts",
                    "passed",
                    [
                        step_trace(
                            name="collect outputs",
                            artifacts=[
                                {
                                    "path": "out.json",
                                    "copied_to": "/runs/x/artifacts/1-out.json",
                                    "ok": True,
                                    "required": True,
                                    "reason": None,
                                },
                                {
                                    "path": "gone.json",
                                    "copied_to": None,
                                    "ok": False,
                                    "required": True,
                                    "reason": "missing",
                                },
                            ],
                        )
                    ],
                )
            ]
        )
        text = render_report(record)
        assert (
            "- with-artifacts step 1 (collect outputs): "
            "artifact: /runs/x/artifacts/1-out.json" in text
        )
        assert "- with-artifacts step 1 (collect outputs): artifact: gone.json (missing)" in text

    def test_file_kind_step_names_inspected_path(self, no_library: None) -> None:
        """Every GREEN names an artifact (§4.7): a file-kind step without collection
        shows the path it inspected (trace target = command)."""
        record = suite_record(
            [
                scenario_record(
                    "file-check",
                    "passed",
                    [
                        step_trace(
                            surface="file",
                            target="pyproject.toml",
                            name="manifest exists",
                        )
                    ],
                )
            ]
        )
        text = render_report(record)
        assert "- file-check step 1 (manifest exists): artifact: pyproject.toml" in text

    def test_no_artifacts_section_message(self, no_library: None) -> None:
        text = render_report(mixed_suite())
        assert "## Artifacts\n(no artifacts collected)" in text

    def test_file_kind_step_with_collection_prints_no_duplicate_path(
        self, no_library: None
    ) -> None:
        """A file-kind step that collected its artifact shows the copy only."""
        record = suite_record(
            [
                scenario_record(
                    "file-check",
                    "passed",
                    [
                        step_trace(
                            surface="file",
                            target="pyproject.toml",
                            name="manifest exists",
                            artifacts=[
                                {
                                    "path": "pyproject.toml",
                                    "copied_to": "/runs/x/artifacts/1-pyproject.toml",
                                    "ok": True,
                                    "required": True,
                                    "reason": None,
                                }
                            ],
                        )
                    ],
                )
            ]
        )
        text = render_report(record)
        assert "artifact: /runs/x/artifacts/1-pyproject.toml" in text
        assert text.count("artifact:") == 1

    def test_scenario_without_steps_shows_no_steps(self, no_library: None) -> None:
        text = render_report(suite_record([scenario_record("empty", "passed", [])]))
        assert "### empty\n(no steps)" in text

    def test_verdict_summary_counts_missing_required_artifacts(self, no_library: None) -> None:
        record = suite_record(
            [
                scenario_record(
                    "missing-art",
                    "passed",
                    [step_trace()],
                    summary={
                        "total": 1,
                        "passed": 1,
                        "failed": 0,
                        "recovered": 0,
                        "artifacts_missing": ["step 1 (x): required artifact 'gone' missing"],
                    },
                )
            ]
        )
        text = render_report(record)
        assert "missing-art | PASS   | 1/1 steps passed; 1 required artifact(s) missing" in text


class TestSignoff:
    def test_unsigned_runs_listed_when_root_provided(
        self, tmp_path: Path, no_library: None
    ) -> None:
        (tmp_path / "run-a" / "scenarios.json").parent.mkdir()
        (tmp_path / "run-a" / "scenarios.json").write_text("{}", encoding="utf-8")
        (tmp_path / "run-b" / "scenarios.json").parent.mkdir()
        (tmp_path / "run-b" / "scenarios.json").write_text("{}", encoding="utf-8")
        (tmp_path / "run-b" / "signed.txt").write_text("signed\n", encoding="utf-8")
        text = render_report(suite_record([]), runs_root=tmp_path)
        assert "Unsigned runs:\n- run-a" in text
        assert "run-b" not in text.split("Unsigned runs:")[1]

    def test_all_signed_when_every_run_signed(self, tmp_path: Path, no_library: None) -> None:
        (tmp_path / "run-a" / "signed.txt").parent.mkdir()
        (tmp_path / "run-a" / "scenarios.json").write_text("{}", encoding="utf-8")
        (tmp_path / "run-a" / "signed.txt").write_text("ok", encoding="utf-8")
        text = render_report(suite_record([]), runs_root=tmp_path)
        assert "Unsigned runs: none (all signed)" in text

    def test_listing_omitted_without_runs_root(self, no_library: None) -> None:
        text = render_report(suite_record([]))
        assert "Unsigned runs" not in text
        assert "## Sign-off" in text
        assert "signed.txt" in text and "W4-T5" in text

    def test_empty_signed_txt_is_unsigned(self, tmp_path: Path, no_library: None) -> None:
        """Report and signoff.is_signed agree: an empty signed.txt is unsigned."""
        from automedia.validation.signoff import is_signed

        run_dir = tmp_path / "run-a"
        run_dir.mkdir()
        (run_dir / "scenarios.json").write_text("{}", encoding="utf-8")
        (run_dir / "signed.txt").write_text("", encoding="utf-8")
        text = render_report(suite_record([]), runs_root=tmp_path)
        assert "Unsigned runs:\n- run-a" in text
        assert is_signed(tmp_path, "run-a") is False

    def test_whitespace_signed_txt_is_unsigned(self, tmp_path: Path, no_library: None) -> None:
        run_dir = tmp_path / "run-a"
        run_dir.mkdir()
        (run_dir / "scenarios.json").write_text("{}", encoding="utf-8")
        (run_dir / "signed.txt").write_text(" \n ", encoding="utf-8")
        text = render_report(suite_record([]), runs_root=tmp_path)
        assert "Unsigned runs:\n- run-a" in text


class TestDeterminism:
    def test_byte_identical_under_scenario_reordering(self, no_library: None) -> None:
        first = mixed_suite()
        second = suite_record(list(reversed(first["scenarios"])))
        assert render_report(first) == render_report(second)

    def test_repeated_render_is_stable(self, no_library: None) -> None:
        text = render_report(mixed_suite())
        assert text == render_report(mixed_suite())

    def test_json_stable_under_reordering(self, no_library: None) -> None:
        first = mixed_suite()
        second = suite_record(list(reversed(first["scenarios"])))
        assert json.dumps(render_report_json(first)) == json.dumps(render_report_json(second))


class TestJsonRender:
    def test_shape_and_counts(self, no_library: None) -> None:
        data = render_report_json(mixed_suite())
        assert set(data) == {
            "trace_id",
            "generated_at",
            "summary",
            "hard_safety",
            "verdicts",
            "blockers",
            "regression_failures",
            "traces",
            "artifacts",
        }
        assert data["trace_id"] == TRACE_ID
        assert data["generated_at"] == GENERATED_AT
        assert data["summary"]["total"] == 6
        assert data["summary"]["boundary_only"] == 1
        assert data["summary"]["regression_failed"] == 0

    def test_verdicts_sorted_with_markers_and_flags(self, no_library: None) -> None:
        data = render_report_json(mixed_suite())
        names = [v["scenario"] for v in data["verdicts"]]
        assert names == sorted(names)
        by_name = {v["scenario"]: v for v in data["verdicts"]}
        assert by_name["scenario-passed"]["marker"] == "PASS"
        assert by_name["scenario-failed"]["marker"] == "FAIL"
        assert by_name["scenario-unconf"]["marker"] == "UNCONF"
        assert by_name["scenario-partial"]["marker"] == "PARTIAL"
        assert by_name["scenario-recovered"]["marker"] == "RECOV"
        assert by_name["scenario-boundary"]["error_boundary"] is True

    def test_blockers_and_traces_structured(self, no_library: None) -> None:
        data = render_report_json(mixed_suite())
        (blocker,) = [b for b in data["blockers"] if b["scenario"] == "scenario-failed"]
        assert blocker["step_index"] == 1
        assert blocker["step"] == "failing call"
        assert blocker["failure"] == "expect.success: expected True, observed False"
        trace = data["traces"]["scenario-failed"][0]
        assert trace["check"] == "server responds"
        assert trace["standard"] == "tool.contract"
        assert trace["duration"] == 0.21

    def test_unconfigured_trace_is_empty(self, no_library: None) -> None:
        data = render_report_json(mixed_suite())
        assert data["traces"]["scenario-unconf"] == []


class TestHardSafety:
    def test_hard_safety_section_blocked_banner(self, no_library: None) -> None:
        record = suite_record(
            [
                scenario_record(
                    "volatile",
                    "failed",
                    [step_trace(status="failed", passed=False)],
                    hard_safety_violation=True,
                )
            ]
        )
        record["blocked"] = True
        text = render_report(record)
        assert "## Hard Safety" in text
        assert "BLOCKED — hard-safety violation(s) present" in text
        assert "- volatile" in text

    def test_hard_safety_section_none_when_no_violations(self, no_library: None) -> None:
        text = render_report(mixed_suite())
        assert "## Hard Safety\nnone" in text

    def test_verdicts_show_hard_flag(self, no_library: None) -> None:
        record = suite_record(
            [scenario_record("volatile", "passed", [step_trace()], hard_safety_violation=True)]
        )
        text = render_report(record)
        assert "volatile | PASS   | 1/1 steps passed; HARD" in text

    def test_report_json_carries_hard_safety(self, no_library: None) -> None:
        record = suite_record(
            [
                scenario_record(
                    "volatile",
                    "failed",
                    [step_trace(status="failed", passed=False)],
                    hard_safety_violation=True,
                ),
                scenario_record("clean", "passed", [step_trace()]),
            ]
        )
        record["blocked"] = True
        data = render_report_json(record)
        assert data["hard_safety"] == {"violations": ["volatile"], "blocked": True}

    def test_report_json_hard_safety_not_blocked_without_blocked_key(
        self, no_library: None
    ) -> None:
        """The suite record lacks the ``blocked`` key — the renderer must still derive
        blocked from the violation list."""
        record = suite_record(
            [
                scenario_record(
                    "volatile",
                    "failed",
                    [step_trace(status="failed", passed=False)],
                    hard_safety_violation=True,
                )
            ]
        )
        data = render_report_json(record)
        assert data["hard_safety"] == {"violations": ["volatile"], "blocked": True}

    def test_hard_safety_independent_of_partial_pass(self, no_library: None) -> None:
        """A partial-pass scenario with the engine's hard flag set is still a
        violation — the report reads the flag, not the status."""
        record = suite_record(
            [
                scenario_record(
                    "dangerous-partial",
                    "partial-pass",
                    [step_trace(status="passed")],
                    hard_safety_violation=True,
                )
            ]
        )
        text = render_report(record)
        hard_block = "## Hard Safety\nBLOCKED — hard-safety violation(s) present\n"
        assert f"{hard_block}- dangerous-partial" in text
        assert "dangerous-partial | PARTIAL | 1/1 steps passed; HARD" in text
        data = render_report_json(record)
        assert data["hard_safety"] == {"violations": ["dangerous-partial"], "blocked": True}

    def test_unconfigured_hard_is_violation(self, no_library: None) -> None:
        record = suite_record(
            [
                scenario_record(
                    "u", "unconfigured", [], reason="missing env: X", hard_safety_violation=True
                )
            ]
        )
        text = render_report(record)
        assert "## Hard Safety\nBLOCKED — hard-safety violation(s) present\n- u" in text
        data = render_report_json(record)
        assert data["hard_safety"] == {"violations": ["u"], "blocked": True}

    def test_violations_sorted_by_name(self, no_library: None) -> None:
        record = suite_record(
            [
                scenario_record("zeta", "passed", [step_trace()], hard_safety_violation=True),
                scenario_record("alpha", "passed", [step_trace()], hard_safety_violation=True),
            ]
        )
        text = render_report(record)
        assert text.index("- alpha") < text.index("- zeta")
        data = render_report_json(record)
        assert data["hard_safety"]["violations"] == ["alpha", "zeta"]


class TestPublicSurface:
    def test_render_report_aliases_text(self, no_library: None) -> None:
        assert render_report(mixed_suite()) == render_report_text(mixed_suite())

    def test_malformed_scenarios_key_degrades_to_empty(self, no_library: None) -> None:
        text = render_report({"trace_id": "t", "generated_at": "g", "scenarios": "nope"})
        assert "total: 0" in text
        data = render_report_json({"trace_id": "t", "generated_at": "g", "scenarios": None})
        assert data["summary"]["total"] == 0
