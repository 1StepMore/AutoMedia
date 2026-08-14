"""MCP surface tests for the 4 validation tools (plan W4-T2).

Registered in ``create_server()``: ``list_validation_scenarios``,
``run_validation_scenario``, ``get_validation_report``,
``validation_coverage_audit``.  These tests drive the REAL server through
``FastMCP.call_tool`` (the actual dispatcher, in-process) with both valid
and invalid arguments — never the handler functions in isolation, so the
envelope shapes, the async Context injection, and the pydantic argument
validation are all exercised.

PLACEMENT (documented): ``tests/test_validation/`` — the tools are the MCP
surface of the validation layer (handlers live in
``automedia/validation/mcp_tools.py``), and like W3-T9's library smoke this
module reads the REAL committed scenario library, so the same skip rule
applies: when ``AUTOMEDIA_VALIDATION_SCENARIOS_DIR`` points to a
non-existent directory, the library is intentionally unavailable and this
module skips.  NOT e2e-marked: every test is fast (no network, no LLM, no
CLI subprocess) and runs in the default pytest gate.

Committed-library expectations (as of 2026-08-14): 91 scenarios (90 +
W4-T7's ``validation-self-check`` meta scenario), 63 MCP tools after
W4-T2 (59 + 4), ``health-check-baseline`` is the
deterministic GREEN-able scenario (its only step calls ``health_check``,
expect ``success: true`` — it passed the W2-T3/W3 empirical suites).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

from automedia.mcp.server import create_server

EXPECTED_VALIDATION_TOOLS: frozenset[str] = frozenset(
    {
        "list_validation_scenarios",
        "run_validation_scenario",
        "get_validation_report",
        "validation_coverage_audit",
    }
)


def _scenarios_dir_or_skip() -> None:
    """Skip when the env override points at a non-existent directory (W3-T9 rule)."""
    override = os.environ.get("AUTOMEDIA_VALIDATION_SCENARIOS_DIR")
    if override and not Path(override).expanduser().is_dir():
        pytest.skip(
            f"AUTOMEDIA_VALIDATION_SCENARIOS_DIR={override!r} points to a "
            "non-existent directory; the validation-tool surface tests are "
            "skipped (documented W4-T2)"
        )


@pytest.fixture(autouse=True, scope="module")
def _library_available() -> None:
    """Every test here reads the real committed scenario library."""
    _scenarios_dir_or_skip()


@pytest.fixture(scope="module")
def server() -> FastMCP:
    """One real server instance for the module (registrations are static)."""
    return create_server()


def _call_tool(server: FastMCP, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call a tool through the real dispatcher and return its structured dict.

    FastMCP's ``call_tool`` returns a tuple (unstructured content blocks,
    structured dict) for dict-annotated tools; the dict is authoritative
    (verified in test_adapters.py against mcp 1.27.2).
    """
    raw = asyncio.run(server.call_tool(name, arguments))
    if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[1], dict):
        return raw[1]
    if isinstance(raw, dict):
        return raw
    raise AssertionError(f"unexpected call_tool result shape for {name}: {raw!r}")


# ===================================================================
# Registration + help_mcp introspection
# ===================================================================


class TestRegistration:
    """The 4 tools are registered and surface in help_mcp automatically."""

    def test_four_validation_tools_registered(self, server: FastMCP) -> None:
        """59 pre-existing tools + 4 validation tools = 63 (AGENTS.md update is W5-T1)."""
        names = set(server._tool_manager._tools.keys())
        assert names >= EXPECTED_VALIDATION_TOOLS, (
            f"missing validation tools: {sorted(EXPECTED_VALIDATION_TOOLS - names)}"
        )
        assert len(names) == 63

    def test_tools_appear_in_help_mcp(self, server: FastMCP) -> None:
        """The registry population in create_server picks up the new tools."""
        payload = _call_tool(server, "help_mcp", {})
        assert payload["tool_count"] == 63
        listed = {
            entry["name"]
            for category in payload["categories"].values()
            for entry in category
        }
        assert listed >= EXPECTED_VALIDATION_TOOLS


# ===================================================================
# list_validation_scenarios
# ===================================================================


class TestListValidationScenarios:
    """Tool 1: flat envelope with the scenario library."""

    def test_returns_library_with_flat_envelope(self, server: FastMCP) -> None:
        payload = _call_tool(server, "list_validation_scenarios", {})
        assert payload["success"] is True
        assert payload["count"] >= 80  # W3-T9 floor; 90 as of 2026-08-14
        assert len(payload["scenarios"]) == payload["count"]
        for entry in payload["scenarios"]:
            assert set(entry) == {"name", "description", "category", "status_hint"}

    def test_meta_scenario_listed_with_static_status_hint(self, server: FastMCP) -> None:
        payload = _call_tool(server, "list_validation_scenarios", {})
        by_name = {entry["name"]: entry for entry in payload["scenarios"]}
        assert "list-validation-scenarios-meta" in by_name
        # health-check-baseline: no env gate, no boundary -> ready (static, honest)
        assert by_name["health-check-baseline"]["status_hint"] == "ready"
        # the journey is env-gated -> hint names the gate, never a runtime probe
        assert by_name["text-only-journey"]["status_hint"].startswith(
            "requires-env: AUTOMEDIA_LLM_API_KEY"
        )


# ===================================================================
# run_validation_scenario
# ===================================================================


