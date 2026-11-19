"""Hyperframes render timeout defaults and tree-kill behaviour (#577).

Three cases:

1. No ``timeout`` configured -> the render subprocess gets 3600 seconds.
2. ``timeout: 5400`` configured -> that value is passed through.
3. A render timeout kills the whole process tree, then still raises
   ``TimeoutExpired`` so the #414 degrade chain sees the same error.
"""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Any

import pytest

from automedia.engines.errors import EngineExecutionError
from automedia.engines.implementations import video_hyperframes as hf
from automedia.engines.implementations.video_hyperframes import HyperFramesVideoEngine


def _assets(tmp_path: Path) -> dict[str, Any]:
    """Minimal one-image asset dict (no chrome, no ffmpeg)."""
    image: Path = tmp_path / "frame.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    return {"images": [str(image)]}


def _engine() -> HyperFramesVideoEngine:
    # ``cli_command`` short-circuits PATH lookup, so no hyperframes install
    # is required on the test machine.
    return HyperFramesVideoEngine(engine_config={"cli_command": ["hyperframes"]})


def test_default_render_timeout_is_3600(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unconfigured engines hand 3600s to the render subprocess."""
    seen: list[int] = []

    def fake_run(
        cmd: list[str],
        *,
        env: dict[str, str],
        timeout: int,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        seen.append(timeout)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(hf, "_run_tree_aware", fake_run)

    _engine().render(_assets(tmp_path), str(tmp_path / "out.mp4"))

    assert seen == [3600]


def test_configured_render_timeout_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit ``timeout`` in engine config wins over the default."""
    seen: list[int] = []

    def fake_run(
        cmd: list[str],
        *,
        env: dict[str, str],
        timeout: int,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        seen.append(timeout)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(hf, "_run_tree_aware", fake_run)

    engine = HyperFramesVideoEngine(engine_config={"cli_command": ["hyperframes"], "timeout": 5400})
    engine.render(_assets(tmp_path), str(tmp_path / "out.mp4"))

    assert seen == [5400]


def test_timeout_kills_whole_process_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A timeout calls ``_kill_tree`` and preserves the #414 error message."""
    killed: list[int] = []
    real_kill_tree = hf._kill_tree
    monkeypatch.setattr(hf, "_kill_tree", killed.append)

    popen_kwargs: dict[str, Any] = {}

    class _FakeProc:
        pid = 4242
        returncode = 0

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            popen_kwargs.update(kwargs)
            self._timed_out = False

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            if not self._timed_out:
                self._timed_out = True
                raise subprocess.TimeoutExpired("hyperframes", timeout)
            return "", ""

        def kill(self) -> None:
            self.returncode = -9

    monkeypatch.setattr(hf.subprocess, "Popen", _FakeProc)

    engine = HyperFramesVideoEngine(engine_config={"cli_command": ["hyperframes"], "timeout": 5400})
    with pytest.raises(EngineExecutionError) as excinfo:
        engine.render(_assets(tmp_path), str(tmp_path / "out.mp4"))

    # Tree kill happened before the error surfaced.
    assert killed == [4242]
    # The #414 degrade chain depends on this exact wording.
    assert "hyperframes render timed out after 5400 seconds." in excinfo.value.details

    # The child runs in its own session/group so the kill can reach
    # grandchildren (node -> chrome).
    if os.name == "nt":
        assert popen_kwargs["creationflags"] == subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert popen_kwargs["start_new_session"] is True

    # ``_kill_tree`` dispatch for this platform.
    if os.name == "nt":
        argv: list[list[str]] = []

        def fake_taskkill(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            argv.append(list(args[0]))
            return subprocess.CompletedProcess(args[0], 0, "", "")

        monkeypatch.setattr(hf.subprocess, "run", fake_taskkill)
        real_kill_tree(4242)
        assert argv == [["taskkill", "/F", "/T", "/PID", "4242"]]
    else:
        sent: list[int] = []

        def fake_killpg(pgid: int, sig: int) -> None:
            sent.append(sig)
            if sig == 0:
                raise ProcessLookupError

        monkeypatch.setattr(hf.os, "getpgid", lambda pid: 999)
        monkeypatch.setattr(hf.os, "killpg", fake_killpg)
        real_kill_tree(4242)
        assert sent[0] == signal.SIGTERM
