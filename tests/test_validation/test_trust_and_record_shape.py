"""Todo 25 (R-06, Tr-03, Tr-05, T-17): trust flags, custom runs_root, record shape.

* R-06 — ``--env-gate skip`` runs carry ``env_gate_skipped: [vars]`` and
  ``trusted: false``, and the evidence-backed coverage audit never counts an
  untrusted scenario as a Proved surface.
* Tr-03 — the coverage audit carries ``generated_at`` and ``scenario_count``.
* T-17 — ``get_validation_report`` honors a caller-provided ``runs_root`` and
  MCP ``run_validation_scenario`` saves by default.
* Tr-05 — an MCP single-scenario run persists the same top-level record keys
  as the CLI single-scenario path.

All fixtures are synthetic (Red Line 4).
"""

from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

# Import the MCP server package first: mcp_tools imports automedia.mcp.mcp_error,
# so a direct mcp_tools-first import hits a partially-initialized circular import
# (same ordering the sibling MCP-surface test uses).
from automedia.mcp.server import create_server  # noqa: F401
from automedia.validation import mcp_tools
from automedia.validation.coverage import coverage_audit
from automedia.validation.engine import (
    make_adapters,
    run_validation_scenario_async,
)
from automedia.validation.persist import list_runs, persist_run, write_latest_pointer
from automedia.validation.schema import Scenario

STANDARDS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "synth"
    / "standards"
    / "standards_fixture.md"
)

_CLI_SCENARIO = """\
name: {name}
description: A synthetic fixture scenario.
intent: Prove the trust and record-shape contract.
user_level: L0
category: baseline
requires_env: [{env}]
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
"""

_TOOL_SCENARIO = """\
name: {name}
description: A synthetic tool fixture scenario.
intent: Prove a passed tool step would otherwise mark a surface covered.
user_level: L0
category: baseline
requires_env: []
steps:
  - name: call the tool
    kind: tool
    check: The tool answers.
    standard: tool.contract
    tool: health_check
    arguments: {{}}
    expect:
      success: true
"""


def _scenario(*, requires_env: list[str] | None = None) -> Scenario:
    return Scenario.from_dict(
        {
            "name": "trust-fixture",
            "description": "Synthetic trust fixture.",
            "intent": "Exercise env_gate_skipped record marking.",
            "user_level": "L0",
            "category": "baseline",
            "requires_env": requires_env or [],
            "steps": [
                {
                    "name": "echo prints ok",
                    "kind": "cli",
                    "check": "echo prints ok",
                    "standard": "founder-expectations.F02",
                    "command": "echo ok",
                    "timeout_seconds": 30,
                    "expect": {"exit_code": 0, "stdout_has": ["ok"]},
                }
            ],
        }
    )


def _write_lib(tmp_path: Path, files: dict[str, str]) -> Path:
    lib = tmp_path / "scenarios"
    lib.mkdir()
    shutil.copy2(STANDARDS_FIXTURE, lib / "STANDARDS.md")
    for filename, content in files.items():
        (lib / filename).write_text(content, encoding="utf-8")
    return lib


class TestEnvGateSkipTrust:
    def test_skipped_run_records_vars_and_untrusted(self) -> None:
        record = asyncio.run(
            run_validation_scenario_async(
                _scenario(),
                make_adapters(None),
                env_gate_skipped=["MISSING_ENV"],
            )
        )
        assert record["status"] == "passed"
        assert record["env_gate_skipped"] == ["MISSING_ENV"]
        assert record["trusted"] is False

    def test_unskipped_run_is_trusted_without_the_marker(self) -> None:
        record = asyncio.run(run_validation_scenario_async(_scenario(), make_adapters(None)))
        # No marker: an absent trusted flag means trusted (the record only
        # carries the flag when a gate was actually bypassed).
        assert record.get("trusted", True) is True
        assert "env_gate_skipped" not in record


class TestCoverageHonoursTrust:
    def test_untrusted_scenario_is_not_covered(self, tmp_path: Path) -> None:
        lib = _write_lib(
            tmp_path,
            {"health.yaml": _TOOL_SCENARIO.format(name="health-fixture")},
        )
        runs_root = tmp_path / "runs"
        persist_run(
            runs_root,
            {
                "trace_id": "trace-fixture",
                "generated_at": "2026-01-01T00:00:00+00:00",
                "confidence": "real",
                "scenarios": [
                    {
                        "scenario": "health-fixture",
                        "status": "passed",
                        "confidence": "real",
                        "trusted": False,
                        "env_gate_skipped": ["MISSING_ENV"],
                        "error_boundary": False,
                        "steps": [
                            {
                                "step_index": 1,
                                "surface": "tool",
                                "target": "health_check",
                                "passed": True,
                                "status": "passed",
                            }
                        ],
                    }
                ],
            },
            stamp="20260101-000000-000000",
        )
        write_latest_pointer(runs_root, "20260101-000000-000000")
        audit = coverage_audit(lib, runs_root=runs_root)
        assert "health_check" not in audit["covered"]["mcp"]
        assert "health_check" in audit["unproven"]["mcp"]


class TestAuditFreshness:
    def test_audit_carries_generated_at_and_scenario_count(self) -> None:
        audit = coverage_audit()
        generated = audit["generated_at"]
        assert isinstance(generated, str) and generated
        datetime.fromisoformat(generated)  # parseable ISO-8601
        assert audit["scenario_count"] == audit["by_level"]["total"]
        assert audit["scenario_count"] > 0


class TestReportRunsRoot:
    def test_get_validation_report_reads_custom_root(self, tmp_path: Path) -> None:
        runs_root = tmp_path / "custom-runs"
        persist_run(
            runs_root,
            {
                "trace_id": "trace-custom",
                "generated_at": "2026-01-01T00:00:00+00:00",
                "scenarios": [{"scenario": "fixture", "status": "passed"}],
            },
            stamp="20260101-000000-000000",
        )
        write_latest_pointer(runs_root, "20260101-000000-000000")
        payload = mcp_tools.get_validation_report(runs_root=str(runs_root))
        assert payload["success"] is True
        assert payload["run_dir"] == "20260101-000000-000000"
        assert payload["scenarios"][0]["scenario"] == "fixture"


class TestMcpSingleRunRecord:
    def test_default_saves_and_matches_cli_shape(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lib = _write_lib(tmp_path, {"green.yaml": _CLI_SCENARIO.format(name="trust-green", env="")})
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(lib))
        runs_root = tmp_path / "runs"
        record = asyncio.run(
            mcp_tools.run_validation_scenario("trust-green", runs_root=str(runs_root))
        )
        assert record["success"] is True
        assert record["status"] == "passed"
        assert list_runs(runs_root), "save defaults to True -> a run dir exists"

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
        assert stored["trusted"] is True
        assert stored["hard_safety_violations"] == []
        assert stored["blocked"] is False

    def test_explicit_save_false_persists_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lib = _write_lib(tmp_path, {"green.yaml": _CLI_SCENARIO.format(name="trust-green", env="")})
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(lib))
        runs_root = tmp_path / "runs"
        asyncio.run(
            mcp_tools.run_validation_scenario("trust-green", runs_root=str(runs_root), save=False)
        )
        assert list_runs(runs_root) == []
