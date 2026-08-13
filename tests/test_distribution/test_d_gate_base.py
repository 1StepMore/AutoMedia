"""Base test patterns for D1-D7 distribution gates.

This file provides reusable test classes and helpers that individual D-gate
test modules (``test_d1_wechat.py``, ``test_d2_twitter.py``, …) can
subclass or compose to avoid duplicating common test patterns.

Usage
-----
Concrete D-gate test files should:

1. Import the gate class and this module.
2. Subclass ``DGateTestBase``, setting ``GATE_CLASS`` and
   ``GATE_NAME`` as class attributes.
3. Override ``mock_llm_target`` with the correct patch target
   (e.g. ``"automedia.gates.distribution.d1_wechat.llm_complete"``).
4. Add gate-specific tests as needed.

Example
-------
.. code-block:: python

    from automedia.gates.distribution.d1_wechat import D1Gate
    from tests.test_distribution.test_d_gate_base import DGateTestBase

    class TestD1(DGateTestBase):
        GATE_CLASS = D1Gate
        GATE_NAME = "D1"
        mock_llm_target = "automedia.gates.distribution.d1_wechat.llm_complete"

        def test_wechat_specific_feature(self, d_gate_context):
            ...
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from automedia.gates.base import BaseGate, _registry
from automedia.gates.distribution.d1_wechat import D1Gate

if TYPE_CHECKING:
    from unittest.mock import MagicMock

# =========================================================================
# Shared mock helpers
# =========================================================================

_CANNED_RESPONSE: str = (
    "## 测试标题：AI技术趋势分析及未来展望\n\n"
    "2025年AI技术持续快速发展，以下是最新趋势分析报告。"
    "随着人工智能技术的不断演进，各行业正在经历前所未有的变革。\n\n"
    "### 趋势一：多模态AI技术的融合应用\n\n"
    "多模态AI能够同时处理文本、图像和音频数据，"
    "为企业提供更丰富的内容生产能力和更智能的交互体验。"
    "这项技术在内容创作、客户服务和教育培训等领域展现出巨大潜力。\n\n"
    "### 趋势二：边缘计算与AI推理的深度融合\n\n"
    "AI推理正在向边缘设备迁移，降低延迟并保护用户隐私。"
    "边缘AI芯片的性能提升使得实时处理成为可能，"
    "尤其是在物联网和智能制造场景中发挥关键作用。\n\n"
    "### 趋势三：生成式AI驱动的内容生产革命\n\n"
    "从文本生成到视频制作，生成式AI正在重新定义内容创作的边界。"
    "自动化生产流程大幅降低了内容制作成本，"
    "同时保持了高质量的输出标准。\n\n"
    "### 趋势四：AI安全与伦理治理框架建立\n\n"
    "随着AI应用的普及，安全性和伦理问题日益受到关注。"
    "各国政府和行业组织正在制定相应的治理框架，"
    "以确保AI技术的负责任发展。\n\n"
    "### 结语：拥抱AI驱动的未来\n\n"
    "AI技术正在深刻改变内容生产方式和企业运营模式。"
    "拥抱变化、持续学习才能在竞争中保持领先地位。"
    "未来已来，让我们共同迎接AI时代的机遇与挑战。"
    "本文由TestBrand提供，欢迎订阅获取更多AI前沿资讯。"
)


@contextmanager
def patch_llm_complete(
    module_path: str,
    response: str = _CANNED_RESPONSE,
) -> Generator[MagicMock, None, None]:
    """Context manager that mocks ``llm_complete`` in a specific D-gate module.

    D-gates import ``llm_complete`` at module level via
    ``from automedia.core.llm_client import llm_complete``, so patching
    must happen at the **importing module** (not the definition site).

    Parameters
    ----------
    module_path:
        Fully-qualified module path, e.g.
        ``"automedia.gates.distribution.d1_wechat.llm_complete"``.
    response:
        The canned string that ``llm_complete`` should return.

    Yields
    ------
    MagicMock
        The patched mock object (for call-count assertions).
    """
    with patch(module_path) as mock:
        mock.return_value = response
        yield mock


@contextmanager
def patch_llm_failure(module_path: str) -> Generator[MagicMock, None, None]:
    """Context manager that makes ``llm_complete`` raise ``LLMError``.

    Parameters
    ----------
    module_path:
        Fully-qualified module path, e.g.
        ``"automedia.gates.distribution.d1_wechat.llm_complete"``.

    Yields
    ------
    MagicMock
        The patched mock object (for call-count assertions).
    """
    from automedia.core.llm_client import LLMError

    with patch(module_path) as mock:
        mock.side_effect = LLMError("LLM API timeout (simulated)")
        yield mock


# =========================================================================
# Context builder helper
# =========================================================================


def make_d_gate_context(
    *,
    project_dir: str = "/tmp/test_project",
    content: str | None = None,
    brand: str = "TestBrand",
    title: str = "Test Title",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a minimal gate_context dict suitable for any D-gate.

    Tests may override individual keys via ``update()`` after creation.
    """
    return {
        "content": content or (
            "AI technology continues to evolve rapidly in 2025. "
            "Multimodal AI models can now process text, images, and audio "
            "simultaneously, enabling richer content experiences."
        ),
        "project_dir": project_dir,
        "brand": brand,
        "title": title,
        "config": config or {},
    }


