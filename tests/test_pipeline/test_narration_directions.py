"""Narration hygiene for production cues (#390).

The script carries ``[画面：…]`` / ``[音效：…]`` notes for whoever edits the
video.  They must not reach TTS or the SRT — but they must stay in the draft,
because the gates validate the author's words.
"""

from __future__ import annotations

from typing import Any

import pytest

from automedia.pipelines.audio_pipeline import AudioPipeline
from automedia.pipelines.narration import strip_narration_markup, strip_stage_directions


class TestStripStageDirections:
    def test_adjacent_cues_are_removed_and_prose_kept(self) -> None:
        raw = "[音效：玻璃碎裂][画面：对着镜头无奈叹气]你有没有发现，排期总在最后一刻崩？"
        assert strip_stage_directions(raw) == "你有没有发现，排期总在最后一刻崩？"

    def test_cue_containing_slash_and_colon_is_removed(self) -> None:
        raw = "[音效：文字贴纸转场声及玻璃碎裂/滑稽打击音效]下一句。"
        assert strip_stage_directions(raw) == "下一句。"

    @pytest.mark.parametrize("opener,closer", [("[", "]"), ("【", "】"), ("（", "）"), ("(", ")")])
    def test_all_bracket_styles(self, opener: str, closer: str) -> None:
        raw = f"{opener}画面：特写键盘{closer}正文在这里。"
        assert strip_stage_directions(raw) == "正文在这里。"

    def test_unterminated_cue_is_removed(self) -> None:
        """草稿被截断时，没闭合的提示符也必须消失，不能念进旁白."""
        raw = "[画面：对着镜头无奈叹气\n正文从这里开始。"
        assert strip_stage_directions(raw) == "正文从这里开始。"

    def test_ordinary_parenthetical_survives(self) -> None:
        """普通括号不是舞台提示（没有 cue 关键词），不能误删."""
        raw = "这套模板（含三份附件）可以直接用。"
        assert strip_stage_directions(raw) == raw


class TestStripNarrationMarkup:
    def test_headings_and_cues_are_both_removed(self) -> None:
        raw = "## 抖音短视频脚本\n\n### 黄金开头\n\n[画面：叹气]三个人管六个账号。\n"
        assert strip_narration_markup(raw) == "三个人管六个账号。"

    def test_draft_content_is_not_mutated(self) -> None:
        """清洗只作用于旁白链路，草稿与 gate 校验仍看原文（#390 期望 2）."""
        from automedia.pipelines.runner import _media_narration_text

        raw = "## 标题\n\n[画面：叹气]正文一句。"
        ctx: dict[str, Any] = {"content": raw, "mode": "short-video"}
        assert _media_narration_text(ctx) == "正文一句。"
        assert ctx["content"] == raw


class TestCaptionsExcludeCues:
    def test_first_cue_is_the_spoken_line(self) -> None:
        raw = "[音效：滑入][画面：无奈叹气]你有没有发现，小团队做内容排期时，总在最后一刻赶稿。"
        cues = AudioPipeline().split_caption_cues(raw)
        assert cues[0] == "你有没有发现，小团队做内容排期时，"
        assert not any("音效" in cue or "画面" in cue for cue in cues)

    def test_cue_break_never_lands_inside_a_direction(self) -> None:
        """先剔提示符再断句，否则一条字幕会从「音效：」中间开始."""
        raw = "[音效：文字贴纸转场声及玻璃碎裂/滑稽打击音效]下一条开始。"
        cues = AudioPipeline().split_caption_cues(raw)
        assert cues == ["下一条开始。"]
