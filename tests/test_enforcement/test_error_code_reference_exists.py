"""Test docs/dev/error-code-reference.md exists and documents MCP error codes.

Enforcement: the MCP error code reference must be present so that agents
and developers can look up error codes, understand error response shapes,
and find resolution steps without reading source code.
"""

from __future__ import annotations

import pytest

ERROR_REFERENCE_MD = "docs/dev/error-code-reference.md"

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
    """Verify docs/dev/error-code-reference.md exists with minimum content."""

    def test_file_exists(self) -> None:
        """Error code reference must exist."""
        content = _read_reference_md()
        assert content, f"{ERROR_REFERENCE_MD} is empty or missing"

    def test_documents_all_enum_codes(self) -> None:
        """Must document every MCPErrorCode enum member."""
        content = _read_reference_md()
        for code in REQUIRED_CODES:
            assert code in content, (
                f"{ERROR_REFERENCE_MD} must document error code {code!r}"
            )

    def test_documents_error_shape(self) -> None:
        """Must describe the error response JSON shape."""
        content = _read_reference_md()
        assert '"error"' in content, (
            f"{ERROR_REFERENCE_MD} must document the error response shape"
        )
        assert '"code"' in content, (
            f"{ERROR_REFERENCE_MD} must document the error code field"
        )
        assert '"resolution"' in content, (
            f"{ERROR_REFERENCE_MD} must document the resolution field"
        )

    def test_references_common_tools(self) -> None:
        """Must reference common tools that return errors."""
        content = _read_reference_md()
        for tool in REQUIRED_TOOLS:
            assert tool in content, (
                f"{ERROR_REFERENCE_MD} must mention tool {tool!r}"
            )


def _read_reference_md() -> str:
    with open(ERROR_REFERENCE_MD, encoding="utf-8") as f:
        return f.read()
