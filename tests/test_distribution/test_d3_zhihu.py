"""Tests for D3 Zhihu Rewrite Gate (D3ZhihuRewrite).

D3 has a different pattern from D1/D2/D4/D6/D7:
- Requires ``topic`` key in gate_context (not just ``content``)
- Uses ``load_prompt()`` and ``llm_complete()`` with ``system_prompt``
- Quality checks: min_length (>800 chars) + section_headings (## / ###)
- Returns ``expected_vs_actual`` instead of ``expected_map`` on some failures
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator
from unittest.mock import patch

import pytest

from automedia.gates.distribution.d3_zhihu import D3ZhihuRewrite

if TYPE_CHECKING:
    from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Canned response: >800 chars with ## / ### headings
# ---------------------------------------------------------------------------

_D3_CANNED: str = (
    "## AI技术趋势深度分析\n\n"
    "人工智能技术正在以前所未有的速度改变我们的世界。"
    "作为一名在AI领域深耕多年的从业者，我想和大家分享"
    "2025年最重要的技术趋势和深度思考。\n\n"
    "### 一、从大语言模型到通用人工智能的演进\n\n"
    "过去两年，以GPT-4、Claude和Gemini为代表的大语言模型"
    "展示了令人惊叹的能力。但真正的突破不在于模型规模的扩大，"
    "而在于推理能力的质变。2025年，我们看到了以下关键进展：\n\n"
    "首先是多模态能力的深度融合。模型不再仅仅是处理文本，"
    "而是能够同时理解图像、音频和视频信息，"
    "这为AI应用开辟了全新的可能性。\n\n"
    "其次是推理成本的持续下降。随着MoE架构和量化技术的成熟，"
    "运行顶级AI模型的成本已经降低了90%以上，"
    "这使得中小企业也能用上最先进的技术。\n\n"
    "### 二、AI在垂直行业的深度应用\n\n"
    "2025年的AI不再只是通用聊天机器人，"
    "而是在各个垂直行业找到了真正的杀手级应用。\n\n"
    "在医疗领域，AI辅助诊断系统已经能够准确识别"
    "超过200种疾病，准确率达到资深医生的水平。"
    "在金融领域，AI风控系统正在实时处理百万级交易，"
    "将欺诈检测的响应时间从小时级缩短到毫秒级。\n\n"
    "在教育领域，个性化学习助手正在根据每个学生的"
    "学习习惯和能力水平动态调整教学内容和节奏。"
    "在制造业，AI视觉检测系统正在以99.9%的准确率"
    "完成产品质检工作。\n\n"
    "### 三、AI安全与治理框架\n\n"
    "随着AI深入到社会各领域，安全与伦理问题日益凸显。"
    "2025年，多个国家和国际组织相继推出了AI治理框架，"
    "包括欧盟AI法案的正式实施和中国生成式AI管理办法的完善。\n\n"
    "企业需要在创新与合规之间找到平衡。"
    "建立负责任的AI开发和部署流程，"
    "不仅是法律要求，更是赢得用户信任的关键。\n\n"
    "### 四、对开发者和企业的建议\n\n"
    "面对AI技术的快速发展，我建议从业者关注以下几点：\n\n"
    "第一，持续学习。AI领域的技术迭代速度前所未有，"
    "保持学习是唯一的生存策略。\n\n"
    "第二，关注实际应用场景。技术本身没有价值，"
    "解决真实问题才是技术的意义所在。\n\n"
    "第三，重视数据质量和隐私保护。"
    "高质量的数据是AI系统的核心竞争力。\n\n"
    "### 结语\n\n"
    "2025年是AI从技术探索走向规模化应用的关键年份。"
    "那些能够将AI技术与业务需求紧密结合的组织，"
    "将在未来的竞争中占据先机。希望这篇文章能为你提供有价值的参考。"
    "欢迎在评论区分享你的观点和见解。"
)


# ---------------------------------------------------------------------------
# Helper to patch llm_complete in D3's module
# ---------------------------------------------------------------------------


@contextmanager
def _patch_d3_llm(
    response: str = _D3_CANNED,
) -> Generator[MagicMock, None, None]:
    """Mock ``llm_complete`` in D3's importing module."""
    target = "automedia.gates.distribution.d3_zhihu.llm_complete"
    with patch(target) as mock:
        mock.return_value = response
        yield mock


