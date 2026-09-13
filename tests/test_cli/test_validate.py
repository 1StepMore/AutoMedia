"""Tests for ``automedia validate`` — the agent-tester validation CLI family (W4-T1).

CLI surface tests live here in ``tests/test_cli/`` (repo convention: command
modules under ``automedia/cli/commands/`` get their surface tests in
``tests/test_cli/``); the engine-surface tests live in
``tests/test_validation/``.  All scenarios used here are synthetic (Red Line
4) — written into ``tmp_path`` with the synth STANDARDS.md fixture — and the
``AUTOMEDIA_VALIDATION_SCENARIOS_DIR`` env override points the CLI at them.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.validation.persist import list_runs, persist_run, write_latest_pointer

runner = CliRunner()

STANDARDS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "synth"
    / "standards"
    / "standards_fixture.md"
)

_SCENARIOS: dict[str, str] = {
    "synth-passing.yaml": """\
name: synth-passing
description: A passing synthetic scenario.
intent: Unit-test the validate run command happy path.
user_level: L0
category: baseline
requires_env: []
steps:
  - name: echo prints ok
    kind: cli
    check: echo prints the word ok
    standard: founder-expectations.F02
    command: echo ok
    timeout_seconds: 30
    expect:
      exit_code: 0
      stdout_has: ["ok"]
""",
    "synth-failing.yaml": """\
name: synth-failing
description: A failing synthetic scenario.
intent: Unit-test the validate run command failure exit code.
user_level: L0
category: baseline
requires_env: []
steps:
  - name: false should succeed
    kind: cli
    check: false exits 0
    standard: founder-expectations.F02
    command: "false"
    timeout_seconds: 30
    expect:
      exit_code: 0
""",
    "synth-env-gated.yaml": """\
name: synth-env-gated
description: An env-gated synthetic scenario.
intent: Unit-test the unconfigured path and --env-gate skip.
user_level: L0
category: baseline
requires_env: ["SYNTH_REQUIRED_ENV"]
steps:
  - name: echo prints ok
    kind: cli
    check: echo prints the word ok
    standard: founder-expectations.F02
    command: echo ok
    timeout_seconds: 30
    expect:
      exit_code: 0
      stdout_has: ["ok"]
""",
    "synth-tool.yaml": """\
name: synth-tool-health
description: A tool-kind synthetic scenario against the real server.
intent: Unit-test that validate run wires the real MCP server (create_server).
user_level: L0
category: baseline
requires_env: []
steps:
  - name: health check answers
    kind: tool
    check: health_check returns a success envelope
    standard: founder-expectations.F02
    tool: health_check
    arguments: {}
    timeout_seconds: 30
    expect:
      success: true
""",
    "synth-hard-failing.yaml": """\
name: synth-hard-failing
description: A hard synthetic scenario that fails.
intent: Unit-test that hard-safety violations exit 1 on validate run.
user_level: L0
category: baseline
requires_env: []
hard: true
steps:
  - name: false should succeed
    kind: cli
    check: false exits 0
    standard: founder-expectations.F02
    command: "false"
    timeout_seconds: 30
    expect:
      exit_code: 0
""",
    "synth-hard-passing.yaml": """\
name: synth-hard-passing
description: A hard synthetic scenario that passes.
intent: Unit-test that a hard scenario which passes still exits 0.
user_level: L0
category: baseline
requires_env: []
hard: true
steps:
  - name: echo prints ok
    kind: cli
    check: echo prints the word ok
    standard: founder-expectations.F02
    command: echo ok
    timeout_seconds: 30
    expect:
      exit_code: 0
      stdout_has: ["ok"]
""",
    "synth-hard-env-gated.yaml": """\
name: synth-hard-env-gated
description: A hard env-gated synthetic scenario (unconfigured is a violation).
intent: Unit-test that a hard unconfigured scenario exits 1 with the marker.
user_level: L0
category: baseline
requires_env: ["SYNTH_REQUIRED_ENV"]
hard: true
steps:
  - name: echo prints ok
    kind: cli
    check: echo prints the word ok
    standard: founder-expectations.F02
    command: echo ok
    timeout_seconds: 30
    expect:
      exit_code: 0
      stdout_has: ["ok"]
