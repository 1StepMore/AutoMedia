"""Tests for D1 WeChat Distribution Gate (D1Gate).

Covers output format verification, empty content handling, file output
creation, and gate_context interaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from automedia.gates.distribution.d1_wechat import D1Gate
from tests.test_distribution.test_d_gate_base import (
    DGateTestBase,
    patch_llm_complete,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Canonical D1 tests via the base test class
# ---------------------------------------------------------------------------

_D1_CANNED: str = (
    "## AI技术趋势分析：2025年展望\n\n"
    "随着人工智能技术的飞速发展，2025年将成为AI应用的关键转折点。"
    "本文将从多个维度深入分析AI技术的最新趋势。\n\n"
    "### 多模态AI的崛起\n\n"
    "多模态AI技术正在改变我们与机器交互的方式。"
    "它能够同时处理文本、图像、音频和视频数据，"
    "为企业提供前所未有的内容生产能力。"
    "这项技术在医疗影像诊断、智能客服和内容创作等领域的应用"
    "正在快速扩展，带来显著的效率提升。\n\n"
    "### 边缘AI的普及\n\n"
    "边缘计算与AI的结合正在推动智能设备的革命。"
    "通过在设备端直接运行AI推理，"
    "我们能够大幅降低延迟并保护用户隐私。"
    "从智能手机到IoT设备，边缘AI正在让智能无处不在。\n\n"
    "### 生成式AI的内容革命\n\n"
    "从ChatGPT到Sora，生成式AI正在重新定义内容创作。"
    "自动化视频生成、智能文案撰写和个性化推荐系统"
    "正在帮助企业以前所未有的速度生产高质量内容。"
    "2025年，我们将看到更多创新的AI原生产品问世。\n\n"
    "### AI安全与伦理\n\n"
    "随着AI能力的增强，安全性和伦理问题变得日益重要。"
    "各国正在建立AI监管框架，企业也需要负责任地开发和部署AI系统。"
    "透明度和可解释性是赢得用户信任的关键。\n\n"
    "### 结语\n\n"
    "2025年将是AI技术从量变到质变的关键一年。"
    "企业需要积极拥抱AI变革，同时在应用过程中注重安全与伦理。"
    "本文由TestBrand提供，欢迎关注获取更多AI前沿资讯。"
)

_D1_MIN_OUTPUT_LENGTH: int = 500


class TestD1(DGateTestBase):
    """D1 WeChat gate tests."""

    GATE_CLASS = D1Gate
    GATE_NAME = "D1"
    mock_llm_target = "automedia.gates.distribution.d1_wechat.llm_complete"
    MIN_OUTPUT_LENGTH = _D1_MIN_OUTPUT_LENGTH

    # ------------------------------------------------------------------
    # Gate-specific tests
    # ------------------------------------------------------------------

    def test_context_extra_d1_output(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Successful gate sets gate_context.extra['d1_output']. """
        gate = D1Gate()
        with patch_llm_complete(self.mock_llm_target, _D1_CANNED):
            gate.execute(d_gate_context)

        extra = d_gate_context.get("extra", {})
        d1_output = extra.get("d1_output", "")
        assert d1_output, "gate_context.extra['d1_output'] was not set"
        assert _D1_CANNED in d1_output or _D1_CANNED[:50] in d1_output

    def test_output_file_in_wechat_dir(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Output file is created under 04_distribution/wechat/."""
        import os

        gate = D1Gate()
        with patch_llm_complete(self.mock_llm_target, _D1_CANNED):
            result = gate.execute(d_gate_context)

        output_path = result.get("output_path", "")
        assert output_path, "No output_path in result"
        assert "04_distribution" in output_path
        assert "wechat" in output_path
        assert os.path.isfile(output_path)

    def test_short_llm_response_fails(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """LLM returning content shorter than MIN_OUTPUT_LENGTH fails."""
        short_content = "Short content."
        gate = D1Gate()
        with patch_llm_complete(self.mock_llm_target, short_content):
            result = gate.execute(d_gate_context)

        assert result["passed"] is False
        length_checks = [
            c for c in result["checks"] if "length" in c["name"].lower()
        ]
        assert len(length_checks) >= 1
        assert length_checks[0]["passed"] is False