# =========================================================================
# Abstract test base
# =========================================================================


class DGateTestBase:
    """Reusable test methods for every D1-D7 gate.

    Concrete subclasses **must** set:

    - ``GATE_CLASS`` — the gate class under test
    - ``GATE_NAME`` — the expected gate name string (e.g. ``"D1"``)
    - ``mock_llm_target`` — the fully-qualified patch target for
      ``llm_complete`` in the gate's module

    Optionally set:

    - ``EXPECTED_FAILURE_MODE`` — (default ``"retry"``)
    - ``MIN_OUTPUT_LENGTH`` — (default ``500``) for length checks
    - ``MIN_OUTPUT_CHECKS`` — (default ``2``) minimum number of checks
      in a successful result
    """

    GATE_CLASS: type[BaseGate] = D1Gate  # overridden by subclasses
    GATE_NAME: str = "D1"  # overridden by subclasses
    EXPECTED_FAILURE_MODE: str = "retry"
    MIN_OUTPUT_LENGTH: int = 500
    MIN_OUTPUT_CHECKS: int = 2

    # Must be overridden by concrete subclasses
    mock_llm_target: str = "automedia.gates.distribution.d1_wechat.llm_complete"

    # ------------------------------------------------------------------
    # Gate metadata & registration
    # ------------------------------------------------------------------

    def test_gate_name(self) -> None:
        gate = self.GATE_CLASS()
        assert gate.gate_name == self.GATE_NAME

    def test_failure_mode(self) -> None:
        gate = self.GATE_CLASS()
        assert gate.failure_mode == self.EXPECTED_FAILURE_MODE

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(self.GATE_CLASS, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert self.GATE_NAME in _registry
        registered_cls = _registry.get(self.GATE_NAME)
        assert registered_cls is self.GATE_CLASS

    # ------------------------------------------------------------------
    # Success path (LLM returns valid content)
    # ------------------------------------------------------------------

    def test_llm_success_returns_passed(self, d_gate_context: dict[str, Any]) -> None:
        """LLM returns valid content → gate passes."""
        gate = self.GATE_CLASS()
        with patch_llm_complete(self.mock_llm_target):
            result = gate.execute(d_gate_context)

        assert result["passed"] is True
        assert result["gate"] == self.GATE_NAME
        assert result["error"] is None

    def test_llm_success_produces_checks(self, d_gate_context: dict[str, Any]) -> None:
        """Successful gate returns at least MIN_OUTPUT_CHECKS checks."""
        gate = self.GATE_CLASS()
        with patch_llm_complete(self.mock_llm_target):
            result = gate.execute(d_gate_context)

        assert len(result["checks"]) >= self.MIN_OUTPUT_CHECKS
        # All checks should pass
        for check in result["checks"]:
            assert check["passed"] is True, f"Check {check['name']!r} failed"

    def test_llm_success_stores_output_path(self, d_gate_context: dict[str, Any]) -> None:
        """Successful gate includes an ``output_path`` or ``modified_content``."""
        gate = self.GATE_CLASS()
        with patch_llm_complete(self.mock_llm_target):
            result = gate.execute(d_gate_context)

        # At least one of these should be present
        has_path = bool(result.get("output_path"))
        has_modified = bool(result.get("modified_content"))
        assert has_path or has_modified, (
            f"Result has neither 'output_path' nor 'modified_content': {result.keys()}"
        )

    # ------------------------------------------------------------------
    # LLM failure path
    # ------------------------------------------------------------------

    def test_llm_failure_returns_failed(self, d_gate_context: dict[str, Any]) -> None:
        """LLM raises exception → gate fails with error message."""
        gate = self.GATE_CLASS()
        with patch_llm_failure(self.mock_llm_target):
            result = gate.execute(d_gate_context)

        assert result["passed"] is False
        assert result["gate"] == self.GATE_NAME
        assert result["error"] is not None

    def test_llm_failure_sets_llm_check_false(self, d_gate_context: dict[str, Any]) -> None:
        """LLM failure → the llm_success check is present and failed."""
        gate = self.GATE_CLASS()
        with patch_llm_failure(self.mock_llm_target):
            result = gate.execute(d_gate_context)

        llm_checks = [c for c in result["checks"] if "llm" in c["name"].lower()]
        assert len(llm_checks) >= 1, "No LLM-related check found in failure result"
        for c in llm_checks:
            assert c["passed"] is False

    # ------------------------------------------------------------------
    # Empty / missing content
    # ------------------------------------------------------------------

    def test_empty_content_returns_failed(self, d_gate_context: dict[str, Any]) -> None:
        """Empty content → gate fails with content_present check = False."""
        ctx = {**d_gate_context, "content": ""}
        gate = self.GATE_CLASS()
        result = gate.execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == self.GATE_NAME
        # Should fail before calling LLM
        content_checks = [c for c in result["checks"] if c["name"] == "content_present"]
        if content_checks:
            assert content_checks[0]["passed"] is False

    def test_missing_content_key_returns_failed(self, d_gate_context: dict[str, Any]) -> None:
        """Missing ``content`` key → gate fails gracefully."""
        ctx = {k: v for k, v in d_gate_context.items() if k != "content"}
        gate = self.GATE_CLASS()
        result = gate.execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == self.GATE_NAME

    # ------------------------------------------------------------------
    # Result structure
    # ------------------------------------------------------------------

    def test_result_has_required_keys(self, d_gate_context: dict[str, Any]) -> None:
        """Result dict always contains ``passed``, ``gate``, ``checks``, ``error``."""
        gate = self.GATE_CLASS()
        with patch_llm_complete(self.mock_llm_target):
            result = gate.execute(d_gate_context)

        assert "passed" in result
        assert "gate" in result
        assert "checks" in result
        assert "error" in result

    def test_checks_have_correct_structure(self, d_gate_context: dict[str, Any]) -> None:
        """Each check dict has ``name``, ``passed`` (bool), ``detail`` (str)."""
        gate = self.GATE_CLASS()
        with patch_llm_complete(self.mock_llm_target):
            result = gate.execute(d_gate_context)

        for check in result["checks"]:
            assert "name" in check
            assert "passed" in check
            assert "detail" in check
            assert isinstance(check["passed"], bool)
            assert isinstance(check["detail"], str)

    # ------------------------------------------------------------------
    # Output file writing
    # ------------------------------------------------------------------

    def test_writes_output_file(self, d_gate_context: dict[str, Any]) -> None:
        """Gate writes an output file to ``04_distribution/<platform>/``."""
        gate = self.GATE_CLASS()
        with patch_llm_complete(self.mock_llm_target):
            result = gate.execute(d_gate_context)

        output_path = result.get("output_path", "")
        if output_path:
            import os

            assert os.path.isfile(output_path), f"Output file not found: {output_path}"
            content = open(output_path, encoding="utf-8").read()
            assert len(content) > 0, "Output file is empty"

    def test_output_file_contains_canned_response(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Output file content matches the canned LLM response."""
        gate = self.GATE_CLASS()
        with patch_llm_complete(self.mock_llm_target):
            result = gate.execute(d_gate_context)

        output_path = result.get("output_path", "")
        if output_path:
            import os

            assert os.path.isfile(output_path)
            content = open(output_path, encoding="utf-8").read()
            assert _CANNED_RESPONSE in content or content.startswith(
                _CANNED_RESPONSE[:50]
            ), "Output file content does not match the canned response"


# =========================================================================
# Concrete tests for D1 (canonical example)
# =========================================================================


class TestD1Canonical(DGateTestBase):
    """Canonical D1 gate tests using the base test patterns.

    Concrete D-gate test modules should follow this exact pattern.
    """

    GATE_CLASS = D1Gate
    GATE_NAME = "D1"
    mock_llm_target = "automedia.gates.distribution.d1_wechat.llm_complete"
