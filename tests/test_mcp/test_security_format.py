"""Security tests for the ``format_output`` MCP tool.

Validates that ``target_format`` is strictly validated against an allowlist
and that path-traversal payloads are rejected before any file I/O occurs.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from automedia.mcp.server import format_output


class TestFormatOutputSecurity:
    """target_format validation — allowlist + path-traversal guard."""

    @staticmethod
    def test_reject_path_traversal() -> None:
        """Path-traversal payload in target_format must return an error dict."""
        result = format_output(content="test", target_format="../../etc/passwd")
        assert "error" in result, f"Expected error key, got: {result}"
        assert (
            "unsupported" in result["error"].lower()
            or "invalid" in result["error"].lower()
            or "not allowed" in result["error"].lower()
        )

    @staticmethod
    def test_reject_path_traversal_backslash() -> None:
        """Backslash-based path traversal must be rejected."""
        result = format_output(
            content="test", target_format="..\\..\\windows\\system32\\config\\sam"
        )
        assert "error" in result

    @staticmethod
    def test_reject_absolute_path() -> None:
        """Absolute path injected as format must be rejected."""
        result = format_output(content="test", target_format="/etc/cron.d/evil")
        assert "error" in result

    @staticmethod
    def test_reject_invalid_format() -> None:
        """Unsupported format identifier must return an error dict."""
        result = format_output(content="test", target_format="exe")
        assert "error" in result, f"Expected error key, got: {result}"
        assert "exe" in result["error"]

    @staticmethod
    def test_reject_dot_dot() -> None:
        """Bare ``..`` as format must be rejected."""
        result = format_output(content="test", target_format="..")
        assert "error" in result

    @patch("automedia.omni.orf_adapter.ORFAdapter")
    def test_accept_valid_format(self, mock_orf_class: pytest.MonkeyPatch) -> None:
        """A valid format must proceed to conversion
        (success or adapter error, not validation error)."""
        from automedia.mcp.server import format_output as fo

        # Make the adapter succeed
        mock_orf_class.return_value.convert.return_value = {"errors": []}

        result = fo(content="# Hello", target_format="html")
        # Should NOT have a validation error — should have output_path / output_format keys
        assert "error" not in result, f"Unexpected validation error: {result}"
        assert "output_format" in result
        assert result["output_format"] == "html"
