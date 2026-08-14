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

    def test_meta_scenario_is_env_free_and_loads_clean(
        self, library: list[Scenario]
    ) -> None:
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

    def test_validate_list_json_shows_meta_scenario(
        self, library: list[Scenario]
    ) -> None:
        result = runner.invoke(app, ["--json", "validate", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == len(library)
        names = {entry["name"] for entry in data["scenarios"]}
        assert names == {scenario.name for scenario in library}
        assert META_SCENARIO in names

    def test_validate_coverage_exits_0_with_missing_zero(
        self, library_root: Path
    ) -> None:
        """The regenerated audit: missing = 0 on both surfaces -> exit 0."""
        result = runner.invoke(app, ["validate", "coverage"])
        assert result.exit_code == 0
        assert "missing = 0" in result.output
        assert "mcp_missing" in result.output or "missing=" in result.output

    def test_validate_coverage_json_regenerated_numbers(
        self, library_root: Path
    ) -> None:
        """W4-T7 regeneration pins: mcp 63 declared / 56 covered / 0 missing;
        cli 18 / 18 / 0; both phantom = 0; boundary_only 7 (waiver)."""
        result = runner.invoke(app, ["--json", "validate", "coverage"])
        assert result.exit_code == 0
        summary: dict[str, Any] = json.loads(result.output)["summary"]
        assert summary["mcp_declared"] == 63
        assert summary["mcp_used"] == 63
        assert summary["mcp_covered"] == 56
        assert summary["mcp_missing"] == 0
        assert summary["mcp_phantom"] == 0
        assert summary["mcp_boundary_only"] == 7
        assert summary["cli_declared"] == 18
        assert summary["cli_covered"] == 18
        assert summary["cli_missing"] == 0
        assert summary["cli_phantom"] == 0


# ===================================================================
# MCP tools through the real dispatcher (missing W4-T2 coverage only)
# ===================================================================


class TestValidationToolsRealDispatcher:
    """The bits W4-T2 did not pin: meta-scenario listing + regenerated audit."""

    def test_list_validation_scenarios_includes_meta_self_check(
        self, server: FastMCP
    ) -> None:
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
        assert summary["mcp_covered"] == 56
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
