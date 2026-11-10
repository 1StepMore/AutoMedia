"""Offline keyword extraction feeding V3 (#471).

The extractor is rule-based (no LLM, no new deps): punctuation/CJK-run
slicing, stopword trimming, frequency ranking.  These tests pin both the
extractor's behaviour and V3's verdicts on realistic contexts — an on-topic
draft passes, an off-topic draft fails, a low-coverage draft fails.
"""

from __future__ import annotations

from automedia.gates.content_semantic import (
    _check_keyword_coverage,
    _check_no_hallucination,
    _check_source_alignment,
)
from automedia.pipelines.keyword_extractor import (
    extract_content_keywords,
    extract_source_keywords,
)

TOPIC = "企业用AI做内容：为什么先跑通流程再谈产量"

SOURCE_MATERIAL = (
    "先跑通流程，再谈产量。流程包括选题、脚本、审核、发布四个环节。"
    "产量是流程跑通后的自然结果，不是目标本身。"
)

#: 正常稿 = 有源可依的改写稿：复述源的措辞与论点（V3 判据语义里的"合格
#: 写作"）。规则词表下，自然发挥的正文（大量新措辞）会红在幻觉判据上——
#: 该限制如实记录在 #471 的报告里，判据不放宽。
ON_TOPIC_BODY = (
    "企业用AI做内容：为什么先跑通流程再谈产量？"
    "其实先跑通流程，再谈产量。流程包括选题、脚本、审核、发布四个环节。"
    "产量是流程跑通后的自然结果，不是目标本身。"
    "流程不通，堆再多素材也是垃圾。"
)

OFF_TOPIC_BODY = (
    "今天聊聊咖啡的冲煮技巧。手冲咖啡的水温控制在92度最合适，"
    "研磨度决定了萃取效率。浅烘豆子适合中等研磨，风味更明亮。"
    "冲煮时间两分半，粉水比一比十五。产量与流程都是浮云。"
)


class TestExtractor:
    def test_source_keywords_cover_topic_terms(self) -> None:
        keywords = extract_source_keywords(f"{TOPIC}\n{SOURCE_MATERIAL}")
        for term in ("流程", "产量", "选题", "脚本", "审核", "发布"):
            assert term in keywords, term

    def test_content_keywords_are_repeated_phrases(self) -> None:
        keywords = extract_content_keywords(ON_TOPIC_BODY)
        for term in ("流程", "产量", "脚本", "审核", "发布"):
            assert term in keywords, term
        assert all(isinstance(k, str) and len(k) >= 2 for k in keywords)

    def test_off_topic_body_keywords_differ_from_source(self) -> None:
        source = extract_source_keywords(f"{TOPIC}\n{SOURCE_MATERIAL}")
        content = extract_content_keywords(OFF_TOPIC_BODY)
        overlap = {k.lower() for k in source} & {k.lower() for k in content}
        # 咖啡稿与 AI 内容源几乎没有共享词——正是跑题信号
        assert len(overlap) / max(1, len(set(content))) < 0.3

    def test_empty_text_is_safe(self) -> None:
        assert extract_source_keywords("") == []
        assert extract_content_keywords("") == []


def _v3_inputs(topic: str, source: str, body: str) -> dict:
    return {
        "source_texts": [topic, source],
        "source_keywords": extract_source_keywords(f"{topic}\n{source}"),
        "content_keywords": extract_content_keywords(body),
    }


class TestV3Verdicts:
    """DoD 3：①正常稿 passed ②跑题稿 failed ③覆盖不足 failed."""

    def test_on_topic_draft_passes_all_three(self) -> None:
        ctx = _v3_inputs(TOPIC, SOURCE_MATERIAL, ON_TOPIC_BODY)
        coverage = _check_keyword_coverage(ctx["source_keywords"], ctx["content_keywords"])
        alignment = _check_source_alignment(ctx["source_texts"])
        hallucination = _check_no_hallucination(ctx["source_keywords"], ctx["content_keywords"])
        assert coverage["passed"] is True, coverage["detail"]
        assert alignment["passed"] is True, alignment["detail"]
        assert hallucination["passed"] is True, hallucination["detail"]

    def test_off_topic_draft_fails(self) -> None:
        ctx = _v3_inputs(TOPIC, SOURCE_MATERIAL, OFF_TOPIC_BODY)
        coverage = _check_keyword_coverage(ctx["source_keywords"], ctx["content_keywords"])
        hallucination = _check_no_hallucination(ctx["source_keywords"], ctx["content_keywords"])
        # 跑题稿至少踩中覆盖率或幻觉两条之一，且覆盖率必红
        assert coverage["passed"] is False, coverage["detail"]
        assert hallucination["passed"] is False, hallucination["detail"]

    def test_insufficient_coverage_fails(self) -> None:
        """正文只复述源材料的一小部分 → 覆盖率不足."""
        thin_body = "流程很重要。流程是第一位的。流程决定一切。"
        ctx = _v3_inputs(TOPIC, SOURCE_MATERIAL, thin_body)
        coverage = _check_keyword_coverage(ctx["source_keywords"], ctx["content_keywords"])
        assert coverage["passed"] is False, coverage["detail"]

    def test_alignment_needs_two_sources(self) -> None:
        """单源（只有 topic）→ 对齐判据如实失败，不放宽."""
        alignment = _check_source_alignment([TOPIC])
        assert alignment["passed"] is False
        assert "need >= 2" in alignment["detail"]
