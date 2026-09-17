"""Chinese (CN) AI-taste detection tests for G1Humanizer gate.

The gate now detects Chinese AI-writing patterns (空洞开头, 笼统主语,
句首废话连接词, 模板化总结, 官腔黑话, 绝对化表述) in addition to the
English ones. These tests prove each Chinese pattern fires, clean natural
Chinese passes, the rewrite removes/softens flagged phrases, and English
behavior is unchanged (regression).
"""

from __future__ import annotations

from typing import Any

from automedia.gates.humanizer import (
    _SENTENCE_SPLIT_RE,
    G1Humanizer,
    _check_absolute_assertions,
    _check_filler_connectors,
    _check_hollow_intros,
    _check_overacademic_vocabulary,
    _check_repetitive_structures,
    _check_template_conclusions,
    _check_vague_subjects,
    _rewrite_content,
)

_CLEAN_CN = "人工智能正在改变我们的生活方式。科技创新让效率大幅提升。团队协作是成功的关键。"


# =========================================================================
# Sentence splitting
# =========================================================================


class TestCnSentenceSplitting:
    """The sentence splitter handles Chinese sentence-enders."""

    def test_splits_on_chinese_punctuation(self) -> None:
        parts = _SENTENCE_SPLIT_RE.split("你好。你好！你好？")
        assert parts == ["你好。", "你好！", "你好？"]

    def test_splits_cjk_directly_after_punctuation(self) -> None:
        parts = _SENTENCE_SPLIT_RE.split("第一句。第二句")
        assert parts == ["第一句。", "第二句"]

    def test_english_split_unchanged(self) -> None:
        parts = _SENTENCE_SPLIT_RE.split("Hello. World!")
        assert parts == ["Hello.", "World!"]

    def test_decimal_point_not_split(self) -> None:
        parts = _SENTENCE_SPLIT_RE.split("Pi is 3.14 exactly.")
        assert parts == ["Pi is 3.14 exactly."]

    def test_no_trailing_empty_sentence(self) -> None:
        parts = _SENTENCE_SPLIT_RE.split("你好。")
        assert parts == ["你好。"]

    def test_split_makes_second_sentence_detectable(self) -> None:
        """A hollow intro in the second sentence is only visible after a split."""
        result = _check_hollow_intros("科技正在改变生活。众所周知，这需要时间。")
        assert result["passed"] is False
        assert "众所周知" in result["detail"]


# =========================================================================
# Hollow intros (空洞开头)
# =========================================================================


class TestCnHollowIntros:
    """Chinese hollow intro detection."""

    def test_detects_zhi_de_zhu_yi(self) -> None:
        result = _check_hollow_intros("值得注意的是，科技正在改变生活。")
        assert result["passed"] is False
        assert "值得注意的是" in result["detail"]

    def test_detects_zhi_de_yi_ti(self) -> None:
        result = _check_hollow_intros("值得一提的是，团队表现优异。")
        assert result["passed"] is False
        assert "值得一提的是" in result["detail"]

    def test_detects_zong_de_lai_shuo(self) -> None:
        result = _check_hollow_intros("总的来说，方案是可行的。")
        assert result["passed"] is False
        assert "总的来说" in result["detail"]

    def test_detects_sui_zhe(self) -> None:
        result = _check_hollow_intros("随着科技的发展，人工智能进入了生活。")
        assert result["passed"] is False
        assert "随着" in result["detail"]

    def test_detects_wo_men_xu_yao_ren_shi_dao(self) -> None:
        result = _check_hollow_intros("我们需要认识到问题的复杂性。")
        assert result["passed"] is False
        assert "我们需要认识到" in result["detail"]

    def test_sentence_initial_only(self) -> None:
        """值得注意 mid-sentence is not a hollow opener."""
        result = _check_hollow_intros("我们值得注意的是这个数字。")
        assert result["passed"] is True

    def test_clean_chinese_passes(self) -> None:
        result = _check_hollow_intros("科技正在改变我们的生活方式。")
        assert result["passed"] is True


# =========================================================================
# Vague subjects (笼统主语)
# =========================================================================


