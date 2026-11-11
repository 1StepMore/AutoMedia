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


@pytest.fixture(autouse=True)
def _isolate_user_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every write of this module inside *tmp_path* (issue #208).

    All three isolation points are armed, because the CLI registers its
    commands lazily: the module that owns ``_USER_CFG_DIR`` is imported on
    first dispatch, so importing it *under* the patched resolver fixes the
    import-time constant, and the attribute patch covers the case where an
    earlier test in the session already imported it.
    """
    monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("automedia.core.paths.get_user_config_dir", lambda: tmp_path)

    import automedia.cli.commands.onboard as onboard_mod

    monkeypatch.setattr(onboard_mod, "_USER_CFG_DIR", tmp_path)


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


class TestOnboardLlmWriteGuards:
    """Issue #208 guards on the onboarding LLM step."""

    def test_empty_provider_is_refused(self, tmp_path: Path) -> None:
        """A blank provider is refused instead of written as ``''``.

        The wizard's prompt default follows the stored provider, so a config
        left with ``provider: ''`` reproduces the incident path: pressing
        Enter keeps the blank and the write must be refused, not silently
        persisted.
        """
        cfg_file = tmp_path / "model_config.yaml"
        cfg_file.write_text("llm:\n  text_generation:\n    provider: ''\n", encoding="utf-8")

        result = runner.invoke(
            app,
            ["onboard", "start", "--step", "llm"],
            input="\ndeepseek-chat\nsk-key\n\n0.7\n2048\nn\n",
        )

        assert result.exit_code == 1
        assert "provider" in result.output.lower()
        assert "provider: ''" in cfg_file.read_text(encoding="utf-8")

    def test_successful_step_backs_up_previous_config(self, tmp_path: Path) -> None:
        """Re-running the step backs up the existing config first."""
        cfg_file = tmp_path / "model_config.yaml"
        cfg_file.write_text(
            "llm:\n  text_generation:\n    provider: old-provider\n", encoding="utf-8"
        )
        before = cfg_file.read_text(encoding="utf-8")

        result = runner.invoke(
            app,
            ["onboard", "start", "--step", "llm"],
            input="deepseek\ndeepseek-chat\nsk-key\n\n0.7\n2048\nn\n",
        )
        assert result.exit_code == 0

        backups = sorted(tmp_path.glob("model_config.yaml.bak-*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == before


class TestOnboardPreflight:
    """Dependency pre-flight that opens the wizard (#352)."""

    def test_detect_os_returns_label(self) -> None:
        import automedia.cli.commands.onboard as onboard_mod

        label = onboard_mod._detect_os()
        assert label
        assert any(token in label for token in ("Windows", "Linux", "macOS", "WSL"))

    def test_start_runs_preflight_before_steps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`onboard start` prints the environment check ahead of step 1."""
        import automedia.cli.commands.onboard as onboard_mod

        monkeypatch.setattr(onboard_mod, "_USER_CFG_DIR", tmp_path)
        result = runner.invoke(
            app,
            ["onboard", "start", "--step", "llm"],
            input="deepseek\ndeepseek-chat\nsk-key\n\n0.7\n2048\nn\n",
        )
        assert result.exit_code == 0
        out = result.output
        assert "Preflight: Environment Check" in out
        assert "Detected system:" in out
        assert out.index("Preflight") < out.index("Step 1/8")
        assert "automedia doctor --install-missing" in out

    def test_preflight_missing_tools_are_informational(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing media tools must not block the wizard nor fail the step."""
        import shutil

        import automedia.cli.commands.onboard as onboard_mod
        import automedia.core.tool_paths as tool_paths_mod

        # Preflight probes go through tool_paths.find_tool (#510), whose
        # shutil.which is called with a `path=` kwarg for the tools-dir scan.
        # Patch the seam the production code actually uses; the stub accepts
        # both call shapes so it intercepts PATH and tools-dir lookups alike.
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setattr(tool_paths_mod.shutil, "which", lambda name, **_: None)
        monkeypatch.setattr(
            onboard_mod.shutil if hasattr(onboard_mod, "shutil") else shutil,
            "which",
            lambda name, **_: None,
        )
        monkeypatch.setattr(onboard_mod, "_USER_CFG_DIR", tmp_path)
        result = runner.invoke(
            app,
            ["onboard", "start", "--step", "llm"],
            input="deepseek\ndeepseek-chat\nsk-key\n\n0.7\n2048\nn\n",
        )
        assert result.exit_code == 0
        assert "Text-only modes need none of them" in result.output