# ---------------------------------------------------------------------------
# Fixture: D3 gate context (adds ``topic`` to base context)
# ---------------------------------------------------------------------------


@pytest.fixture()
def d3_gate_context(d_gate_context: dict[str, Any]) -> dict[str, Any]:
    """D3 gate context with ``topic`` key added."""
    d_gate_context["topic"] = "AI Technology Trends 2025"
    return d_gate_context


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestD3Zhihu:
    """D3 Zhihu Rewrite gate tests."""

    GATE_CLASS = D3ZhihuRewrite
    GATE_NAME = "D3"

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def test_gate_name(self) -> None:
        """Gate name is 'D3'."""
        gate = D3ZhihuRewrite()
        assert gate.gate_name == "D3"

    def test_failure_mode(self) -> None:
        """Failure mode is 'retry'."""
        gate = D3ZhihuRewrite()
        assert gate.failure_mode == "retry"

    # ------------------------------------------------------------------
    # Success path
    # ------------------------------------------------------------------

    def test_success_with_topic(
        self, d3_gate_context: dict[str, Any]
    ) -> None:
        """Valid context + LLM success → gate passes."""
        gate = D3ZhihuRewrite()
        with _patch_d3_llm(_D3_CANNED):
            result = gate.execute(d3_gate_context)

        assert result["passed"] is True
        assert result["gate"] == "D3"
        assert result["error"] is None

    def test_success_produces_checks(
        self, d3_gate_context: dict[str, Any]
    ) -> None:
        """Successful gate returns quality checks."""
        gate = D3ZhihuRewrite()
        with _patch_d3_llm(_D3_CANNED):
            result = gate.execute(d3_gate_context)

        check_names = {c["name"] for c in result["checks"]}
        assert "zhihu_content_generated" in check_names
        assert "min_length" in check_names
        assert "section_headings" in check_names
        for check in result["checks"]:
            assert check["passed"] is True

    # ------------------------------------------------------------------
    # Empty / missing content
    # ------------------------------------------------------------------

    def test_empty_content_fails(
        self, d3_gate_context: dict[str, Any]
    ) -> None:
        """Empty content → gate fails with passed=False."""
        ctx = {**d3_gate_context, "content": ""}
        gate = D3ZhihuRewrite()
        result = gate.execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == "D3"

    def test_missing_topic_fails(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Missing 'topic' → gate fails before LLM call."""
        # d_gate_context does NOT have 'topic'
        gate = D3ZhihuRewrite()
        result = gate.execute(d_gate_context)

        assert result["passed"] is False
        assert result["gate"] == "D3"
        assert "topic" in result.get("error", "").lower()

    # ------------------------------------------------------------------
    # LLM failure
    # ------------------------------------------------------------------

    def test_llm_failure_fails(
        self, d3_gate_context: dict[str, Any]
    ) -> None:
        """LLM exception → gate fails with error."""
        from automedia.core.llm_client import LLMError

        target = "automedia.gates.distribution.d3_zhihu.llm_complete"
        with patch(target) as mock:
            mock.side_effect = LLMError("API timeout")
            result = D3ZhihuRewrite().execute(d3_gate_context)

        assert result["passed"] is False
        assert result["gate"] == "D3"

    # ------------------------------------------------------------------
    # Output file creation
    # ------------------------------------------------------------------

    def test_output_file_in_zhihu_dir(
        self, d3_gate_context: dict[str, Any]
    ) -> None:
        """Output file is created under 04_distribution/zhihu/."""
        import os

        gate = D3ZhihuRewrite()
        with _patch_d3_llm(_D3_CANNED):
            result = gate.execute(d3_gate_context)

        output_path = result.get("output_path", "")
        assert output_path, "No output_path in result"
        assert "04_distribution" in output_path
        assert "zhihu" in output_path
        assert os.path.isfile(output_path)

    def test_output_file_content_matches_canned(
        self, d3_gate_context: dict[str, Any]
    ) -> None:
        """Output file content matches the canned LLM response."""
        import os

        gate = D3ZhihuRewrite()
        with _patch_d3_llm(_D3_CANNED):
            result = gate.execute(d3_gate_context)

        output_path = result.get("output_path", "")
        if output_path:
            assert os.path.isfile(output_path)
            content = open(output_path, encoding="utf-8").read()
            assert _D3_CANNED in content or content.startswith(
                _D3_CANNED[:50]
            )
