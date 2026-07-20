"""Tests for D5 Bilibili Rewrite Gate (D5BilibiliRewrite).

D5 has a different pattern from D1/D2/D4/D6/D7:
- Requires ``topic`` key in gate_context
- Uses ``load_prompt()`` and ``llm_complete()`` with ``system_prompt``
- Quality checks: min_length (>500 chars) + scene_markers ([SCENE])
- Returns ``expected_vs_actual`` on some failures
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator
from unittest.mock import patch

import pytest

from automedia.gates.distribution.d5_bilibili import D5BilibiliRewrite

if TYPE_CHECKING:
    from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Canned response: >500 chars with [SCENE] markers
# ---------------------------------------------------------------------------

_D5_CANNED: str = (
    "[SCENE] 开场\n\n"
    "大家好，欢迎来到我的频道！今天我们来聊聊2025年AI技术的最新发展。"
    "这期视频干货满满，一定要看到最后。\n\n"
    "[SCENE] 多模态AI技术解析\n\n"
    "首先我们来看多模态AI。简单来说，"
    "就是让AI同时理解文字、图像、声音和视频。"
    "比如现在的AI可以根据文字描述直接生成视频，"
    "这在两年前还是科幻电影里的场景。\n\n"
    "这项技术的核心突破在于transformer架构的扩展。"
    "通过将不同模态的数据映射到同一个语义空间，"
    "AI能够实现跨模态的理解和生成。"
    "实际应用中，医疗领域的AI已经能同时分析"
    "病历文本和医学影像，大幅提升诊断准确率。\n\n"
    "[SCENE] 边缘AI的崛起\n\n"
    "第二个重要趋势是边缘AI。"
    "过去AI计算主要依赖云端，延迟高且依赖网络。"
    "现在最新的手机芯片已经能本地运行大模型，"
    "实时处理语音、图像等数据。\n\n"
    "这对隐私保护来说是个大利好。"
    "你的数据不需要上传到云端，在本地就完成了处理。"
    "苹果、高通和联发科都在大力推动这个方向。\n\n"
    "[SCENE] 总结与展望\n\n"
    "2025年AI技术的发展速度超出所有人的预期。"
    "多模态AI让机器更懂人类，边缘AI让智能无处不在。"
    "如果你觉得这期视频有帮助，记得一键三连！"
    "我们下期再见。"
)


# ---------------------------------------------------------------------------
# Helper to patch llm_complete in D5's module
# ---------------------------------------------------------------------------


@contextmanager
def _patch_d5_llm(
    response: str = _D5_CANNED,
) -> Generator[MagicMock, None, None]:
    """Mock ``llm_complete`` and ``load_prompt`` in D5's importing module.

    D5's ``execute`` calls ``load_prompt("bilibili_rewrite")`` before
    ``llm_complete()``, and the prompt template file does not exist on
    disk. We patch both at the importing module.
    """
    prompt_target = "automedia.gates.distribution.d5_bilibili.load_prompt"
    llm_target = "automedia.gates.distribution.d5_bilibili.llm_complete"
    with patch(prompt_target) as mock_prompt, patch(llm_target) as mock_llm:
        mock_prompt.return_value = "You are a Bilibili video script writer."
        mock_llm.return_value = response
        yield mock_llm


# ---------------------------------------------------------------------------
# Fixture: D5 gate context (adds ``topic`` to base context)
# ---------------------------------------------------------------------------


@pytest.fixture()
def d5_gate_context(d_gate_context: dict[str, Any]) -> dict[str, Any]:
    """D5 gate context with ``topic`` key added."""
    d_gate_context["topic"] = "AI Technology Trends 2025"
    return d_gate_context


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestD5Bilibili:
    """D5 Bilibili Rewrite gate tests."""

    GATE_CLASS = D5BilibiliRewrite
    GATE_NAME = "D5"

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def test_gate_name(self) -> None:
        """Gate name is 'D5'."""
        gate = D5BilibiliRewrite()
        assert gate.gate_name == "D5"

    def test_failure_mode(self) -> None:
        """Failure mode is 'retry'."""
        gate = D5BilibiliRewrite()
        assert gate.failure_mode == "retry"

    # ------------------------------------------------------------------
    # Success path
    # ------------------------------------------------------------------

    def test_success_with_topic(
        self, d5_gate_context: dict[str, Any]
    ) -> None:
        """Valid context + LLM success → gate passes."""
        gate = D5BilibiliRewrite()
        with _patch_d5_llm(_D5_CANNED):
            result = gate.execute(d5_gate_context)

        assert result["passed"] is True
        assert result["gate"] == "D5"
        assert result["error"] is None

    def test_success_produces_checks(
        self, d5_gate_context: dict[str, Any]
    ) -> None:
        """Successful gate returns quality checks."""
        gate = D5BilibiliRewrite()
        with _patch_d5_llm(_D5_CANNED):
            result = gate.execute(d5_gate_context)

        check_names = {c["name"] for c in result["checks"]}
        assert "bilibili_content_generated" in check_names
        assert "min_length" in check_names
        assert "scene_markers" in check_names
        for check in result["checks"]:
            assert check["passed"] is True

    # ------------------------------------------------------------------
    # Empty / missing content
    # ------------------------------------------------------------------

    def test_empty_content_fails(
        self, d5_gate_context: dict[str, Any]
    ) -> None:
        """Empty content → gate fails with passed=False."""
        ctx = {**d5_gate_context, "content": ""}
        gate = D5BilibiliRewrite()
        result = gate.execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == "D5"

    def test_missing_topic_fails(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Missing 'topic' → gate fails before LLM call."""
        gate = D5BilibiliRewrite()
        result = gate.execute(d_gate_context)

        assert result["passed"] is False
        assert result["gate"] == "D5"
        assert "topic" in result.get("error", "").lower()

    def test_missing_project_dir_fails(
        self, d5_gate_context: dict[str, Any]
    ) -> None:
        """Missing 'project_dir' → gate fails."""
        ctx = {k: v for k, v in d5_gate_context.items() if k != "project_dir"}
        gate = D5BilibiliRewrite()
        result = gate.execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == "D5"

    # ------------------------------------------------------------------
    # LLM failure
    # ------------------------------------------------------------------

    def test_llm_failure_fails(
        self, d5_gate_context: dict[str, Any]
    ) -> None:
        """LLM exception → gate fails with error."""
        from automedia.core.llm_client import LLMError

        prompt_target = "automedia.gates.distribution.d5_bilibili.load_prompt"
        llm_target = "automedia.gates.distribution.d5_bilibili.llm_complete"
        with patch(prompt_target) as mock_prompt, patch(llm_target) as mock_llm:
            mock_prompt.return_value = "System prompt."
            mock_llm.side_effect = LLMError("API timeout")
            result = D5BilibiliRewrite().execute(d5_gate_context)

        assert result["passed"] is False
        assert result["gate"] == "D5"
        assert "llm" in result.get("error", "").lower()

    # ------------------------------------------------------------------
    # Output file creation
    # ------------------------------------------------------------------

    def test_output_file_in_bilibili_dir(
        self, d5_gate_context: dict[str, Any]
    ) -> None:
        """Output file is created under 04_distribution/bilibili/."""
        import os

        gate = D5BilibiliRewrite()
        with _patch_d5_llm(_D5_CANNED):
            result = gate.execute(d5_gate_context)

        output_path = result.get("output_path", "")
        assert output_path, "No output_path in result"
        assert "04_distribution" in output_path
        assert "bilibili" in output_path
        assert os.path.isfile(output_path)

    def test_output_file_has_content(
        self, d5_gate_context: dict[str, Any]
    ) -> None:
        """Output file is non-empty."""
        import os

        gate = D5BilibiliRewrite()
        with _patch_d5_llm(_D5_CANNED):
            result = gate.execute(d5_gate_context)

        output_path = result.get("output_path", "")
        if output_path:
            assert os.path.isfile(output_path)
            assert os.path.getsize(output_path) > 0
