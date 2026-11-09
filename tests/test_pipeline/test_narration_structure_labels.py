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

#: The writer model's real output from the 2026-11-10 short-video run — a
#: different dialect of the same scaffolding: bolded ``口播文案：`` labels,
#: bolded section headers with parenthesised timecodes, colonised ``[切：…]``
#: cues, bracketed ``[画面：…]`` / ``[音效：…]`` notes.
WRITER_MODEL_SCRIPT = """**黄金开头（0:00-0:03）**
*   **[画面：黑屏，中间出现巨大的红色文字"别堆素材！"]**
*   **[音效：重低音打击声]**
*   **口播文案**：壹目贯维告诉你真相：没流程的AI，就是个笑话！

**正文（0:03-0:45）**
*   **[画面：快速闪过AI生成的各种杂乱、风格不一的图片，画面抖动]**
*   **[音效：刺耳的电流声]**
*   **口播文案**：别以为AI能救命！没有规矩，它就是个大号噪音制造机。\
你喂进去垃圾，它吐出来的全是废品。

*   **[切：画面瞬间变得干净，出现壹目贯维的操作界面，手指快速点击流程设置]**
*   **[音效：清脆的科技感音效]**
*   **口播文案**：这就是为什么我们用壹目贯维。先把规矩定死，剩下的交给机器自动填空。

**高潮/反转（0:45-0:55）**
*   **[画面：壹目贯维Logo特写，配合聚光灯效果]**
*   **[音效：重音]**
*   **口播文案**：记住，AI只是工具，流程才是灵魂！

**引导互动（0:55-0:60）**
*   **[画面：壹目贯维注册引导界面，出现"立即注册"按钮]**
*   **口播文案**：立即注册壹目贯维，免费体验这套流程，让你的AI内容起飞！"""

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


class TestWriterModelFormatVariants:
    """The writer model's actual output format (2026-11-10 short-video run,
    chased down while doing the #455 ASR acceptance): bolded ``口播文案：``
    labels, section headers carrying ``（0:00-0:03）`` timecodes, colonised
    ``[切：…]`` cues."""

    def test_koubo_wen_an_prefix_is_peeled_off(self) -> None:
        raw = "**口播文案**：壹目贯维告诉你真相：没流程的AI，就是个笑话！"
        assert strip_narration_markup(raw) == "壹目贯维告诉你真相：没流程的AI，就是个笑话！"

    def test_section_header_timecode_paren_is_stripped(self) -> None:
        cleaned = strip_narration_markup("**黄金开头（0:00-0:03）**")
        assert "0:00" not in cleaned
        assert "（" not in cleaned and "）" not in cleaned

    def test_colonised_cut_cue_is_stripped_with_body(self) -> None:
        raw = "[切：画面瞬间变得干净，出现壹目贯维的操作界面]先把规矩定死。"
        assert strip_narration_markup(raw) == "先把规矩定死。"

    def test_writer_model_script_is_clean_end_to_end(self) -> None:
        narration = _cleaned_narration(WRITER_MODEL_SCRIPT)
        counts = {
            name: len(re.findall(pattern, narration)) for name, pattern in _STRUCTURE_TOKENS.items()
        }
        assert counts == dict.fromkeys(_STRUCTURE_TOKENS, 0)
        assert "壹目贯维告诉你真相" in narration
