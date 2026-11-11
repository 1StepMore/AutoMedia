"""The pluggable VLM seam behind V1's per-frame verdicts (#473).

Mock-channel tests: a related frame passes, an unrelated frame fails, and the
no-channel path keeps the honest ``unjudged`` (never a default pass).  V1's
thresholds and the frame-extraction logic are untouched — these tests only
pin the producer side and the V1 verdicts that flow from real entries.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any

from automedia.gates.vision_qa import V1VisionQA
from automedia.pipelines.vision_entries import build_vision_entries
from automedia.pipelines.vlm_client import MockVLMClient, OpenAICompatVLMClient


@dataclass
class _Proc:
    returncode: int = 0
    stdout: bytes = b"12.5"
    stderr: bytes = b""


class _FakeRun:
    """Materialises the frame file on success (same shape as test_vision_entries)."""

    def __init__(self, *, fail_on: set[str] | None = None) -> None:
        self.fail_on = fail_on or set()

    def __call__(self, argv: list[str], **kwargs: Any) -> _Proc:
        if argv[0].endswith("ffprobe"):
            return _Proc()
        dest = argv[-1]
        if os.path.basename(dest) in self.fail_on:
            return _Proc(returncode=1, stderr=b"boom")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(b"frame")
        return _Proc(returncode=0)


_SCENE = {"id": 1, "index": 0, "start": 0.0, "duration": 4.0, "text": "一张办公桌"}


class _FakeResponse:
    """Minimal stand-in for the SDK response object."""

    def __init__(self, content: str) -> None:
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]


def _make_client(content: str) -> tuple[OpenAICompatVLMClient, dict[str, Any]]:
    captured: dict[str, Any] = {}

    class _Completions:
        @staticmethod
        def create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return _FakeResponse(content)

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    return OpenAICompatVLMClient(_Client(), "glm-4v"), captured


class TestOpenAICompatVLMClientParsing:
    def test_parses_json_verdict(self, tmp_path: Any) -> None:
        frame = tmp_path / "scene-1-mid.jpg"
        frame.write_bytes(bytes([0xFF, 0xD8, 0xFF]) + b"fakejpeg")
        client, _ = _make_client('{"related": true, "reason": "desk matches narration"}')
        verdict = client.judge_frame(str(frame), "一张办公桌")
        assert verdict == {"related": True, "reason": "desk matches narration"}

    def test_unparseable_answer_is_not_a_pass(self, tmp_path: Any) -> None:
        frame = tmp_path / "scene-1-mid.jpg"
        frame.write_bytes(bytes([0xFF, 0xD8, 0xFF]) + b"fakejpeg")
        client, _ = _make_client("I think the frame looks fine!!")
        verdict = client.judge_frame(str(frame), "一张办公桌")
        assert verdict["related"] is False
        assert "unparseable" in verdict["reason"]

    def test_image_sent_as_data_url(self, tmp_path: Any) -> None:
        frame = tmp_path / "frame.jpg"
        frame.write_bytes(bytes([0xFF, 0xD8, 0xFF]) + b"fakejpeg")
        client, captured = _make_client('{"related": true, "reason": "ok"}')
        client.judge_frame(str(frame), "旁白")
        parts = captured["messages"][1]["content"]
        assert parts[0]["type"] == "text"
        assert "旁白" in parts[0]["text"]
        assert parts[1]["type"] == "image_url"
        assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        encoded = parts[1]["image_url"]["url"].split(",", 1)[1]
        assert base64.b64decode(encoded)


class TestVisionEntriesWithMockChannel:
    def _build(self, tmp_path: Any, client: Any) -> tuple[list[dict[str, Any]], dict[str, int]]:
        return build_vision_entries(
            str(tmp_path / "output.mp4"),
            [_SCENE],
            [str(tmp_path / "scene-01.png")],
            ["generated"],
            str(tmp_path / "frames"),
            ffmpeg_path="ffmpeg",
            ffprobe_path="ffprobe",
            run=_FakeRun(),
            vlm_client=client,
        )

    def test_related_frame_is_judged_pass(self, tmp_path: Any) -> None:
        client = MockVLMClient(default_related=True, reason="frame shows the desk")
        entries, stats = self._build(tmp_path, client)
        generated = [e for e in entries if e["source"] == "generated"]
        assert generated and generated[0]["checked"] is True
        assert generated[0]["qa_passed"] is True
        assert generated[0]["verdict"].startswith("vlm: related")
        assert stats["judged"] >= 1
        # the channel saw the frame + narration
        assert client.calls and client.calls[0][1] == "一张办公桌"

    def test_unrelated_frame_is_judged_fail(self, tmp_path: Any) -> None:
        client = MockVLMClient(default_related=False, reason="black frame, no desk")
        entries, stats = self._build(tmp_path, client)
        generated = [e for e in entries if e["source"] == "generated"]
        assert generated[0]["checked"] is True
        assert generated[0]["qa_passed"] is False
        assert generated[0]["verdict"].startswith("vlm: unrelated")
        assert stats["judged"] >= 1

    def test_v1_verdicts_follow_real_entries(self, tmp_path: Any) -> None:
        """V1 的「entries 全判 + 红线」按真实判定走：全相关 → pass."""
        client = MockVLMClient(default_related=True)
        entries, _ = self._build(tmp_path, client)
        result = V1VisionQA().execute({"entries": entries})
        assert result["passed"] is True

        client_bad = MockVLMClient(default_related=False)
        entries_bad, _ = self._build(tmp_path, client_bad)
        result_bad = V1VisionQA().execute({"entries": entries_bad})
        assert result_bad["passed"] is False

    def test_judging_failure_degrades_to_unjudged(self, tmp_path: Any) -> None:
        class _ExplodingClient:
            def judge_frame(self, image_path: str, narration: str) -> dict[str, Any]:
                raise RuntimeError("transport down")

        entries, stats = self._build(tmp_path, _ExplodingClient())
        generated = [e for e in entries if e["source"] == "generated"]
        assert generated[0]["checked"] is False
        assert "VLM judging failed" in generated[0]["verdict"]
        assert stats["unjudged"] >= 1


class TestNoChannelStaysUnjudged:
    def test_no_client_keeps_unjudged(self, tmp_path: Any, monkeypatch: Any) -> None:
        """无通道 → unjudged + 原因（契约：绝不默认 pass）."""
        from automedia.pipelines import vlm_client as vlm_module

        monkeypatch.setattr(vlm_module, "create_vlm_client", lambda *a, **k: None)
        entries, stats = build_vision_entries(
            str(tmp_path / "output.mp4"),
            [_SCENE],
            [str(tmp_path / "scene-01.png")],
            ["generated"],
            str(tmp_path / "frames"),
            ffmpeg_path="ffmpeg",
            ffprobe_path="ffprobe",
            run=_FakeRun(),
            vlm_client=None,
        )
        generated = [e for e in entries if e["source"] == "generated"]
        assert generated[0]["checked"] is False
        assert generated[0]["qa_passed"] is False
        assert "no vision-capable model configured" in generated[0]["verdict"]
        assert stats["unjudged"] >= 1

    def test_create_vlm_client_returns_none_without_config(self, monkeypatch: Any) -> None:
        from automedia.pipelines.vlm_client import create_vlm_client

        monkeypatch.setattr(
            "automedia.core.config_loader.load_config",
            lambda *a, **k: {"llm": {"vision": {}}},
        )
        assert create_vlm_client({"llm": {"vision": {}}}) is None


class TestJudgePromptShape:
    def test_system_prompt_demands_json(self) -> None:
        from automedia.pipelines.vlm_client import _JUDGE_SYSTEM_PROMPT

        assert "JSON" in _JUDGE_SYSTEM_PROMPT
        json.loads('{"related": true, "reason": "x"}')  # the demanded shape parses