class TestRunValidationScenario:
    """Tool 2: name filter (recursion bound) + real in-process execution."""

    def test_runs_named_scenario_through_real_dispatcher(self, server: FastMCP) -> None:
        """health-check-baseline runs a health_check step via Context injection."""
        payload = _call_tool(
            server, "run_validation_scenario", {"scenario_name": "health-check-baseline"}
        )
        assert payload["success"] is True
        assert payload["scenario"] == "health-check-baseline"
        assert payload["status"] == "passed"
        assert payload["summary"]["total"] == 1
        assert payload["summary"]["passed"] == 1
        step = payload["steps"][0]
        assert step["surface"] == "tool"
        assert step["target"] == "health_check"
        assert step["passed"] is True

    def test_rejects_empty_name(self, server: FastMCP) -> None:
        """The REQUIRED name filter rejects empty/blank names (recursion bound M5)."""
        for bad_name in ("", "   "):
            payload = _call_tool(
                server, "run_validation_scenario", {"scenario_name": bad_name}
            )
            assert payload["success"] is False
            assert payload["error"]["code"] == "INVALID_PARAM"
            assert "scenario_name" in payload["error"]["message"]

    def test_rejects_unknown_name_listing_available(self, server: FastMCP) -> None:
        payload = _call_tool(
            server, "run_validation_scenario", {"scenario_name": "no-such-scenario"}
        )
        assert payload["success"] is False
        assert payload["error"]["code"] == "NOT_FOUND"
        assert "no-such-scenario" in payload["error"]["message"]
        assert "health-check-baseline" in payload["error"]["resolution"]


# ===================================================================
# get_validation_report
# ===================================================================


class TestGetValidationReport:
    """Tool 3: run-record reading, latest via latest.txt."""

    def test_no_runs_is_error_envelope_naming_root(
        self,
        server: FastMCP,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        payload = _call_tool(server, "get_validation_report", {})
        assert payload["success"] is False
        assert payload["error"]["code"] == "NOT_FOUND"
        assert "validation-runs" in payload["error"]["message"] + payload["error"]["resolution"]

    def test_saved_run_readable_via_latest(
        self,
        server: FastMCP,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        run = _call_tool(
            server,
            "run_validation_scenario",
            {"scenario_name": "health-check-baseline", "save": True},
        )
        assert run["success"] is True
        assert run["status"] == "passed"

        payload = _call_tool(server, "get_validation_report", {})
        assert payload["success"] is True
        assert payload["run_dir"]  # the stamp dir read via latest.txt
        assert payload["trace_id"] == run["trace_id"]
        assert payload["scenarios"][0]["status"] == "passed"

    def test_explicit_run_dir_read(
        self,
        server: FastMCP,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        run = _call_tool(
            server,
            "run_validation_scenario",
            {"scenario_name": "health-check-baseline", "save": True},
        )
        assert run["success"] is True
        payload = _call_tool(server, "get_validation_report", {"run_dir": "nope"})
        assert payload["success"] is False
        assert payload["error"]["code"] == "NOT_FOUND"
        # the real stamp is readable by name
        stamp = Path(tmp_path / "validation-runs" / "latest.txt").read_text(
            encoding="utf-8"
        ).strip()
        payload = _call_tool(server, "get_validation_report", {"run_dir": stamp})
        assert payload["success"] is True
        assert payload["run_dir"] == stamp
        assert payload["scenarios"][0]["scenario"] == "health-check-baseline"


# ===================================================================
# validation_coverage_audit
# ===================================================================


class TestValidationCoverageAudit:
    """Tool 4: static audit — the current deterministic numbers.

    The committed ``scenarios/baseline/coverage-audit.json`` is regenerated
    by W4-T7 (``python -m automedia.validation.coverage``) — it now shows
    mcp 63 declared / 56 covered / 0 missing (the W4-T7 meta scenario
    ``validation-self-check`` covers the remaining 3 tools) and cli 18 / 18
    / 0.  This test pins that post-W4-T7 reality.
    """

    def test_audit_reflects_the_four_new_registrations(self, server: FastMCP) -> None:
        payload = _call_tool(server, "validation_coverage_audit", {})
        assert payload["success"] is True
        summary = payload["summary"]
        # 59 pre-existing + the 4 new tools
        assert summary["mcp_declared"] == 63
        assert summary["mcp_used"] == 63
        # the meta scenarios cover all 4 validation tools (W4-T7's
        # validation-self-check closed the 3-tool gap) -> missing = 0
        assert summary["mcp_covered"] == 56
        assert summary["mcp_phantom"] == 0
        assert payload["phantom_mcp"] == []
        assert "list_validation_scenarios" in payload["covered_mcp"]
        assert summary["mcp_missing"] == 0
        assert payload["missing_mcp"] == []
        assert summary["mcp_boundary_only"] == 7

    def test_cli_side_reflects_w4t1_validate_command(self, server: FastMCP) -> None:
        """W4-T1's validate command: declared 18, phantom ∅ (covered via list)."""
        payload = _call_tool(server, "validation_coverage_audit", {})
        summary = payload["summary"]
        assert summary["cli_declared"] == 18
        assert summary["cli_used"] == 18
        assert summary["cli_covered"] == 18
        assert summary["cli_missing"] == 0
        assert summary["cli_phantom"] == 0
        assert payload["phantom_cli"] == []
        assert "validate" in payload["declared_cli"]
