"""Tests for MCP setup tools: init_config, configure_llm, add_brand.

Tests the three first-time setup tool handlers in
:mod:`automedia.mcp.tools`.  Uses ``@patch`` to avoid file-system
side effects on the real ``~/.automedia/`` directory.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from automedia.mcp.tools import add_brand, configure_llm, init_config

# ===================================================================
# Tests: init_config
# ===================================================================


class TestInitConfig:
    """Tests for the ``init_config`` MCP tool."""

    def test_creates_dot_automedia_directory(self, tmp_path: Path) -> None:
        """init_config creates .automedia/ directory at project_dir."""
        result = init_config(project_dir=str(tmp_path))
        assert result["success"] is True
        assert (tmp_path / ".automedia").is_dir()
        assert (tmp_path / ".automedia" / "config.yaml").is_file()

    def test_returns_config_paths(self, tmp_path: Path) -> None:
        """init_config returns config_dir and config_file paths."""
        result = init_config(project_dir=str(tmp_path))
        assert "config_dir" in result
        assert "config_file" in result
        assert str(tmp_path) in result["config_dir"]
        assert "config.yaml" in result["config_file"]

    def test_idempotent_when_config_exists(self, tmp_path: Path) -> None:
        """init_config is idempotent — calling twice does not error."""
        r1 = init_config(project_dir=str(tmp_path))
        r2 = init_config(project_dir=str(tmp_path))
        assert r1["success"] is True
        assert r2["success"] is True
        assert r1["config_dir"] == r2["config_dir"]
        assert r1["config_file"] == r2["config_file"]

    def test_error_on_invalid_path(self) -> None:
        """init_config handles invalid paths gracefully."""
        result = init_config(project_dir="/nonexistent_parent_dir_42")
        assert result["success"] is False
        assert "error" in result


# ===================================================================
# Tests: configure_llm
# ===================================================================


class TestConfigureLLM:
    """Tests for the ``configure_llm`` MCP tool."""

    def test_returns_success_with_provider(self, tmp_path: Path) -> None:
        """configure_llm returns success=True with provider info."""
        with (
            patch(
                "automedia.cli.commands.init_cmd._USER_CFG_DIR",
                tmp_path,
            ),
            patch(
                "automedia.cli.commands.init_cmd._MODEL_CONFIG_FILE",
                tmp_path / "model_config.yaml",
            ),
        ):
            result = configure_llm(provider="deepseek", model="deepseek-chat")

        assert result["success"] is True
        assert result["provider"] == "deepseek"
        assert result["model"] == "deepseek-chat"
        assert "config_file" in result

    def test_writes_config_file(self, tmp_path: Path) -> None:
        """configure_llm writes model_config.yaml to disk."""
        with (
            patch(
                "automedia.cli.commands.init_cmd._USER_CFG_DIR",
                tmp_path,
            ),
            patch(
                "automedia.cli.commands.init_cmd._MODEL_CONFIG_FILE",
                tmp_path / "model_config.yaml",
            ),
        ):
            configure_llm(provider="openai", model="gpt-4o-mini")

        assert (tmp_path / "model_config.yaml").is_file()

    def test_accepts_api_key(self, tmp_path: Path) -> None:
        """configure_llm accepts optional api_key."""
        with (
            patch(
                "automedia.cli.commands.init_cmd._USER_CFG_DIR",
                tmp_path,
            ),
            patch(
                "automedia.cli.commands.init_cmd._MODEL_CONFIG_FILE",
                tmp_path / "model_config.yaml",
            ),
        ):
            result = configure_llm(
                provider="anthropic",
                model="claude-3-sonnet-20240229",
                api_key="sk-test-123",
            )

        assert result["success"] is True
        assert result["provider"] == "anthropic"

        # Verify the key was written to the file
        content = (tmp_path / "model_config.yaml").read_text(encoding="utf-8")
        assert "sk-test-123" in content

    def test_handles_empty_provider(self, tmp_path: Path) -> None:
        """configure_llm handles empty provider gracefully (writes empty)."""
        with (
            patch(
                "automedia.cli.commands.init_cmd._USER_CFG_DIR",
                tmp_path,
            ),
            patch(
                "automedia.cli.commands.init_cmd._MODEL_CONFIG_FILE",
                tmp_path / "model_config.yaml",
            ),
        ):
            result = configure_llm(provider="")

        assert result["success"] is True
        assert result["provider"] == ""


# ===================================================================
# Tests: add_brand
# ===================================================================


class TestAddBrand:
    """Tests for the ``add_brand`` MCP tool."""

    def test_returns_success_with_brand_info(self) -> None:
        """add_brand returns success=True with brand metadata."""
        with patch(
            "automedia.manifests.brand_profile_schema.save_brand_profile",
        ) as mock_save:
            result = add_brand(
                name="test-brand",
                industry="Technology",
                target_audience="Developers",
            )

        assert result["success"] is True
        assert result["brand_name"] == "test-brand"
        assert result["industry"] == "Technology"
        assert result["target_audience"] == "Developers"
        # Verify save_brand_profile was called with the right data
        mock_save.assert_called_once_with(
            "test-brand",
            {
                "brand_name": "test-brand",
                "industry": "Technology",
                "target_audience": "Developers",
            },
        )

    def test_with_minimal_fields(self) -> None:
        """add_brand works with only the required name field."""
        with patch(
            "automedia.manifests.brand_profile_schema.save_brand_profile",
        ) as mock_save:
            result = add_brand(name="minimal-brand")

        assert result["success"] is True
        assert result["brand_name"] == "minimal-brand"
        assert result["industry"] == ""
        assert result["target_audience"] == ""
        mock_save.assert_called_once_with(
            "minimal-brand",
            {"brand_name": "minimal-brand"},
        )

    def test_error_on_save_failure(self) -> None:
        """add_brand returns error when save_brand_profile raises."""
        with patch(
            "automedia.manifests.brand_profile_schema.save_brand_profile",
            side_effect=OSError("save failed"),
        ):
            result = add_brand(name="")

        assert result["success"] is False
        assert "error" in result


# ===================================================================
# Tests: module-level import verification
# ===================================================================


class TestToolsImport:
    """All three setup tools are importable from tools module."""

    def test_all_tools_available(self) -> None:
        """All three tool functions are importable."""
        from automedia.mcp.tools import add_brand, configure_llm, init_config

        assert callable(init_config)
        assert callable(configure_llm)
        assert callable(add_brand)


# ===================================================================
# Tests: server registration
# ===================================================================


class TestServerRegistration:
    """All three setup tools are registered on the MCP server."""

    def test_tools_registered_on_server(self) -> None:
        """init_config, configure_llm, and add_brand are registered."""
        from automedia.mcp.server import create_server

        server = create_server()
        tool_names = list(server._tool_manager._tools.keys())

        assert "init_config" in tool_names
        assert "configure_llm" in tool_names
        assert "add_brand" in tool_names
