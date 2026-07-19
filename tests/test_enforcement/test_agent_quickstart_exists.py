"""Test AGENT_QUICKSTART.md exists and contains minimum onboarding content.

Red-line enforcement: the agent onboarding guide must be present for any
agent entering the codebase for the first time, ensuring they know where
to find AGENTS.md, how to connect MCP, and how to verify their setup.
"""

from __future__ import annotations

import pytest

QUICKSTART_MD = "docs/AGENT_QUICKSTART.md"


@pytest.mark.redline
class TestAgentQuickstartExists:
    """Verify docs/AGENT_QUICKSTART.md exists with minimum content."""

    def test_file_exists(self) -> None:
        """AGENT_QUICKSTART.md must exist."""
        content = _read_quickstart_md()
        assert content, f"{QUICKSTART_MD} is empty or missing"

    def test_references_agents_md(self) -> None:
        """Must reference AGENTS.md as the first step."""
        content = _read_quickstart_md()
        assert "AGENTS.md" in content, (
            f"{QUICKSTART_MD} must reference AGENTS.md"
        )

    def test_references_mcp(self) -> None:
        """Must mention MCP server setup."""
        content = _read_quickstart_md()
        assert "MCP" in content, (
            f"{QUICKSTART_MD} must mention MCP"
        )

    def test_has_six_steps(self) -> None:
        """Must contain 6-step onboarding structure."""
        content = _read_quickstart_md()
        step_count = content.count("## Step ")
        assert step_count == 6, (
            f"{QUICKSTART_MD} must have 6 steps, found {step_count}"
        )

    def test_has_install_command(self) -> None:
        """Must include a pip install command."""
        content = _read_quickstart_md()
        assert "pip install" in content, (
            f"{QUICKSTART_MD} must include an install command"
        )


def _read_quickstart_md() -> str:
    with open(QUICKSTART_MD, encoding="utf-8") as f:
        return f.read()
