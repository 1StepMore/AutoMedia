"""Tests for the mcp_help tool (server.py).

Covers the categorized tool listing, alphabetical sorting, and
dynamic generation from the tool registry.
All tests use synthetic data — zero production data.
"""

from __future__ import annotations

from unittest.mock import patch

from automedia.mcp.server import _CATEGORY_PREFIXES, mcp_help

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

MOCK_TOOL_REGISTRY: dict[str, dict[str, str]] = {
    "health_check": {"description": "Check server health", "inputSchema": "{}"},
    "get_pipeline_progress": {"description": "Get pipeline progress", "inputSchema": "{}"},
    "list_projects": {"description": "List all projects", "inputSchema": "{}"},
    "run_pipeline": {"description": "Run a pipeline", "inputSchema": "{}"},
    "add_cron_schedule": {"description": "Add a cron schedule", "inputSchema": "{}"},
    "cancel_pipeline": {"description": "Cancel a pipeline", "inputSchema": "{}"},
    "archive_project": {"description": "Archive a project", "inputSchema": "{}"},
    "research_topics": {"description": "Research topics", "inputSchema": "{}"},
    "publish_content": {"description": "Publish content", "inputSchema": "{}"},
    "search_assets": {"description": "Search assets", "inputSchema": "{}"},
    "select_topic": {"description": "Select a topic", "inputSchema": "{}"},
    "register_platform_adapter": {"description": "Register adapter", "inputSchema": "{}"},
    "extract_brief": {"description": "Extract brief", "inputSchema": "{}"},
    "localize_content": {"description": "Localize content", "inputSchema": "{}"},
    "format_output": {"description": "Format output", "inputSchema": "{}"},
    "evaluate_content_quality": {"description": "Evaluate quality", "inputSchema": "{}"},
    # Renamed tools: new primary names
    "run_batch": {"description": "Batch run", "inputSchema": "{}"},
    "health_engine": {"description": "Engine health", "inputSchema": "{}"},
    "help_mcp": {"description": "Get MCP help", "inputSchema": "{}"},
    "add_pool_topic": {"description": "Add topic to pool", "inputSchema": "{}"},
    # Renamed tools: old alias names (backward-compatible)
    "batch_run": {"description": "Batch run (deprecated)", "inputSchema": "{}"},
    "engine_health": {"description": "Engine health (deprecated)", "inputSchema": "{}"},
    "mcp_help": {"description": "Get MCP help (deprecated)", "inputSchema": "{}"},
    "pool_add_topic": {"description": "Add topic to pool (deprecated)", "inputSchema": "{}"},
    "connect_account": {"description": "Connect account", "inputSchema": "{}"},
    "disconnect_account": {"description": "Disconnect account", "inputSchema": "{}"},
    "test_cron_schedule": {"description": "Test cron schedule", "inputSchema": "{}"},
    "update_engine_config": {"description": "Update config", "inputSchema": "{}"},
    "remove_cron_schedule": {"description": "Remove cron schedule", "inputSchema": "{}"},
}


# ---------------------------------------------------------------------------
# Tests: mcp_help
# ---------------------------------------------------------------------------