class TestCnVagueSubjects:
    """Chinese vague/generic subject detection."""

    def test_detects_wo_men_ying_gai(self) -> None:
        result = _check_vague_subjects("我们应该立即采取行动。")
        assert result["passed"] is False
        assert "我们应该" in result["detail"]

    def test_detects_wo_men_bi_xu(self) -> None:
        result = _check_vague_subjects("我们必须重视数据安全。")
        assert result["passed"] is False
        assert "我们必须" in result["detail"]

    def test_detects_wo_men_xu_yao(self) -> None:
        result = _check_vague_subjects("我们需要更高效的工具。")
        assert result["passed"] is False
        assert "我们需要" in result["detail"]

    def test_detects_da_jia_dou_yao(self) -> None:
        result = _check_vague_subjects("大家都要参与讨论。")
        assert result["passed"] is False
        assert "大家都要" in result["detail"]

    def test_clean_chinese_passes(self) -> None:
        result = _check_vague_subjects("公司制定了明确的年度计划。")
        assert result["passed"] is True


# =========================================================================
# Filler connectors (句首废话连接词)
# =========================================================================


class TestCnFillerConnectors:
    """Chinese sentence-start filler connector detection."""

    def test_detects_ci_wai(self) -> None:
        result = _check_filler_connectors("此外，成本也在下降。")
        assert result["passed"] is False
        assert "此外" in result["detail"]

    def test_detects_yu_ci_tong_shi(self) -> None:
        result = _check_filler_connectors("与此同时，团队扩大了规模。")
        assert result["passed"] is False
        assert "与此同时" in result["detail"]

    def test_detects_ran_er(self) -> None:
        result = _check_filler_connectors("然而，结果并不理想。")
        assert result["passed"] is False
        assert "然而" in result["detail"]

    def test_detects_shou_xian(self) -> None:
        result = _check_filler_connectors("首先，我们需要明确目标。")
        assert result["passed"] is False
        assert "首先" in result["detail"]

    def test_detects_zui_hou(self) -> None:
        result = _check_filler_connectors("最后，我们完成了任务。")
        assert result["passed"] is False
        assert "最后" in result["detail"]

    def test_detects_yi_fang_mian(self) -> None:
        result = _check_filler_connectors("一方面，效率提升了。")
        assert result["passed"] is False
        assert "一方面" in result["detail"]

    def test_sentence_start_only(self) -> None:
        """A connector mid-sentence is not a sentence-start filler."""
        result = _check_filler_connectors("我们此外还要考虑成本。")
        assert result["passed"] is True

    def test_clean_chinese_passes(self) -> None:
        result = _check_filler_connectors("项目进展顺利，团队配合默契。")
        assert result["passed"] is True


# =========================================================================
# Template conclusions (模板化总结)
# =========================================================================


class TestCnTemplateConclusions:
    """Chinese template conclusion detection."""

    def test_detects_zong_shang_suo_shu(self) -> None:
        result = _check_template_conclusions("综上所述，项目取得了成功。")
        assert result["passed"] is False
        assert "综上所述" in result["detail"]

    def test_detects_zong_er_yan_zhi(self) -> None:
        result = _check_template_conclusions("总而言之，这是一个正确的决定。")
        assert result["passed"] is False
        assert "总而言之" in result["detail"]

    def test_detects_zong_zhi(self) -> None:
        result = _check_template_conclusions("总之，我们达成了目标。")
        assert result["passed"] is False
        assert "总之" in result["detail"]

    def test_detects_you_ci_ke_jian(self) -> None:
        result = _check_template_conclusions("由此可见，改革势在必行。")
        assert result["passed"] is False
        assert "由此可见" in result["detail"]

    def test_clean_chinese_passes(self) -> None:
        result = _check_template_conclusions("项目交付了预期的结果。")
        assert result["passed"] is True


# =========================================================================
# Over-academic vocabulary (官腔黑话)
# =========================================================================


class TestCnOveracademicVocabulary:
    """Chinese officialese / buzzword detection."""

    def test_detects_fu_neng(self) -> None:
        result = _check_overacademic_vocabulary("平台为商家全面赋能。")
        assert result["passed"] is False
        assert "赋能" in result["detail"]

    def test_detects_zhu_shou(self) -> None:
        result = _check_overacademic_vocabulary("数字化是转型的重要抓手。")
        assert result["passed"] is False
        assert "抓手" in result["detail"]

    def test_detects_bi_huan(self) -> None:
        result = _check_overacademic_vocabulary("我们打通了运营的闭环。")
        assert result["passed"] is False
        assert "闭环" in result["detail"]

    def test_detects_ke_li_du(self) -> None:
        result = _check_overacademic_vocabulary("方案需要细化到颗粒度。")
        assert result["passed"] is False
        assert "颗粒度" in result["detail"]

    def test_detects_di_ceng_luo_ji(self) -> None:
        result = _check_overacademic_vocabulary("这符合商业的底层逻辑。")
        assert result["passed"] is False
        assert "底层逻辑" in result["detail"]

    def test_detects_sheng_tai(self) -> None:
        result = _check_overacademic_vocabulary("平台正在构建完整的内容生态。")
        assert result["passed"] is False
        assert "生态" in result["detail"]

    def test_does_not_flag_sheng_tai_xi_tong(self) -> None:
        """生态系统 is a legitimate term, not the buzzword 生态."""
        result = _check_overacademic_vocabulary("城市生态系统非常重要。")
        assert result["passed"] is True

    def test_clean_chinese_passes(self) -> None:
        result = _check_overacademic_vocabulary("我们使用简单可靠的方法解决问题。")
        assert result["passed"] is True


