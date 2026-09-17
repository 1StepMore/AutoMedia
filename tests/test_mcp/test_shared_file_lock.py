"""Tests for the cross-platform advisory lock in ``mcp/tools/_shared.py``.

Covers health-assessment **P0-2**: ``_shared.py`` used to ``import fcntl`` at
module scope, which made the entire MCP tool layer unimportable on Windows
(``fcntl`` is POSIX-only) while ``pyproject.toml`` claimed ``OS Independent``.

Two properties are locked here:

1. **Import-level**: the module must import successfully when ``fcntl`` is
   unavailable (``_fcntl is None``), instead of raising ``ImportError``.
2. **Behavioural**: the Windows (no-op) branch still round-trips
   ``active_pipelines.json`` correctly — the no-op is semantically equivalent
   because the write path is an atomic ``os.replace(tmp, path)`` replacement.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from automedia.mcp.tools import _shared

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"


@pytest.fixture()
def active_pipelines_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``active_pipelines.json`` at a temporary file."""
    path = tmp_path / "active_pipelines.json"
    monkeypatch.setattr(_shared, "_active_pipelines_path", path)
    return path


class TestFcntlOptionalImport:
    """``fcntl`` must be an optional dependency, not an import-time requirement."""

    def test_module_imports_without_fcntl(self) -> None:
        """Given ``fcntl`` cannot be imported, When the module loads, Then no error.

        Run in a subprocess so the blocked ``fcntl`` cannot leak into the
        parent test process's module cache.
        """
        code = (
            "import sys;"
            "sys.modules['fcntl'] = None;"
            "import automedia.mcp.tools._shared as s;"
            "assert s._fcntl is None, s._fcntl;"
            "print('ok')"
        )
        env = {**os.environ, "PYTHONPATH": str(_SRC_DIR)}

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

        assert result.returncode == 0, f"import failed without fcntl:\n{result.stderr}"
        assert "ok" in result.stdout

    def test_noop_branch_is_selected_when_fcntl_is_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Given ``_fcntl is None``, When the lock is taken, Then it is a no-op."""
        monkeypatch.setattr(_shared, "_fcntl", None)

        calls: list[str] = []
        with _shared._file_lock(_RecordingHandle(calls), exclusive=True):
            calls.append("body")

        assert calls == ["body"], "no fcntl call must happen on the no-op branch"


class _RecordingHandle(io.StringIO):
    """Minimal file-like stand-in that records ``fileno`` accesses."""

    def __init__(self, calls: list[str]) -> None:
        super().__init__()
        self._calls = calls

    def fileno(self) -> int:
        self._calls.append("fileno")
        return -1


class TestActivePipelinesRoundTripOnNoOpBranch:
    """The lock-free (Windows) branch must not change read/write semantics."""

    def test_write_then_read_round_trips(
        self,
        active_pipelines_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Given the no-op lock branch, When writing then reading, Then data survives."""
        monkeypatch.setattr(_shared, "_fcntl", None)

        payload: dict[str, dict[str, Any]] = {
            "proj123abc456": {"status": "running", "topic": "t", "brand": "b"},
        }
        _shared._write_active_pipelines(payload)

        assert active_pipelines_path.is_file()
        assert json.loads(active_pipelines_path.read_text(encoding="utf-8")) == payload
        assert _shared._read_active_pipelines() == payload

    def test_read_of_missing_file_returns_empty(
        self,
        active_pipelines_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Given no file on disk, When reading, Then an empty dict is returned."""
        monkeypatch.setattr(_shared, "_fcntl", None)

        assert not active_pipelines_path.exists()
        assert _shared._read_active_pipelines() == {}

    def test_repeated_writes_overwrite_the_existing_file(
        self,
        active_pipelines_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Given the file already exists, When written again, Then it is replaced.

        中文说明：``Path.rename`` 映射到 ``os.rename``，在 Windows 上当目标已存在时
        抛 ``FileExistsError``——即第一次写入之后的**每一次**写入都会失败。
        此处用「连续写两次」把该 Windows 专属缺陷钉死（改用 ``os.replace``）。
        """
        monkeypatch.setattr(_shared, "_fcntl", None)

        _shared._write_active_pipelines({"proj123abc456": {"status": "running"}})
        _shared._write_active_pipelines({"proj123abc456": {"status": "completed"}})

        assert _shared._read_active_pipelines() == {"proj123abc456": {"status": "completed"}}
        assert not active_pipelines_path.with_suffix(".tmp").exists(), "临时文件必须已被替换"

    def test_update_pipeline_entry_merges_under_noop_lock(
        self,
        active_pipelines_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Given an existing entry, When updated, Then the merge is persisted."""
        monkeypatch.setattr(_shared, "_fcntl", None)

        _shared._update_pipeline_entry("proj123abc456", {"status": "running"})
        _shared._update_pipeline_entry("proj123abc456", {"topic": "后续主题"})

        entry = _shared._read_active_pipelines()["proj123abc456"]
        assert entry["status"] == "running"
        assert entry["topic"] == "后续主题"
