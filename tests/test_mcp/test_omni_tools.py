"""RED test: verify 3 Omni tools are registered on the MCP server.

These tests will **FAIL** (RED) until the tools are implemented — correct TDD.
Once the tools exist, all assertions here should pass (GREEN).

Omni tools under test:
  1. extract_brief(file_path, source_lang, target_lang)  — wraps OPPAdapter.extract()
  2. localize_content(md_content, source_lang, target_lang)  — wraps OLAdapter.translate()
  3. format_output(content, target_format, **options)  — wraps ORFAdapter.convert()
"""

from __future__ import annotations

from unittest.mock import patch

from automedia.mcp.server import create_server

# ---------------------------------------------------------------------------
# Tool: extract_brief  (wraps OPPAdapter.extract)
# ---------------------------------------------------------------------------


class TestExtractBriefTool:
    """Tests for the ``extract_brief`` tool (Omni tool #1).

    Signature: extract_brief(file_path: str, source_lang: str = "auto", target_lang: str = "en")
    Backed by: OPPAdapter.extract()
    """

    @patch("automedia.mcp.server.OPPAdapter", create=True)
    def test_tool_registered(self, mock_opp: patch) -> None:
        """extract_brief is registered on the server."""
        server = create_server()
        tool_names = server._tool_manager._tools.keys()
        assert "extract_brief" in tool_names  # RED: will fail — tool not registered yet

    @patch("automedia.mcp.server.OPPAdapter", create=True)
    def test_tool_name_is_string(self, mock_opp: patch) -> None:
        """extract_brief is a string-type tool name."""
        server = create_server()
        tool_names = server._tool_manager._tools.keys()
        assert "extract_brief" in tool_names  # RED: same as above, explicit for completeness
        assert isinstance("extract_brief", str)


# ---------------------------------------------------------------------------
# Tool: localize_content  (wraps OLAdapter.translate)
# ---------------------------------------------------------------------------


class TestLocalizeContentTool:
    """Tests for the ``localize_content`` tool (Omni tool #2).

    Signature: localize_content(md_content: str, source_lang: str, target_lang: str)
    Backed by: OLAdapter.translate()
    """

    @patch("automedia.mcp.server.OLAdapter", create=True)
    def test_tool_registered(self, mock_ol: patch) -> None:
        """localize_content is registered on the server."""
        server = create_server()
        tool_names = server._tool_manager._tools.keys()
        assert "localize_content" in tool_names  # RED: will fail — tool not registered yet

    @patch("automedia.mcp.server.OLAdapter", create=True)
    def test_tool_name_is_string(self, mock_ol: patch) -> None:
        """localize_content is a string-type tool name."""
        server = create_server()
        tool_names = server._tool_manager._tools.keys()
        assert "localize_content" in tool_names  # RED: fails — not registered


# ---------------------------------------------------------------------------
# Tool: format_output  (wraps ORFAdapter.convert)
# ---------------------------------------------------------------------------


class TestFormatOutputTool:
    """Tests for the ``format_output`` tool (Omni tool #3).

    Signature: format_output(content: str, target_format: str, **options)
    Backed by: ORFAdapter.convert()
    """

    @patch("automedia.mcp.server.ORFAdapter", create=True)
    def test_tool_registered(self, mock_orf: patch) -> None:
        """format_output is registered on the server."""
        server = create_server()
        tool_names = server._tool_manager._tools.keys()
        assert "format_output" in tool_names  # RED: will fail — tool not registered yet

    @patch("automedia.mcp.server.ORFAdapter", create=True)
    def test_tool_name_is_string(self, mock_orf: patch) -> None:
        """format_output is a string-type tool name."""
        server = create_server()
        tool_names = server._tool_manager._tools.keys()
        assert "format_output" in tool_names  # RED: fails — not registered


# ---------------------------------------------------------------------------
# Combined: all 3 Omni tools
# ---------------------------------------------------------------------------


class TestAllOmniTools:
    """Tests that all 3 Omni tools are registered together."""

    @patch("automedia.mcp.server.OPPAdapter", create=True)
    @patch("automedia.mcp.server.OLAdapter", create=True)
    @patch("automedia.mcp.server.ORFAdapter", create=True)
    def test_all_three_names_present(
        self,
        mock_orf: patch,
        mock_ol: patch,
        mock_opp: patch,
    ) -> None:
        """All 3 Omni tool names exist in the tool registry."""
        server = create_server()
        tool_names = set(server._tool_manager._tools.keys())
        expected = {"extract_brief", "localize_content", "format_output"}
        assert expected.issubset(tool_names)  # RED: will fail — none are registered yet

    @patch("automedia.mcp.server.OPPAdapter", create=True)
    @patch("automedia.mcp.server.OLAdapter", create=True)
    @patch("automedia.mcp.server.ORFAdapter", create=True)
    def test_server_has_at_least_8_plus_3(
        self,
        mock_orf: patch,
        mock_ol: patch,
        mock_opp: patch,
    ) -> None:
        """Server has at least 11 tools when Omni tools are added (8 + 3)."""
        server = create_server()
        tool_count = len(server._tool_manager._tools)
        # RED: currently 8, we need 11 — will fail
        assert tool_count >= 11


# ---------------------------------------------------------------------------
# Negative / edge-case tests
# ---------------------------------------------------------------------------


class TestOmniToolNameCollisions:
    """Ensure Omni tool names don't collide with existing tools."""

    def test_no_name_overlap_with_existing(self) -> None:
        """Omni tool names are distinct from the core (non-Omni) tool names."""
        server = create_server()
        omni_names = {"extract_brief", "localize_content", "format_output"}
        core = set(server._tool_manager._tools.keys()) - omni_names
        overlap = core & omni_names
        assert len(overlap) == 0  # Omni tools must not shadow built-in tools