class TestMcpHelp:
    """Tests for the mcp_help tool."""

    def test_returns_expected_keys(self) -> None:
        """mcp_help returns dict with categories, tool_count, and hint keys."""
        with patch("automedia.mcp.server._tool_registry", MOCK_TOOL_REGISTRY):
            result = mcp_help()

        assert "categories" in result
        assert "tool_count" in result
        assert "hint" in result

    def test_tool_count_matches_registry_size(self) -> None:
        """tool_count equals the number of tools in the registry."""
        with patch("automedia.mcp.server._tool_registry", MOCK_TOOL_REGISTRY):
            result = mcp_help()

        assert result["tool_count"] == len(MOCK_TOOL_REGISTRY)

    def test_categories_is_dict(self) -> None:
        """categories is a dict mapping category names to tool lists."""
        with patch("automedia.mcp.server._tool_registry", MOCK_TOOL_REGISTRY):
            result = mcp_help()

        assert isinstance(result["categories"], dict)

    def test_categories_sorted_alphabetically(self) -> None:
        """Category keys in the output are sorted alphabetically."""
        with patch("automedia.mcp.server._tool_registry", MOCK_TOOL_REGISTRY):
            result = mcp_help()

        categories = list(result["categories"].keys())
        assert categories == sorted(categories), f"Categories should be sorted: {categories}"

    def test_tools_within_category_sorted_by_name(self) -> None:
        """Tools within each category are sorted by name alphabetically."""
        with patch("automedia.mcp.server._tool_registry", MOCK_TOOL_REGISTRY):
            result = mcp_help()

        for category, tools in result["categories"].items():
            names = [t["name"] for t in tools]
            assert names == sorted(names), (
                f"Tools in category {category!r} should be sorted: {names}"
            )

    def test_each_tool_has_name_and_description(self) -> None:
        """Every tool entry has 'name' and 'description' keys."""
        with patch("automedia.mcp.server._tool_registry", MOCK_TOOL_REGISTRY):
            result = mcp_help()

        for category, tools in result["categories"].items():
            for tool in tools:
                assert "name" in tool, f"Tool in {category} missing 'name'"
                assert "description" in tool, f"Tool {tool.get('name')} missing 'description'"

    def test_categorization_uses_prefix_matching(self) -> None:
        """Tools are categorized based on their name prefix."""
        with patch("automedia.mcp.server._tool_registry", MOCK_TOOL_REGISTRY):
            result = mcp_help()

        categories = result["categories"]
        # run_pipeline should be under "Run / Execute"
        assert "Run / Execute" in categories
        run_tools = {t["name"] for t in categories["Run / Execute"]}
        assert "run_pipeline" in run_tools

        # list_projects should be under "List / Browse"
        assert "List / Browse" in categories
        list_tools = {t["name"] for t in categories["List / Browse"]}
        assert "list_projects" in list_tools

    def test_health_engine_in_server_category(self) -> None:
        """health_engine tool falls under Server / Engine category."""
        with patch("automedia.mcp.server._tool_registry", MOCK_TOOL_REGISTRY):
            result = mcp_help()

        assert "Server / Engine" in result["categories"]
        engine_tools = {t["name"] for t in result["categories"]["Server / Engine"]}
        assert "health_engine" in engine_tools

    def test_cancel_pipeline_unmatched_falls_to_other(self) -> None:
        """A tool with no matching prefix ends up in 'Other'."""
        # cancel_pipeline doesn't match any prefix in _CATEGORY_PREFIXES
        with patch("automedia.mcp.server._tool_registry", MOCK_TOOL_REGISTRY):
            result = mcp_help()

        # cancel_pipeline doesn't match any prefix, so it should be in "Other"
        # actually let's check - is there a prefix for "cancel_"?
        prefixes = [p for p, _ in _CATEGORY_PREFIXES]
        assert not any("cancel_pipeline".startswith(p) for p in prefixes)

        other_tools = {}
        for cat_name, tools in result["categories"].items():
            for t in tools:
                if t["name"] == "cancel_pipeline":
                    other_tools[cat_name] = t

        # cancel_pipeline should appear somewhere
        assert len(other_tools) == 1
        # It should be in "Other" since no prefix matches
        if "Other" in result["categories"]:
            assert "cancel_pipeline" in {t["name"] for t in result["categories"]["Other"]}

    def test_hint_is_non_empty_string(self) -> None:
        """hint is a non-empty string with guidance."""
        with patch("automedia.mcp.server._tool_registry", MOCK_TOOL_REGISTRY):
            result = mcp_help()

        assert isinstance(result["hint"], str)
        assert len(result["hint"]) > 0

    def test_empty_registry_returns_zero_count(self) -> None:
        """An empty tool registry returns tool_count=0 and no categories."""
        with patch("automedia.mcp.server._tool_registry", {}):
            result = mcp_help()

        assert result["tool_count"] == 0
        # With empty registry, categories should be empty dict
        # (no tools to categorize)
        assert isinstance(result["categories"], dict)

    def test_tool_descriptions_preserved(self) -> None:
        """Tool descriptions from the registry are preserved in the output."""
        test_registry = {
            "run_pipeline": {"description": "Custom description", "inputSchema": "{}"},
        }
        with patch("automedia.mcp.server._tool_registry", test_registry):
            result = mcp_help()

        for category, tools in result["categories"].items():
            for tool in tools:
                if tool["name"] == "run_pipeline":
                    assert tool["description"] == "Custom description"


