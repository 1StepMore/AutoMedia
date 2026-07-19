"""Test AGENTS.md contains the recommended install section.

Red-line enforcement: the agent-facing docs must list correct install commands
so that AI coding agents know which extras to use.
"""

from __future__ import annotations

import pytest

AGENTS_MD = "AGENTS.md"


@pytest.mark.redline
class TestAgentsInstallSection:
    """Verify AGENTS.md has a 'Recommended Agent Install' section."""

    def test_dev_install_command_present(self) -> None:
        """AGENTS.md must mention ``pip install -e \".[dev]\"``."""
        content = _read_agents_md()
        assert 'pip install -e ".[dev]"' in content, (
            f"{AGENTS_MD} is missing the [dev] install command"
        )

    def test_mcp_install_command_present(self) -> None:
        """AGENTS.md must mention ``pip install -e \".[mcp]\"``."""
        content = _read_agents_md()
        assert 'pip install -e ".[mcp]"' in content, (
            f"{AGENTS_MD} is missing the [mcp] install command"
        )


def _read_agents_md() -> str:
    with open(AGENTS_MD, encoding="utf-8") as f:
        return f.read()
