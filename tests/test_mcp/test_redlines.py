"""Tests for the ``get_redlines`` MCP red-line introspection tool.

Tests the ``get_redlines`` tool handler in ``automedia.mcp.tools``.
"""
from __future__ import annotations

from automedia.mcp.tools import get_redlines

# ---------------------------------------------------------------------------
# Tests: get_redlines
# ---------------------------------------------------------------------------


def test_get_redlines_returns_dict_with_redlines_and_total() -> None:
    """get_redlines() returns a dict with 'redlines' list and 'total' count."""
    result = get_redlines()
    assert isinstance(result, dict)
    assert "redlines" in result
    assert "total" in result


def test_get_redlines_total_matches_list_length() -> None:
    """The 'total' field matches the length of the 'redlines' list."""
    result = get_redlines()
    assert result["total"] == len(result["redlines"])


def test_get_redlines_has_at_least_eight_entries() -> None:
    """At least 8 red-line constraints are returned (AGENTS.md §5 lists 9)."""
    result = get_redlines()
    assert result["total"] >= 8


def test_get_redlines_entries_are_strings() -> None:
    """Every redline entry is a non-empty string."""
    result = get_redlines()
    for entry in result["redlines"]:
        assert isinstance(entry, str)
        assert len(entry) > 0


def test_get_redlines_contains_must_and_must_not() -> None:
    """Each redline starts with 'MUST' or 'MUST NOT'."""
    result = get_redlines()
    for entry in result["redlines"]:
        assert entry.startswith("MUST") or entry.startswith("MUST NOT")
