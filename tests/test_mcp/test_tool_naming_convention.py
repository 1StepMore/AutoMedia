"""Convention test: all MCP tool names must match the verb_noun pattern.

Enforces the naming convention that every registered MCP tool name must
match ``^[a-z]+_[a-z]`` — a lowercase verb or prefix, underscore, then
at least one lowercase letter (the start of the noun).

This is a regression guard: new tools added without following this
convention will be caught here.
"""

from __future__ import annotations

import re

TOOL_NAME_PATTERN = re.compile(r"^[a-z]+_[a-z]")


def test_all_tool_names_follow_convention() -> None:
    """Every registered MCP tool name must match ^[a-z]+_[a-z]."""
    from automedia.mcp.server import create_server

    server = create_server()
    names = list(server._tool_manager._tools.keys())

    assert len(names) > 0, "Should have registered tools"

    violations: list[str] = []
    for name in names:
        if not TOOL_NAME_PATTERN.match(name):
            violations.append(name)

    assert not violations, (
        f"Tool names violating verb_noun convention: {violations}\n"
        f"Expected pattern: {TOOL_NAME_PATTERN.pattern!r}"
    )


def test_tool_count_includes_aliases() -> None:
    """The tool count includes both primary and deprecated alias names."""
    from automedia.mcp.server import create_server

    server = create_server()
    names = list(server._tool_manager._tools.keys())

    # Both new and old names should be present
    for new_name, old_name in [
        ("add_pool_topic", "pool_add_topic"),
        ("run_batch", "batch_run"),
        ("health_engine", "engine_health"),
        ("help_mcp", "mcp_help"),
    ]:
        assert new_name in names, f"New tool name {new_name!r} should be registered"
        assert old_name in names, f"Old tool name {old_name!r} should still be registered as alias"
