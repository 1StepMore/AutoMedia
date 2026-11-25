"""Tests for the shared publishable-copy cleaner (#464).

The image track (``text_with_cover`` / ``social-thread``) posts the CW draft
verbatim; ``clean_publishable_copy`` strips script structure at the draft →
publishable-copy boundary while keeping reader-facing content.  The video
track's narration functions are re-exported unchanged — their own suites
(``tests/test_pipeline/test_narration_*.py``) pin that behaviour.
"""

from __future__ import annotations

import re
from typing import ClassVar

import pytest

from automedia.core.text_cleaning import (
    clean_publishable_copy,
    strip_narration_markup,
    strip_source_citations,
)


def _hit_counts(text: str) -> dict[str, int]:
    """Count the #464 marker inventory the DoD requires to be zero."""
    patterns = {
        "heading": r"^#{1,6}\s",
        "stage_direction": r"[［\[]\s*(?:画面|音效)[：：]",
        "sticker_tag": r"[［\[]\s*文字贴纸[：：]",
        "narration_prefix": r"(?:\*{0,2})(?:旁白|口播)(?:\*{0,2})\s*[：：]",
        "short_cue": r"[［\[]切[］\]]",
        "transition": r"[［\[]\s*转场[：：]",
    }
    return {name: len(re.findall(pat, text, re.M)) for name, pat in patterns.items()}


class TestCleanPublishableCopySocialThread:
    """social-thread 帖文清洗（#445 夜跑证据的标记形态，合成样本）."""

    DRAFT = """## Post 1: 别为了追求数量用AI做内容！质量才是王道

[画面：镜头剧烈晃动或快速推近] [文字贴纸：别盲目追求数量]
[音效：重低音Bass Drop]
旁白：很多公司以为AI能一键生成百万视频，结果全是垃圾。这完全搞错了顺序。

## Post 2: 垃圾进，垃圾出

[画面：[切] 绿幕背景] [转场：快速推拉] [文字贴纸：无效内卷]
旁白：没有经过优化的流程，再好的模型也救不了你。
"""

    def test_all_markers_removed(self) -> None:
        cleaned = clean_publishable_copy(self.DRAFT)
        counts = _hit_counts(cleaned)
        assert all(v == 0 for v in counts.values()), counts

    def test_content_is_kept(self) -> None:
        """剥标记不剥内容：标题文本、贴纸文案、正文原句都还在."""
        cleaned = clean_publishable_copy(self.DRAFT)
        assert "别为了追求数量用AI做内容！质量才是王道" in cleaned
        assert "垃圾进，垃圾出" in cleaned
        # 卡住条款：[文字贴纸：xxx] 的 xxx 是要上卡的文字 → 保留
        assert "别盲目追求数量" in cleaned
        assert "无效内卷" in cleaned
        assert "很多公司以为AI能一键生成百万视频" in cleaned
        assert "没有经过优化的流程" in cleaned

    def test_post_label_and_markers_gone(self) -> None:
        cleaned = clean_publishable_copy(self.DRAFT)
        assert "Post 1" not in cleaned
        assert "Post 2" not in cleaned
        assert "画面" not in cleaned
        assert "音效" not in cleaned


class TestCleanPublishableCopyTextWithCover:
    """text_with_cover 正文草稿清洗（#445 夜跑证据的标记形态，合成样本）."""

    DRAFT = """**1. 黄金开头（0:00-0:03）**

[画面：镜头怼脸，表情严肃]
旁白：别以为人工智能能救命。

**2. 痛点展开（0:03-0:15）**

[画面：屏幕录制展示混乱流程]
旁白：先跑通流程，再谈产量。
"""

    def test_all_markers_removed(self) -> None:
        cleaned = clean_publishable_copy(self.DRAFT)
        counts = _hit_counts(cleaned)
        assert all(v == 0 for v in counts.values()), counts

    def test_body_words_kept(self) -> None:
        cleaned = clean_publishable_copy(self.DRAFT)
        assert "别以为人工智能能救命" in cleaned
        assert "先跑通流程，再谈产量" in cleaned
        # 剥的是标记与结构，不是标题词本身（标题词归 #461）
        assert "黄金开头" in cleaned

    def test_no_literal_emphasis_markers(self) -> None:
        cleaned = clean_publishable_copy(self.DRAFT)
        assert "**" not in cleaned


class TestCleanPublishableCopyProsePreservation:
    """正常用法不许误剥（对照 #455 契约的「允许清单」立场）."""

    def test_plain_article_untouched(self) -> None:
        article = (
            "# 我的观点\n\n"
            "这是一篇普通文章。画面：一片湖。我们聊到「切」这个字的使用。\n\n"
            "结尾正常收束。"
        )
        cleaned = clean_publishable_copy(article)
        assert "这是一篇普通文章" in cleaned
        assert "画面：一片湖" in cleaned  # 散文里的「画面：」不是舞台提示
        assert "「切」这个字" in cleaned

    def test_empty_and_none_safe(self) -> None:
        assert clean_publishable_copy("") == ""


