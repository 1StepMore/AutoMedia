"""Test that the Agent Quickstart content exists in active documentation.

The AGENT_QUICKSTART.md content has been absorbed into README.md (Agent Quickstart
section). This test verifies the onboarding content is preserved there.
"""

from __future__ import annotations

import pytest

README_MD = "README.md"


@pytest.mark.redline
class TestAgentQuickstartExists:
    """Verify README.md contains Agent Quickstart content."""

    def test_has_quickstart_section(self) -> None:
        """README.md must have an Agent Quickstart section."""
        content = _read_readme_md()
        assert "## Agent Quickstart" in content, (
            f"{README_MD} must contain an Agent Quickstart section"
        )

    def test_references_agents_md(self) -> None:
        """Must reference AGENTS.md as a key resource."""
        content = _read_readme_md()
        assert "AGENTS.md" in content, (
            f"{README_MD} must reference AGENTS.md"
        )

    def test_references_mcp(self) -> None:
        """Must mention MCP server setup."""
        content = _read_readme_md()
        assert "MCP" in content, (
            f"{README_MD} must mention MCP"
        )


def _read_readme_md() -> str:
    with open(README_MD, encoding="utf-8") as f:
        return f.read()