""",
}


@pytest.fixture()
def scenarios_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A synthetic scenario library (STANDARDS.md + 4 scenarios), wired via
    the ``AUTOMEDIA_VALIDATION_SCENARIOS_DIR`` env override."""
    library = tmp_path / "scenarios"
    library.mkdir()
    shutil.copy(STANDARDS_FIXTURE, library / "STANDARDS.md")
    for filename, content in _SCENARIOS.items():
        (library / filename).write_text(content, encoding="utf-8")
    monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(library))
    return library


def _make_run_record(status: str = "passed") -> dict[str, object]:
    """A minimal synthetic suite-shaped run record for report/diff tests."""
    return {
        "trace_id": "trace-1",
        "generated_at": "2026-08-14T00:00:00+00:00",
        "scenarios": [
            {
                "scenario": "synth-passing",
                "status": status,
                "summary": {
                    "total": 1,
                    "passed": 1,
                    "failed": 0,
                    "recovered": 0,
                    "artifacts_missing": 0,
                },
                "steps": [],
                "cleanup": [],
                "trace_id": "trace-1",
                "error_boundary": False,
            }
        ],
    }


# =========================================================================
# Registration (the 18th CLI command)
# =========================================================================


class TestValidateRegistration:
    """The validate family is registered as a standalone sub-app."""

    def test_validate_appears_in_top_level_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "validate" in result.output

    def test_validate_help_lists_the_family(self) -> None:
        result = runner.invoke(app, ["validate", "--help"])
        assert result.exit_code == 0
        for name in ("list", "run", "report", "diff", "coverage", "matrix", "sign"):
            assert name in result.output


# =========================================================================
# validate list
# =========================================================================


