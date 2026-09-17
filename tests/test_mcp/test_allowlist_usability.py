"""Tests for mcp_allowlist.yaml usability."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from automedia.mcp.allowlist import (
    _load_allowlist,
    _reset_allowlist_cache,
    check_path_allowed,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestAllowlistUsability:
    """Default allowlist should be usable out of the box."""

    def test_allowlist_yaml_parses_correctly(self) -> None:
        """mcp_allowlist.yaml must parse without errors."""
        _reset_allowlist_cache()
        allowlist_path = (
            Path(__file__).parent.parent.parent / "src" / "automedia" / "mcp" / "mcp_allowlist.yaml"
        )
        entries = _load_allowlist(allowlist_path=allowlist_path)
        # Default file should have at least /tmp/automedia/
        assert len(entries) >= 1
        assert any("/tmp/automedia" in os.path.realpath(e) for e in entries)

    def test_default_allowlist_excludes_repo_root(self) -> None:
        """The shipped allowlist must not grant the whole repository.

        中文说明：``./`` 会让 MCP 的每个文件操作都能读写整份 checkout。默认姿态
        必须是 scoped（``./data/`` / ``./output/`` / ``./projects/`` / ``/tmp/automedia/``），
        需要整仓访问的用户须显式取消注释或改用 ``AUTOMEDIA_MCP_ALLOWLIST_PATH``。
        这里按**解析后的等价路径**判定，而不是字符串比对——``./`` 会随工作目录
        解析成不同字面量。
        """
        _reset_allowlist_cache()
        repo_root = Path(__file__).parent.parent.parent.resolve()
        allowlist_path = repo_root / "src" / "automedia" / "mcp" / "mcp_allowlist.yaml"

        entries = _load_allowlist(allowlist_path=allowlist_path)

        resolved = {Path(os.path.realpath(e)) for e in entries}
        assert repo_root not in resolved, (
            f"allowlist must not contain the repo root; got {sorted(map(str, resolved))}"
        )


class TestAllowlistPathEnvVar:
    """The env var must actually be honoured (regression: it was documented only).

    ``.env.example``, ``docs/user/mcp-setup.md`` and the systemd templates all
    advertised ``AUTOMEDIA_MCP_ALLOWLIST_PATH`` as the way to point the server
    at a custom allowlist, but no code read it — configuring it did nothing.
    """

    @pytest.fixture(autouse=True)
    def _clean_cache(self) -> object:
        _reset_allowlist_cache()
        yield
        _reset_allowlist_cache()

    def test_env_var_selects_custom_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        custom = tmp_path / "custom_allowlist.yaml"
        custom.write_text(f"allowed_directories:\n  - {tmp_path}\n", encoding="utf-8")
        monkeypatch.setenv("AUTOMEDIA_MCP_ALLOWLIST_PATH", str(custom))

        entries = _load_allowlist()

        assert entries == [os.path.realpath(str(tmp_path))]

    def test_missing_configured_file_denies_all(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AUTOMEDIA_MCP_ALLOWLIST_PATH", str(tmp_path / "absent.yaml"))

        assert _load_allowlist() == []
        assert check_path_allowed(str(tmp_path)) is False


class TestValidationFixturesReachable:
    """The allowlist must let the committed validation scenarios read their fixtures.

    Regression: dropping the repository root from the allowlist made the OPP
    step of ``partial-pass-omni-extraction`` fail (the fixture it extracts lives
    under ``scenarios/``), flipping that scenario's verdict from ``partial-pass``
    to ``failed`` — and the failure was misread as a Windows environment artifact.
    """

    @pytest.fixture(autouse=True)
    def _clean_cache(self) -> object:
        _reset_allowlist_cache()
        yield
        _reset_allowlist_cache()

    def test_committed_scenario_fixture_is_reachable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(REPO_ROOT)
        _reset_allowlist_cache()

        fixture = REPO_ROOT / "scenarios" / "fixtures" / "sample-draft.md"

        assert fixture.is_file()
        assert check_path_allowed(str(fixture)) is True
