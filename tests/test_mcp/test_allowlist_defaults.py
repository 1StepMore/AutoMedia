"""Factory-state allowlist defaults (issue #703).

The shipped allowlist deliberately excludes the repository root, so before
#703 a factory-fresh MCP server rejected every default-path tool call
(``list_projects`` resolved ``base_dir='.'`` to the repo root, which is
nowhere on the allowlist).  The fix makes the application's own data
directories implicit: the user config tree (``~/.automedia/`` — ``projects``,
``demo``, ``output``) and the resolved projects directory
(``AUTOMEDIA_PROJECTS_DIR`` or ``<cwd>/.automedia/output/projects``) are
allowed without registration, while the repository root stays closed.

Every test here scopes the allowlist to an empty YAML (``allowed_directories:
[]``) so only the implicit directories are in effect — proving the implicit
set works even with an operator list that grants nothing itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from automedia.mcp.allowlist import (
    AllowlistDenied,
    _require_allowed,
    _reset_allowlist_cache,
    check_path_allowed,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture()
def empty_allowlist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Only implicit directories are in effect: an empty YAML allowlist."""
    allowlist = tmp_path / "allowlist.yaml"
    allowlist.write_text("allowed_directories: []\n", encoding="utf-8")
    monkeypatch.setenv("AUTOMEDIA_MCP_ALLOWLIST_PATH", str(allowlist))
    monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path / "config"))
    _reset_allowlist_cache()
    yield tmp_path
    _reset_allowlist_cache()


class TestImplicitDirectories:
    def test_projects_dir_under_implicit_set_is_allowed(self, empty_allowlist: Path) -> None:
        """AUTOMEDIA_PROJECTS_DIR is effective without YAML registration."""
        assert check_path_allowed(str(empty_allowlist / "projects" / "p1")) is True

    def test_config_dir_subtrees_are_implicit(self, empty_allowlist: Path) -> None:
        assert check_path_allowed(str(empty_allowlist / "config" / "projects")) is True
        assert check_path_allowed(str(empty_allowlist / "config" / "demo")) is True
        assert check_path_allowed(str(empty_allowlist / "config" / "output")) is True

    def test_repo_root_still_denied(self, empty_allowlist: Path) -> None:
        """Implicit directories never include the repository root."""
        assert check_path_allowed(str(REPO_ROOT)) is False

    def test_unrelated_path_still_denied(self, empty_allowlist: Path) -> None:
        assert check_path_allowed("/etc") is False


class TestAllowlistDeniedError:
    def test_require_allowed_raises_allowlist_denied(self, empty_allowlist: Path) -> None:
        with pytest.raises(AllowlistDenied) as excinfo:
            _require_allowed("/etc", tool_name="list_projects")
        assert "Allowed:" in str(excinfo.value)
        # Still catchable as PermissionError for existing handlers.
        assert isinstance(excinfo.value, PermissionError)
