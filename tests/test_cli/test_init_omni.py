"""Tests for ``automedia init --omni`` interactive wizard."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from automedia.cli.app import app

runner = CliRunner()


class TestInitOmniCommand:
    """Tests for ``automedia init --omni``."""

    def test_omni_flag_in_help(self) -> None:
        """``--help`` output includes the ``--omni`` flag."""
        result = runner.invoke(app, ["init", "--help"], color=False)
        assert result.exit_code == 0
        assert "--omni" in result.output

    def test_omni_creates_config_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All expected config files are created under ``~/.automedia/``."""
        monkeypatch.setenv("HOME", str(tmp_path))
        import automedia.cli.commands.init_cmd as init_mod

        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", tmp_path / ".automedia")

        result = runner.invoke(
            app,
            ["init", "--omni"],
            input="proxy\n50\n",
        )
        assert result.exit_code == 0

        cfg_dir = tmp_path / ".automedia"
        assert (cfg_dir / "omni_config.yaml").is_file()
        assert (cfg_dir / "omni_allowlist.yaml").is_file()
        assert (cfg_dir / "omni" / "ol_config.yaml").is_file()

    def test_omni_config_contains_custom_values(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User-provided values appear in the written config."""
        monkeypatch.setenv("HOME", str(tmp_path))
        import automedia.cli.commands.init_cmd as init_mod

        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", tmp_path / ".automedia")

        result = runner.invoke(
            app,
            ["init", "--omni"],
            input="sdk\n100\n",
        )
        assert result.exit_code == 0

        with open(tmp_path / ".automedia" / "omni_config.yaml") as fh:
            config = yaml.safe_load(fh)
        assert config["integration_mode"] == "sdk"
        assert config["max_auto_extract_mb"] == 100

    def test_omni_config_default_values(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defaults are used when the user provides empty input."""
        monkeypatch.setenv("HOME", str(tmp_path))
        import automedia.cli.commands.init_cmd as init_mod

        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", tmp_path / ".automedia")

        result = runner.invoke(
            app,
            ["init", "--omni"],
            input="\n\n",
        )
        assert result.exit_code == 0

        with open(tmp_path / ".automedia" / "omni_config.yaml") as fh:
            config = yaml.safe_load(fh)
        assert config["integration_mode"] == "proxy"
        assert config["max_auto_extract_mb"] == 50

    def test_omni_template_copy_preserves_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Copied template files contain expected content."""
        monkeypatch.setenv("HOME", str(tmp_path))
        import automedia.cli.commands.init_cmd as init_mod

        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", tmp_path / ".automedia")

        result = runner.invoke(
            app,
            ["init", "--omni"],
            input="parallel\n75\n",
        )
        assert result.exit_code == 0

        cfg_dir = tmp_path / ".automedia"

        # allowlist — check it has expected keys
        with open(cfg_dir / "omni_allowlist.yaml") as fh:
            allowlist = yaml.safe_load(fh)
        assert "allowed_paths" in allowlist
        assert "write_paths" in allowlist

        # ol_config — check it has expected keys
        with open(cfg_dir / "omni" / "ol_config.yaml") as fh:
            ol_cfg = yaml.safe_load(fh)
        assert "source_lang" in ol_cfg
        assert "target_lang" in ol_cfg
        assert "llm_pool" in ol_cfg

    def test_omni_success_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A green success message is printed after init completes."""
        monkeypatch.setenv("HOME", str(tmp_path))
        import automedia.cli.commands.init_cmd as init_mod

        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", tmp_path / ".automedia")

        result = runner.invoke(
            app,
            ["init", "--omni"],
            input="proxy\n50\n",
        )
        assert result.exit_code == 0
        assert "Omni configuration written" in result.output
        assert "omni_config.yaml" in result.output
        assert "omni_allowlist.yaml" in result.output
        assert "ol_config.yaml" in result.output

    def test_omni_creates_directory_if_not_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ``~/.automedia/`` directory is created if absent."""
        monkeypatch.setenv("HOME", str(tmp_path))
        import automedia.cli.commands.init_cmd as init_mod

        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", tmp_path / ".automedia")

        assert not (tmp_path / ".automedia").exists()

        result = runner.invoke(
            app,
            ["init", "--omni"],
            input="proxy\n50\n",
        )
        assert result.exit_code == 0
        assert (tmp_path / ".automedia").is_dir()