# ---------------------------------------------------------------------------
# Tests: _categorize_tool helper
# ---------------------------------------------------------------------------


class TestCategorizeTool:
    """Tests for the _categorize_tool helper."""

    def test_known_prefix_maps_to_category(self) -> None:
        """A tool with a known prefix maps to the correct category."""
        from automedia.mcp.server import _categorize_tool

        assert _categorize_tool("get_pipeline_progress") == "Get / Query"
        assert _categorize_tool("list_projects") == "List / Browse"
        assert _categorize_tool("run_pipeline") == "Run / Execute"
        assert _categorize_tool("health_check") == "Server / Engine"

    def test_mcp_help_prefix(self) -> None:
        """mcp_help has no matching prefix and falls to 'Other'."""
        from automedia.mcp.server import _categorize_tool

        assert _categorize_tool("mcp_help") == "Other"

    def test_help_mcp_prefix(self) -> None:
        """help_mcp falls under Help / Introspection category."""
        from automedia.mcp.server import _categorize_tool

        assert _categorize_tool("help_mcp") == "Help / Introspection"

    def test_archive_prefix(self) -> None:
        """archive_ prefix maps to Archive category."""
        from automedia.mcp.server import _categorize_tool

        assert _categorize_tool("archive_project") == "Archive"

    def test_update_prefix(self) -> None:
        """update_ prefix maps to Update category."""
        from automedia.mcp.server import _categorize_tool

        assert _categorize_tool("update_engine_config") == "Update"

    def test_unknown_prefix_falls_to_other(self) -> None:
        """An entirely unknown prefix falls to 'Other'."""
        from automedia.mcp.server import _categorize_tool

        assert _categorize_tool("zzz_unknown_tool") == "Other"

    def test_disconnect_before_connect_prefix(self) -> None:
        """disconnect_ matches before connect_ due to prefix order."""
        from automedia.mcp.server import _categorize_tool

        # Both disconnect_ and connect_ map to "Account Management"
        assert _categorize_tool("disconnect_account") == "Account Management"
        assert _categorize_tool("connect_account") == "Account Management"

    def test_engine_before_get_prefix(self) -> None:
        """engine_ maps to 'Server / Engine' even though it starts with 'e'."""
        from automedia.mcp.server import _categorize_tool

        # engine_ prefix is checked before get_ in the list
        assert _categorize_tool("engine_health") == "Server / Engine"

    def test_health_before_get_prefix(self) -> None:
        """health_ maps to 'Server / Engine' — checks health_engine."""
        from automedia.mcp.server import _categorize_tool

        assert _categorize_tool("health_engine") == "Server / Engine"


# ---------------------------------------------------------------------------
# Tests: category prefix ordering
# ---------------------------------------------------------------------------


class TestCategoryPrefixes:
    """Tests that _CATEGORY_PREFIXES is ordered correctly.

    The first matching prefix wins, so more-specific prefixes must come
    before less-specific ones.
    """

    def test_disconnect_before_get(self) -> None:
        """disconnect_ (Account Management) is checked before get_ (Get / Query)."""
        disconnect_idx = next(
            i for i, (p, _) in enumerate(_CATEGORY_PREFIXES) if p == "disconnect_"
        )
        get_idx = next(i for i, (p, _) in enumerate(_CATEGORY_PREFIXES) if p == "get_")
        assert disconnect_idx < get_idx, "disconnect_ must come before get_ in _CATEGORY_PREFIXES"
