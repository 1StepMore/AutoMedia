"""Tests for the Remotion video engine (#351 heavy track).

All Node/WSL execution is mocked — the E2E render runs in the WSL suite.
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.engines.errors import EngineExecutionError
from automedia.engines.implementations.video_remotion import (
    VideoRemotionEngine,
    _wsl_arg_paths,
)


@pytest.fixture(autouse=True)
def _azure_registered() -> None:
    from automedia.engines.registry import EngineRegistry

    if "remotion" not in EngineRegistry():
        EngineRegistry().register("remotion", VideoRemotionEngine, modality="video")


class TestRegistration:
    def test_registered_as_video_engine(self) -> None:
        from automedia.engines.registry import EngineRegistry

        assert "remotion" in EngineRegistry().list_by_modality("video")


class TestWslArgPaths:
    def test_windows_paths_translate(self) -> None:
        assert _wsl_arg_paths([r"D:\贯维\hf\e2e", "out.mp4"]) == [
            "/mnt/d/贯维/hf/e2e",
            "out.mp4",
        ]

    def test_posix_paths_pass_through(self) -> None:
        assert _wsl_arg_paths(["/home/x/y", "a.mp3"]) == ["/home/x/y", "a.mp3"]


class TestWslDist:
    def test_explicit_empty_forces_native(self) -> None:
        engine = VideoRemotionEngine({"wsl_dist": ""})
        assert engine._wsl_dist() is None

    def test_explicit_dist_wins(self) -> None:
        engine = VideoRemotionEngine({"wsl_dist": "Debian"})
        assert engine._wsl_dist() == "Debian"

    def test_windows_host_defaults_to_ubuntu(self) -> None:
        with patch("shutil.which", return_value=r"C:\Windows\System32\wsl.exe"):
            engine = VideoRemotionEngine({})
            if os.name == "nt":
                assert engine._wsl_dist() == "Ubuntu"
            else:
                assert engine._wsl_dist() is None


class TestCheckAvailable:
    def test_no_node_native_fails(self) -> None:
        engine = VideoRemotionEngine({"wsl_dist": "", "project_dir": os.path.join(os.sep, "nope")})
        with patch("shutil.which", return_value=None):
            ok, msg = engine.check_available()
        assert ok is False
        assert "node" in msg

    def test_workspace_without_remotion_hinted(self, tmp_path: Any) -> None:
        engine = VideoRemotionEngine({"wsl_dist": "", "project_dir": str(tmp_path)})
        mock = MagicMock(returncode=0, stdout="v22.0.0", stderr="")
        with (
            patch("shutil.which", return_value="/usr/bin/node"),
            patch.object(engine, "_node_cmd", return_value=mock),
        ):
            ok, msg = engine.check_available()
        assert ok is False
        assert "npm i remotion" in msg

    def test_ready_workspace_passes(self, tmp_path: Any) -> None:
        (tmp_path / "node_modules" / "remotion").mkdir(parents=True)
        engine = VideoRemotionEngine({"wsl_dist": "", "project_dir": str(tmp_path)})
        mock = MagicMock(returncode=0, stdout="v22.0.0", stderr="")
        with (
            patch("shutil.which", return_value="/usr/bin/node"),
            patch.object(engine, "_node_cmd", return_value=mock),
        ):
            ok, msg = engine.check_available()
        assert ok is True
        assert "workspace ready" in msg


class TestRender:
    def _engine(self, tmp_path: Any) -> VideoRemotionEngine:
        return VideoRemotionEngine({"wsl_dist": "", "project_dir": str(tmp_path / "ws")})

    def test_render_without_timeline_refused(self, tmp_path: Any) -> None:
        with pytest.raises(EngineExecutionError, match="scene timeline"):
            self._engine(tmp_path).render({"images": ["x.png"]}, str(tmp_path / "out.mp4"))

    def test_render_provisions_storyboard_and_copies_media(self, tmp_path: Any) -> None:
        engine = self._engine(tmp_path)
        media = tmp_path / "scene-01.png"
        media.write_bytes(b"png")
        audio = tmp_path / "narration.mp3"
        audio.write_bytes(b"mp3")
        out = str(tmp_path / "out.mp4")

        def fake_node(args: list[str], cwd: Any, timeout: int) -> MagicMock:
            # simulate remotion writing the output
            with open(out, "wb") as fh:
                fh.write(b"mp4")
            return MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch.object(engine, "check_available", return_value=(True, "ready")),
            patch.object(engine, "_node_cmd", side_effect=fake_node) as node,
        ):
            result = engine.render(
                {
                    "audio": str(audio),
                    "scene_media": [str(media)],
                    "scenes": [
                        {"index": 1, "text": "第一场，内容够长。", "start": 0.0, "duration": 4.0},
                        {"index": 2, "text": "第二场，结论在这里。", "start": 4.0, "duration": 2.5},
                    ],
                },
                out,
            )
        assert result == os.path.abspath(out)

        ws = tmp_path / "ws"
        payload = json.loads((ws / "input" / "storyboard.json").read_text(encoding="utf-8"))
        # --props replaces TOP-LEVEL props — the payload wraps the storyboard
        sb = payload["storyboard"]
        assert sb["fps"] == 30
        assert [s["startFrame"] for s in sb["scenes"]] == [0, 120]
        assert [s["durationFrames"] for s in sb["scenes"]] == [120, 75]
        assert sb["scenes"][0]["media"] == "media-01.png"
        assert sb["audio"] == "narration.mp3"
        # staticFile serves from <workspace>/public
        assert (ws / "public" / "media-01.png").is_file()
        assert (ws / "public" / "narration.mp3").is_file()
        # shipped template sources provisioned into the workspace
        assert (ws / "src" / "composition.tsx").is_file()
        # the node invocation asked remotion to render with the storyboard
        argv = node.call_args[0][0]
        assert "remotion" in argv and "AutoMedia" in argv and "--props" in argv

    def test_render_failure_raises_with_output(self, tmp_path: Any) -> None:
        engine = self._engine(tmp_path)
        mock = MagicMock(returncode=1, stdout="boom", stderr="bad")
        with (
            patch.object(engine, "check_available", return_value=(True, "ready")),
            patch.object(engine, "_node_cmd", return_value=mock),
        ):
            with pytest.raises(EngineExecutionError, match="remotion render failed"):
                engine.render(
                    {"scenes": [{"index": 1, "text": "x", "start": 0.0, "duration": 1.0}]},
                    str(tmp_path / "out.mp4"),
                )
