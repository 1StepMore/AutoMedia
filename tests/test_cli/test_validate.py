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
from automedia.validation.persist import persist_run, write_latest_pointer

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
        for name in ("list", "run", "report", "diff", "coverage"):
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
        assert data["total"] == 4
        names = {entry["name"] for entry in data["scenarios"]}
        assert names == {"synth-passing", "synth-failing", "synth-env-gated", "synth-tool-health"}

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

    def test_run_passing_scenario_exits_0(
        self, scenarios_dir: Path, tmp_path: Path
    ) -> None:
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

    def test_run_unconfigured_exits_0(
        self, scenarios_dir: Path, tmp_path: Path
    ) -> None:
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

    def test_run_failed_scenario_exits_1(
        self, scenarios_dir: Path, tmp_path: Path
    ) -> None:
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
        result = runner.invoke(
            app, ["validate", "run", "--runs-root", str(tmp_path / "runs")]
        )
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

    def test_run_invalid_env_gate_value_exits_2(
        self, scenarios_dir: Path, tmp_path: Path
    ) -> None:
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

    def test_run_json_is_machine_readable(
        self, scenarios_dir: Path, tmp_path: Path
    ) -> None:
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


# =========================================================================
# validate report
# =========================================================================


class TestValidateReport:
    """``validate report`` — renders a run record (minimal fallback until
    W4-T3's renderer lands)."""

    def test_report_no_runs_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app, ["validate", "report", "--runs-root", str(tmp_path / "runs")]
        )
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
        result = runner.invoke(
            app, ["validate", "diff", "--runs-root", str(tmp_path / "runs")]
        )
        assert result.exit_code == 1
        assert "No runs recorded" in result.output

    def test_diff_prints_latest_two_runs(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        persist_run(runs, _make_run_record(), stamp="20260101-000000-000001")
        persist_run(runs, _make_run_record(), stamp="20260102-000000-000002")
        result = runner.invoke(
            app, ["validate", "diff", "--runs-root", str(runs)]
        )
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


# =========================================================================
# validate coverage
# =========================================================================


class TestValidateCoverage:
    """``validate coverage`` — exit 1 when missing is non-empty."""

    def test_coverage_exits_1_when_missing_nonempty(self, scenarios_dir: Path) -> None:
        """The synthetic library covers no automedia commands, so the audit
        against the real app.py (18 declared) reports missing CLI commands."""
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
        # The live app.py now registers 18 commands (validate is the 18th).
        assert summary["cli_declared"] == 18
        # server.py registers 59 + 4 W4-T2 validation tools (landed in parallel).
        assert summary["mcp_declared"] == 63
        assert summary["cli_missing"] == 18  # synthetic library covers none
