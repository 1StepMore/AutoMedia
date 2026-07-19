"""Test that MCP error code reference content exists in mcp-setup.md.

The error-code-reference.md content has been merged into docs/user/mcp-setup.md
as a dedicated "## Error Code Reference" section.
"""

from __future__ import annotations

import pytest

MCP_SETUP_MD = "docs/user/mcp-setup.md"

# Known error codes that must be documented
REQUIRED_CODES: set[str] = {
    "INVALID_PARAM",
    "NOT_FOUND",
    "PIPELINE_ERROR",
    "ENGINE_ERROR",
    "ALLOWLIST_DENIED",
    "UNKNOWN",
}

# Tools that must appear in the reference
REQUIRED_TOOLS: set[str] = {
    "run_pipeline",
    "archive_project",
    "add_cron_schedule",
    "get_config",
}


@pytest.mark.redline
class TestErrorCodeReferenceExists:
    """Verify docs/user/mcp-setup.md contains Error Code Reference section."""

    def test_has_error_code_section(self) -> None:
        """mcp-setup.md must have an Error Code Reference section."""
        content = _read_mcp_setup_md()
        assert "## Error Code Reference" in content, (
            f"{MCP_SETUP_MD} must contain an Error Code Reference section"
        )

    def test_documents_all_enum_codes(self) -> None:
        """Must document every MCPErrorCode enum member."""
        content = _read_mcp_setup_md()
        for code in REQUIRED_CODES:
            assert code in content, (
                f"{MCP_SETUP_MD} must document error code {code!r}"
            )

    def test_documents_error_shape(self) -> None:
        """Must describe the error response JSON shape."""
        content = _read_mcp_setup_md()
        assert '"error"' in content, (
            f"{MCP_SETUP_MD} must document the error response shape"
        )
        assert '"code"' in content, (
            f"{MCP_SETUP_MD} must document the error code field"
        )
        assert '"resolution"' in content, (
            f"{MCP_SETUP_MD} must document the resolution field"
        )

    def test_references_common_tools(self) -> None:
        """Must reference common tools that return errors."""
        content = _read_mcp_setup_md()
        for tool in REQUIRED_TOOLS:
            assert tool in content, (
                f"{MCP_SETUP_MD} must mention tool {tool!r}"
            )


def _read_mcp_setup_md() -> str:
    with open(MCP_SETUP_MD, encoding="utf-8") as f:
        return f.read()
