"""Tests for D7 TikTok Distribution Gate (D7Gate).

Covers output format verification (100-500 char range), empty content
handling, file output creation, and output-length quality validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from automedia.gates.distribution.d7_tiktok import D7Gate
from tests.test_distribution.test_d_gate_base import (
    DGateTestBase,
    patch_llm_complete,
    patch_llm_failure,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock


# Canned response: between 100 and 500 characters
_D7_CANNED: str = (
    "你知道吗？2025年的AI已经能自动生成完整视频了！"
    "[cut to] 从脚本到配音到画面，全部AI搞定。"
    "[text overlay] 这不是科幻电影。"
    "我用了3个月的AI工具，内容产量翻了10倍。"
    "关注我，每天分享一个AI效率工具。"
    "评论区告诉我你最想学什么！"
)

_D7_MIN_OUTPUT_LENGTH: int = 100
_D7_MAX_OUTPUT_LENGTH: int = 500


class TestD7(DGateTestBase):
    """D7 TikTok gate tests."""

    GATE_CLASS = D7Gate
    GATE_NAME = "D7"
    mock_llm_target = "automedia.gates.distribution.d7_tiktok.llm_complete"
    MIN_OUTPUT_LENGTH = _D7_MIN_OUTPUT_LENGTH

    # ------------------------------------------------------------------
    # Override inherited tests — the default _CANNED_RESPONSE (~570 chars)
    # exceeds D7's 500-char max, so success-path tests must use _D7_CANNED.
    # ------------------------------------------------------------------

    def test_llm_success_returns_passed(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        gate = D7Gate()
        with patch_llm_complete(self.mock_llm_target, _D7_CANNED):
            result = gate.execute(d_gate_context)

        assert result["passed"] is True
        assert result["gate"] == self.GATE_NAME
        assert result["error"] is None

    def test_llm_success_produces_checks(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        gate = D7Gate()
        with patch_llm_complete(self.mock_llm_target, _D7_CANNED):
            result = gate.execute(d_gate_context)

        assert len(result["checks"]) >= self.MIN_OUTPUT_CHECKS
        for check in result["checks"]:
            assert check["passed"] is True, f"Check {check['name']!r} failed"

    def test_llm_success_stores_output_path(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        gate = D7Gate()
        with patch_llm_complete(self.mock_llm_target, _D7_CANNED):
            result = gate.execute(d_gate_context)

        has_path = bool(result.get("output_path"))
        has_modified = bool(result.get("modified_content"))
        assert has_path or has_modified, (
            f"Result has neither 'output_path' nor 'modified_content': "
            f"{result.keys()}"
        )

    # ------------------------------------------------------------------
    # Gate-specific tests
    # ------------------------------------------------------------------

    def test_context_extra_d7_output(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Successful gate sets gate_context.extra['d7_output']. """
        gate = D7Gate()
        with patch_llm_complete(self.mock_llm_target, _D7_CANNED):
            gate.execute(d_gate_context)

        extra = d_gate_context.get("extra", {})
        d7_output = extra.get("d7_output", "")
        assert d7_output, "gate_context.extra['d7_output'] was not set"
        assert _D7_CANNED[:50] in d7_output

    def test_output_file_in_tiktok_dir(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Output file is created under 04_distribution/tiktok/."""
        import os

        gate = D7Gate()
        with patch_llm_complete(self.mock_llm_target, _D7_CANNED):
            result = gate.execute(d_gate_context)

        output_path = result.get("output_path", "")
        assert output_path, "No output_path in result"
        assert "04_distribution" in output_path
        assert "tiktok" in output_path
        assert os.path.isfile(output_path)

    def test_output_too_short_fails(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Response shorter than MIN_OUTPUT_LENGTH fails."""
        too_short = "Too short."
        gate = D7Gate()
        with patch_llm_complete(self.mock_llm_target, too_short):
            result = gate.execute(d_gate_context)

        assert result["passed"] is False
        length_checks = [
            c for c in result["checks"] if "length" in c["name"].lower()
        ]
        assert len(length_checks) >= 1
        assert length_checks[0]["passed"] is False

    def test_output_too_long_fails(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Response longer than MAX_OUTPUT_LENGTH fails."""
        too_long = "A" * (_D7_MAX_OUTPUT_LENGTH + 100)
        gate = D7Gate()
        with patch_llm_complete(self.mock_llm_target, too_long):
            result = gate.execute(d_gate_context)

        assert result["passed"] is False
        length_checks = [
            c for c in result["checks"] if "length" in c["name"].lower()
        ]
        assert len(length_checks) >= 1
        assert length_checks[0]["passed"] is False
