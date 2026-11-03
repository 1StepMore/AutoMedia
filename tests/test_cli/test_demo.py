"""Tests for the credential-free demo mode (#360).

End-to-end against a tmp sandbox: fake LLM, local image engine, isolated
config dir — no network, no real credentials, no touch of the user's config.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app

runner = CliRunner()


@pytest.fixture()
def demo_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the demo output into tmp and isolate the overlay."""
    import automedia.cli.commands.demo as demo_mod

    base = tmp_path / "demo"
    monkeypatch.setattr(
        demo_mod,
        "_demo_dirs",
        lambda: (base / "config", base / "projects"),
    )
    monkeypatch.setenv("AUTOMEDIA_DOTENV_PATH", str(tmp_path / "empty.env"))
    # make sure ambient credentials can't leak into the demo run
    monkeypatch.delenv("AUTOMEDIA_LLM_API_KEY", raising=False)
    monkeypatch.delenv("AUTOMEDIA_FAKE_LLM", raising=False)
    return base


class TestDemoCommand:
    def test_demo_produces_complete_project_without_credentials(
        self, demo_sandbox: Path
    ) -> None:
        result = runner.invoke(app, ["demo"])
        assert result.exit_code == 0, result.output
        assert "Demo complete" in result.output

        projects = demo_sandbox / "projects"
        info_files = list(projects.glob("*/00_project_info.json"))
        assert info_files, "no project info produced"

        project_dir = info_files[0].parent
        # drafts exist (fake-LLM content went through the writing gate)
        drafts = list(project_dir.rglob("*.md"))
        assert any(len(p.read_text(encoding="utf-8")) > 400 for p in drafts)
        # cover image produced by the local engine
        images = list(project_dir.rglob("*.png"))
        assert images, "no cover image produced"
        # the demo marker explains the data is synthetic
        marker = project_dir / "DEMO.md"
        assert marker.is_file()
        assert "synthetic demo data" in marker.read_text(encoding="utf-8")

    def test_demo_does_not_touch_real_credentials(
        self, demo_sandbox: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AUTOMEDIA_LLM_API_KEY", "sk-do-not-leak")
        result = runner.invoke(app, ["demo"])
        assert result.exit_code == 0, result.output
        # the demo cleared the ambient key for its own run and restored env
        assert os.environ.get("AUTOMEDIA_FAKE_LLM") is None
        # no credential material in the output or the project tree
        assert "sk-do-not-leak" not in result.output
        for p in (demo_sandbox / "projects").rglob("*"):
            if p.is_file():
                assert "sk-do-not-leak" not in p.read_text(encoding="utf-8", errors="ignore")

    def test_demo_env_restored_after_run(self, demo_sandbox: Path) -> None:
        before = dict(os.environ)
        result = runner.invoke(app, ["demo"])
        assert result.exit_code == 0, result.output
        assert os.environ.get("AUTOMEDIA_FAKE_LLM") is None
        assert os.environ.get("AUTOMEDIA_CONFIG_DIR") == before.get("AUTOMEDIA_CONFIG_DIR")
