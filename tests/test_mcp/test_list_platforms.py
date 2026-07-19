"""Tests for MCP platform listing tool — ``list_platforms``.

Tests the ``list_platforms`` MCP tool handler in ``automedia.mcp.tools``.
Uses ``@patch`` on ``AdapterRegistry.list`` to avoid singletons affecting
other tests.
"""

from __future__ import annotations

from unittest.mock import patch

from automedia.mcp.tools import list_platforms


class TestListPlatforms:
    """list_platforms() must return sorted platform names and count."""

    def test_returns_platforms_and_total(self) -> None:
        """Returns dict with 'platforms' (list of str) and 'total' (int)."""
        with patch(
            "automedia.adapters.registry.AdapterRegistry.list",
            return_value=["wechat", "weibo", "xiaohongshu"],
        ):
            result = list_platforms()

        assert result["success"] is True
        assert result["platforms"] == ["wechat", "weibo", "xiaohongshu"]
        assert result["total"] == 3

    def test_empty_when_no_adapters(self) -> None:
        """Returns empty list when no adapters are registered."""
        with patch(
            "automedia.adapters.registry.AdapterRegistry.list",
            return_value=[],
        ):
            result = list_platforms()

        assert result["success"] is True
        assert result["platforms"] == []
        assert result["total"] == 0

    def test_error_handling(self) -> None:
        """Returns zeroed response when AdapterRegistry raises."""
        with patch(
            "automedia.adapters.registry.AdapterRegistry.list",
            side_effect=RuntimeError("registry broken"),
        ):
            result = list_platforms()

        assert result["platforms"] == []
        assert result["total"] == 0
        assert "error" in result
