"""Script structure must not reach the narrator or the subtitles (#455).

The writer's draft mixes spoken prose with editor-facing scaffolding:
metadata rows (``主题：`` / ``品牌：``), shot headers (``镜头1｜0:03-0:09``),
the ``口播：`` label and transition tags such as ``[切]``.  #444 removed
markdown emphasis only; TTS still read the scaffolding aloud and the SRT
carried it verbatim.  The cleaner now drops structure labels too, while
leaving ordinary bracketed prose alone.
"""

from __future__ import annotations

import re

import pytest

from automedia.pipelines.narration import strip_narration_markup
from automedia.pipelines.video_timeline import split_narration

REAL_SCRIPT = """
## 抖音短视频脚本

主题：企业用AI做内容——先跑通流程，再谈产量
品牌：壹目贯维 ｜ 时长：约60秒 ｜ 风格：潮流·接地气
口播：做AI内容的老板，别再卷产量了——产量是结果，不是目标。

镜头1｜0:03-0:09
口播：你是不是也这样：招了人，买了账号，让AI一天狂输出一堆视频——播量平平，连好坏都讲不太清楚？
[切]
镜头2｜0:09-0:15
口播：与其铺一堆内容试错，不如先把一条内容的链路跑顺。
[切]
"""

_STRUCTURE_TOKENS = {
    "shot_labels": r"镜头\s*\d+",
    "timecodes": r"\d{1,2}:\d{2}\s*[-–—~]\s*\d{1,2}:\d{2}",
    "spoken_prefix": r"口播\s*[:：]",
    "transition_tags": r"\[切\]",
    "metadata_labels": r"(?:主题|品牌|时长|风格|平台|BGM)\s*[:：]",
}


def _cleaned_narration(raw: str) -> str:
    return "".join(split_narration(strip_narration_markup(raw)))


class TestStructureRows:
    @pytest.mark.parametrize(
        "row",
        [
            "主题：企业用AI做内容",
            "品牌：壹目贯维 ｜ 时长：约60秒 ｜ 风格：潮流·接地气",
            "镜头1｜0:03-0:09",
        ],
    )
    def test_structure_only_rows_disappear(self, row: str) -> None:
        assert strip_narration_markup(row) == ""

    def test_shot_header_before_spoken_line_is_peeled_off(self) -> None:
        assert strip_narration_markup("镜头2｜0:09-0:15口播：把链路跑顺。") == "把链路跑顺。"


class TestSpokenLineSurvives:
    def test_spoken_prefix_and_transition_tags_are_removed(self) -> None:
        raw = "口播：先把一条内容的链路跑顺。[切]"
        assert strip_narration_markup(raw) == "先把一条内容的链路跑顺。"

    def test_ordinary_parenthetical_survives(self) -> None:
        raw = "这套模板（含三份附件）可以直接用。"
        assert strip_narration_markup(raw) == raw

    def test_bracketed_prose_outside_cue_vocabulary_survives(self) -> None:
        raw = "用[AI]做内容，不是用[人海战术]堆产量。"
        assert strip_narration_markup(raw) == raw


class TestRealScriptIsClean:
    def test_no_structure_token_survives_sentence_split(self) -> None:
        narration = _cleaned_narration(REAL_SCRIPT)
        counts = {
            name: len(re.findall(pattern, narration)) for name, pattern in _STRUCTURE_TOKENS.items()
        }
        assert counts == dict.fromkeys(_STRUCTURE_TOKENS, 0)

    def test_first_spoken_line_is_prose_not_a_label(self) -> None:
        narration = _cleaned_narration(REAL_SCRIPT)
        assert "做AI内容的老板，别再卷产量了" in narration
        assert not narration.startswith(("主题", "口播", "品牌"))
        assert "不如先把一条内容的链路跑顺" in narration
