"""Section-heading words must not reach the narrator (#461).

After #455/#459 stripped the timecodes, the heading-word bodies survived as
standalone lines (``黄金开头`` / ``正文`` / ``高潮/反转`` / ``引导互动``) and
TTS read them aloud.  The #461 裁定 strips the **label form** only: a whole
line of heading words (separators allowed), or a ``标题词：`` prefix at line
start.  The same words in ordinary prose (``这段高潮在于节奏``) survive.
"""

from __future__ import annotations

from automedia.core.text_cleaning import (
    _SECTION_HEADING_WORDS as HEADING_WORDS,
)
from automedia.pipelines.narration import strip_narration_markup


class TestHeadingWordInventory:
    """The centralized list is the single authority (契约 DoD 1)."""

    def test_owner_mandated_words_present(self) -> None:
        for word in ("黄金开头", "正文", "高潮", "引导互动", "结尾", "开场", "收尾"):
            assert word in HEADING_WORDS
        # 反转 comes from the #461 night-run ASR evidence (heading 行 = 高潮/反转)
        assert "反转" in HEADING_WORDS


class TestLabelFormsStripped:
    """标签形态必剥（DoD 3-①）."""

    def test_bare_standalone_word_dropped(self) -> None:
        cleaned = strip_narration_markup("**黄金开头（0:00-0:03）**\n口播：别堆素材。")
        assert "黄金开头" not in cleaned
        assert "别堆素材。" in cleaned

    def test_bold_standalone_word_dropped(self) -> None:
        cleaned = strip_narration_markup("**正文**\n先跑通流程再谈产量。")
        assert "正文" not in cleaned

    def test_slash_joined_words_dropped(self) -> None:
        """``高潮/反转`` — the real night-run draft's heading 行 (#461 证据)."""
        cleaned = strip_narration_markup("**高潮/反转（0:45-0:55）**\n记住，流程才是灵魂。")
        assert "高潮" not in cleaned
        assert "反转" not in cleaned
        assert "记住，流程才是灵魂。" in cleaned

    def test_standalone_word_without_markup_dropped(self) -> None:
        cleaned = strip_narration_markup("引导互动\n立即注册。")
        assert "引导互动" not in cleaned
        assert "立即注册。" in cleaned

    def test_colon_label_prefix_stripped_words_kept(self) -> None:
        cleaned = strip_narration_markup("高潮：节奏先乱后稳。")
        assert "节奏先乱后稳。" in cleaned
        # 标签本身不再出现
        assert cleaned.splitlines() == ["节奏先乱后稳。"]

    def test_all_owner_words_stripped_as_bare_lines(self) -> None:
        for word in HEADING_WORDS:
            cleaned = strip_narration_markup(f"**{word}**\n这句是口播。")
            assert word not in cleaned, word
            assert "这句是口播。" in cleaned


class TestProseUsagePreserved:
    """正文里的正常用法不许误剥（DoD 3-②）."""

    def test_word_inside_sentence_kept(self) -> None:
        cleaned = strip_narration_markup("这段高潮在于节奏的突变。")
        assert "这段高潮在于节奏的突变。" in cleaned

    def test_word_with_trailing_prose_kept(self) -> None:
        """「高潮来了」— 标题词后面跟着非标题词，不是标签形态."""
        cleaned = strip_narration_markup("高潮来了的时候，观众才会停留。")
        assert "高潮来了的时候，观众才会停留。" in cleaned

    def test_word_with_suffix_not_headed_by_colon_kept(self) -> None:
        cleaned = strip_narration_markup("结尾彩蛋别错过。")
        assert "结尾彩蛋别错过。" in cleaned

    def test_ordinary_prose_line_untouched(self) -> None:
        prose = "我们把流程跑通，产量自己会来。"
        assert strip_narration_markup(prose) == prose


class TestRealDraftRegression:
    """真实稿回归（DoD 4）：#455 夜跑真稿清洗后标题词命中 = 0，正文只减标题行."""

    REAL_DRAFT = """**黄金开头（0:00-0:03）**
壹目贯维告诉你真相：没流程的AI，就是个笑话！

**正文（0:03-0:45）**
别以为AI能救命！没有规矩，它就是个大号噪音制造机。

**高潮/反转（0:45-0:55）**
记住，AI只是工具，流程才是灵魂！

**引导互动（0:55-0:60）**
立即注册壹目贯维，免费体验这套流程。
"""

    def test_zero_heading_hits_after_cleaning(self) -> None:
        cleaned = strip_narration_markup(self.REAL_DRAFT)
        for word in HEADING_WORDS:
            assert word not in cleaned, word

    def test_prose_lines_all_kept(self) -> None:
        cleaned = strip_narration_markup(self.REAL_DRAFT)
        assert "壹目贯维告诉你真相" in cleaned
        assert "没有规矩，它就是个大号噪音制造机" in cleaned
        assert "记住，AI只是工具，流程才是灵魂" in cleaned
        assert "立即注册壹目贯维" in cleaned

    def test_length_delta_is_only_heading_lines(self) -> None:
        """正文长度变化 = 被剥掉的标题行本身，不伤正文."""
        cleaned = strip_narration_markup(self.REAL_DRAFT)
        prose_lines = [
            strip_narration_markup(line)
            for line in self.REAL_DRAFT.splitlines()
            if line and not line.startswith("**")
        ]
        assert cleaned == "\n".join(prose_lines)
