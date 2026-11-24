"""Tests for the vision-entries producer (issue #387)."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Any

import pytest

from automedia.pipelines.vision_entries import build_vision_entries

_SCENE = {"id": 1, "index": 0, "start": 0.0, "duration": 4.0, "text": "第一场文案"}


@dataclass
class _Proc:
    returncode: int = 0
    stdout: bytes = b"12.5"
    stderr: bytes = b""


class _FakeRun:
    """Records ffmpeg/ffprobe invocations; materialises the frame file on success."""

    def __init__(self, *, fail_on: set[str] | None = None, ffprobe_ok: bool = True) -> None:
        self.calls: list[list[str]] = []
        self.fail_on = fail_on or set()
        self.ffprobe_ok = ffprobe_ok

    def __call__(self, argv: list[str], **kwargs: Any) -> _Proc:
        self.calls.append(list(argv))
        if argv[0].endswith("ffprobe"):
            return _Proc(returncode=0 if self.ffprobe_ok else 1)
        dest = argv[-1]
        if os.path.basename(dest) in self.fail_on:
            return _Proc(returncode=1, stderr=b"boom")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(b"frame")
        return _Proc(returncode=0)


def _build(
    tmp_path: Any,
    *,
    kinds: list[str] | None = None,
    run: Any = None,
    scene: dict[str, Any] | None = None,
    **kw: Any,
):
    return build_vision_entries(
        str(tmp_path / "output.mp4"),
        [scene or _SCENE],
        [str(tmp_path / "scene-01.png")],
        kinds if kinds is not None else ["generated"],
        str(tmp_path / "frames"),
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        run=run or _FakeRun(),
        **kw,
    )


class TestBuildVisionEntries:
    def test_generated_scene_is_unjudged_never_pass(self, tmp_path: Any) -> None:
        """生成图无视觉模型时必须记 unjudged——不得默认 pass（#387 红线）。"""
        entries, stats = _build(tmp_path)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["checked"] is False
        assert entry["qa_passed"] is False
        assert entry["verdict"].startswith("unjudged")
        assert entry["source"] == "generated"
        assert stats["unjudged"] == 1 and stats["judged"] == 0

    def test_panel_scene_short_circuits(self, tmp_path: Any) -> None:
        """文字面板：面板文字就是该场文案，相关性由构造保证——登记通过。"""
        entries, stats = _build(tmp_path, kinds=["panel"])
        entry = entries[0]
        assert entry["checked"] is True
        assert entry["qa_passed"] is True
        assert entry["verdict"].startswith("panel")
        assert stats["judged"] == 1 and stats["unjudged"] == 0

    def test_frames_extracted_at_mid_and_end(self, tmp_path: Any) -> None:
        fake = _FakeRun()
        entries, stats = _build(tmp_path, run=fake)
        ffmpeg_calls = [c for c in fake.calls if c[0].endswith("ffmpeg")]
        assert len(ffmpeg_calls) == 2  # mid + end
        # mid 帧 -ss = start + duration/2 = 2.0
        assert ffmpeg_calls[0][ffmpeg_calls[0].index("-ss") + 1].startswith("2.")
        assert os.path.isfile(entries[0]["mid_frame_path"])
        assert os.path.isfile(entries[0]["end_silence_frame_path"])
        assert stats["frames_extracted"] == 2
        assert stats["frames_failed"] == 0

    def test_extraction_failure_leaves_path_empty_and_counts(self, tmp_path: Any) -> None:
        fake = _FakeRun(fail_on={"scene-1-mid.jpg"})
        entries, stats = _build(tmp_path, run=fake)
        assert entries[0]["mid_frame_path"] == ""
        assert entries[0]["end_silence_frame_path"] != ""
        assert stats["frames_failed"] == 1
        assert stats["frames_extracted"] == 1

    def test_missing_ffmpeg_raises(self, tmp_path: Any, monkeypatch: Any) -> None:
        """ffmpeg unavailable -> must raise (independent of ffmpeg on the machine)."""
        monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None)
        with pytest.raises(FileNotFoundError):
            build_vision_entries(
                str(tmp_path / "output.mp4"),
                [_SCENE],
                [],
                [],
                str(tmp_path / "frames"),
                ffmpeg_path=None,
                ffprobe_path=None,
                run=_FakeRun(),
            )

    def test_zero_frames_raises_so_v1_stays_skipped(self, tmp_path: Any) -> None:
        """视觉证据链整链为空 → raise（runner 降级为不写 entries，V1 如实 skip）。"""
        fake = _FakeRun(fail_on={"scene-1-mid.jpg", "scene-1-end.jpg"})
        with pytest.raises(RuntimeError, match="evidence chain is empty"):
            _build(tmp_path, run=fake)

    def test_missing_kind_defaults_to_unjudged(self, tmp_path: Any) -> None:
        """scene_media_kinds 缺场（素材丢失）→ 不能短路，仍记 unjudged。"""
        entries, stats = _build(tmp_path, kinds=[])
        assert entries[0]["source"] == "missing"
        assert entries[0]["checked"] is False
        assert stats["unjudged"] == 1