class TestNarrationReexportUnchanged:
    """视频轨行为不变：narration.py 的再导出与原实现等价（#459 回归锚）."""

    def test_strip_narration_markup_still_drops_script_structure(self) -> None:
        script = (
            "主题：先跑通流程\n"
            "镜头1｜0:03-0:09 [画面：镜头怼脸]\n"
            "口播：别以为人工智能能救命。\n"
            "[切]\n"
        )
        cleaned = strip_narration_markup(script)
        assert "主题" not in cleaned
        assert "镜头1" not in cleaned
        assert "口播" not in cleaned
        assert "画面" not in cleaned
        assert "别以为人工智能能救命。" in cleaned


class TestNestedCuesAreNeverSpoken:
    """嵌套方括号的分镜指令必须剥干净（#693，失败稿真实字符串）.

    写作模型实际产出 ``[画面：…[文字：…]]`` — 旧正则的 body 禁止内层方括号，
    整条 cue 原样保留，被 TTS 念出来、写进 SRT（narration.json 证据）。
    """

    # 失败稿原句：20261125_播客音频如何提升品牌影响力
    NESTED_CUES: ClassVar[list[str]] = [
        "[画面：分屏，左侧是生硬念广告的枯燥画面，右侧大红叉[文字：全是广告=直接劝退！]]",
        "[画面：绿幕讲解，博主出镜手势比划，弹出[文字：聊点真东西，才对味！]]",
        "[画面：[文字：聊透的，才是真爱粉！]，搭配数据攀升的动态特效]",
        "[画面：画面定格，[文字：播客，越听越靠谱！]加粗放大，光影扫过]",
        "[画面：[文字：扣「播客」领思路]，左下角亮关注按钮]",
    ]

    @pytest.mark.parametrize("cue", NESTED_CUES)
    def test_nested_cue_is_fully_removed(self, cue: str) -> None:
        cleaned = strip_narration_markup(cue)
        assert "[画面" not in cleaned
        assert "文字：" not in cleaned
        assert cleaned == ""

    def test_nested_cue_inline_is_removed_and_prose_kept(self) -> None:
        raw = (
            "口播：那咋破这个局？[画面：绿幕讲解，弹出[文字：聊点真东西，才对味！]]你得聊点真东西。"
        )
        cleaned = strip_narration_markup(raw)
        assert "[画面" not in cleaned
        assert "文字：" not in cleaned
        assert "那咋破这个局？" in cleaned
        assert "你得聊点真东西。" in cleaned

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # ``文字`` / ``文案`` / ``标题`` 是画面标注，不是口播（#693）。
            ("[文字：扣「播客」领思路]评论区见。", "评论区见。"),
            ("【标题：品牌播客起号思路】记住这点。", "记住这点。"),
            # 未闭合但内层已闭合的嵌套 cue 交给 dangling 规则。
            ("[画面：分屏，弹出[文字：直接劝退！]\n正文从这里开始。", "正文从这里开始。"),
        ],
    )
    def test_new_keywords_and_dangling_nested_cue(self, raw: str, expected: str) -> None:
        assert strip_narration_markup(raw) == expected


class TestLineLevelBracketHeadingIsNeverSpoken:
    """整行只有一个 ``【…】`` 标签的章节标题不该被念（#693）.

    失败稿的 ``【黄金开头（0:00-0:03）】`` 被 Whisper 证实整条念了出来
    （``黃金開頭,做撥可撥了小半年…``）。规则保守：标签内 ≤20 字、无句末
    标点；行内标签（前后有正文）不处理。
    """

    @pytest.mark.parametrize(
        "heading",
        [
            "【黄金开头（0:00-0:03）】",
            "【正文（0:03-0:45）】",
            "【高潮/反转（0:45-0:55）】",
            "【引导互动（0:55-0:60）】",
        ],
    )
    def test_line_level_tag_is_dropped(self, heading: str) -> None:
        cleaned = strip_narration_markup(f"{heading}\n口播：正文一句。")
        assert cleaned == "正文一句。"

    def test_bolded_line_level_tag_is_dropped(self) -> None:
        """失败稿里标题实际带 ``**`` 包裹，强调剥掉后应同样整行丢弃."""
        cleaned = strip_narration_markup("**【黄金开头（0:00-0:03）】**\n做播客播了小半年。")
        assert "黄金开头" not in cleaned
        assert cleaned == "做播客播了小半年。"

    def test_inline_tag_with_prose_is_kept(self) -> None:
        """正文里出现的 ``【…】``（前后有正文）不是章节标题，保留."""
        raw = "【重点】这件事很重要"
        assert strip_narration_markup(raw) == raw
        raw2 = "开头说完【重点】这件事很重要。"
        assert strip_narration_markup(raw2) == raw2

    def test_long_or_punctuated_tag_is_conservatively_kept(self) -> None:
        """超过 20 字或含句末标点的整行标签不命中，原样保留（保守规则）."""
        long_tag = "【这是一个超过了二十个字的标签所以不应该被整行丢弃的标题示范用例】"
        assert strip_narration_markup(long_tag) == long_tag
        punctuated = "【重点来了。】"
        assert strip_narration_markup(punctuated) == punctuated


