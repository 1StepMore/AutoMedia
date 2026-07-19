"""Tests for the dynamic MCP instruction generator (instructions.py).

Verifies that ``generate_instructions()`` produces output containing all
tools from ``_tool_registry``, with readable formatting and sections.
"""

from __future__ import annotations

from typing import Any

from automedia.mcp.instructions import generate_instructions

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

MOCK_TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "health_check": {"description": "Check server health", "parameters": {}},
    "get_pipeline_progress": {"description": "Get pipeline progress", "parameters": {}},
    "list_projects": {"description": "List all projects", "parameters": {}},
    "run_pipeline": {"description": "Run a pipeline", "parameters": {}},
    "add_cron_schedule": {"description": "Add a cron schedule", "parameters": {}},
    "cancel_pipeline": {"description": "Cancel a pipeline", "parameters": {}},
    "archive_project": {"description": "Archive a project", "parameters": {}},
    "research_topics": {"description": "Research topics", "parameters": {}},
    "publish_content": {"description": "Publish content", "parameters": {}},
    "search_assets": {"description": "Search assets", "parameters": {}},
    "select_topic": {"description": "Select a topic", "parameters": {}},
    "register_platform_adapter": {"description": "Register adapter", "parameters": {}},
    "extract_brief": {"description": "Extract brief", "parameters": {}},
    "localize_content": {"description": "Localize content", "parameters": {}},
    "format_output": {"description": "Format output", "parameters": {}},
    "evaluate_content_quality": {"description": "Evaluate quality", "parameters": {}},
    "run_batch": {"description": "Batch run", "parameters": {}},
    "health_engine": {"description": "Engine health", "parameters": {}},
    "help_mcp": {"description": "Get MCP help", "parameters": {}},
    "add_pool_topic": {"description": "Add topic to pool", "parameters": {}},
    "batch_run": {"description": "Batch run (deprecated)", "parameters": {}},
    "engine_health": {"description": "Engine health (deprecated)", "parameters": {}},
    "mcp_help": {"description": "Get MCP help (deprecated)", "parameters": {}},
    "pool_add_topic": {"description": "Add topic to pool (deprecated)", "parameters": {}},
    "connect_account": {"description": "Connect account", "parameters": {}},
    "disconnect_account": {"description": "Disconnect account", "parameters": {}},
    "test_cron_schedule": {"description": "Test cron schedule", "parameters": {}},
    "update_engine_config": {"description": "Update config", "parameters": {}},
    "remove_cron_schedule": {"description": "Remove cron schedule", "parameters": {}},
    "list_accounts": {"description": "List accounts", "parameters": {}},
    "get_account_health": {"description": "Get account health", "parameters": {}},
    "list_cron_schedules": {"description": "List cron schedules", "parameters": {}},
    "get_cron_health": {"description": "Get cron health", "parameters": {}},
    "list_platforms": {"description": "List platforms", "parameters": {}},
    "run_brand_strategy": {"description": "Run brand strategy", "parameters": {}},
    "run_pipeline_from_strategy": {"description": "Run pipeline from strategy", "parameters": {}},
    "get_redlines": {"description": "Get red lines", "parameters": {}},
    "list_overridable_templates": {"description": "List overridable templates", "parameters": {}},
    "list_workflows": {"description": "List workflows", "parameters": {}},
    "list_brands": {"description": "List brands", "parameters": {}},
    "get_config": {"description": "Get config", "parameters": {}},
    "pause_pipeline": {"description": "Pause a pipeline", "parameters": {}},
    "resume_pipeline": {"description": "Resume a pipeline", "parameters": {}},
    "retry_gate": {"description": "Retry a gate", "parameters": {}},
    "skip_gate": {"description": "Skip a gate", "parameters": {}},
    "localize_output": {"description": "Localize output", "parameters": {}},
    "get_pipeline_status": {"description": "Get pipeline status", "parameters": {}},
    "get_project_assets": {"description": "Get project assets", "parameters": {}},
    "approve_gate": {"description": "Approve a gate", "parameters": {}},
    "reject_gate": {"description": "Reject a gate", "parameters": {}},
    "get_pending_approvals": {"description": "Get pending approvals", "parameters": {}},
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerateInstructions:
    """Tests for the generate_instructions function."""

    def test_returns_string(self) -> None:
        """generate_instructions returns a string."""
        result = generate_instructions(MOCK_TOOL_REGISTRY)
        assert isinstance(result, str)

    def test_contains_all_tool_names(self) -> None:
        """Output contains every tool name from the registry."""
        result = generate_instructions(MOCK_TOOL_REGISTRY)
        for name in MOCK_TOOL_REGISTRY:
            assert name in result, f"Tool {name!r} missing from instructions"

    def test_contains_all_tool_descriptions(self) -> None:
        """Output contains descriptions from the registry."""
        result = generate_instructions(MOCK_TOOL_REGISTRY)
        for info in MOCK_TOOL_REGISTRY.values():
            desc = info["description"]
            assert desc in result, f"Description {desc!r} missing from instructions"

    def test_contains_error_handling_section(self) -> None:
        """Output includes the error handling documentation."""
        result = generate_instructions(MOCK_TOOL_REGISTRY)
        assert "ERROR HANDLING" in result
        assert '{"error": "description' in result
        assert "path not allowed" in result
        assert "No pending topics found" in result

    def test_contains_red_lines_section(self) -> None:
        """Output includes the red lines documentation."""
        result = generate_instructions(MOCK_TOOL_REGISTRY)
        assert "RED LINES" in result
        assert "Red Line 8" in result
        assert "force=True" in result

    def test_contains_hitl_section(self) -> None:
        """Output includes the HITL / director mode documentation."""
        result = generate_instructions(MOCK_TOOL_REGISTRY)
        assert "HITL" in result
        assert "automedia hitl approve" in result
        assert "approve_gate" in result
        assert "reject_gate" in result

    def test_contains_workflow_examples(self) -> None:
        """Output includes example multi-step workflows."""
        result = generate_instructions(MOCK_TOOL_REGISTRY)
        assert "Workflow A" in result
        assert "Workflow B" in result
        assert "Workflow C" in result
        assert "Workflow D" in result

    def test_output_starts_with_header(self) -> None:
        """Output starts with the AutoMedia header."""
        result = generate_instructions(MOCK_TOOL_REGISTRY)
        assert result.startswith("AutoMedia — Automated Media Production Pipeline")

    def test_unknown_tools_appear_in_other_section(self) -> None:
        """Tools not in any predefined category appear in 'OTHER TOOLS' section."""
        registry_with_unknown = dict(MOCK_TOOL_REGISTRY)
        registry_with_unknown["zzz_custom_tool"] = {
            "description": "A custom tool not in any category",
            "parameters": {},
        }
        result = generate_instructions(registry_with_unknown)
        assert "OTHER TOOLS" in result
        assert "zzz_custom_tool" in result

    def test_empty_registry_produces_minimal_output(self) -> None:
        """An empty registry produces a minimal output with no tool listings."""
        result = generate_instructions({})
        assert isinstance(result, str)
        assert "AutoMedia" in result
        assert "0 MCP tools" in result or "MCP tools" in result

    def test_readable_format(self) -> None:
        """Output is readable — uses newlines, indentation, and separators."""
        result = generate_instructions(MOCK_TOOL_REGISTRY)
        # Has proper line breaks
        assert "\n" in result
        # Has separator lines (━━━)
        assert "━━━" in result
        # Has tool descriptions with indentation
        for name in list(MOCK_TOOL_REGISTRY)[:3]:
            assert f"  {name}()" in result

    def test_tool_count_in_header(self) -> None:
        """Header includes correct tool count."""
        result = generate_instructions(MOCK_TOOL_REGISTRY)
        expected = f"{len(MOCK_TOOL_REGISTRY)} MCP tools"
        assert expected in result

    def test_regression_real_server_instructions(self) -> None:
        """When called with the real server's registry, all tools appear.

        This is a smoke test using ``create_server()`` to populate the
        actual tool registry and asserting every registered tool name
        shows up in the generated instructions.
        """
        from automedia.mcp.server import _tool_registry, create_server

        create_server()  # populates _tool_registry as a side effect
        assert len(_tool_registry) > 0, "Tool registry should be populated"

        result = generate_instructions(_tool_registry)
        for name in _tool_registry:
            assert name in result, f"Tool {name!r} missing from generated instructions"
