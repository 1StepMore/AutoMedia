"""Comprehensive tests for ``automedia init`` command.

Covers:
    - ``_write_model_config`` internal helper
    - ``init_cmd`` dispatch for all template/JSON combinations
    - ``_init_interactive`` wizard
    - ``_init_minimal`` JSON output
    - ``_init_omni`` missing-template errors (JSON + text)
    - ``_init_omni`` JSON success output
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from automedia.cli.app import app

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from *text*."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the last JSON object from *text* (after any ANSI text prefix)."""
    clean = _strip_ansi(text)
    brace = clean.index("{")
    return json.loads(clean[brace:])


def _assert_json_at_end(text: str, expected_subset: dict[str, Any]) -> None:
    """Parse JSON from *text* and assert *expected_subset* is contained."""
    data = _extract_json(text)
    for key, val in expected_subset.items():
        assert data[key] == val, f"Expected {{{key!r}: {val!r}}}, got {data}"


# =========================================================================
# _write_model_config
# =========================================================================


class TestWriteModelConfig:
    """Tests for the internal ``_write_model_config()`` helper."""

    def test_creates_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Directory ``~/.automedia/`` is created if missing."""
        import automedia.cli.commands.init_cmd as init_mod

        cfg_dir = tmp_path / ".automedia"
        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", cfg_dir)
        monkeypatch.setattr(init_mod, "_MODEL_CONFIG_FILE", cfg_dir / "model_config.yaml")

        assert not cfg_dir.exists()
        init_mod._write_model_config({"llm": {"text_generation": {"provider": "test"}}})

        assert cfg_dir.is_dir()
        assert (cfg_dir / "model_config.yaml").is_file()

    def test_writes_valid_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Written YAML can be parsed back to the original dict."""
        import automedia.cli.commands.init_cmd as init_mod

        cfg_dir = tmp_path / ".automedia"
        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", cfg_dir)
        monkeypatch.setattr(init_mod, "_MODEL_CONFIG_FILE", cfg_dir / "model_config.yaml")

        expected = {
            "llm": {"text_generation": {"provider": "anthropic", "model": "claude-3.5-sonnet"}},
        }
        init_mod._write_model_config(expected)

        with open(cfg_dir / "model_config.yaml") as fh:
            actual = yaml.safe_load(fh)
        assert actual == expected

    def test_sets_restrictive_permissions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """File is created with 0o600 permissions."""
        import automedia.cli.commands.init_cmd as init_mod

        cfg_dir = tmp_path / ".automedia"
        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", cfg_dir)
        monkeypatch.setattr(init_mod, "_MODEL_CONFIG_FILE", cfg_dir / "model_config.yaml")

        init_mod._write_model_config({"llm": {"text_generation": {"provider": "x"}}})
        mode = os.stat(cfg_dir / "model_config.yaml").st_mode & 0o777
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_preserves_unicode(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unicode characters are preserved in the written YAML."""
        import automedia.cli.commands.init_cmd as init_mod

        cfg_dir = tmp_path / ".automedia"
        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", cfg_dir)
        monkeypatch.setattr(init_mod, "_MODEL_CONFIG_FILE", cfg_dir / "model_config.yaml")

        data = {"llm": {"text_generation": {"api_key": "🔑"}}}
        init_mod._write_model_config(data)

        content = (cfg_dir / "model_config.yaml").read_text(encoding="utf-8")
        assert "🔑" in content

    def test_existing_directory_reused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Writing a second time reuses existing directory without error."""
        import automedia.cli.commands.init_cmd as init_mod

        cfg_dir = tmp_path / ".automedia"
        cfg_dir.mkdir(parents=True)
        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", cfg_dir)
        monkeypatch.setattr(init_mod, "_MODEL_CONFIG_FILE", cfg_dir / "model_config.yaml")

        init_mod._write_model_config({"v": 1})
        init_mod._write_model_config({"v": 2})

        with open(cfg_dir / "model_config.yaml") as fh:
            actual = yaml.safe_load(fh)
        assert actual == {"v": 2}


# =========================================================================
# init_cmd dispatch — template / JSON combinations
# =========================================================================


class TestInitCmdDispatch:
    """Tests for ``init_cmd()`` routing logic."""

    def test_template_minimal_json_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``init --template minimal --json`` produces valid JSON on stdout."""
        import automedia.cli.commands.init_cmd as init_mod

        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", tmp_path / ".automedia")
        monkeypatch.setattr(
            init_mod, "_MODEL_CONFIG_FILE", tmp_path / ".automedia" / "model_config.yaml"
        )

        result = runner.invoke(app, ["--json", "init", "--template", "minimal"])
        assert result.exit_code == 0

        # The JSON output follows a text message from _write_model_config
        _assert_json_at_end(result.output, {"status": "ok"})
        assert "model_config.yaml" in result.output

    def test_unknown_template_text_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``init --template bogus`` prints an error message to stderr."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init", "--template", "bogus"])
        assert result.exit_code == 1
        assert "Unknown template" in result.output

    def test_unknown_template_json_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``init --template bogus --json`` prints a JSON error."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["--json", "init", "--template", "bogus"])
        assert result.exit_code == 1

        _assert_json_at_end(result.output, {"status": "error"})
        assert "bogus" in result.output

    def test_interactive_not_supported_in_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``init --json`` (without ``--template``) refuses interactive mode."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["--json", "init"])
        assert result.exit_code == 1

        _assert_json_at_end(result.output, {"status": "error"})
        assert "Interactive init not supported" in result.output

    def test_help_includes_omni_flag(self) -> None:
        """``init --help`` includes the ``--omni`` flag."""
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
        clean = _strip_ansi(result.output)
        assert "--omni" in clean

    def test_help_includes_template_option(self) -> None:
        """``init --help`` includes the ``--template`` option."""
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
        clean = _strip_ansi(result.output)
        assert "--template" in clean


# =========================================================================
# _init_interactive — interactive wizard
# =========================================================================


class TestInitInteractive:
    """Tests for the interactive configuration wizard."""

    def test_interactive_creates_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Interactive wizard writes a valid config file."""
        import automedia.cli.commands.init_cmd as init_mod

        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", tmp_path / ".automedia")
        monkeypatch.setattr(
            init_mod, "_MODEL_CONFIG_FILE", tmp_path / ".automedia" / "model_config.yaml"
        )

        result = runner.invoke(
            app,
            ["init"],
            input="openai\ngpt-4o-mini\nsk-test123\nhttps://api.openai.com/v1\n",
        )
        assert result.exit_code == 0
        clean = _strip_ansi(result.output)
        assert "AutoMedia Configuration Wizard" in clean
        assert "Configuration written" in clean

        cfg_file = tmp_path / ".automedia" / "model_config.yaml"
        assert cfg_file.is_file()

        with open(cfg_file) as fh:
            config = yaml.safe_load(fh)
        assert config["llm"]["text_generation"]["provider"] == "openai"
        assert config["llm"]["text_generation"]["model"] == "gpt-4o-mini"
        assert config["llm"]["text_generation"]["api_key"] == "sk-test123"
        assert config["llm"]["text_generation"]["base_url"] == "https://api.openai.com/v1"

    def test_interactive_omits_base_url_when_blank(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the user leaves base_url blank, the key is omitted from config."""
        import automedia.cli.commands.init_cmd as init_mod

        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", tmp_path / ".automedia")
        monkeypatch.setattr(
            init_mod, "_MODEL_CONFIG_FILE", tmp_path / ".automedia" / "model_config.yaml"
        )

        result = runner.invoke(
            app,
            ["init"],
            input="deepseek\ndeepseek-chat\nsk-ds-key\n\n",
        )
        assert result.exit_code == 0

        with open(tmp_path / ".automedia" / "model_config.yaml") as fh:
            config = yaml.safe_load(fh)
        assert config["llm"]["text_generation"]["provider"] == "deepseek"
        assert "base_url" not in config["llm"]["text_generation"]

    def test_interactive_uses_defaults_on_empty_input(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty optional input falls back to the typer prompt defaults."""
        import automedia.cli.commands.init_cmd as init_mod

        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", tmp_path / ".automedia")
        monkeypatch.setattr(
            init_mod, "_MODEL_CONFIG_FILE", tmp_path / ".automedia" / "model_config.yaml"
        )

        # Empty provider, model (use defaults) and blank base_url — API key is required
        # so we must provide it.
        result = runner.invoke(
            app,
            ["init"],
            input="\n\nsk-some-key\n\n",
        )
        assert result.exit_code == 0

        with open(tmp_path / ".automedia" / "model_config.yaml") as fh:
            config = yaml.safe_load(fh)
        assert config["llm"]["text_generation"]["provider"] == "openai"
        assert config["llm"]["text_generation"]["model"] == "gpt-4o-mini"
        assert config["llm"]["text_generation"]["api_key"] == "sk-some-key"
        assert "base_url" not in config["llm"]["text_generation"]


# =========================================================================
# _init_omni — edge cases (missing templates, JSON output)
# =========================================================================


class TestInitOmniEdgeCases:
    """Edge cases for ``_init_omni`` beyond the happy path."""

    def test_omni_missing_templates_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``init --omni --json`` with missing templates returns JSON error."""
        import automedia.cli.commands.init_cmd as init_mod

        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", tmp_path / ".automedia")
        fake_manifests = tmp_path / "no_manifests_here"
        monkeypatch.setattr(init_mod, "_MANIFESTS_DIR", fake_manifests)

        result = runner.invoke(app, ["--json", "init", "--omni"], input="proxy\n50\n")
        assert result.exit_code == 1

        _assert_json_at_end(result.output, {"status": "error"})
        assert "template" in result.output.lower()

    def test_omni_missing_templates_text(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``init --omni`` with missing templates prints text error."""
        import automedia.cli.commands.init_cmd as init_mod

        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", tmp_path / ".automedia")
        fake_manifests = tmp_path / "no_manifests_here"
        monkeypatch.setattr(init_mod, "_MANIFESTS_DIR", fake_manifests)

        result = runner.invoke(app, ["init", "--omni"], input="proxy\n50\n")
        assert result.exit_code == 1

        clean = _strip_ansi(result.output)
        assert "template" in clean.lower()

    def test_omni_json_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``init --omni --json`` produces valid JSON on success."""
        import automedia.cli.commands.init_cmd as init_mod

        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", tmp_path / ".automedia")

        result = runner.invoke(
            app,
            ["--json", "init", "--omni"],
            input="sdk\n100\n",
        )
        assert result.exit_code == 0

        _assert_json_at_end(result.output, {"status": "ok"})
        assert "config_dir" in result.output
        assert "omni_config.yaml" in result.output
        assert "omni_allowlist.yaml" in result.output


# =========================================================================
# _init_minimal — JSON output path (line 114)
# =========================================================================


class TestInitMinimal:
    """Additional tests for ``_init_minimal``."""

    def test_minimal_json_contains_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--template minimal --json`` includes the correct path in output."""
        import automedia.cli.commands.init_cmd as init_mod

        cfg_dir = tmp_path / ".automedia"
        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", cfg_dir)
        monkeypatch.setattr(init_mod, "_MODEL_CONFIG_FILE", cfg_dir / "model_config.yaml")

        result = runner.invoke(app, ["--json", "init", "--template", "minimal"])
        assert result.exit_code == 0

        _assert_json_at_end(result.output, {"status": "ok"})
        assert "model_config.yaml" in result.output

    def test_minimal_creates_file_nonjson(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--template minimal`` (no --json) creates the config file."""
        import automedia.cli.commands.init_cmd as init_mod

        cfg_dir = tmp_path / ".automedia"
        monkeypatch.setattr(init_mod, "_USER_CFG_DIR", cfg_dir)
        monkeypatch.setattr(init_mod, "_MODEL_CONFIG_FILE", cfg_dir / "model_config.yaml")

        result = runner.invoke(app, ["init", "--template", "minimal"])
        assert result.exit_code == 0

        assert (cfg_dir / "model_config.yaml").is_file()

        with open(cfg_dir / "model_config.yaml") as fh:
            config = yaml.safe_load(fh)
        assert config["llm"]["text_generation"]["provider"] == "openai"
        assert config["llm"]["text_generation"]["api_key"] == ""
