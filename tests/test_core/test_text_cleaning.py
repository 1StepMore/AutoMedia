"""Tests for the shared publishable-copy cleaner (#464).

The image track (``text_with_cover`` / ``social-thread``) posts the CW draft
verbatim; ``clean_publishable_copy`` strips script structure at the draft →
publishable-copy boundary while keeping reader-facing content.  The video
track's narration functions are re-exported unchanged — their own suites
(``tests/test_pipeline/test_narration_*.py``) pin that behaviour.
"""

from __future__ import annotations

import re

import pytest

from automedia.core.text_cleaning import (
    clean_publishable_copy,
    strip_narration_markup,
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