# =========================================================================
# Absolute assertions (绝对化表述)
# =========================================================================


class TestCnAbsoluteAssertions:
    """Chinese absolute assertion detection."""

    def test_detects_hao_wu_zhui_wen(self) -> None:
        result = _check_absolute_assertions("毫无疑问，这是最佳方案。")
        assert result["passed"] is False
        assert "毫无疑问" in result["detail"]

    def test_detects_wu_yong_zhi_yi(self) -> None:
        result = _check_absolute_assertions("这是毋庸置疑的胜利。")
        assert result["passed"] is False
        assert "毋庸置疑" in result["detail"]

    def test_detects_yi_ding_hui(self) -> None:
        result = _check_absolute_assertions("这个策略一定会成功。")
        assert result["passed"] is False
        assert "一定会" in result["detail"]

    def test_detects_yong_yuan_bu_hui(self) -> None:
        result = _check_absolute_assertions("我们永远不会放弃。")
        assert result["passed"] is False
        assert "永远不会" in result["detail"]

    def test_detects_suo_you_ren_du(self) -> None:
        result = _check_absolute_assertions("所有人都认同这个方案。")
        assert result["passed"] is False
        assert "所有人都" in result["detail"]

    def test_detects_wei_yi_fang_fa(self) -> None:
        result = _check_absolute_assertions("这是解决问题的唯一的方法。")
        assert result["passed"] is False
        assert "唯一的方法" in result["detail"]

    def test_neutral_absolute_value_usage_passes(self) -> None:
        """绝对 in 绝对值 is a neutral technical term — must stay unflagged."""
        result = _check_absolute_assertions("这个数据的绝对值是五。")
        assert result["passed"] is True

    def test_clean_chinese_passes(self) -> None:
        result = _check_absolute_assertions("这个方案看起来比较稳妥。")
        assert result["passed"] is True


# =========================================================================
# Repetitive structures (重复性结构)
# =========================================================================


class TestCnRepetitiveStructures:
    """Chinese repetitive sentence-opening detection."""

    def test_detects_three_wo_men_openings(self) -> None:
        text = "我们应该创新。我们应该专注。我们应该坚持。"
        result = _check_repetitive_structures(text)
        assert result["passed"] is False
        assert "我" in result["detail"]

    def test_varied_openings_pass(self) -> None:
        text = "我们坚持创新。客户体验很好。团队协作高效。"
        result = _check_repetitive_structures(text)
        assert result["passed"] is True


# =========================================================================
# Rewrite (改写)
# =========================================================================


class TestCnRewrite:
    """_rewrite_content removes/softens flagged Chinese phrases."""

    def test_removes_hollow_intro(self) -> None:
        result = _rewrite_content("值得注意的是，科技正在改变生活。")
        assert "值得注意的是" not in result

    def test_removes_sui_zhe_clause(self) -> None:
        result = _rewrite_content("随着科技的发展，人工智能改变了生活。")
        assert "随着" not in result

    def test_removes_filler_connector(self) -> None:
        result = _rewrite_content("此外，我们还需要更多时间。")
        assert "此外" not in result

    def test_removes_template_conclusion(self) -> None:
        result = _rewrite_content("综上所述，项目取得了成功。")
        assert "综上所述" not in result

    def test_softens_hao_wu_zhui_wen(self) -> None:
        result = _rewrite_content("毫无疑问，这是最好的选择。")
        assert "毫无疑问" not in result
        assert "可以说" in result

    def test_softens_yong_yuan_bu_hui(self) -> None:
        result = _rewrite_content("我们永远不会忘记这次教训。")
        assert "永远不会" not in result
        assert "通常不会" in result


# =========================================================================
# Gate-level integration (deterministic path)
# =========================================================================


