"""Shared pytest fixtures for D-gate (distribution gate) tests.

All fixtures produce synthetic data — zero production data.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock LLM client
# ---------------------------------------------------------------------------

_DEFAULT_CANNED_RESPONSE: str = (
    "## 测试标题：AI技术趋势分析\n\n"
    "2025年AI技术持续快速发展，以下是最新趋势分析。\n\n"
    "### 趋势一：多模态AI\n\n"
    "多模态AI能够同时处理文本、图像和音频数据。\n\n"
    "### 趋势二：边缘计算\n\n"
    "AI推理正在向边缘设备迁移，降低延迟并保护隐私。\n\n"
    "### 结语\n\n"
    "AI技术正在深刻改变内容生产方式，拥抱变化才能保持竞争力。"
)


@contextmanager
def _mock_llm_response(response: str = _DEFAULT_CANNED_RESPONSE) -> Generator[MagicMock, None, None]:
    """Mock ``llm_complete`` in ``automedia.core.llm_client``.

    D-gates call ``llm_complete(prompt, config=config)`` directly (not the
    structured variant), so we patch at the call site in the LLM client
    module.
    """
    with patch("automedia.core.llm_client.llm_complete") as mock:
        mock.return_value = response
        yield mock


@contextmanager
def _mock_llm_failure() -> Generator[MagicMock, None, None]:
    """Simulate an LLM API failure for D-gates.

    The patched ``llm_complete`` raises ``LLMError``, which D-gates catch
    and convert into a failing check.
    """
    from automedia.core.llm_client import LLMError

    with patch("automedia.core.llm_client.llm_complete") as mock:
        mock.side_effect = LLMError("LLM API timeout (simulated)")
        yield mock


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_llm_client() -> dict[str, Any]:
    """Fixture providing LLM mock helpers for D-gate tests.

    Returns a dict with two keys:

    ``response``
        Context manager that patches ``llm_complete`` to return a
        canned response string.
    ``failure``
        Context manager that patches ``llm_complete`` to raise
        ``LLMError``.

    Example
    -------
    >>> def test_gate_success(mock_llm_client):
    ...     gate = MyGate()
    ...     with mock_llm_client["response"]("custom text"):
    ...         result = gate.execute(context)
    ...         assert result["passed"]
    """
    return {
        "response": _mock_llm_response,
        "failure": _mock_llm_failure,
    }


@pytest.fixture()
def d_gate_context(temp_project_dir: str) -> dict[str, Any]:
    """Synthetic gate context suitable for all D1-D7 distribution gates.

    Provides all keys that D-gates commonly expect:
    ``content``, ``project_dir``, ``brand``, ``title``, ``config``.

    Tests may override individual keys using ``context.update(...)``.
    """
    return {
        "content": (
            "AI technology continues to evolve rapidly in 2025. "
            "Multimodal AI models can now process text, images, and audio "
            "simultaneously, enabling richer content experiences. "
            "Edge computing brings AI inference closer to users, "
            "reducing latency and improving privacy. "
            "This article explores the key trends shaping the future "
            "of AI-powered content production."
        ),
        "project_dir": temp_project_dir,
        "brand": "TestBrand",
        "title": "AI Technology Trends 2025",
        "config": {},
    }


@pytest.fixture()
def temp_project_dir(tmp_path: Any) -> str:
    """Create a temporary project directory with ``04_distribution/`` subdirectory.

    D-gates write output files under ``04_distribution/<platform>/``,
    so this fixture pre-creates the distribution directory structure.
    """
    dist_dir = tmp_path / "04_distribution"
    dist_dir.mkdir(parents=True, exist_ok=True)
    return str(tmp_path)