class _SequenceVLM:
    """按脚本逐次返回判定（或抛异常），并记录真实调用次数。"""

    model_name = "sequence-vlm"

    def __init__(self, seq: list[Any]) -> None:
        self.seq = list(seq)
        self.calls = 0

    def judge_frame(self, image_path: str, narration: str) -> dict[str, Any]:
        item = self.seq[min(self.calls, len(self.seq) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


_UNREADABLE = {"related": False, "determinable": False, "reason": "unreadable"}
_READABLE = {"related": True, "determinable": True, "reason": "ok"}


class TestVLMTransientRetry:
    """一次读图抖动不该把该场打成 unjudged（#666）。"""

    @pytest.fixture(autouse=True)
    def _no_backoff(self, monkeypatch: Any) -> None:
        # 退避只影响真实等待，测试里置空以免拖慢。
        monkeypatch.setattr("automedia.pipelines.vision_entries.time.sleep", lambda *_: None)
        monkeypatch.delenv("AUTOMEDIA_VLM_ATTEMPTS", raising=False)

    def test_readable_first_time_uses_one_attempt(self, tmp_path: Any) -> None:
        client = _SequenceVLM([_READABLE])
        entries, stats = _build(tmp_path, vlm_client=client)
        assert client.calls == 1
        assert entries[0]["checked"] is True
        assert stats["vlm_attempts"] == 1

    def test_case_a_unreadable_then_readable_is_judged_pass(self, tmp_path: Any) -> None:
        """A：第一次 unreadable、第二次读到 → checked/qa_passed，且打过 2 次。"""
        client = _SequenceVLM([_UNREADABLE, _READABLE])
        entries, stats = _build(tmp_path, vlm_client=client)
        entry = entries[0]
        assert entry["checked"] is True
        assert entry["qa_passed"] is True
        assert entry["verdict"].startswith("vlm: related")
        assert client.calls == 2
        assert stats["vlm_attempts"] >= 2

    def test_case_b_unreadable_twice_stays_unjudged(self, tmp_path: Any) -> None:
        """B：两次都读不了 → 仍 unjudged（不放松判据）。"""
        client = _SequenceVLM([_UNREADABLE, _UNREADABLE])
        entries, stats = _build(tmp_path, vlm_client=client)
        entry = entries[0]
        assert entry["checked"] is False
        assert entry["verdict"].startswith("unjudged:")
        assert client.calls == 2
        assert stats["unjudged"] == 1

    def test_case_c_exception_twice_stays_unjudged(self, tmp_path: Any) -> None:
        """C：判官抛异常两次 → 不抛到上层，仍记 unjudged。"""
        client = _SequenceVLM([RuntimeError("transport down"), RuntimeError("transport down")])
        entries, stats = _build(tmp_path, vlm_client=client)
        entry = entries[0]
        assert entry["checked"] is False
        assert entry["verdict"].startswith("unjudged:")
        assert "VLM judging failed" in entry["verdict"]
        assert client.calls == 2
        assert stats["unjudged"] == 1

    def test_env_attempts_override_takes_effect(self, tmp_path: Any, monkeypatch: Any) -> None:
        monkeypatch.setenv("AUTOMEDIA_VLM_ATTEMPTS", "1")
        client = _SequenceVLM([_UNREADABLE, _READABLE])
        entries, _ = _build(tmp_path, vlm_client=client)
        assert client.calls == 1
        assert entries[0]["checked"] is False

    def test_invalid_env_attempts_falls_back_to_default(self, monkeypatch: Any) -> None:
        from automedia.pipelines import vision_entries as ve

        for raw in ("", "abc", "0", "-3"):
            monkeypatch.setenv("AUTOMEDIA_VLM_ATTEMPTS", raw)
            assert ve._resolve_max_vlm_attempts() == ve._MAX_VLM_ATTEMPTS


class _RecordingVLM:
    """Records the narration text handed to the judge; always returns readable."""

    model_name = "recording-vlm"

    def __init__(self) -> None:
        self.narrations: list[str] = []

    def judge_frame(self, image_path: str, narration: str) -> dict[str, Any]:
        self.narrations.append(narration)
        return {"related": True, "determinable": True, "reason": "ok"}


class TestVLMSeeOnScreenText:
    """The judge must compare the frame with what the frame shows (#670).

    #660 renders only the narrowed ``display`` excerpt (+ title) on the frame,
    so handing it the whole narration paragraph makes a correct frame read as
    unrelated/unreadable.
    """

    def test_judge_gets_display_when_scene_has_one(self, tmp_path: Any) -> None:
        scene = {
            **_SCENE,
            "display": "自动化的价值",
            "text": "自动化的价值也不是用机器替代创作者，而是把被重复动作挤占的时间还给你。",
        }
        client = _RecordingVLM()
        _build(tmp_path, scene=scene, vlm_client=client)
        assert client.narrations == ["自动化的价值"]

    def test_judge_falls_back_to_text_without_display(self, tmp_path: Any) -> None:
        scene = {**_SCENE, "text": "第一场文案"}
        client = _RecordingVLM()
        _build(tmp_path, scene=scene, vlm_client=client)
        assert client.narrations == ["第一场文案"]