class TestValidateList:
    """``validate list`` — load only, stable meta contract."""

    def test_list_satisfies_meta_scenario_contract(self, scenarios_dir: Path) -> None:
        """The committed cli/validate-list-meta.yaml asserts exit 0 and
        stdout_has ["list", "run"] — the output must contain those strings."""
        result = runner.invoke(app, ["validate", "list"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "run" in result.output
        assert "scenarios" in result.output

    def test_list_names_scenarios_with_hints(self, scenarios_dir: Path) -> None:
        result = runner.invoke(app, ["validate", "list"])
        assert result.exit_code == 0
        assert "synth-passing" in result.output
        assert "synth-env-gated" in result.output
        assert "SYNTH_REQUIRED_ENV" in result.output  # env-gated hint

    def test_list_json_is_machine_readable(self, scenarios_dir: Path) -> None:
        result = runner.invoke(app, ["--json", "validate", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 7
        names = {entry["name"] for entry in data["scenarios"]}
        assert names == {
            "synth-passing",
            "synth-failing",
            "synth-env-gated",
            "synth-tool-health",
            "synth-hard-failing",
            "synth-hard-passing",
            "synth-hard-env-gated",
        }

    def test_list_empty_library_exits_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty library still loads when the handbook is present
        (the loader fails loudly only when STANDARDS.md is absent)."""
        empty = tmp_path / "empty-library"
        empty.mkdir()
        shutil.copy(STANDARDS_FIXTURE, empty / "STANDARDS.md")
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(empty))
        result = runner.invoke(app, ["validate", "list"])
        assert result.exit_code == 0
        assert "0 scenarios" in result.output


# =========================================================================
# validate run
# =========================================================================


class TestValidateRun:
    """``validate run`` — one named scenario, exit 1 only on status failed."""

    def test_run_passing_scenario_exits_0(self, scenarios_dir: Path, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "validate",
                "run",
                "--scenario",
                "synth-passing",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 0
        assert "Status: passed" in result.output
        assert "Run recorded:" in result.output

    def test_run_tool_scenario_against_real_server(
        self, scenarios_dir: Path, tmp_path: Path
    ) -> None:
        """Tool-kind steps dispatch through the real create_server() instance."""
        result = runner.invoke(
            app,
            [
                "validate",
                "run",
                "--scenario",
                "synth-tool-health",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 0
        assert "Status: passed" in result.output

    def test_run_unconfigured_exits_0(self, scenarios_dir: Path, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "validate",
                "run",
                "--scenario",
                "synth-env-gated",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 0
        assert "unconfigured" in result.output
        assert "SYNTH_REQUIRED_ENV" in result.output

    def test_run_env_gate_skip_runs_unconfigured_scenario(
        self, scenarios_dir: Path, tmp_path: Path
    ) -> None:
        result = runner.invoke(
            app,
            [
                "validate",
                "run",
                "--scenario",
                "synth-env-gated",
                "--env-gate",
                "skip",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 0
        assert "Status: passed" in result.output

    def test_run_env_gate_skip_records_untrusted_marker(
        self, scenarios_dir: Path, tmp_path: Path
    ) -> None:
        """gap R-06: a skipped run is visibly non-Proved in its record."""
        runs_root = tmp_path / "runs"
        result = runner.invoke(
            app,
            [
                "validate",
                "run",
                "--scenario",
                "synth-env-gated",
                "--env-gate",
                "skip",
                "--runs-root",
                str(runs_root),
            ],
        )
        assert result.exit_code == 0
        (run_name,) = list_runs(runs_root)
        stored = json.loads((runs_root / run_name / "scenarios.json").read_text(encoding="utf-8"))
        assert set(stored) == {
            "trace_id",
            "generated_at",
            "scenarios",
            "hard_safety_violations",
            "blocked",
            "confidence",
            "trusted",
        }
        assert stored["trusted"] is False
        scenario_record = stored["scenarios"][0]
        assert scenario_record["env_gate_skipped"] == ["SYNTH_REQUIRED_ENV"]
        assert scenario_record["trusted"] is False

    def test_run_failed_scenario_exits_1(self, scenarios_dir: Path, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "validate",
                "run",
                "--scenario",
                "synth-failing",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 1
        assert "Status: failed" in result.output

    def test_run_missing_scenario_option_is_usage_error(
        self, scenarios_dir: Path, tmp_path: Path
    ) -> None:
        result = runner.invoke(app, ["validate", "run", "--runs-root", str(tmp_path / "runs")])
        assert result.exit_code == 2
        assert "Missing option" in result.output

    def test_run_unknown_scenario_exits_1_with_available_names(
        self, scenarios_dir: Path, tmp_path: Path
    ) -> None:
        result = runner.invoke(
            app,
            [
                "validate",
                "run",
                "--scenario",
                "does-not-exist",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 1
        assert "Unknown scenario" in result.output
        assert "synth-passing" in result.output  # lists available names

    def test_run_invalid_env_gate_value_exits_2(self, scenarios_dir: Path, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "validate",
                "run",
                "--scenario",
                "synth-passing",
                "--env-gate",
                "bogus",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 2

    def test_run_json_is_machine_readable(self, scenarios_dir: Path, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "--json",
                "validate",
                "run",
                "--scenario",
                "synth-passing",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["scenario"] == "synth-passing"
        assert data["status"] == "passed"

    def test_run_hard_failed_exits_1(self, scenarios_dir: Path, tmp_path: Path) -> None:
        """A hard scenario that fails is a hard-safety violation → exit 1."""
        result = runner.invoke(
            app,
            [
                "validate",
                "run",
                "--scenario",
                "synth-hard-failing",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 1
        assert "Status: failed" in result.output

    def test_run_hard_unconfigured_exits_1(self, scenarios_dir: Path, tmp_path: Path) -> None:
        """A hard env-gated scenario that is unconfigured is a violation →
        exit 1 (NEW: plain unconfigured alone exits 0, hard does not)."""
        result = runner.invoke(
            app,
            [
                "validate",
                "run",
                "--scenario",
                "synth-hard-env-gated",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 1
        assert "unconfigured" in result.output

    def test_run_hard_passed_exits_0(self, scenarios_dir: Path, tmp_path: Path) -> None:
        """A hard scenario that passes is NOT a violation → exit 0."""
        result = runner.invoke(
            app,
            [
                "validate",
                "run",
                "--scenario",
                "synth-hard-passing",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 0
        assert "Status: passed" in result.output

    def test_run_failed_non_hard_exits_1(self, scenarios_dir: Path, tmp_path: Path) -> None:
        """Non-hard failures keep the existing exit-1 contract."""
        result = runner.invoke(
            app,
            [
                "validate",
                "run",
                "--scenario",
                "synth-failing",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 1
        assert "Status: failed" in result.output

    def test_run_hard_text_marks_violation(self, scenarios_dir: Path, tmp_path: Path) -> None:
        """Hard violations on a non-failed status carry the text marker."""
        result = runner.invoke(
            app,
            [
                "validate",
                "run",
                "--scenario",
                "synth-hard-env-gated",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 1
        assert "HARD SAFETY VIOLATION" in result.output

    def test_run_hard_json_flags_violation(self, scenarios_dir: Path, tmp_path: Path) -> None:
        """The JSON projection exposes the hard-safety flag."""
        result = runner.invoke(
            app,
            [
                "--json",
                "validate",
                "run",
                "--scenario",
                "synth-hard-env-gated",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["hard_safety_violation"] is True


class TestValidateRunAll:
    """``validate run --all`` — whole library, one immutable suite record (R-09)."""

    def test_run_all_persists_one_suite_record(self, scenarios_dir: Path, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        result = runner.invoke(app, ["validate", "run", "--all", "--runs-root", str(runs)])
        # The synthetic library carries failures, so the pinned exit policy
        # is 1; the evidence is the persisted suite record, not the exit code.
        assert result.exit_code == 1
        assert "Suite run:" in result.output
        assert "Run recorded:" in result.output
        run_names = [p.name for p in runs.iterdir() if p.is_dir()]
        assert len(run_names) == 1
        record = json.loads((runs / run_names[0] / "scenarios.json").read_text(encoding="utf-8"))
        assert len(record["scenarios"]) == 7
        assert record["trace_id"]
        assert (runs / "latest.txt").is_file()

    def test_run_all_json_is_machine_readable(self, scenarios_dir: Path, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        result = runner.invoke(
            app, ["--json", "validate", "run", "--all", "--runs-root", str(runs)]
        )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["run_dir"]
        assert len(data["scenarios"]) == 7
        assert data["counts"]["failed"] >= 1

    def test_run_all_with_scenario_is_usage_error(
        self, scenarios_dir: Path, tmp_path: Path
    ) -> None:
        result = runner.invoke(
            app,
            [
                "validate",
                "run",
                "--all",
                "--scenario",
                "synth-passing",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 2
        assert "mutually exclusive" in result.output


# =========================================================================
# validate report
# =========================================================================


class TestValidateReport:
    """``validate report`` — renders a run record (minimal fallback until
    W4-T3's renderer lands)."""

    def test_report_no_runs_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["validate", "report", "--runs-root", str(tmp_path / "runs")])
        assert result.exit_code == 1
        assert "No runs recorded" in result.output

    def test_report_renders_record(self, tmp_path: Path) -> None:
        """W4-T3's renderer produces the report (fallback only if absent)."""
        runs = tmp_path / "runs"
        record_path = persist_run(runs, _make_run_record(), stamp="20260101-000000-000001")
        write_latest_pointer(runs, record_path.parent.name)
        result = runner.invoke(
            app, ["validate", "report", "--run", "latest", "--runs-root", str(runs)]
        )
        assert result.exit_code == 0
        assert "Validation report" in result.output
        assert "synth-passing" in result.output
        assert "PASS" in result.output

    def test_report_unknown_run_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["validate", "report", "--run", "nope", "--runs-root", str(tmp_path / "runs")],
        )
        assert result.exit_code == 1

    def test_report_json_returns_the_record(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        persist_run(runs, _make_run_record(), stamp="20260101-000000-000001")
        write_latest_pointer(runs, "20260101-000000-000001")
        result = runner.invoke(
            app,
            ["--json", "validate", "report", "--run", "latest", "--runs-root", str(runs)],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["verdicts"][0]["status"] == "passed"


# =========================================================================
# validate diff
# =========================================================================


class TestValidateDiff:
    """``validate diff`` — minimal fallback prints the latest two run names
    until W4-T4's diff module lands."""

    def test_diff_no_runs_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["validate", "diff", "--runs-root", str(tmp_path / "runs")])
        assert result.exit_code == 1
        assert "No runs recorded" in result.output

    def test_diff_prints_latest_two_runs(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        persist_run(runs, _make_run_record(), stamp="20260101-000000-000001")
        persist_run(runs, _make_run_record(), stamp="20260102-000000-000002")
        result = runner.invoke(app, ["validate", "diff", "--runs-root", str(runs)])
        assert result.exit_code == 0
        assert "20260102-000000-000002" in result.output
        assert "20260101-000000-000001" in result.output

    def test_diff_with_baseline(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        persist_run(runs, _make_run_record(), stamp="20260102-000000-000002")
        result = runner.invoke(
            app,
            [
                "validate",
                "diff",
                "--baseline",
                str(tmp_path / "baseline.json"),
                "--runs-root",
                str(runs),
            ],
        )
        assert result.exit_code == 0
        assert "Baseline:" in result.output

    def test_diff_text_renders_sections(self, tmp_path: Path) -> None:
        """Text output renders the diff as sectioned headings, not raw JSON."""
        runs = tmp_path / "runs"
        persist_run(runs, _make_run_record("failed"), stamp="20260101-000000-000001")
        persist_run(runs, _make_run_record("passed"), stamp="20260102-000000-000002")
        result = runner.invoke(app, ["validate", "diff", "--runs-root", str(runs)])
        assert result.exit_code == 0
        assert "## Diff" in result.output
        # At least one non-empty bucket renders its section heading
        assert any(
            f"## {bucket}" in result.output
            for bucket in ("new_passes", "new_failures", "regressed", "improved")
        )

    def test_diff_json_payload_unchanged(self, tmp_path: Path) -> None:
        """--json keeps the machine-readable payload with the full diff keys."""
        runs = tmp_path / "runs"
        persist_run(runs, _make_run_record("failed"), stamp="20260101-000000-000001")
        persist_run(runs, _make_run_record("passed"), stamp="20260102-000000-000002")
        result = runner.invoke(app, ["--json", "validate", "diff", "--runs-root", str(runs)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for key in (
            "new_passes",
            "new_failures",
            "regressed",
            "improved",
            "stable",
            "quality_trend",
            "summary",
        ):
            assert key in data["diff"]

    def test_diff_default_baseline_used(self, tmp_path: Path) -> None:
        """A committed baseline under <root>/scenarios/baseline/ is auto-resolved."""
        baseline_dir = tmp_path / "scenarios" / "baseline"
        baseline_dir.mkdir(parents=True)
        baseline = _make_run_record("failed")
        baseline["baseline"] = True
        (baseline_dir / "2026-08-14-preflight.json").write_text(
            json.dumps(baseline), encoding="utf-8"
        )
        runs = tmp_path / "runs"
        persist_run(runs, _make_run_record("passed"), stamp="20260102-000000-000002")
        result = runner.invoke(app, ["validate", "diff", "--runs-root", str(runs)])
        assert result.exit_code == 0
        assert any(token in result.output for token in ("baseline", "Baseline", "2026-08-14"))

    def test_diff_no_baseline_file_falls_back(self, tmp_path: Path) -> None:
        """No committed baseline → falls back to the two-latest-runs behavior."""
        runs = tmp_path / "runs"
        persist_run(runs, _make_run_record("failed"), stamp="20260101-000000-000001")
        persist_run(runs, _make_run_record("passed"), stamp="20260102-000000-000002")
        result = runner.invoke(app, ["validate", "diff", "--runs-root", str(runs)])
        assert result.exit_code == 0
        # Two-latest-runs behavior: the two run names are printed
        assert "20260102-000000-000002" in result.output
        assert "20260101-000000-000001" in result.output


# =========================================================================
# validate coverage
# =========================================================================


class TestValidateCoverage:
    """``validate coverage`` — exit 1 when missing is non-empty."""

    def test_coverage_exits_1_when_missing_nonempty(self, scenarios_dir: Path) -> None:
        """The synthetic library covers no automedia commands, so the audit
        against the real app.py (19 declared) reports missing CLI commands."""
        result = runner.invoke(app, ["validate", "coverage"])
        assert result.exit_code == 1
        assert "Coverage audit" in result.output
        assert "declared=" in result.output
        assert "missing" in result.output

    def test_coverage_json_audit_shape(self, scenarios_dir: Path) -> None:
        result = runner.invoke(app, ["--json", "validate", "coverage"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        summary: dict[str, Any] = data["summary"]
        # The live app.py now registers 19 commands (pipeline is the 19th).
        assert summary["cli_declared"] == 19
        # server.py registers 59 + 6 validation tools (W4-T2 + matrix + the
        # gap R-09 run_validation_suite tool) + get_pipeline_state
        # + get_gate_report + review_decision (productization-roadmap todo 9).
        assert summary["mcp_declared"] == 68
        assert summary["cli_missing"] == 19  # synthetic library covers none

    def test_coverage_reports_evidence_buckets_and_exits_1(
        self, scenarios_dir: Path, tmp_path: Path
    ) -> None:
        runs = tmp_path / "runs"
        persist_run(
            runs,
            {
                "trace_id": "t",
                "generated_at": "2026-01-01T00:00:00+00:00",
                "confidence": "mock",
                "scenarios": [
                    {
                        "scenario": "synth-passing",
                        "status": "passed",
                        "confidence": "mock",
                        "steps": [],
                    }
                ],
            },
            stamp="20260101-000000-000000",
        )
        write_latest_pointer(runs, "20260101-000000-000000")
        result = runner.invoke(app, ["validate", "coverage", "--runs-root", str(runs)])
        assert result.exit_code == 1
        assert "Evidence run: 20260101-000000-000000" in result.output
        assert "Buckets:" in result.output
        assert "Unproven" in result.output


# =========================================================================
# validate matrix
# =========================================================================


class TestValidateMatrix:
    """``validate matrix`` — per-scenario surface coverage + last-run status."""

    def test_matrix_text_output(self, scenarios_dir: Path) -> None:
        result = runner.invoke(app, ["validate", "matrix"])
        assert result.exit_code == 0
        for surface in ("mcp", "cli", "gates", "modes"):
            assert surface in result.output
        assert "Validation matrix" in result.output
        assert "Hard-safety scenarios:" in result.output

    def test_matrix_json(self, scenarios_dir: Path) -> None:
        result = runner.invoke(app, ["--json", "validate", "matrix"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for key in ("surfaces", "scenarios", "rows", "flags", "summary"):
            assert key in data
        assert "mcp" in data["surfaces"]
        assert "cli" in data["surfaces"]

    def test_matrix_text_lists_scenarios_and_hard_flags(self, scenarios_dir: Path) -> None:
        result = runner.invoke(app, ["validate", "matrix"])
        assert result.exit_code == 0
        assert "synth-hard-failing" in result.output
        assert "synth-passing" in result.output
        assert "hard=yes" in result.output


# =========================================================================
# validate sign
# =========================================================================


class TestValidateSign:
    """``validate sign`` — the director sign-off surface (gap Tr-07)."""

    def _seed_run(self, runs: Path, name: str = "20260101-000000-000001") -> str:
        record_path = persist_run(runs, _make_run_record(), stamp=name)
        write_latest_pointer(runs, record_path.parent.name)
        return name

    def test_sign_creates_signed_txt(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        name = self._seed_run(runs)
        result = runner.invoke(app, ["validate", "sign", name, "--runs-root", str(runs)])
        assert result.exit_code == 0
        assert "Signed" in result.output
        signed = runs / name / "signed.txt"
        assert signed.is_file()
        assert "approved" in signed.read_text(encoding="utf-8")

    def test_sign_records_custom_verdict_and_signer(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        name = self._seed_run(runs)
        result = runner.invoke(
            app,
            [
                "validate",
                "sign",
                name,
                "--verdict",
                "rejected",
                "--signer",
                "qa-lead",
                "--runs-root",
                str(runs),
            ],
        )
        assert result.exit_code == 0
        assert "qa-lead rejected" in (runs / name / "signed.txt").read_text(encoding="utf-8")

    def test_sign_missing_run_name_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["validate", "sign", "--runs-root", str(tmp_path / "runs")])
        assert result.exit_code == 1
        assert "run name is required" in result.output

    def test_sign_empty_run_name_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["validate", "sign", "", "--runs-root", str(tmp_path / "runs")])
        assert result.exit_code == 1

    def test_sign_unknown_run_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app, ["validate", "sign", "ghost-run", "--runs-root", str(tmp_path / "runs")]
        )
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_sign_empty_verdict_exits_1(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        name = self._seed_run(runs)
        result = runner.invoke(
            app,
            ["validate", "sign", name, "--verdict", "", "--runs-root", str(runs)],
        )
        assert result.exit_code == 1

    def test_sign_json_is_machine_readable(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        name = self._seed_run(runs)
        result = runner.invoke(app, ["--json", "validate", "sign", name, "--runs-root", str(runs)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["run"] == name
        assert data["verdict"] == "approved"
