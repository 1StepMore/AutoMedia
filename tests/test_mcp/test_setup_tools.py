"""Tests for MCP setup tools: init_config, configure_llm, add_brand.

Tests the three first-time setup tool handlers in
:mod:`automedia.mcp.tools`.  Every test that can reach the model-config
writer is isolated through ``AUTOMEDIA_CONFIG_DIR`` (a ``tmp_path``), which
is the same escape hatch the product's user-scope guard recognises: a test
that forgot to isolate would write into the real ``~/.automedia`` and fail
the guard loudly instead of passing silently (issue #208).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from automedia.mcp.tools import add_brand, configure_llm, init_config, onboard

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


def _model_config_under(tmp_path: Path) -> Path:
    """Return the model_config.yaml path inside an isolated config dir."""
    return tmp_path / "model_config.yaml"


class TestConfigureLLM:
    """Tests for the ``configure_llm`` MCP tool."""

    @pytest.fixture(autouse=True)
    def _isolate_user_config_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Redirect every user-config write of these tests into *tmp_path*."""
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))

    def test_returns_success_with_provider(self, tmp_path: Path) -> None:
        """configure_llm returns success=True with provider info."""
        cfg_file = _model_config_under(tmp_path)

        result = configure_llm(provider="deepseek", model="deepseek-chat")

        assert result["success"] is True
        assert result["provider"] == "deepseek"
        assert result["model"] == "deepseek-chat"
        assert "config_file" in result
        assert cfg_file.is_file()

    def test_writes_config_file(self, tmp_path: Path) -> None:
        """configure_llm writes model_config.yaml to disk."""
        cfg_file = _model_config_under(tmp_path)

        configure_llm(provider="openai", model="gpt-4o-mini")

        assert cfg_file.is_file()
        assert "provider: openai" in cfg_file.read_text(encoding="utf-8")

    def test_accepts_api_key(self, tmp_path: Path) -> None:
        """configure_llm accepts optional api_key."""
        cfg_file = _model_config_under(tmp_path)

        result = configure_llm(
            provider="anthropic",
            model="claude-3-sonnet-20240229",
            api_key="sk-test-123",
        )

        assert result["success"] is True
        assert result["provider"] == "anthropic"

        # Verify the key was written to the file
        content = cfg_file.read_text(encoding="utf-8")
        assert "sk-test-123" in content

    def test_handles_empty_provider(self, tmp_path: Path) -> None:
        """configure_llm refuses an empty provider instead of writing it.

        Contract changed by issue #208: an empty provider used to be written
        as ``provider: ''`` — a config that looks configured but resolves to
        nothing at runtime.  It is now refused, and an existing config is
        left untouched.
        """
        cfg_file = _model_config_under(tmp_path)
        cfg_file.write_text(
            "llm:\n  text_generation:\n    provider: amd\n",
            encoding="utf-8",
        )

        result = configure_llm(provider="")

        assert result["success"] is False
        assert "error" in result
        assert "provider" in str(result["error"])
        assert "provider: amd" in cfg_file.read_text(encoding="utf-8")

    def test_refusal_creates_no_backup(self, tmp_path: Path) -> None:
        """A refused write aborts before the backup step."""
        cfg_file = _model_config_under(tmp_path)
        cfg_file.write_text("llm:\n  text_generation:\n    provider: amd\n", encoding="utf-8")

        configure_llm(provider="")

        assert not list(tmp_path.glob("model_config.yaml.bak-*"))

    def test_backs_up_existing_config(self, tmp_path: Path) -> None:
        """A successful write backs up the previous file first (issue #208)."""
        cfg_file = _model_config_under(tmp_path)
        cfg_file.write_text(
            "llm:\n  text_generation:\n    provider: amd\n    model: old-model\n",
            encoding="utf-8",
        )
        before = cfg_file.read_text(encoding="utf-8")

        result = configure_llm(provider="deepseek", model="deepseek-chat")

        assert result["success"] is True
        backups = sorted(tmp_path.glob("model_config.yaml.bak-*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == before
        assert "provider: deepseek" in cfg_file.read_text(encoding="utf-8")

    def test_preserves_existing_fallback(self, tmp_path: Path) -> None:
        """configure_llm preserves an existing fallback list on update."""
        cfg_file = _model_config_under(tmp_path)
        cfg_file.write_text(
            "llm:\n"
            "  text_generation:\n"
            "    provider: old-provider\n"
            "    model: old-model\n"
            "    fallback:\n"
            "      - provider: fallback-provider\n"
            "        model: fallback-model\n",
            encoding="utf-8",
        )

        result = configure_llm(provider="deepseek", model="deepseek-chat")

        assert result["success"] is True
        content = cfg_file.read_text(encoding="utf-8")
        assert "fallback-provider" in content
        assert "fallback-model" in content
        assert "deepseek" in content
        assert "deepseek-chat" in content

    def test_preserves_existing_base_url(self, tmp_path: Path) -> None:
        """configure_llm preserves an existing base_url when not updated."""
        cfg_file = _model_config_under(tmp_path)
        cfg_file.write_text(
            "llm:\n"
            "  text_generation:\n"
            "    provider: old-provider\n"
            "    base_url: https://custom.example.com/v1\n",
            encoding="utf-8",
        )

        result = configure_llm(provider="deepseek", model="deepseek-chat")

        assert result["success"] is True
        content = cfg_file.read_text(encoding="utf-8")
        assert "https://custom.example.com/v1" in content
        assert "deepseek" in content

    def test_regression_83_configure_llm_preserves_fallback(self, tmp_path: Path) -> None:
        """Regression #83: configure_llm must not destroy an existing fallback chain.

        Before the fix, configure_llm did a destructive full-file overwrite of
        model_config.yaml, silently destroying any existing LLM fallback list.
        The fix makes it use the merge-preserving save_model_config writer so
        that absent keys (like fallback) are kept intact while provider/model
        are updated.
        """
        cfg_file = _model_config_under(tmp_path)
        cfg_file.write_text(
            "llm:\n"
            "  text_generation:\n"
            "    provider: old-provider\n"
            "    model: old-model\n"
            "    fallback:\n"
            "      - provider: fb-provider\n"
            "        model: fb-model\n",
            encoding="utf-8",
        )

        result = configure_llm(provider="deepseek", model="deepseek-chat")

        assert result["success"] is True
        content = cfg_file.read_text(encoding="utf-8")
        assert "deepseek" in content
        assert "deepseek-chat" in content
        assert "fb-provider" in content
        assert "fb-model" in content


# ===================================================================
# Tests: onboard
# ===================================================================


class TestOnboard:
    """Tests for the ``onboard`` MCP tool."""

    @pytest.fixture(autouse=True)
    def _isolate_user_config_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Redirect every user-config write of these tests into *tmp_path*."""
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))

    def test_base_url_merge_preserves_fallback(self, tmp_path: Path) -> None:
        """onboard's base_url merge preserves an existing fallback list."""
        cfg_file = tmp_path / "model_config.yaml"
        cfg_file.write_text(
            "llm:\n"
            "  text_generation:\n"
            "    provider: old-provider\n"
            "    fallback:\n"
            "      - provider: fallback-provider\n"
            "        model: fallback-model\n",
            encoding="utf-8",
        )

        result = onboard(
            llm_provider="deepseek",
            llm_key="sk-test-123",
            base_url="https://custom.example.com/v1",
        )

        assert result["success"] is True
        content = cfg_file.read_text(encoding="utf-8")
        assert "fallback-provider" in content
        assert "fallback-model" in content
        assert "https://custom.example.com/v1" in content
        assert "deepseek" in content

    def test_empty_provider_is_refused(self, tmp_path: Path) -> None:
        """onboard with an empty provider configures nothing and succeeds.

        A blank ``llm_provider`` means "skip LLM setup" (the brand step may
        still run), so it must not reach the writer and must not be reported
        as a configured LLM.
        """
        result = onboard(llm_provider="", brand_name="")

        assert result["success"] is True
        assert "llm" not in result
        assert not (tmp_path / "model_config.yaml").exists()


# ===================================================================
# Tests: add_brand
# ===================================================================


class TestAddBrand:
    """Tests for the ``add_brand`` MCP tool."""

    def test_returns_success_with_brand_info(self) -> None:
        """add_brand returns success=True with brand metadata."""
        with patch(
            "automedia.mcp.tools.brands.save_brand_profile",
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
            "automedia.mcp.tools.brands.save_brand_profile",
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
            "automedia.mcp.tools.brands.save_brand_profile",
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
