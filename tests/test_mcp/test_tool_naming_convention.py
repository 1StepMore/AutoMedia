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

# Tool names that intentionally break the verb_noun convention.
# Add entries here only when there is a strong semantic reason (e.g. the
# name is a well-known single-word command or product name).
_ALLOWED_VIOLATIONS: set[str] = {
    "onboard",  # mirrors the `automedia onboard` CLI subcommand name
}


def test_all_tool_names_follow_convention() -> None:
    """Every registered MCP tool name must match ^[a-z]+_[a-z]."""
    from automedia.mcp.server import create_server

    server = create_server()
    names = list(server._tool_manager._tools.keys())

    assert len(names) > 0, "Should have registered tools"

    violations: list[str] = []
    for name in names:
        if name in _ALLOWED_VIOLATIONS:
            continue
        if not TOOL_NAME_PATTERN.match(name):
            violations.append(name)

    assert not violations, (
        f"Tool names violating verb_noun convention: {violations}\n"
        f"Expected pattern: {TOOL_NAME_PATTERN.pattern!r}\n"
        f"To add an intentional exception, add to _ALLOWED_VIOLATIONS in this file."
    )
