"""Bare POSIX utility resolution for CLI steps on Windows (#625 follow-up).

``auto-journey`` step 3 asks ``find ${AUTOMEDIA_PROJECTS_DIR} -name
"*_draft.md" -size +500c``.  Windows ``CreateProcess`` searches
``%SystemRoot%\\system32`` *before* ``PATH``, so the bare ``find`` token always
hit the Windows *text* search tool: ``exit 2`` plus
``找不到文件 - *_draft.md`` while the draft demonstrably existed.  The adapter
now resolves a whitelisted bare utility to an absolute non-system path; the
scenario (an owner-only expectation) is untouched, and the assertion keeps
asking the same question ("that glob, that size").

Confidence: mock for the resolution units, real for the subprocess case.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import automedia.validation.adapters as adapters
from automedia.validation.adapters import CLIAdapter, _resolve_posix_util
from automedia.validation.schema import Step

# These cases drive ``shutil.which`` down its win32 branch; off Windows that
# reaches ``_winapi``, which is ``None`` here and has no
# ``NeedCurrentDirectoryForExePath``.  Windows-only, everything else stays.
WINDOWS_ONLY = pytest.mark.skipif(
    sys.platform != "win32",
    reason="NeedCurrentDirectoryForExePathW only exists on Windows",
)


def cli_step(command: str) -> Step:
    """A valid cli-kind step with the given command."""
    data: dict[str, Any] = {
        "name": "run command",
        "kind": "cli",
        "check": "command runs",
        "standard": "founder-expectations.F01",
        "command": command,
        "expect": {"success": True},
    }
    return Step.from_dict(data)


@pytest.fixture()
def fake_system_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A stand-in ``%SystemRoot%`` holding a decoy ``find.exe``."""
    root = tmp_path / "Windows"
    (root / "system32").mkdir(parents=True)
    (root / "system32" / "find.exe").write_text("decoy", encoding="utf-8")
    monkeypatch.setenv("SystemRoot", str(root))
    monkeypatch.setenv("windir", str(root))
    return root / "system32"


def _tool_dir(tmp_path: Path, name: str = "tools") -> Path:
    """A directory holding a non-system ``find.exe``."""
    directory = tmp_path / name
    directory.mkdir()
    (directory / "find.exe").write_text("gnu-ish", encoding="utf-8")
    return directory


class TestResolvePosixUtil:
    """``_resolve_posix_util`` only rewrites what it can prove is safe."""

    @WINDOWS_ONLY
    def test_win32_resolves_to_the_non_system_candidate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        tools = _tool_dir(tmp_path)
        monkeypatch.setenv("PATH", str(tools))

        assert os.path.normcase(_resolve_posix_util("find")) == os.path.normcase(
            str(tools / "find.exe")
        )

    @WINDOWS_ONLY
    def test_system_root_candidate_is_skipped(
        self, tmp_path: Path, fake_system_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        tools = _tool_dir(tmp_path)
        # system32 first, exactly like a real Windows PATH.
        monkeypatch.setenv("PATH", f"{fake_system_root}{os.pathsep}{tools}")

        resolved = _resolve_posix_util("find")

        assert os.path.normcase(resolved) == os.path.normcase(str(tools / "find.exe"))
        assert not os.path.normcase(resolved).startswith(os.path.normcase(str(fake_system_root)))

    @WINDOWS_ONLY
    def test_only_system_candidates_fall_back_to_the_token(
        self, tmp_path: Path, fake_system_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("PATH", str(fake_system_root))

        # Honest fallback: nothing better to use, so behaviour is unchanged.
        assert _resolve_posix_util("find") == "find"

    def test_non_whitelisted_token_is_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("PATH", str(_tool_dir(tmp_path)))

        assert _resolve_posix_util("python") == "python"

    def test_non_windows_is_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("PATH", str(_tool_dir(tmp_path)))

        assert _resolve_posix_util("find") == "find"

    @pytest.mark.parametrize("token", ["C:/tools/find.exe", r"tools\find.exe", "./find"])
    def test_token_with_a_path_separator_is_untouched(
        self, token: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("PATH", str(_tool_dir(tmp_path)))

        assert _resolve_posix_util(token) == token


def _gnu_find() -> str | None:
    """Return the resolved ``find`` when it really is GNU findutils."""
    candidate = _resolve_posix_util("find")
    try:
        completed = subprocess.run(
            [candidate, "--version"], capture_output=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    stdout = completed.stdout.decode("utf-8", errors="replace")
    if completed.returncode == 0 and "GNU findutils" in stdout:
        return candidate
    return None


GNU_FIND = _gnu_find()


class TestCLIAdapterPosixUtil:
    """The adapter resolves the leading token, nothing else changes."""

    def test_adapter_rewrites_the_leading_token_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # If the rewrite happened, `find --version` runs the interpreter and
        # prints "Python ..."; without it the token reaches the platform's own
        # `find` (Windows text tool => exit 2).
        monkeypatch.setattr(adapters, "_resolve_posix_util", lambda token: sys.executable)

        result = CLIAdapter().run(cli_step("find --version"))

        assert result.output["exit_code"] == 0
        assert "Python" in result.output["stdout"]

    @pytest.mark.skipif(GNU_FIND is None, reason="no GNU findutils resolvable here")
    def test_find_name_and_size_assertion_works_through_the_adapter(self, tmp_path: Path) -> None:
        """The real step-3 command shape: one draft >500B, one small file."""
        projects = tmp_path / "projects"
        projects.mkdir()
        draft = projects / "20260101_draft.md"
        draft.write_text("d" * 600, encoding="utf-8")
        (projects / "small_draft.md").write_text("too small", encoding="utf-8")

        result = CLIAdapter().run(cli_step(f'find "{projects}" -name "*_draft.md" -size +500c'))

        assert result.output["exit_code"] == 0, result.output["stderr"]
        assert "20260101_draft.md" in result.output["stdout"]
        # The size filter is part of the assertion and must still apply.
        assert "small_draft.md" not in result.output["stdout"]
