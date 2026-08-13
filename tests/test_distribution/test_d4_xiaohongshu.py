"""Tests for D4 Xiaohongshu Rewrite Gate (D4Gate).

Covers output format verification (emoji/section headings), empty content
handling, file output creation, and content quality check validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from automedia.gates.distribution.d4_xiaohongshu import D4Gate
from tests.test_distribution.test_d_gate_base import (
    DGateTestBase,
    patch_llm_complete,
    patch_llm_failure,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock


# Canned response: >200 chars with ## heading (satisfies emoji OR section)
_D4_CANNED: str = (
    "## 我发现了AI内容创作的秘密\n\n"
    "不得不说，最近用AI工具做内容创作真的太香了！"
    "作为一个每天要产出大量内容的运营，"
    "我试了各种AI写作工具，终于找到了最佳组合。\n\n"
    "首先，用ChatGPT来生成选题和框架，"
    "然后用Claude来优化语言表达，"
    "最后用我们的自动化工具一键发布到各平台。\n\n"
    "谁懂啊，以前一天只能写2篇文章，"
    "现在轻轻松松10篇+，质量还更稳定。\n\n"
    "建议收藏这篇笔记，以后肯定用得上。"
    "你们平时用AI做内容吗？评论区聊聊～"
)

_D4_MIN_OUTPUT_LENGTH: int = 200


class TestD4(DGateTestBase):
    """D4 Xiaohongshu gate tests."""

    GATE_CLASS = D4Gate
    GATE_NAME = "D4"
    mock_llm_target = "automedia.gates.distribution.d4_xiaohongshu.llm_complete"
    MIN_OUTPUT_LENGTH = _D4_MIN_OUTPUT_LENGTH

    # ------------------------------------------------------------------
    # Gate-specific tests
    # ------------------------------------------------------------------

    def test_context_extra_d4_output(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Successful gate sets gate_context.extra['d4_output']. """
        gate = D4Gate()
        with patch_llm_complete(self.mock_llm_target, _D4_CANNED):
            gate.execute(d_gate_context)

        extra = d_gate_context.get("extra", {})
        d4_output = extra.get("d4_output", "")
        assert d4_output, "gate_context.extra['d4_output'] was not set"
        assert _D4_CANNED[:50] in d4_output

    def test_output_file_in_xiaohongshu_dir(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Output file is created under 04_distribution/xiaohongshu/."""
        import os

        gate = D4Gate()
        with patch_llm_complete(self.mock_llm_target, _D4_CANNED):
            result = gate.execute(d_gate_context)

        output_path = result.get("output_path", "")
        assert output_path, "No output_path in result"
        assert "04_distribution" in output_path
        assert "xiaohongshu" in output_path
        assert os.path.isfile(output_path)

    def test_content_quality_fails_no_emoji_nor_section(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Response without emoji or section heading fails quality check."""
        plain_text = "This is plain text without any emoji or markdown headings. " * 10
        assert len(plain_text) > _D4_MIN_OUTPUT_LENGTH
        gate = D4Gate()
        with patch_llm_complete(self.mock_llm_target, plain_text):
            result = gate.execute(d_gate_context)

        assert result["passed"] is False
        quality_checks = [
            c for c in result["checks"] if "quality" in c["name"].lower()
        ]
        assert len(quality_checks) >= 1
        assert quality_checks[0]["passed"] is False
