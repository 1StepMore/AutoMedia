"""The lint executor — V0's honest ``lint_result`` producer (#470).

Three objective checks, stdlib only: SRT/cue structure (index sequence,
``HH:MM:SS,mmm --> HH:MM:SS,mmm``, the ``-->`` separator), subtitle time
monotonicity, and script field completeness (every timeline scene carries
spoken text and a positive duration).  Bad samples must fail **naming the
position**; good samples pass silently.
"""

from __future__ import annotations

from typing import Any

from automedia.pipelines.lint_executor import run_lint

GOOD_SRT = """1
00:00:00,000 --> 00:00:03,200
别堆素材，先跑通流程。

2
00:00:03,200 --> 00:00:07,500
流程通了，产量自然来。
"""

GOOD_SCENES: list[dict[str, Any]] = [
    {"id": "scene-1", "index": 0, "start": 0.0, "duration": 3.2, "text": "别堆素材，先跑通流程。"},
    {"id": "scene-2", "index": 1, "start": 3.2, "duration": 4.3, "text": "流程通了，产量自然来。"},
]


def _ctx(srt: str = GOOD_SRT, scenes: list[dict[str, Any]] | None = GOOD_SCENES) -> dict[str, Any]:
    ctx: dict[str, Any] = {"srt_text": srt}
    if scenes is not None:
        ctx["video_timeline_scenes"] = scenes
    return ctx


class TestGoodSamplesPass:
    def test_clean_run_passes_every_check(self) -> None:
        result = run_lint(_ctx())
        assert result is not None
        assert result["errors"] == 0
        assert result["warnings"] == 0
        assert result["syntax_ok"] is True
        assert result["checks"] == {
            "srt_structure": "passed",
            "time_monotonic": "passed",
            "script_fields": "passed",
        }

    def test_clean_run_is_silent(self) -> None:
        """无问题时不产生噪音（DoD 4）：problems/warnings 为空."""
        result = run_lint(_ctx())
        assert result is not None
        assert result["problems"] == []
        assert result["warnings_detail"] == []


class TestSrtStructureFailures:
    def test_bad_index_sequence_names_the_cue(self) -> None:
        bad = GOOD_SRT.replace("2\n00:00:03,200", "5\n00:00:03,200")
        result = run_lint(_ctx(srt=bad))
        assert result is not None
        assert result["errors"] > 0
        assert result["checks"]["srt_structure"] == "failed"
        assert any("cue 2" in p and "does not follow" in p for p in result["problems"])

    def test_missing_arrow_names_the_cue(self) -> None:
        bad = GOOD_SRT.replace("-->", "=>")
        result = run_lint(_ctx(srt=bad))
        assert result is not None
        assert result["checks"]["srt_structure"] == "failed"
        assert result["syntax_ok"] is False
        assert any("missing '-->'" in p for p in result["problems"])

    def test_bad_time_format_names_the_cue(self) -> None:
        bad = GOOD_SRT.replace("00:00:03,200 --> 00:00:07,500", "3:20 --> 7:500")
        result = run_lint(_ctx(srt=bad))
        assert result is not None
        assert result["syntax_ok"] is True  # the other cue's timing parses
        assert any("not 'HH:MM:SS,mmm --> HH:MM:SS,mmm'" in p for p in result["problems"])


class TestMonotonicityFailures:
    def test_overlap_names_both_cues(self) -> None:
        bad = GOOD_SRT.replace("00:00:03,200 --> 00:00:07,500", "00:00:01,000 --> 00:00:07,500")
        result = run_lint(_ctx(srt=bad))
        assert result is not None
        assert result["checks"]["time_monotonic"] == "failed"
        assert any("overlaps previous cue 1" in p for p in result["problems"])

    def test_end_before_start_fails(self) -> None:
        bad = GOOD_SRT.replace("00:00:03,200 --> 00:00:07,500", "00:00:05,000 --> 00:00:04,000")
        result = run_lint(_ctx(srt=bad))
        assert result is not None
        assert any("end" in p and "before start" in p for p in result["problems"])


class TestScriptFieldFailures:
    def test_scene_without_text_fails_naming_the_scene(self) -> None:
        scenes = [{"id": "scene-1", "index": 0, "duration": 3.2, "text": ""}]
        result = run_lint(_ctx(scenes=scenes))
        assert result is not None
        assert result["checks"]["script_fields"] == "failed"
        assert any("scene scene-1" in p and "口播" in p for p in result["problems"])

    def test_scene_without_duration_fails_naming_the_scene(self) -> None:
        scenes = [{"id": "scene-2", "index": 1, "duration": 0.0, "text": "流程通了。"}]
        result = run_lint(_ctx(scenes=scenes))
        assert result is not None
        assert any("scene scene-2" in p and "时长" in p for p in result["problems"])

    def test_no_scene_timeline_records_skip_not_pass(self) -> None:
        """无场景时间轴（旧单轨路径）→ 该项记 skipped + 缺什么，绝不算 pass."""
        result = run_lint(_ctx(scenes=[]))
        assert result is not None
        assert result["checks"]["script_fields"] == "skipped"
        assert any("no scene timeline" in w for w in result["warnings_detail"])
        assert result["warnings"] == 1


class TestNoiseGuards:
    def test_warnings_capped(self) -> None:
        result = run_lint(_ctx(scenes=[]))
        assert result is not None
        assert result["warnings"] <= 10

    def test_missing_srt_returns_none(self) -> None:
        """无 SRT → 不写 lint_result，V0 走原本的诚实 skip."""
        assert run_lint({"srt_text": "", "subtitles_path": ""}) is None

    def test_reads_srt_from_disk_path(self, tmp_path: Any) -> None:
        srt_file = tmp_path / "narration.srt"
        srt_file.write_text(GOOD_SRT, encoding="utf-8")
        result = run_lint({"srt_text": "", "subtitles_path": str(srt_file)})
        assert result is not None
        assert result["errors"] == 0
