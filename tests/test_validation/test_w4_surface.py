"""W4-T7 surface tests — the W4 validation surface against the REAL library.

Pins the W4-T1..T6 shipped surface contract without live runs: the CLI
family through typer's ``CliRunner``, the 4 validation MCP tools through the
real dispatcher (``create_server().call_tool``), and the W4-T7 meta
scenario ``validation-self-check`` as a loadable, env-free member of the
library.

What is deliberately NOT duplicated here: the W4-T2 engine-run coverage
(health-check GREEN, empty-name/unknown-name rejection, report envelopes)
lives in ``test_mcp_validation_tools.py``; the synthetic-library CLI family
tests (24 of them) live in ``tests/test_cli/test_validate.py``.  This
module adds ONLY what W4-T7 must pin: the meta scenario's contract, the
regenerated coverage numbers (missing = 0), and the real-library CLI
shapes.

Same skip rule as W3-T9/W4-T2: when ``AUTOMEDIA_VALIDATION_SCENARIOS_DIR``
points to a non-existent directory the library is intentionally unavailable
and this module skips.  NOT e2e-marked: no network, no LLM, no CLI
subprocesses — CliRunner and in-process ``call_tool`` only, so the default
pytest gate (``-m 'not e2e'``) runs every test here.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.mcp.server import create_server
from automedia.validation.loader import default_scenarios_dir, load_scenarios
from automedia.validation.schema import Scenario
from automedia.validation.standards import StandardsRegistry

runner = CliRunner()

META_SCENARIO = "validation-self-check"
META_SCENARIOS: tuple[str, ...] = (
    "list-validation-scenarios-meta",
    "validate-list-meta",
    META_SCENARIO,
)


def _scenarios_dir_or_skip() -> Path:
    """The scenarios dir; skip when the env override is broken (W3-T9 rule)."""
    override = os.environ.get("AUTOMEDIA_VALIDATION_SCENARIOS_DIR")
    if override and not Path(override).expanduser().is_dir():
        pytest.skip(
            f"AUTOMEDIA_VALIDATION_SCENARIOS_DIR={override!r} points to a "
            "non-existent directory; the W4-T7 surface tests are skipped "
            "(documented W4-T7)"
        )
    return default_scenarios_dir()


@pytest.fixture(scope="module")
def library_root() -> Path:
    """The real committed scenarios directory (skip when unavailable)."""
    return _scenarios_dir_or_skip()


@pytest.fixture(scope="module")
def library(library_root: Path) -> list[Scenario]:
    """The whole committed library through the real loader + registry."""
    return load_scenarios(library_root, standards=StandardsRegistry.from_default())


@pytest.fixture(scope="module")
def server() -> FastMCP:
    """One real server instance for the module (registrations are static)."""
    return create_server()


def _call_tool(server: FastMCP, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call a tool through the real dispatcher and return its structured dict."""
    raw = asyncio.run(server.call_tool(name, arguments))
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[1], dict):
        return raw[1]
    if isinstance(raw, dict):
        return raw
    raise AssertionError(f"unexpected call_tool result shape for {name}: {raw!r}")


# ===================================================================
# Meta scenario contract (plan C2)
# ===================================================================


class TestMetaScenarioContract:
    """validation-self-check: the W4-T7 meta self-validation scenario."""

    def test_meta_scenario_is_member_of_library(self, library: list[Scenario]) -> None:
        by_name = {scenario.name: scenario for scenario in library}
        for name in META_SCENARIOS:
            assert name in by_name, f"meta scenario {name!r} missing from library"

    def test_meta_scenario_is_env_free_and_loads_clean(self, library: list[Scenario]) -> None:
        """requires_env == [] + every cited standard known (recursion guard
        parity with the W3-T9 smoke test's meta assertions)."""
        by_name = {scenario.name: scenario for scenario in library}
        scenario = by_name[META_SCENARIO]
        assert scenario.requires_env == []
        known = StandardsRegistry.from_default().known_keys()
        cited = {step.standard for step in scenario.steps}
        cited.update(step.standard for step in scenario.cleanup_steps)
        assert cited <= known, f"unknown standards cited: {sorted(cited - known)}"

    def test_meta_scenario_steps_are_deterministic_tool_calls(
        self, library: list[Scenario]
    ) -> None:
        """All 3 primary steps are tool-kind calls to the 3 validation tools,
        each asserting only the success envelope; the cleanup removes the
        scratch runs root."""
        by_name = {scenario.name: scenario for scenario in library}
        scenario = by_name[META_SCENARIO]
        assert [step.tool for step in scenario.steps] == [
            "run_validation_scenario",
            "get_validation_report",
            "validation_coverage_audit",
        ]
        assert all(step.expect.success is True for step in scenario.steps)
        cleanup = scenario.cleanup_steps
        assert len(cleanup) == 1
        assert cleanup[0].kind == "cli"
        assert cleanup[0].command == "rm -rf validation-runs"


# ===================================================================
# CLI family against the real library
# ===================================================================


