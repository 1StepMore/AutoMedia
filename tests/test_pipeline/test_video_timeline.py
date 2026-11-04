"""Tests for the narration-aligned scene timeline (#351).

Method under test: promo/docs/时间轴-旁白分段对齐法.md — sentence-aligned
segmentation, per-segment TTS, ffprobe-measured cut points, honest
degradation when TTS/ffprobe are unavailable.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.pipelines import video_timeline as vt
from automedia.pipelines.video_timeline import (
    MAX_SCENES,
    build_scene_timeline,
    concat_audio,
    probe_audio_duration,
    split_narration,
)


class _FakeTTS:
    """Records calls; writes a fake audio file per synthesis.

    Failure points are chosen by output shape, not call order, so the
    per-segment path and the legacy single-track path can be failed
    independently:

    - ``fail_segment_from=N``: the Nth (and later) *segment* call raises.
    - ``fail_legacy``: the whole-text (narration.mp3) call raises.
    """

    def __init__(self, fail_segment_from: int | None = None, fail_legacy: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self._fail_segment_from = fail_segment_from
        self._fail_legacy = fail_legacy

    def generate_tts(self, text: str, voice: str = "", output_path: str = "") -> str:
        self.calls.append((text, output_path))
        if "narration-segment" in output_path:
            n = sum(1 for _, out in self.calls if "narration-segment" in out)
            if self._fail_segment_from is not None and n >= self._fail_segment_from:
                raise RuntimeError("segment tts boom")
        elif self._fail_legacy:
            raise RuntimeError("legacy tts boom")
        assert output_path
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as fh:
            fh.write(b"ID3fakeaudio" * 64)
        return output_path


def _probe_patch(durations: dict[str, float] | float):
    """Patch probe_audio_duration with a canned mapping or constant."""

    def _probe(path: str, ffprobe_cmd: str = "ffprobe", timeout: int = 30) -> float | None:
        if isinstance(durations, float):
            return durations
        for key, val in durations.items():
            if path.endswith(key):
                return val
        return None

    return patch.object(vt, "probe_audio_duration", side_effect=_probe)


class TestSplitNarration:
    def test_sentence_aligned_split(self) -> None:
        text = "第一句讲背景。第二句讲方法！第三句给结论？第四句收尾。"
        segs = split_narration(text)
        assert len(segs) == 4
        assert segs[0].endswith("。") and segs[0].startswith("第一句")

    def test_tiny_fragments_merge_into_previous(self) -> None:
        segs = split_narration(
            "这是一个足够长的句子，包含很多字。好！结尾也要足够长才行呀，这句很长。"
        )
        # "好！" is too short to stand alone → merged
        assert len(segs) == 2
        assert segs[0].endswith("好！")

    def test_caps_at_max_scenes(self) -> None:
        text = "。".join(f"第{i}句有足够多的字" for i in range(12)) + "。"
        segs = split_narration(text, max_scenes=MAX_SCENES)
        assert len(segs) <= MAX_SCENES

    def test_no_punctuation_single_segment(self) -> None:
        assert split_narration("没有任何句读的一整段话") == ["没有任何句读的一整段话"]

    def test_empty(self) -> None:
        assert split_narration("") == []
        assert split_narration("   ") == []


class TestProbeAudioDuration:
    def test_parses_duration(self) -> None:
        mock = MagicMock(returncode=0, stdout="3.520000\n")
        with patch("subprocess.run", return_value=mock):
            assert probe_audio_duration("a.mp3") == 3.52

    def test_nonzero_rc_is_none(self) -> None:
        mock = MagicMock(returncode=1, stdout="")
        with patch("subprocess.run", return_value=mock):
            assert probe_audio_duration("a.mp3") is None

    def test_garbage_output_is_none(self) -> None:
        mock = MagicMock(returncode=0, stdout="N/A\n")
        with patch("subprocess.run", return_value=mock):
            assert probe_audio_duration("a.mp3") is None

    def test_missing_ffprobe_is_none(self) -> None:
        with patch("subprocess.run", side_effect=OSError("no ffprobe")):
            assert probe_audio_duration("a.mp3") is None


class TestConcatAudio:
    def test_single_file_copied_to_canonical_name(self, tmp_path: Any) -> None:
        """A lone segment is copied to narration.mp3 — downstream (V7 records,
        tests, docs) expects the canonical track name, not the segment name."""
        f = tmp_path / "narration-segment-01.mp3"
        f.write_bytes(b"segment-bytes")
        out = str(tmp_path / "narration.mp3")
        assert concat_audio([str(f)], out) == out
        with open(out, "rb") as fh:
            assert fh.read() == b"segment-bytes"

    def test_concat_calls_ffmpeg(self, tmp_path: Any) -> None:
        a = tmp_path / "a.mp3"
        b = tmp_path / "b.mp3"
        out = str(tmp_path / "full.mp3")
        mock = MagicMock(returncode=0)

        def _fake_run(cmd: list[str], **_: Any) -> MagicMock:
            assert cmd[0] == "ffmpeg" and "-f" in cmd and "concat" in cmd
            with open(out, "wb") as fh:
                fh.write(b"concat")
            return mock

        with patch("subprocess.run", side_effect=_fake_run):
            result = concat_audio([str(a), str(b)], out)
        assert result == out

    def test_ffmpeg_missing_returns_none(self, tmp_path: Any) -> None:
        a = tmp_path / "a.mp3"
        b = tmp_path / "b.mp3"
        with patch("subprocess.run", side_effect=OSError("no ffmpeg")):
            assert concat_audio([str(a), str(b)], str(tmp_path / "out.mp3")) is None


class TestBuildSceneTimeline:
    def test_narration_aligned_cut_points(self, tmp_path: Any) -> None:
        text = "第一场讲背景，内容足够长。第二场讲方法，也有不少的字。第三场给出最终的结论与展望。"
        durations = {
            "narration-segment-01.mp3": 4.0,
            "narration-segment-02.mp3": 6.0,
            "narration-segment-03.mp3": 2.5,
            "narration.mp3": 12.5,
        }
        concat_path = str(tmp_path / "narration.mp3")
        with _probe_patch(durations), patch.object(vt, "concat_audio", return_value=concat_path):
            tl = build_scene_timeline(text, audio_pipeline=_FakeTTS(), audio_dir=str(tmp_path))

        assert tl["timeline_mode"] == "narration_aligned"
        scenes = tl["scenes"]
        assert [s["duration"] for s in scenes] == [4.0, 6.0, 2.5]
        assert scenes[1]["start"] == pytest.approx(4.0)
        assert scenes[2]["start"] == pytest.approx(10.0)
        assert tl["total_duration"] == pytest.approx(12.5)
        assert tl["narration_path"].endswith("narration.mp3")
        # per-scene texts are the sentence-aligned segments
        assert scenes[0]["text"].startswith("第一场")

    def test_per_segment_tts_failure_degrades(self, tmp_path: Any) -> None:
        text = "第一场讲这里的内容。第二场讲那里的方法，也要够长。第三场做最后的总结，还是够长的。"
        with (
            _probe_patch({"narration.mp3": 12.0}),
            patch.object(vt, "concat_audio", return_value=None),
        ):
            tl = build_scene_timeline(
                text,
                audio_pipeline=_FakeTTS(fail_segment_from=2),
                audio_dir=str(tmp_path),
                legacy_audio_path="",
            )
        assert tl["timeline_mode"] == "fallback_proportional"
        assert "per-segment TTS failed" in tl["reason"]
        assert len(tl["scenes"]) == 3
        # even split over the measured total
        starts = [s["start"] for s in tl["scenes"]]
        assert starts == [0.0, 4.0, 8.0]

    def test_ffprobe_missing_degrades_to_even_split(self, tmp_path: Any) -> None:
        text = "第一场的内容足够长。第二场的内容也足够长。"
        concat_path = str(tmp_path / "narration.mp3")
        with (
            _probe_patch({}),
            patch.object(vt, "concat_audio", return_value=concat_path),
        ):
            tl = build_scene_timeline(text, audio_pipeline=_FakeTTS(), audio_dir=str(tmp_path))
        assert tl["timeline_mode"] == "fallback_proportional"
        assert "ffprobe" in tl["reason"]

    def test_total_failure_unavailable(self, tmp_path: Any) -> None:
        tl = build_scene_timeline(
            "内容。",
            audio_pipeline=_FakeTTS(fail_segment_from=1, fail_legacy=True),
            audio_dir=str(tmp_path),
            legacy_audio_path="",
        )
        assert tl["timeline_mode"] == "unavailable"
        assert tl["scenes"] == []
        assert tl["reason"]


class TestCollectVideoAssetsPassesTimeline:
    def test_scenes_and_media_flow_into_assets(self) -> None:
        from automedia.pipelines.runner import _collect_video_assets

        ctx: dict[str, Any] = {
            "images": "",
            "fallback_frame": "/p/f.png",
            "audio_path": "/p/narration.mp3",
            "content": "c",
            "video_timeline_scenes": [
                {"id": "scene-1", "index": 1, "start": 0.0, "duration": 4.0, "text": "t"}
            ],
            "scene_media": ["/p/scene-01.png"],
        }
        with (
            patch(
                "os.path.isfile",
                side_effect=lambda p: p in {"/p/f.png", "/p/narration.mp3", "/p/scene-01.png"},
            ),
        ):
            assets = _collect_video_assets(ctx)
        assert assets["scenes"][0]["id"] == "scene-1"
        assert assets["scene_media"] == ["/p/scene-01.png"]

    def test_no_timeline_keeps_legacy_shape(self) -> None:
        from automedia.pipelines.runner import _collect_video_assets

        ctx: dict[str, Any] = {
            "fallback_frame": "/p/f.png",
            "audio_path": "/p/narration.mp3",
            "content": "c",
        }
        with patch("os.path.isfile", side_effect=lambda p: p in {"/p/f.png", "/p/narration.mp3"}):
            assets = _collect_video_assets(ctx)
        assert "scenes" not in assets


class TestProvisioningConsumesTimeline:
    """The hyperframes project provisioning renders the timeline scenes."""

    def _provision(self, tmp_path: Any, assets: dict[str, Any]) -> str:
        from automedia.engines.implementations.video_hyperframes import HyperFramesVideoEngine

        engine = HyperFramesVideoEngine()
        project = str(tmp_path / "proj")
        os.makedirs(project)
        with patch.object(HyperFramesVideoEngine, "_get_audio_duration", return_value=12.5):
            engine._provision_default_hyperframes_project(project, assets)
        return project

    def test_timeline_scenes_drive_compositions(self, tmp_path: Any) -> None:
        scene_png = tmp_path / "scene-01.png"
        scene_png.write_bytes(b"png")
        assets: dict[str, Any] = {
            "images": [str(scene_png)],
            "audio": "",
            "content": "legacy-content",
            "scenes": [
                {
                    "id": "scene-1",
                    "index": 1,
                    "start": 0.0,
                    "duration": 4.0,
                    "text": "第一场讲背景的内容。",
                },
                {
                    "id": "scene-2",
                    "index": 2,
                    "start": 4.0,
                    "duration": 8.5,
                    "text": "第二场给出结论，内容也足够长。",
                },
            ],
            "scene_media": [str(scene_png), ""],
        }
        self._provision(tmp_path, assets)

        comp1 = (tmp_path / "proj" / "compositions" / "01-scene.html").read_text(encoding="utf-8")
        comp2 = (tmp_path / "proj" / "compositions" / "02-scene.html").read_text(encoding="utf-8")
        # per-scene text landed in its own composition
        assert "第一场讲背景的内容" in comp1
        assert "第二场给出结论" in comp2
        # motion grammar present (exit mid-motion, camera push, stamp effect)
        assert "x: -2140" in comp1
        assert "scale: 1.04" in comp1
        assert "blur(4px)" in comp1
        # scene 1 carries its media (relative to compositions/); scene 2
        # falls back to the graphic block
        assert "../images/scene-01.png" in comp1
        assert "media graphic" in comp2
        # scene count footer
        assert "02 / 02" in comp2
        # legacy content must NOT leak into timeline-driven scenes
        assert "legacy-content" not in comp1

    def test_index_wires_all_scenes(self, tmp_path: Any) -> None:
        assets: dict[str, Any] = {
            "images": [],
            "audio": "",
            "content": "",
            "scenes": [
                {
                    "id": "scene-1",
                    "index": 1,
                    "start": 0.0,
                    "duration": 4.0,
                    "text": "甲场，内容够长。",
                },
                {
                    "id": "scene-2",
                    "index": 2,
                    "start": 4.0,
                    "duration": 4.0,
                    "text": "乙场，内容也够长。",
                },
                {
                    "id": "scene-3",
                    "index": 3,
                    "start": 8.0,
                    "duration": 4.5,
                    "text": "丙场，结论在这里。",
                },
            ],
        }
        self._provision(tmp_path, assets)
        index_html = (tmp_path / "proj" / "index.html").read_text(encoding="utf-8")
        assert 'data-composition-src="compositions/01-scene.html"' in index_html
        assert 'data-composition-src="compositions/03-scene.html"' in index_html
        assert (tmp_path / "proj" / "compositions" / "03-scene.html").is_file()