class TestCnGateIntegration:
    """Gate-level behavior on Chinese content."""

    def test_clean_chinese_content_passes_all_checks(self) -> None:
        ctx: dict[str, Any] = {"content": _CLEAN_CN, "config": {"enable_llm": False}}
        result = G1Humanizer().execute(ctx)
        assert result["passed"] is True
        assert result["modified_content"] is None

    def test_chinese_ai_taste_content_fails(self) -> None:
        ctx: dict[str, Any] = {
            "content": "值得注意的是，科技正在改变生活。此外，我们需要重视隐私。",
            "config": {"enable_llm": False},
        }
        result = G1Humanizer().execute(ctx)
        assert result["passed"] is False
        assert result["modified_content"] is not None


# =========================================================================
# English regression
# =========================================================================


class TestCnEnglishRegression:
    """English detection/rewrite behavior must be unchanged."""

    def test_english_hollow_intro_still_detected(self) -> None:
        result = _check_hollow_intros("In today's world, technology is everywhere.")
        assert result["passed"] is False

    def test_english_filler_still_detected(self) -> None:
        result = _check_filler_connectors("Furthermore, the results were strong.")
        assert result["passed"] is False
        assert "Furthermore" in result["detail"]

    def test_english_mid_sentence_filler_still_passes(self) -> None:
        result = _check_filler_connectors("The plan was furthermore refined by the team.")
        assert result["passed"] is True

    def test_english_template_conclusion_still_detected(self) -> None:
        result = _check_template_conclusions("In conclusion, the project was a success.")
        assert result["passed"] is False

    def test_english_absolute_still_detected(self) -> None:
        result = _check_absolute_assertions("This always works perfectly.")
        assert result["passed"] is False

    def test_english_academic_still_detected(self) -> None:
        result = _check_overacademic_vocabulary("We utilize modern tools.")
        assert result["passed"] is False
        assert "utilize" in result["detail"]

    def test_english_repetitive_still_detected(self) -> None:
        text = "The system works. The system scales. The system adapts."
        result = _check_repetitive_structures(text)
        assert result["passed"] is False

    def test_english_rewrite_unchanged(self) -> None:
        result = _rewrite_content("In today's world, technology matters.")
        assert "in today" not in result.lower()


class TestRewriteRemovesMidTextSentenceStarts:
    """issue #74: rewrite previously only removed sentence-initial patterns at
    the very start of the text (^ anchored on the whole string); mid-text
    sentence starts survived, leaving the detector re-flagging the content.
    """

    def test_removes_mid_text_template_conclusion(self) -> None:
        result = _rewrite_content("人工智能正在改变世界。综上所述，这是一个重要的趋势。")
        assert "综上所述" not in result
        assert _check_template_conclusions(result)["passed"] is True

    def test_removes_mid_text_filler_connector(self) -> None:
        result = _rewrite_content("人工智能发展迅速。此外，我们还需要关注监管问题。")
        assert "此外" not in result
        assert _check_filler_connectors(result)["passed"] is True

    def test_removes_mid_text_hollow_intro(self) -> None:
        result = _rewrite_content("人工智能发展迅速。值得注意的是，这项技术需要谨慎对待。")
        assert "值得注意的是" not in result
        assert _check_hollow_intros(result)["passed"] is True

    def test_removes_sequential_cn_fillers(self) -> None:
        text = "首先，我们需要明确目标。其次，我们要制定计划。最后，严格执行。"
        result = _rewrite_content(text)
        for phrase in ("首先", "其次", "最后"):
            assert phrase not in result, f"{phrase} should be removed"
        assert _check_filler_connectors(result)["passed"] is True

    def test_removes_mid_text_vague_subject(self) -> None:
        result = _rewrite_content("人工智能发展迅速。我们应该加强监管。")
        assert "我们应该" not in result
        assert _check_vague_subjects(result)["passed"] is True

    def test_english_mid_text_removed_with_space_preserved(self) -> None:
        result = _rewrite_content(
            "AI is growing fast. Furthermore, we must act now. In conclusion, the outlook is good."
        )
        assert "furthermore" not in result.lower()
        assert "in conclusion" not in result.lower()
        assert "fast. we" in result  # inter-sentence space not fused
        assert _check_filler_connectors(result)["passed"] is True
        assert _check_template_conclusions(result)["passed"] is True

    def test_text_start_removal_unchanged(self) -> None:
        result = _rewrite_content("综上所述，人工智能是未来的方向。")
        assert "综上所述" not in result
