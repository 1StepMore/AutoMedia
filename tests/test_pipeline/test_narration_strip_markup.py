"""Markdown emphasis must not reach the narrator or the subtitles (#444).

The writer marks emphasis with ``**主题**``; TTS reads the asterisks aloud and
the SRT renders them verbatim.  TTS and SRT share one cleaner so the two
outputs cannot drift apart again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from automedia.pipelines.audio_pipeline import AudioPipeline
from automedia.pipelines.narration import strip_emphasis_markers, strip_narration_markup


class TestStripEmphasisMarkers:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("**主题**：先跑通流程", "主题：先跑通流程"),
            ("__主题__：先跑通流程", "主题：先跑通流程"),
            ("*主题*：先跑通流程", "主题：先跑通流程"),
            ("_主题_：先跑通流程", "主题：先跑通流程"),
            ("保留 snake_case 标识符", "保留 snake_case 标识符"),
            ("未配对的标记**", "未配对的标记"),
        ],
    )
    def test_only_the_markers_are_removed(self, raw: str, expected: str) -> None:
        assert strip_emphasis_markers(raw) == expected


class TestNarrationMarkupIncludesEmphasis:
    def test_headings_cues_and_emphasis_all_go(self) -> None:
        # 主题：本身是结构标签（#455 丢弃），这里只钉强调标记的剥离。
        raw = "## 抖音短视频脚本\n\n[画面：叹气]**排期**：先把链路跑通。\n"
        assert strip_narration_markup(raw) == "排期：先把链路跑通。"


class TestSrtDropsEmphasis:
    def test_generated_srt_has_no_markers(self, tmp_path: Path) -> None:
        path = AudioPipeline().generate_srt_from_scenes(
            [{"text": "**排期**：先把链路跑通。", "start": 0.0, "duration": 2.0}],
            str(tmp_path / "subtitle.srt"),
        )
        assert path
        body = Path(path).read_text(encoding="utf-8")
        assert "**" not in body
        assert "排期：先把链路跑通。" in body


class TestOneCleanerForTtsAndSrt:
    def test_srt_cues_are_the_cleaned_narration(self) -> None:
        raw = "## 标题\n\n[画面：叹气]**主题**：先跑通流程。\n- 第二句。"
        expected = strip_narration_markup(raw).replace("\n", "")
        assert "".join(AudioPipeline().split_caption_cues(raw)) == expected
