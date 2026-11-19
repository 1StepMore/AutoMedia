"""Hyperframes render timeout defaults and tree-kill behaviour (#577).

Cases:

1. No ``timeout`` configured -> the render subprocess gets 3600 seconds.
2. ``timeout: 5400`` configured -> that value is passed through.
3. ``_run_tree_aware`` kills the whole process tree on timeout and re-raises
   ``TimeoutExpired`` so the #414 degrade chain sees the same error.
4. ``_kill_tree`` dispatches to taskkill (Windows) or killpg (POSIX).
5. A render timeout still surfaces the exact #414 message.

The tree-kill behaviour is exercised on ``_run_tree_aware`` directly: faking
``subprocess.Popen`` for the whole engine also intercepts the unrelated
``subprocess.run`` preflight calls, which made the test depend on the
interpreter version (it failed on 3.11 while passing on 3.13).
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
    # ``cli_command`` short-circuits PATH lookup, so no hyperframes install
    # is required on the test machine.
    HyperFramesVideoEngine(engine_config={"cli_command": ["hyperframes"]}).render(
        _assets(tmp_path), str(tmp_path / "out.mp4")
    )

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


def test_run_tree_aware_kills_tree_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A timeout kills the whole tree, then re-raises ``TimeoutExpired``."""
    killed: list[int] = []
    monkeypatch.setattr(hf, "_kill_tree", killed.append)

    popen_kwargs: dict[str, Any] = {}

    class _FakeProc:
        pid = 4242
        returncode = 0

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            popen_kwargs.update(kwargs)
            self._timed_out = False

        # ``subprocess.run``/our helper always pass ``input`` first, so the
        # signature must accept it positionally (a ``timeout``-only signature
        # breaks on some interpreters).
        def communicate(self, input: Any = None, timeout: float | None = None) -> tuple[str, str]:
            if not self._timed_out:
                self._timed_out = True
                delay: float = timeout if timeout is not None else 0.0
                raise subprocess.TimeoutExpired("hyperframes", delay)
            return "", ""

        def kill(self) -> None:
            self.returncode = -9

    monkeypatch.setattr(hf.subprocess, "Popen", _FakeProc)

    with pytest.raises(subprocess.TimeoutExpired):
        hf._run_tree_aware(["hyperframes", "render"], env={}, timeout=5400)

    assert killed == [4242]

    # The child runs in its own session/group so the kill can reach
    # grandchildren (node -> chrome).
    if os.name == "nt":
        assert popen_kwargs["creationflags"] == subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        assert popen_kwargs["start_new_session"] is True


def test_render_reports_timeout_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A render timeout surfaces the exact #414 wording."""

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        timed_out: float = kwargs.get("timeout") or 0.0
        raise subprocess.TimeoutExpired("hyperframes", timed_out)

    monkeypatch.setattr(hf, "_run_tree_aware", fake_run)

    engine = HyperFramesVideoEngine(engine_config={"cli_command": ["hyperframes"], "timeout": 5400})
    with pytest.raises(EngineExecutionError) as excinfo:
        engine.render(_assets(tmp_path), str(tmp_path / "out.mp4"))

    # The #414 degrade chain depends on this exact wording.
    assert "hyperframes render timed out after 5400 seconds." in excinfo.value.details


def test_kill_tree_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_kill_tree`` uses taskkill on Windows and killpg elsewhere."""
    if os.name == "nt":
        argv: list[list[str]] = []

        def fake_taskkill(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            argv.append(list(args[0]))
            return subprocess.CompletedProcess(args[0], 0, "", "")

        monkeypatch.setattr(hf.subprocess, "run", fake_taskkill)
        hf._kill_tree(4242)
        assert argv == [["taskkill", "/F", "/T", "/PID", "4242"]]
    else:
        sent: list[int] = []

        def fake_killpg(pgid: int, sig: int) -> None:
            sent.append(sig)
            if sig == 0:
                raise ProcessLookupError

        monkeypatch.setattr(hf.os, "getpgid", lambda pid: 999)
        monkeypatch.setattr(hf.os, "killpg", fake_killpg)
        hf._kill_tree(4242)
        assert sent[0] == signal.SIGTERM
