"""Own tools directory resolution + persistence — issue #510.

``ffmpeg``/``ffprobe`` can live in AutoMedia's own tools directory
(``%LOCALAPPDATA%\\automedia-tools\\bin``) which is not on ``PATH``. A bare
``shutil.which`` reported them missing and forgot every discovery. These
tests pin the :func:`~automedia.core.tool_paths.find_tool` contract:

1. a tool that exists *only* in the tools directory is found;
2. the discovery is persisted into ``<user config>/tools.yaml``;
3. a pinned path wins and is returned as-is;
4. a stale pin fails loudly (``ToolPathError``) — never a silent fallback
   to PATH — even when a same-named tool is visible on PATH.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import yaml

from automedia.core.tool_paths import ToolPathError, find_tool, tools_bin_dir


def _make_fake_tool(directory: Path, name: str) -> Path:
    """Create an executable stub *name* inside *directory* (platform-aware)."""
    suffix = ".exe" if sys.platform == "win32" else ""
    exe = directory / f"{name}{suffix}"
    exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    if sys.platform != "win32":
        exe.chmod(0o755)
    return exe


@pytest.fixture()
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Isolate user config + tools dir + PATH into *tmp_path*.

    PATH is pointed at an empty directory so no real ffmpeg/ffprobe on the
    developer machine can satisfy ``shutil.which`` — only what the test
    plants can be found.
    """
    user_config = tmp_path / "userconfig"
    user_config.mkdir()
    empty_path = tmp_path / "emptypath"
    empty_path.mkdir()
    monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(user_config))
    monkeypatch.delenv("AUTOMEDIA_TOOLS_DIR", raising=False)
    monkeypatch.setenv("PATH", str(empty_path))
    return {"user_config": user_config, "tmp": tmp_path}


def test_tools_bin_dir_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOMEDIA_TOOLS_DIR", str(tmp_path / "custom-tools"))
    assert tools_bin_dir() == tmp_path / "custom-tools"


def test_tools_bin_dir_windows_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AUTOMEDIA_TOOLS_DIR", raising=False)
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        assert tools_bin_dir() == tmp_path / "automedia-tools" / "bin"
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        assert tools_bin_dir() == tmp_path / "automedia-tools" / "bin"


def test_tool_only_in_tools_dir_is_found(
    isolated_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fake ffmpeg that exists ONLY in the tools dir must be hit (#510 DoD 1)."""
    tools_dir = isolated_env["tmp"] / "tools"
    tools_dir.mkdir()
    monkeypatch.setenv("AUTOMEDIA_TOOLS_DIR", str(tools_dir))
    fake = _make_fake_tool(tools_dir, "ffmpeg")

    found = find_tool("ffmpeg")
    assert found is not None
    assert Path(found) == fake


def test_discovery_is_persisted_to_tools_yaml(
    isolated_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tools-dir hit writes the absolute path back into tools.yaml."""
    tools_dir = isolated_env["tmp"] / "tools"
    tools_dir.mkdir()
    monkeypatch.setenv("AUTOMEDIA_TOOLS_DIR", str(tools_dir))
    fake = _make_fake_tool(tools_dir, "ffprobe")

    assert find_tool("ffprobe") is not None

    data = yaml.safe_load((isolated_env["user_config"] / "tools.yaml").read_text(encoding="utf-8"))
    pinned = data["tool_paths"]["ffprobe"]
    assert Path(pinned) == fake.resolve()


def test_pinned_path_wins(isolated_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    """An existing pin is returned as-is, ahead of PATH and the tools dir."""
    tools_dir = isolated_env["tmp"] / "tools"
    tools_dir.mkdir()
    monkeypatch.setenv("AUTOMEDIA_TOOLS_DIR", str(tools_dir))
    tools_fake = _make_fake_tool(tools_dir, "ffmpeg")
    elsewhere = isolated_env["tmp"] / "elsewhere"
    elsewhere.mkdir()
    pin_fake = _make_fake_tool(elsewhere, "ffmpeg")

    (isolated_env["user_config"] / "tools.yaml").write_text(
        yaml.dump({"tool_paths": {"ffmpeg": str(pin_fake)}}), encoding="utf-8"
    )

    found = find_tool("ffmpeg")
    assert found == str(pin_fake)
    assert Path(found) != tools_fake


def test_stale_pin_raises_instead_of_degrading(
    isolated_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pin whose file is gone raises ToolPathError — never a PATH fallback.

    Reverse-proof per #510 DoD 2: even though a same-named fake ffmpeg sits
    in the tools dir (and PATH is scanned first), the stale pin must be a
    loud error, not a silent degrade to whatever else is found.
    """
    tools_dir = isolated_env["tmp"] / "tools"
    tools_dir.mkdir()
    monkeypatch.setenv("AUTOMEDIA_TOOLS_DIR", str(tools_dir))
    _make_fake_tool(tools_dir, "ffmpeg")

    stale = isolated_env["tmp"] / "gone" / "ffmpeg.exe"
    (isolated_env["user_config"] / "tools.yaml").write_text(
        yaml.dump({"tool_paths": {"ffmpeg": str(stale)}}), encoding="utf-8"
    )

    with pytest.raises(ToolPathError, match="no longer exists"):
        find_tool("ffmpeg")


def test_missing_everywhere_returns_none(isolated_env: dict[str, Path]) -> None:
    """Nothing pinned, nothing on PATH, empty tools dir ⇒ None (no error)."""
    (isolated_env["tmp"] / "tools").mkdir()
    os.environ["AUTOMEDIA_TOOLS_DIR"] = str(isolated_env["tmp"] / "tools")
    try:
        assert find_tool("ffmpeg") is None
    finally:
        del os.environ["AUTOMEDIA_TOOLS_DIR"]


def test_hyperframes_engine_sees_tools_dir_ffmpeg(
    isolated_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Engine-level: check_available() is True via the ffmpeg fallback (#510 DoD 3).

    The engine has no cli_path/cli_command configured and no hyperframes on
    PATH; ffmpeg exists only in the tools directory.
    """
    from automedia.engines.implementations.video_hyperframes import HyperFramesVideoEngine

    tools_dir = isolated_env["tmp"] / "tools"
    tools_dir.mkdir()
    monkeypatch.setenv("AUTOMEDIA_TOOLS_DIR", str(tools_dir))
    _make_fake_tool(tools_dir, "ffmpeg")

    available, reason = HyperFramesVideoEngine({}).check_available()
    assert available is True
    assert "ffmpeg fallback" in reason


def test_hyperframes_engine_reports_stale_pin(
    isolated_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Engine-level: a stale ffmpeg pin is an explicit failure, not a degrade."""
    from automedia.engines.implementations.video_hyperframes import HyperFramesVideoEngine

    tools_dir = isolated_env["tmp"] / "tools"
    tools_dir.mkdir()
    monkeypatch.setenv("AUTOMEDIA_TOOLS_DIR", str(tools_dir))
    _make_fake_tool(tools_dir, "ffmpeg")  # PATH-equivalent decoy must NOT be used

    stale = isolated_env["tmp"] / "gone" / "ffmpeg.exe"
    (isolated_env["user_config"] / "tools.yaml").write_text(
        yaml.dump({"tool_paths": {"ffmpeg": str(stale)}}), encoding="utf-8"
    )

    available, reason = HyperFramesVideoEngine({}).check_available()
    assert available is False
    assert "no longer exists" in reason
