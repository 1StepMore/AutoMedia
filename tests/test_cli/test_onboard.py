"""Tests for ``automedia onboard --step llm`` behavior.

Covers:
    - LLM step writes provider/model to model_config.yaml
    - LLM step warns when no fallback is configured
    - LLM step adds a fallback provider interactively
    - LLM step preserves an existing fallback on re-run
    - LLM step rerun preserves previously added fallback
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from automedia.cli.app import app

runner = CliRunner()


class TestOnboardStepLlm:
    """Tests for the LLM onboarding step."""

    def test_llm_step_writes_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Writing provider/model works and no fallback is added when declined."""
        import automedia.cli.commands.onboard as onboard_mod

        monkeypatch.setattr(onboard_mod, "_USER_CFG_DIR", tmp_path)
        result = runner.invoke(
            app,
            ["onboard", "start", "--step", "llm"],
            input="deepseek\ndeepseek-chat\nsk-key\n\n0.7\n2048\nn\n",
        )
        assert result.exit_code == 0

        cfg_file = tmp_path / "model_config.yaml"
        assert cfg_file.is_file()

        with open(cfg_file, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
        assert config["llm"]["text_generation"]["provider"] == "deepseek"
        assert config["llm"]["text_generation"]["model"] == "deepseek-chat"
        assert config["llm"]["text_generation"]["api_key"] == "sk-key"
        assert "fallback" not in config["llm"]["text_generation"]

    def test_llm_step_warns_on_no_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A warning mentioning fallback appears when no fallback is configured."""
        import automedia.cli.commands.onboard as onboard_mod

        monkeypatch.setattr(onboard_mod, "_USER_CFG_DIR", tmp_path)
        result = runner.invoke(
            app,
            ["onboard", "start", "--step", "llm"],
            input="deepseek\ndeepseek-chat\nsk-key\n\n0.7\n2048\nn\n",
        )
        assert result.exit_code == 0
        assert "fallback" in result.output.lower()

    def test_llm_step_adds_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Accepting the fallback prompt adds a fallback entry to the YAML."""
        import automedia.cli.commands.onboard as onboard_mod

        monkeypatch.setattr(onboard_mod, "_USER_CFG_DIR", tmp_path)
        result = runner.invoke(
            app,
            ["onboard", "start", "--step", "llm"],
            input="deepseek\ndeepseek-chat\nsk-key\n\n0.7\n2048\ny\nopenai\ngpt-4o-mini\nfb-sk-key\n\n",
        )
        assert result.exit_code == 0

        cfg_file = tmp_path / "model_config.yaml"
        with open(cfg_file, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)

        fallback = config["llm"]["text_generation"].get("fallback", [])
        assert len(fallback) == 1
        assert fallback[0]["provider"] == "openai"
        assert fallback[0]["model"] == "gpt-4o-mini"
        assert fallback[0]["api_key"] == "fb-sk-key"
        assert "base_url" not in fallback[0]

    def test_llm_step_preserves_existing_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A pre-existing fallback list survives the LLM step when declined."""
        import automedia.cli.commands.onboard as onboard_mod

        monkeypatch.setattr(onboard_mod, "_USER_CFG_DIR", tmp_path)

        cfg_file = tmp_path / "model_config.yaml"
        tmp_path.mkdir(parents=True, exist_ok=True)
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

        result = runner.invoke(
            app,
            ["onboard", "start", "--step", "llm"],
            input="deepseek\ndeepseek-chat\nsk-key\n\n0.7\n2048\nn\n",
        )
        assert result.exit_code == 0

        with open(cfg_file, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)

        fallback = config["llm"]["text_generation"].get("fallback", [])
        assert len(fallback) == 1
        assert fallback[0]["provider"] == "fallback-provider"
        assert fallback[0]["model"] == "fallback-model"
        assert config["llm"]["text_generation"]["provider"] == "deepseek"

    def test_llm_step_rerun_preserves(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A fallback added in a first run persists after a second LLM step run."""
        import automedia.cli.commands.onboard as onboard_mod

        monkeypatch.setattr(onboard_mod, "_USER_CFG_DIR", tmp_path)

        runner.invoke(
            app,
            ["onboard", "start", "--step", "llm"],
            input="deepseek\ndeepseek-chat\nsk-key\n\n0.7\n2048\ny\nopenai\ngpt-4o-mini\nfb-sk-key\n\n",
        )

        cfg_file = tmp_path / "model_config.yaml"
        assert cfg_file.is_file()

        result = runner.invoke(
            app,
            ["onboard", "start", "--step", "llm"],
            input="anthropic\nclaude-3.5-sonnet\nsk-claude\n\n0.5\n4096\nn\n",
        )
        assert result.exit_code == 0

        with open(cfg_file, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)

        fallback = config["llm"]["text_generation"].get("fallback", [])
        assert len(fallback) == 1
        assert fallback[0]["provider"] == "openai"
        assert fallback[0]["model"] == "gpt-4o-mini"
        assert config["llm"]["text_generation"]["provider"] == "anthropic"
