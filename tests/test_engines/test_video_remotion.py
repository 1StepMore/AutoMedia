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
            pytest.raises(EngineExecutionError, match="remotion render failed"),
        ):
            engine.render(
                {"scenes": [{"index": 1, "text": "x", "start": 0.0, "duration": 1.0}]},
                str(tmp_path / "out.mp4"),
            )


class TestTargetSize:
    """Platform frame size resolution (#523) — same contract as #519."""

    def _engine(self, tmp_path: Any, **config: Any) -> VideoRemotionEngine:
        base = {"wsl_dist": "", "project_dir": str(tmp_path / "ws")}
        base.update(config)
        return VideoRemotionEngine(base)

    def test_assets_platform_size_wins(self, tmp_path: Any) -> None:
        # runner stamps douyin/weibo/kuaishou as 1080x1920 on the assets
        assert self._engine(tmp_path)._target_size({"width": 1080, "height": 1920}) == (1080, 1920)

    def test_config_used_when_assets_carry_no_size(self, tmp_path: Any) -> None:
        engine = self._engine(tmp_path, width=1280, height=720)
        assert engine._target_size({}) == (1280, 720)

    def test_no_size_still_defaults_to_landscape_1080p(self, tmp_path: Any) -> None:
        assert self._engine(tmp_path)._target_size({}) == (1920, 1080)

    def test_storyboard_carries_platform_size(self, tmp_path: Any) -> None:
        engine = self._engine(tmp_path)
        media = tmp_path / "scene-01.png"
        media.write_bytes(b"png")
        out = str(tmp_path / "out.mp4")

        def fake_node(args: list[str], cwd: Any, timeout: int) -> MagicMock:
            with open(out, "wb") as fh:
                fh.write(b"mp4")
            return MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch.object(engine, "check_available", return_value=(True, "ready")),
            patch.object(engine, "_node_cmd", side_effect=fake_node),
        ):
            engine.render(
                {
                    "width": 1080,
                    "height": 1920,
                    "scene_media": [str(media)],
                    "scenes": [
                        {"index": 1, "text": "第一场，内容够长。", "start": 0.0, "duration": 4.0},
                    ],
                },
                out,
            )
        payload = json.loads(
            (tmp_path / "ws" / "input" / "storyboard.json").read_text(encoding="utf-8")
        )
        assert payload["storyboard"]["width"] == 1080
        assert payload["storyboard"]["height"] == 1920


class TestVerifyOutputSize:
    """Delivery-side net (#523) — refuse to ship a wrong-shape video."""

    MATCH_JSON = '{"streams": [{"width": 1080, "height": 1920}]}'
    MISMATCH_JSON = '{"streams": [{"width": 1920, "height": 1080}]}'

    def _assets(self) -> dict[str, Any]:
        return {"width": 1080, "height": 1920, "scenes": []}

    def test_verify_passes_when_probed_size_matches(self, tmp_path: Any) -> None:
        with (
            patch("automedia.engines.implementations.video_remotion.find_tool") as m_which,
            patch("automedia.engines.implementations.video_remotion.subprocess.run") as m_run,
            patch(
                "automedia.engines.implementations.video_remotion.os.path.isfile",
                return_value=True,
            ),
        ):
            m_which.return_value = "/usr/bin/ffprobe"
            m_run.return_value = MagicMock(returncode=0, stdout=self.MATCH_JSON, stderr="")
            result = VideoRemotionEngine({})._verify_output_size(
                str(tmp_path / "out.mp4"),
                self._assets(),
            )
        assert result == (1080, 1920)

    def test_verify_raises_when_probed_size_mismatches(self, tmp_path: Any) -> None:
        with (
            patch("automedia.engines.implementations.video_remotion.find_tool") as m_which,
            patch("automedia.engines.implementations.video_remotion.subprocess.run") as m_run,
            patch(
                "automedia.engines.implementations.video_remotion.os.path.isfile",
                return_value=True,
            ),
        ):
            m_which.return_value = "/usr/bin/ffprobe"
            m_run.return_value = MagicMock(returncode=0, stdout=self.MISMATCH_JSON, stderr="")
            with pytest.raises(EngineExecutionError, match="1920x1080 does not match"):
                VideoRemotionEngine({})._verify_output_size(
                    str(tmp_path / "out.mp4"),
                    self._assets(),
                )

    def test_verify_skips_without_ffprobe(self, tmp_path: Any) -> None:
        """> No ffprobe → warn-and-continue, never a manufactured failure."""
        with (
            patch("automedia.engines.implementations.video_remotion.find_tool") as m_which,
            patch("automedia.engines.implementations.video_remotion.subprocess.run") as m_run,
        ):
            m_which.return_value = None
            result = VideoRemotionEngine({})._verify_output_size(
                str(tmp_path / "out.mp4"),
                self._assets(),
            )
        assert result is None
        assert m_run.called is False

    def test_probe_returns_none_on_garbage_stdout(self, tmp_path: Any) -> None:
        with (
            patch("automedia.engines.implementations.video_remotion.find_tool") as m_which,
            patch("automedia.engines.implementations.video_remotion.subprocess.run") as m_run,
            patch(
                "automedia.engines.implementations.video_remotion.os.path.isfile",
                return_value=True,
            ),
        ):
            m_which.return_value = "/usr/bin/ffprobe"
            m_run.return_value = MagicMock(returncode=0, stdout="not json", stderr="")
            assert VideoRemotionEngine({})._probe_video_size(str(tmp_path / "out.mp4")) is None