class TestValidateCliRealLibrary:
    """The validate family answers against the real committed library."""

    def test_validate_list_json_shows_meta_scenario(self, library: list[Scenario]) -> None:
        result = runner.invoke(app, ["--json", "validate", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == len(library)
        names = {entry["name"] for entry in data["scenarios"]}
        assert names == {scenario.name for scenario in library}
        assert META_SCENARIO in names

    def test_validate_coverage_reports_unproven_and_exits_1(
        self, library_root: Path
    ) -> None:
        """Evidence-backed contract (gap T-01): the static surfaces are fully
        declared/used (missing = 0), but coverage now counts only surfaces
        reached by a passed step in the newest persisted run, so an
        evidence-free/static environment reports them `unproven` and exits 1
        (never default GREEN)."""
        result = runner.invoke(app, ["validate", "coverage"])
        assert result.exit_code == 1
        assert "Coverage audit" in result.output
        assert "Gates:" in result.output
        assert "Modes:" in result.output
        assert "missing = 0 (excluding boundary-only, listed above)" in result.output
        assert "Evidence run:" in result.output
        assert "Buckets:" in result.output
        assert "Unproven" in result.output

    def test_validate_coverage_json_regenerated_numbers(self, library_root: Path) -> None:
        """W4-T7 regeneration pins: mcp 68 declared / 60 covered / 0 missing;
        cli 19 / 19 / 0; both phantom = 0; boundary_only 8 (waiver).
        Issue #78 final contract (A3 landed): the pipeline surfaces are fully
        declared — gates 33 / 33 / 0 missing, modes 9 / 9 / 0.  Gap T-01 adds
        the evidence buckets and makes the static job exit 1 while surfaces
        are unproven.
        Issue #86: the 5th validation MCP tool ``validation_matrix`` is now
        declared and covered by ``validation-matrix-meta``. The
        graph-engineering-rollout adds ``get_pipeline_state`` and the
        productization-roadmap adds ``get_gate_report`` (covered by
        ``gate-report-surface``) and ``review_decision`` (covered by
        ``review-decision-surface``). Gap R-09 adds ``run_validation_suite``
        (boundary-only, covered by ``validation-suite-boundary``) — mcp 68 /
        60, cli 19."""
        result = runner.invoke(app, ["--json", "validate", "coverage"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        summary: dict[str, Any] = data["summary"]
        assert summary["mcp_declared"] == 68
        assert summary["mcp_used"] == 68
        assert summary["mcp_covered"] == 60
        assert summary["mcp_missing"] == 0
        assert summary["mcp_phantom"] == 0
        assert summary["mcp_boundary_only"] == 8
        assert summary["cli_declared"] == 19
        assert summary["cli_covered"] == 19
        assert summary["cli_missing"] == 0
        assert summary["cli_phantom"] == 0
        assert summary["gates_declared"] == 33
        assert summary["gates_used"] == 33
        assert summary["gates_covered"] == 33
        assert summary["gates_missing"] == 0
        assert summary["gates_phantom"] == 0
        assert summary["modes_declared"] == 9
        assert summary["modes_used"] == 9
        assert summary["modes_covered"] == 9
        assert summary["modes_missing"] == 0
        assert summary["modes_phantom"] == 0
        assert data["missing_count"] == 0
        for surface in ("mcp", "cli", "gates", "modes"):
            assert surface in data["covered"]
            assert surface in data["unproven"]
            assert surface in data["missing"]


# ===================================================================
# MCP tools through the real dispatcher (missing W4-T2 coverage only)
# ===================================================================


class TestValidationToolsRealDispatcher:
    """The bits W4-T2 did not pin: meta-scenario listing + regenerated audit."""

    def test_list_validation_scenarios_includes_meta_self_check(self, server: FastMCP) -> None:
        payload = _call_tool(server, "list_validation_scenarios", {})
        assert payload["success"] is True
        assert payload["count"] >= 91  # 90 committed + validation-self-check
        by_name = {entry["name"]: entry for entry in payload["scenarios"]}
        assert META_SCENARIO in by_name
        # env-free + not a boundary probe -> ready (static, honest)
        assert by_name[META_SCENARIO]["status_hint"] == "ready"

    def test_audit_through_dispatcher_shows_missing_zero(self, server: FastMCP) -> None:
        """The coverage audit reaches missing = 0 via the real dispatcher."""
        payload = _call_tool(server, "validation_coverage_audit", {})
        assert payload["success"] is True
        summary: dict[str, Any] = payload["summary"]
        assert summary["mcp_missing"] == 0
        assert summary["mcp_covered"] == 60
        assert summary["mcp_phantom"] == 0
        assert summary["cli_missing"] == 0
        assert payload["missing_mcp"] == []
        assert payload["missing_cli"] == []
        assert payload["phantom_mcp"] == []
        assert payload["phantom_cli"] == []
        for tool in (
            "run_validation_scenario",
            "get_validation_report",
            "validation_coverage_audit",
        ):
            assert tool in payload["covered_mcp"]
