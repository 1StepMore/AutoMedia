"""V1 evidence recording (issue #638) — ``05_review/vision-qa.json`` + readable detail.

V1 判负必须留证据：无论 pass / fail 都落盘逐条结果（含判官理由原文与
reused/generated 来源标注）；``all_entries_passed`` 的 detail 同时给
0-based 索引与人读场景名。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from automedia.gates.vision_qa import V1VisionQA
from automedia.pipelines.vision_entries import build_vision_entries
from automedia.pipelines.vlm_client import MockVLMClient

#: 长于 200 字符的理由（现行为在 verdict 展示层截 200），标记放在 200 字符
#: 之后——证据文件的 ``reason`` 必须保留原文，含这个标记。
_LONG_REASON = (
    "the frame shows a generic gradient background that carries no relation to "
    "the narration line about quarterly revenue growth; the composition is "
    "empty, the palette clashes with the brand guide, and the key subject is "
    "missing entirely. SECOND_REASON_MARKER: the topic keyword never appears "
    "in any visual element of the frame."
)

_SCENES = [
    {"id": 1, "index": 0, "start": 0.0, "duration": 4.0, "text": "第一场文案"},
    {"id": 2, "index": 1, "start": 4.0, "duration": 4.0, "text": "第二场文案"},
]


@dataclass
class _Proc:
    returncode: int = 0
    stdout: bytes = b"12.5"
    stderr: bytes = b""


class _FakeRun:
    """Records ffmpeg/ffprobe invocations; materialises the frame file on success."""

    def __call__(self, argv: list[str], **kwargs: Any) -> _Proc:
        if argv[0].endswith("ffprobe"):
            return _Proc()
        dest = argv[-1]
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(b"frame")
        return _Proc()


def _build_entries(
    tmp_path: Any,
    *,
    kinds: list[str] | None = None,
    vlm: Any = None,
) -> list[dict[str, Any]]:
    entries, _stats = build_vision_entries(
        str(tmp_path / "output.mp4"),
        _SCENES,
        ["cover.png", "scene-02.png"],
        kinds if kinds is not None else ["reused", "generated"],
        str(tmp_path / "frames"),
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        run=_FakeRun(),
        vlm_client=vlm,
    )
    return entries


def _read_evidence(tmp_path: Any) -> dict[str, Any]:
    path = tmp_path / "05_review" / "vision-qa.json"
    assert path.is_file(), f"evidence file missing at {path}"
    return json.loads(path.read_text(encoding="utf-8"))


class TestVisionQAEvidence:
    def test_writes_vision_qa_json_on_pass(self, tmp_path: Any) -> None:
        """V1 pass 也必须留证据：文件存在、``passed: true``、entries 完整。"""
        entries = _build_entries(tmp_path, vlm=MockVLMClient(default_related=True))
        result = V1VisionQA().execute({"entries": entries, "project_dir": str(tmp_path)})
        assert result["passed"] is True

        data = _read_evidence(tmp_path)
        assert data["passed"] is True
        assert len(data["entries"]) == len(entries)
        for i, record in enumerate(data["entries"]):
            for key in (
                "index",
                "name",
                "kind",
                "image_path",
                "checked",
                "qa_passed",
                "verdict",
                "reason",
            ):
                assert key in record, f"entry {i} missing key {key}"
            assert record["index"] == i
            assert record["checked"] is True
            assert record["qa_passed"] is True

    def test_writes_vision_qa_json_on_fail(self, tmp_path: Any) -> None:
        """V1 fail：文件存在，失败 entry 的 reason 保留判官原文（不被截断）。"""
        entries = _build_entries(
            tmp_path, vlm=MockVLMClient(default_related=False, reason=_LONG_REASON)
        )
        result = V1VisionQA().execute({"entries": entries, "project_dir": str(tmp_path)})
        assert result["passed"] is False

        data = _read_evidence(tmp_path)
        assert data["passed"] is False
        failed = [e for e in data["entries"] if not e["qa_passed"]]
        assert failed, "expected at least one failed entry in the evidence"
        for record in failed:
            assert record["reason"].strip(), "failed entry must carry a non-empty reason"
        # 完整原文：200 字符之后的"第二个理由"标记必须在场，证明未截断。
        assert any("SECOND_REASON_MARKER" in e["reason"] for e in failed)

    def test_entry_kind_is_recorded(self, tmp_path: Any) -> None:
        """reused / generated 两种来源都要出现在证据 json 里。"""
        entries = _build_entries(
            tmp_path, kinds=["reused", "generated"], vlm=MockVLMClient(default_related=True)
        )
        assert {e["kind"] for e in entries} == {"reused", "generated"}

        result = V1VisionQA().execute({"entries": entries, "project_dir": str(tmp_path)})
        assert result["passed"] is True
        data = _read_evidence(tmp_path)
        assert {e["kind"] for e in data["entries"]} == {"reused", "generated"}

    def test_all_entries_passed_detail_lists_scene_names(self, tmp_path: Any) -> None:
        """detail 同时给 0-based 索引与人读场景名；name 缺失退回只给索引。"""
        entries = _build_entries(
            tmp_path, vlm=MockVLMClient(default_related=False, reason="unrelated frame")
        )
        result = V1VisionQA().execute({"entries": entries, "project_dir": str(tmp_path)})
        assert result["passed"] is False
        check = next(c for c in result["checks"] if c["name"] == "all_entries_passed")
        assert check["passed"] is False
        # 索引 [0, 1]（1-based 场景号是 01/02）：人读名必须并列给出。
        assert "[0, 1]" in check["detail"]
        assert "scene-01" in check["detail"]
        assert "scene-02" in check["detail"]

        # name 缺失的裸数据：退回只给索引，不造名。
        bare = [
            {
                "mid_frame_path": "f0.png",
                "end_silence_frame_path": "e0.png",
                "checked": True,
                "qa_passed": False,
            }
        ]
        result_bare = V1VisionQA().execute({"entries": bare})
        check_bare = next(
            c for c in result_bare["checks"] if c["name"] == "all_entries_passed"
        )
        assert check_bare["detail"] == "entries [0] failed vision QA"
