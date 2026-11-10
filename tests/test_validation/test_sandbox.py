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


class TestSandboxAllowlistProvisioning:
    """The sandbox provisions a scoped allowlist (T2-2 pairing).

    The MCP tools gate caller-supplied paths fail-closed; committed
    scenarios address sandbox paths (``base_dir: ${AUTOMEDIA_PROJECTS_DIR}``,
    ``/tmp/automedia/`` recovery paths), so the sandbox must carry its own
    allowlist or those steps would flip to ALLOWLIST_DENIED.
    """

    def test_owned_sandbox_provisions_scoped_allowlist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from automedia.mcp.allowlist import check_path_allowed

        monkeypatch.delenv("AUTOMEDIA_MCP_ALLOWLIST_PATH", raising=False)
        with validation_sandbox() as sandbox:
            allowlist_path = os.environ["AUTOMEDIA_MCP_ALLOWLIST_PATH"]
            assert allowlist_path
            assert sandbox.env.get("AUTOMEDIA_MCP_ALLOWLIST_PATH") == allowlist_path
            assert check_path_allowed(str(sandbox.projects_dir)) is True
            assert check_path_allowed(str(sandbox.config_dir)) is True
            # Recovery scenarios pin /tmp/automedia/ paths.
            assert check_path_allowed("/tmp/automedia/recovery-x") is True
            assert check_path_allowed(str(sandbox.root.parent / "elsewhere")) is False

        assert "AUTOMEDIA_MCP_ALLOWLIST_PATH" not in os.environ
        # Cache reset on exit: the tmp dirs are no longer allowed.
        assert check_path_allowed(str(sandbox.projects_dir)) is False

    def test_sandbox_allowlist_grants_committed_scenarios(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Partial-pass scenarios extract ``scenarios/fixtures/`` through MCP.

        The sandbox overrides ``AUTOMEDIA_MCP_ALLOWLIST_PATH``, so it must
        carry ``./scenarios/`` itself or the shipped allowlist is bypassed and
        ``extract_brief`` flips the scenario to ``failed``.
        """
        from automedia.mcp.allowlist import check_path_allowed

        monkeypatch.delenv("AUTOMEDIA_MCP_ALLOWLIST_PATH", raising=False)
        monkeypatch.delenv(CONFIG_ENV, raising=False)
        monkeypatch.delenv(PROJECTS_ENV, raising=False)
        monkeypatch.chdir(Path(__file__).resolve().parents[2])

        with validation_sandbox():
            fixture = Path.cwd() / "scenarios" / "fixtures" / "sample-draft.md"
            assert check_path_allowed(str(fixture)) is True

    def test_explicit_dirs_branch_also_provisions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from automedia.mcp.allowlist import check_path_allowed

        config = tmp_path / "cfg"
        projects = tmp_path / "proj"
        config.mkdir()
        projects.mkdir()
        monkeypatch.setenv(CONFIG_ENV, str(config))
        monkeypatch.setenv(PROJECTS_ENV, str(projects))
        monkeypatch.delenv("AUTOMEDIA_MCP_ALLOWLIST_PATH", raising=False)

        with validation_sandbox() as sandbox:
            assert sandbox.temporary is False
            assert os.environ["AUTOMEDIA_MCP_ALLOWLIST_PATH"]
            assert check_path_allowed(str(projects)) is True
            assert check_path_allowed(str(tmp_path / "denied")) is False

    def test_caller_allowlist_path_is_honoured(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        custom = tmp_path / "custom.yaml"
        custom.write_text(f"allowed_directories:\n  - {tmp_path}\n", encoding="utf-8")
        monkeypatch.setenv("AUTOMEDIA_MCP_ALLOWLIST_PATH", str(custom))
        monkeypatch.delenv(CONFIG_ENV, raising=False)
        monkeypatch.delenv(PROJECTS_ENV, raising=False)

        with validation_sandbox():
            assert os.environ["AUTOMEDIA_MCP_ALLOWLIST_PATH"] == str(custom)


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


class TestModelConfigSeeding:
    """Owned config dirs are seeded so ``automedia run`` clears its precheck (#466)."""

    def test_owned_sandbox_seeds_minimal_model_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import yaml

        monkeypatch.delenv(CONFIG_ENV, raising=False)
        monkeypatch.delenv(PROJECTS_ENV, raising=False)
        with validation_sandbox() as sandbox:
            seed_path = sandbox.config_dir / "model_config.yaml"
            assert seed_path.is_file()
            data = yaml.safe_load(seed_path.read_text(encoding="utf-8"))
        # Template matches ``automedia init`` minimal output
        # (init_cmd._init_minimal): provider/model placeholders, empty api_key.
        assert data["llm"]["text_generation"]["provider"] == "openai"
        assert data["llm"]["text_generation"]["model"] == "gpt-4o-mini"
        assert data["llm"]["text_generation"]["api_key"] == ""

    def test_seed_is_removed_with_the_sandbox(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(CONFIG_ENV, raising=False)
        monkeypatch.delenv(PROJECTS_ENV, raising=False)
        with validation_sandbox() as sandbox:
            seed_path = sandbox.config_dir / "model_config.yaml"
            root = sandbox.root
            assert seed_path.is_file()
        assert not root.exists()
        assert not seed_path.exists()

    def test_explicit_config_dir_is_never_seeded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projects"
        config_dir.mkdir()
        projects_dir.mkdir()
        monkeypatch.setenv(CONFIG_ENV, str(config_dir))
        monkeypatch.setenv(PROJECTS_ENV, str(projects_dir))
        with validation_sandbox():
            pass
        assert not (config_dir / "model_config.yaml").exists()

    def test_seed_helper_never_clobbers_an_existing_file(self, tmp_path: Path) -> None:
        from automedia.validation.sandbox import _seed_model_config

        existing = tmp_path / "model_config.yaml"
        existing.write_text("llm:\n  text_generation:\n    provider: glm\n", encoding="utf-8")
        assert _seed_model_config(tmp_path) == existing
        assert "provider: glm" in existing.read_text(encoding="utf-8")


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
