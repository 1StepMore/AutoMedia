"""``runner._produce_media_assets`` 的行为锁定（健康度 P0-1 接线）。

中文说明：V0–V7 校验的是媒体产物，而产物必须在**第一个 V 门之前**产出。
本文件用假引擎/假外部命令锁定三段语义：

* **无内容 / 无命令 ⇒ 一个键都不写**（V 门据此报 ``skipped``，而非拿假数据通过）；
* **链路完整 ⇒ 写出 V2/V5/V7 的输入键**（V 门不再跳过，改为真实判定）；
* **幂等** ⇒ 重复调用只产出一次。

真实外部命令（edge-tts / whisper / ffmpeg）在本机不存在，因此"真实产出"
不可在此验证——产出的**正确性**由这里对文件与上下文的断言锁定。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import patch

import pytest

from automedia.gates._context import GateContext
from automedia.gates._result import missing_input_result
from automedia.pipelines.runner import _media_narration_text, _produce_media_assets

_AUDIO_PATH = "automedia.pipelines.audio_pipeline.AudioPipeline"
_IMAGE_PATH = "automedia.pipelines.image_pipeline.ImagePipeline"
_ENGINE_PATH = "automedia.engines.resolve_engine"
_WHICH_PATH = "shutil.which"


class _FakeAudioPipeline:
    """最小 TTS/ASR/SRT 替身：在磁盘上留下真实文件。"""

    instances: ClassVar[list[_FakeAudioPipeline]] = []

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config
        _FakeAudioPipeline.instances.append(self)

    def generate_tts(self, text: str, voice: str = "", output_path: str = "") -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-mp3")
        return os.path.abspath(output_path)

    def transcribe_audio(self, audio_path: str, language: str = "zh") -> dict[str, Any]:
        return {"text": "hello world", "segments": [{"start": 0.0, "end": 1.0, "text": "hello"}]}

    def generate_srt(self, transcription: dict[str, Any], output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
        return os.path.abspath(output_path)


class _FakeImagePipeline:
    """最小图片替身：写出一张假帧。"""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config

    def generate_fallback_frame(self, topic: str, project_dir: str) -> str:
        path = Path(project_dir) / "02_images" / "fallback" / "fallback_frame.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-png")
        return str(path)


class _FakeVideoEngine:
    """最小视频引擎替身：写出一个假 mp4。"""

    def render(self, assets: dict[str, Any], output_path: str) -> str:
        assert assets.get("images") and assets.get("audio"), "render 需要图片与音频"
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-mp4")
        return os.path.abspath(output_path)


def _video_context(tmp_path: Path, *, content: str = "real content") -> GateContext:
    """构造一个 video 模式的上下文。"""
    return GateContext(
        topic="t",
        brand="b",
        mode="video_only",
        project_dir=str(tmp_path),
        content=content,
    )


@pytest.fixture(autouse=True)
def _reset_fake_instances() -> None:
    """每个用例前清空替身实例记录。"""
    _FakeAudioPipeline.instances.clear()


class TestNarrationText:
    """内容来源优先级：CW 产出 → 源材料 → 空。"""

    def test_uses_content_when_present(self) -> None:
        assert _media_narration_text(_video_context(Path("."), content="body")) == "body"

    def test_placeholder_falls_back_to_source_material(self) -> None:
        """``video_only`` 的占位符不能当旁白，改用 ``source_content``。"""
        ctx = _video_context(Path("."), content="[content skipped in video_only mode]")
        ctx["source_content"] = "source body"
        assert _media_narration_text(ctx) == "source body"

    def test_empty_when_nothing_available(self) -> None:
        ctx = _video_context(Path("."), content="[content skipped in video_only mode]")
        assert _media_narration_text(ctx) == ""


class TestNothingProducedPaths:
    """缺内容或缺命令 ⇒ 不写任何 V 门输入键（诚实跳过）。"""

    def test_no_content_writes_nothing(self, tmp_path: Path) -> None:
        ctx = _video_context(tmp_path, content="[content skipped in video_only mode]")
        _produce_media_assets(ctx)

        assert ctx.was_written("audio_path") is False
        assert ctx.was_written("video_path") is False
        assert ctx.was_written("required_files") is False
        # 且 V 门确实会跳过
        assert missing_input_result("V2", ctx, ("transcription", "audio_path")) is not None

    def test_missing_tools_writes_nothing(self, tmp_path: Path) -> None:
        ctx = _video_context(tmp_path)
        with patch(_WHICH_PATH, return_value=None):
            _produce_media_assets(ctx)

        assert ctx.was_written("audio_path") is False
        assert ctx.was_written("required_files") is False
        assert missing_input_result("V5", ctx, ("whisper_text", "srt_text")) is not None


class TestFullChain:
    """链路完整 ⇒ 写出 V2/V5/V7 的输入键，且 V 门不再跳过。"""

    def _run(self, tmp_path: Path) -> GateContext:
        ctx = _video_context(tmp_path)
        with (
            patch(_WHICH_PATH, return_value="/usr/bin/fake"),
            patch(_AUDIO_PATH, _FakeAudioPipeline),
            patch(_IMAGE_PATH, _FakeImagePipeline),
            patch(_ENGINE_PATH, return_value=_FakeVideoEngine()),
        ):
            _produce_media_assets(ctx)
        return ctx

    def test_audio_and_video_paths_written(self, tmp_path: Path) -> None:
        ctx = self._run(tmp_path)

        assert os.path.isfile(str(ctx.get("audio_path")))
        assert os.path.isfile(str(ctx.get("subtitles_path")))
        assert os.path.isfile(str(ctx.get("video_path")))

    def test_gate_inputs_written(self, tmp_path: Path) -> None:
        ctx = self._run(tmp_path)

        assert ctx.get("transcription") == "hello world"
        assert ctx.get("whisper_text") == "hello world"
        assert ctx.get("srt_text")
        assert ctx.was_written("audio_path") is True

    def test_v2_v5_v7_no_longer_skipped(self, tmp_path: Path) -> None:
        """这三门所需的键全部产出 ⇒ ``missing_input_result`` 返回 ``None``。"""
        ctx = self._run(tmp_path)

        assert missing_input_result("V2", ctx, ("transcription", "audio_path")) is None
        assert missing_input_result("V5", ctx, ("whisper_text", "srt_text")) is None
        assert (
            missing_input_result("V7", ctx, ("required_files", "file_sizes", "md5_records")) is None
        )

    def test_v7_artifact_ledger_is_self_consistent(self, tmp_path: Path) -> None:
        """V7 的清单只登记真实存在的文件，且 md5 记录自洽。"""
        ctx = self._run(tmp_path)

        required = ctx.get("required_files")
        assert isinstance(required, list) and required
        assert all(os.path.isfile(p) for p in required)

        sizes = ctx.get("file_sizes")
        assert isinstance(sizes, dict)
        assert all(sizes[p] > 0 for p in required)

        records = ctx.get("md5_records")
        assert isinstance(records, dict)
        for path in required:
            assert records[path]["expected"] == records[path]["actual"]

    def test_gates_never_scored_stay_skipped(self, tmp_path: Path) -> None:
        """无可信生产者的门（V0/V1/V3/V4/V6）仍须跳过——绝不写假数据。"""
        ctx = self._run(tmp_path)

        assert missing_input_result("V0", ctx, ("lint_result",)) is not None
        assert missing_input_result("V1", ctx, ("entries",)) is not None
        assert (
            missing_input_result("V3", ctx, ("source_keywords", "content_keywords", "source_texts"))
            is not None
        )
        assert missing_input_result("V4", ctx, ("voice_id", "segments")) is not None
        assert (
            missing_input_result(
                "V6", ctx, ("avg_brightness", "contrast", "opacity", "pixel_valid")
            )
            is not None
        )


class TestIdempotence:
    """重复调用只产出一次（V 门前 + finalize 兜底两条路径共用）。"""

    def test_second_call_is_a_noop(self, tmp_path: Path) -> None:
        ctx = _video_context(tmp_path)
        with (
            patch(_WHICH_PATH, return_value="/usr/bin/fake"),
            patch(_AUDIO_PATH, _FakeAudioPipeline),
            patch(_IMAGE_PATH, _FakeImagePipeline),
            patch(_ENGINE_PATH, return_value=_FakeVideoEngine()),
        ):
            _produce_media_assets(ctx)
            first_path = ctx.get("audio_path")
            _produce_media_assets(ctx)

        assert len(_FakeAudioPipeline.instances) == 1
        assert ctx.get("audio_path") == first_path

    def test_failure_still_marks_done(self, tmp_path: Path) -> None:
        """中途失败也在 ``finally`` 里置位，避免反复重试。"""
        ctx = _video_context(tmp_path)
        with (
            patch(_WHICH_PATH, return_value="/usr/bin/fake"),
            patch(_AUDIO_PATH, side_effect=RuntimeError("boom")),
        ):
            _produce_media_assets(ctx)

        assert ctx.get("_media_stage_done") is True