class TestEmojiAreNeverSpoken:
    """emoji 不是口播内容：旁白与字幕边界直接删除（#496）.

    TTS 会把 👇 念成对图形的描述（夜跑 ASR 记成「反手十指向下指」），
    ASR 再把这句话写回 narration.json，观众听到的就是没人写过的话。
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("评论区聊聊👇", "评论区聊聊"),
            ("评论区聊聊👇。", "评论区聊聊。"),
            ("👉 点这里了解", "点这里了解"),
            ("跑通了✅️再发", "跑通了再发"),
            ("这条会🔥", "这条会"),
            ("家庭👨\u200d👩\u200d👧合影", "家庭合影"),
            ("1️⃣ 第一步", "第一步"),
            ("价格 19.9 元（含税），谢谢！", "价格 19.9 元（含税），谢谢！"),
            ("(ok), fine.", "(ok), fine."),
        ],
    )
    def test_pictographs_go_and_letters_stay(self, raw: str, expected: str) -> None:
        assert strip_narration_markup(raw) == expected

    def test_emoji_after_a_script_label_is_still_not_narration(self) -> None:
        assert strip_narration_markup("口播：评论区聊聊👇") == "评论区聊聊"


class TestSourceCitationsAreNeverSpoken:
    """行内引用标记不是口播内容（#664）.

    写作提示词要求成稿对数字带出处，``[Source: /home/…/x.md]`` 进了 TTS 后
    被整条念出来（ASR 记成 ``sourcehomerenanzai鞋杠…``），字幕链路却不含这段，
    音频于是多出整段无字幕的话、V5 锚点整体错位。
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # 任务单上的真实行形（#664 证据）：标记去掉、句子保留、不留双空格。
            (
                "在期限内完成 [Source: /home/renanzai/.hermes/x.md]。时间不够。",
                "在期限内完成。时间不够。",
            ),
            ("完成[Source: x] 。", "完成。"),
            ("完成。[Source: x] 时间不够。", "完成。时间不够。"),
            ("完成 [Source: x] ，然后继续。", "完成，然后继续。"),
            ("[来源：内部文档] 先把链路跑通。", "先把链路跑通。"),
            # 半角/全角冒号、单复数、大小写都是同一类标记。
            ("结论如下 [Source：/x/y.md]，仅供参考。", "结论如下，仅供参考。"),
            ("结论如下 [Sources: a, b] 仅供参考。", "结论如下仅供参考。"),
            # 一行两个标记都要剥（非贪婪，不能只剥第一个）。
            ("[SOURCE: ref][source：ref2] 一句话。", "一句话。"),
            ("done [Source: ref] next", "done next"),
        ],
    )
    def test_citation_goes_and_the_sentence_stays(self, raw: str, expected: str) -> None:
        assert strip_source_citations(raw) == expected

    def test_citation_only_line_is_dropped(self) -> None:
        assert strip_source_citations("[Source: x]\n正文。") == "正文。"

    def test_prose_mentioning_sources_is_untouched(self) -> None:
        prose = "这一段引用的来源是公开报告。[画面：镜头怼脸] 开场。"
        assert strip_source_citations(prose) == prose

    @pytest.mark.parametrize(
        "prose",
        [
            # 普通方括号注记不是引用标记，原样保留（既有行为）。
            "先看结论[注]再动手。",
            # 完全没有标记的句子必须逐字节不变。
            "这是一个没有任何标记的普通句子，标点齐全。",
        ],
    )
    def test_non_citation_prose_is_byte_identical(self, prose: str) -> None:
        assert strip_source_citations(prose) == prose

    def test_narration_markup_drops_citations_for_tts_and_srt(self) -> None:
        raw = "在更紧的期限内完成 [Source: /home/renanzai/.hermes/x.md]。时间不够。"
        cleaned = strip_narration_markup(raw)
        assert cleaned == "在更紧的期限内完成。时间不够。"
        assert "Source" not in cleaned
        assert "renanzai" not in cleaned
        assert "  " not in cleaned
