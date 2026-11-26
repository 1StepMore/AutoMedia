"""Hermetic regression tests for ``automedia demo`` local-only guarantee (#698).

The bug: ``demo()`` set ``AUTOMEDIA_FAKE_LLM`` / ``AUTOMEDIA_CONFIG_DIR`` but
never pinned ``engines.image.chain``, whose built-in default is
``[comfyui, local]`` — so on any machine with ComfyUI answering on
127.0.0.1:8188 the demo drove ComfyUI and polled ``/history/<uuid>`` for
minutes. These tests simulate a *reachable* ComfyUI (probe monkeypatched to
succeed, generate monkeypatched to record contact) and assert the demo never
contacts it and pins ``chain == ["local"]`` in its sandbox config.

No network, no keys: a reachable ComfyUI is faked in-process.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import automedia.cli.commands.demo as demo_mod
from automedia.cli.app import app
from automedia.engines.implementations.image_comfyui import ComfyUIImageEngine

runner = CliRunner()


@pytest.fixture()
def demo_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the demo output into tmp and isolate the overlay."""
    base = tmp_path / "demo"
    monkeypatch.setattr(
        demo_mod,
        "_demo_dirs",
        lambda: (base / "config", base / "projects"),
    )
    monkeypatch.setenv("AUTOMEDIA_DOTENV_PATH", str(tmp_path / "empty.env"))
    monkeypatch.delenv("AUTOMEDIA_LLM_API_KEY", raising=False)
    monkeypatch.delenv("AUTOMEDIA_FAKE_LLM", raising=False)
    return base


class TestDemoLocalOnlyByConstruction:
    def test_demo_never_contacts_comfyui_even_when_reachable(
        self, demo_sandbox: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ComfyUI answers on 8188 (faked) — the demo must still stay local-only."""
        from automedia.engines.errors import EngineExecutionError

        contact = {"probes": 0, "generates": 0}

        def fake_check_available(self: ComfyUIImageEngine) -> tuple[bool, str]:
            contact["probes"] += 1
            return True, "ComfyUI reachable (monkeypatched)"

        def fake_generate(
            self: ComfyUIImageEngine,
            prompt: str,
            width: int,
            height: int,
            output_path: str,
        ) -> str:
            contact["generates"] += 1
            raise EngineExecutionError(
                engine_name="comfyui",
                details="demo must never drive ComfyUI (#698)",
            )

        monkeypatch.setattr(ComfyUIImageEngine, "check_available", fake_check_available)
        monkeypatch.setattr(ComfyUIImageEngine, "generate", fake_generate)

        result = runner.invoke(app, ["demo"])
        assert result.exit_code == 0, result.output
        assert "Demo complete" in result.output
        assert contact["probes"] == 0, (
            "demo probed ComfyUI — engines.image.chain is not pinned to [local]"
        )
        assert contact["generates"] == 0, (
            "demo drove ComfyUI generate — engines.image.chain is not pinned to [local]"
        )

    def test_demo_sandbox_config_pins_local_image_chain(
        self, demo_sandbox: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Make the ComfyUI probe raise so no real HTTP happens even on
        # pre-fix code (where the chain is unpinned): the candidate is
        # skipped and the run falls back to local either way.
        def raising_check(self: ComfyUIImageEngine) -> tuple[bool, str]:
            raise RuntimeError("ComfyUI probe monkeypatched to raise (#698)")

        monkeypatch.setattr(ComfyUIImageEngine, "check_available", raising_check)

        result = runner.invoke(app, ["demo"])
        assert result.exit_code == 0, result.output

        # the sandbox config file itself pins the local chain, idempotently
        sandbox_yaml = demo_sandbox / "config" / "demo_sandbox.yaml"
        assert sandbox_yaml.is_file()
        data = yaml.safe_load(sandbox_yaml.read_text(encoding="utf-8"))
        assert data["engines"]["image"]["chain"] == ["local"]

        # the merged config the pipeline actually sees resolves the same way
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(demo_sandbox / "config"))
        from automedia.core.config_loader import load_config
        from automedia.core.env_overlay import reset_dotenv_overlay_cache

        reset_dotenv_overlay_cache()
        assert load_config()["engines"]["image"]["chain"] == ["local"]
