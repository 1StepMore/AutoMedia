"""Sandbox isolation tests (#333/#334)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from automedia.validation.adapters import CLIAdapter
from automedia.validation.sandbox import (
    CONFIG_ENV,
    KEEP_ENV,
    PROJECTS_ENV,
    validation_sandbox,
)
from automedia.validation.schema import Step


def _cli(command: str, timeout: float | None = None) -> Step:
    data = {
        "name": "run",
        "kind": "cli",
        "check": "runs",
        "standard": "founder-expectations.F01",
        "command": command,
        "expect": {"success": True},
    }
    if timeout is not None:
        data["timeout_seconds"] = timeout
    return Step.from_dict(data)


class TestSandboxDirectories:
    def test_creates_both_dirs_and_exports_them(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(CONFIG_ENV, raising=False)
        monkeypatch.delenv(PROJECTS_ENV, raising=False)
        with validation_sandbox() as sandbox:
            assert sandbox.temporary is True
            assert sandbox.config_dir.is_dir()
            assert sandbox.projects_dir.is_dir()
            assert os.environ[CONFIG_ENV] == str(sandbox.config_dir)
            assert os.environ[PROJECTS_ENV] == str(sandbox.projects_dir)
            root = sandbox.root
        assert not root.exists()
        assert CONFIG_ENV not in os.environ
        assert PROJECTS_ENV not in os.environ

    def test_explicit_dirs_are_honoured(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = tmp_path / "cfg"
        projects = tmp_path / "proj"
        config.mkdir()
        projects.mkdir()
        monkeypatch.setenv(CONFIG_ENV, str(config))
        monkeypatch.setenv(PROJECTS_ENV, str(projects))
        with validation_sandbox() as sandbox:
            assert sandbox.temporary is False
            assert sandbox.config_dir == config.resolve()
            assert sandbox.projects_dir == projects.resolve()
        assert config.is_dir() and projects.is_dir()

    def test_missing_half_only_fills_that_half(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = tmp_path / "cfg"
        config.mkdir()
        monkeypatch.setenv(CONFIG_ENV, str(config))
        monkeypatch.delenv(PROJECTS_ENV, raising=False)
        with validation_sandbox() as sandbox:
            assert sandbox.config_dir == config.resolve()
            assert sandbox.projects_dir == sandbox.root / "projects"

    def test_keep_env_preserves_the_root(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(CONFIG_ENV, raising=False)
        monkeypatch.delenv(PROJECTS_ENV, raising=False)
        monkeypatch.setenv(KEEP_ENV, "1")
        with validation_sandbox() as sandbox:
            root = sandbox.root
        assert root.is_dir()
        import shutil

        shutil.rmtree(root, ignore_errors=True)


class TestIdempotency:
    def test_each_invocation_starts_from_a_clean_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(CONFIG_ENV, raising=False)
        monkeypatch.delenv(PROJECTS_ENV, raising=False)
        with validation_sandbox() as first:
            first_config = first.config_dir
            (first_config / "accounts").mkdir()
            assert (first_config / "accounts").is_dir()
        with validation_sandbox() as second:
            assert second.config_dir != first_config
            assert not (second.config_dir / "accounts").exists()


class TestCliAdapterExpansion:
    def test_expands_env_vars_in_commands(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOMEDIA_TEST_DIR", "/tmp/automedia-expand")
        result = CLIAdapter().run(_cli("echo ${AUTOMEDIA_TEST_DIR}"))
        assert result.ok is True
        assert "/tmp/automedia-expand" in result.output["stdout"]

    def test_tool_arguments_expand_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, object] = {}

        class _Server:
            async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
                captured.update(arguments)
                return {"success": True}

        from automedia.validation.adapters import ToolAdapter

        monkeypatch.setenv("AUTOMEDIA_TEST_DIR", "/tmp/automedia-expand")
        step = Step.from_dict(
            {
                "name": "call",
                "kind": "tool",
                "check": "runs",
                "standard": "tool.contract",
                "tool": "health_check",
                "arguments": {
                    "base_dir": "${AUTOMEDIA_TEST_DIR}",
                    "nested": ["${AUTOMEDIA_TEST_DIR}"],
                },
                "expect": {"success": True},
            }
        )
        import asyncio

        asyncio.run(ToolAdapter(_Server()).run_async(step))
        assert captured["base_dir"] == "/tmp/automedia-expand"
        assert captured["nested"] == ["/tmp/automedia-expand"]

    def test_file_step_expands_env_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "artifact.txt"
        target.write_text("ok", encoding="utf-8")
        monkeypatch.setenv("AUTOMEDIA_TEST_FILE", str(target))
        from automedia.validation.adapters import FileAdapter

        step = Step.from_dict(
            {
                "name": "inspect",
                "kind": "file",
                "check": "exists",
                "standard": "founder-expectations.F01",
                "command": "${AUTOMEDIA_TEST_FILE}",
                "expect": {"artifact_exists": "${AUTOMEDIA_TEST_FILE}"},
            }
        )
        result = FileAdapter().run(step)
        assert result.ok is True
        assert result.output["exists"] is True
