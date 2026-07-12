"""Tests for mcp_allowlist.yaml usability."""

from __future__ import annotations

import os
from pathlib import Path

from automedia.mcp.allowlist import _reset_allowlist_cache, _load_allowlist


class TestAllowlistUsability:
    """Default allowlist should be usable out of the box."""

    def test_allowlist_yaml_parses_correctly(self) -> None:
        """mcp_allowlist.yaml must parse without errors."""
        _reset_allowlist_cache()
        allowlist_path = Path(__file__).parent.parent.parent / "src" / "automedia" / "mcp" / "mcp_allowlist.yaml"
        entries = _load_allowlist(allowlist_path=allowlist_path)
        # Default file should have at least /tmp/automedia/
        assert len(entries) >= 1
        assert any("/tmp/automedia" in os.path.realpath(e) for e in entries)
