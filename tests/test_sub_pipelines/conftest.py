"""Shared pytest fixtures for P-gate (sub-pipeline repurpose) integration tests.

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
# Canned LLM responses for P-gate steps
# ---------------------------------------------------------------------------

P1_CANNED_REWRITE: str = (
    "## AI技术趋势分析：2025年展望\n\n"
    "2025年AI技术持续快速发展，多模态AI和边缘计算正在深刻改变内容生产行业。"
    "人工智能的进步正在重新定义内容创作的方式。"
    "从自然语言处理到计算机视觉，AI正在各个领域展现强大的能力。\n\n"
    "### 多模态AI的融合应用\n\n"
    "多模态AI能够同时处理文本、图像和音频数据。"
    "这项技术正在重新定义内容创作的可能性。"
    "企业可以利用多模态AI创建更丰富、更吸引人的内容体验。"
    "从智能客服到智能营销，多模态AI的应用场景非常广泛。"
    "随着技术的不断进步，多模态AI的性能还将持续提升。"
    "未来几年，我们将看到更多创新性的多模态AI应用。\n\n"
    "### 边缘计算与AI推理\n\n"
    "AI推理正在向边缘设备迁移，降低延迟并保护用户隐私。"
    "边缘AI芯片的性能提升使得实时处理成为可能。"
    "在物联网和智能制造场景中，边缘AI发挥关键作用。"
    "边缘计算与AI的结合正在改变数据处理的方式。"
    "企业可以更快地做出数据驱动的决策。"
    "同时，用户数据的安全性也得到了更好的保障。\n\n"
    "### 结语\n\n"
    "AI技术正在深刻改变内容生产方式。"
    "未来已来，让我们共同迎接AI时代的机遇与挑战。"
    "本文由TestBrand提供。欢迎订阅获取更多AI前沿资讯。"
)

P1_CANNED_FACT_CHECK: str = '{"passed": true, "issues": [], "summary": "All claims verified."}'

P1_CANNED_HUMANIZE: str = (
    "## AI技术趋势分析：2025年展望\n\n"
    "2025年AI技术还在快速迭代，多模态AI和边缘计算已经在改变内容生产行业了。"
    "人工智能的进步正在重新定义内容创作的方式。"
    "从自然语言处理到计算机视觉，AI正在各个领域展现强大的能力。\n\n"
    "### 多模态AI的融合应用\n\n"
    "多模态AI能同时搞定文本、图像和音频数据。"
    "这技术正在重新定义内容创作的可能性。"
    "企业可以用多模态AI创建更丰富、更吸引人的内容体验。"
    "从智能客服到智能营销，多模态AI的应用场景非常广泛。"
    "随着技术的不断进步，多模态AI的性能还在持续提升。"
    "未来几年，我们会看到更多创新性的多模态AI应用。\n\n"
    "### 边缘计算与AI推理\n\n"
    "AI推理搬到边缘设备上，延迟低了，隐私也更安全。"
    "边缘AI芯片的性能提升让实时处理成为可能。"
    "在物联网和智能制造场景中，边缘AI发挥关键作用。"
    "边缘计算和AI的结合正在改变数据处理的方式。"
    "企业可以更快地做出数据驱动的决策。"
    "同时，用户数据的安全性也得到了更好的保障。\n\n"
    "### 结语\n\n"
    "AI技术正在深刻改变内容生产方式。"
    "未来已来，一起拥抱AI时代的机遇与挑战。"
    "本文由TestBrand提供。欢迎订阅获取更多AI前沿资讯。"
)

P3_CANNED_REWRITE: str = (
    "## AI技术趋势分析：2025年展望\n\n"
    "亲爱的读者朋友们，2025年AI技术还在快速迭代，"
    "多模态AI和边缘计算正在改变内容生产行业。"
    "人工智能的进步正在重新定义内容创作的方式。"
    "从自然语言处理到计算机视觉，AI正在各个领域展现强大的能力。\n\n"
    "### 多模态AI的融合应用\n\n"
    "多模态AI能同时搞定文本、图像和音频数据。"
    "这技术正在重新定义内容创作的可能性。"
    "企业可以用多模态AI创建更丰富、更吸引人的内容体验。"
    "从智能客服到智能营销，多模态AI的应用场景非常广泛。"
    "随着技术的不断进步，多模态AI的性能还在持续提升。"
    "未来几年，我们会看到更多创新性的多模态AI应用。\n\n"
    "### 边缘计算与AI推理\n\n"
    "AI推理搬到边缘设备上，延迟低了，隐私也更安全。"
    "边缘AI芯片的性能提升让实时处理成为可能。"
    "在物联网和智能制造场景中，边缘AI发挥关键作用。"
    "边缘计算和AI的结合正在改变数据处理的方式。"
    "企业可以更快地做出数据驱动的决策。"
    "同时，用户数据的安全性也得到了更好的保障。\n\n"
    "### 结语\n\n"
    "AI技术正在深刻改变内容生产方式。"
    "未来已来，一起拥抱AI时代的机遇与挑战。"
    "本文由TestBrand提供。欢迎订阅获取更多AI前沿资讯。"
)

P4_CANNED_REWRITE: str = (
    "[TIMESTAMP] 00:00\n"
    "大家好啊！今天我们来聊聊2025年的AI技术趋势。"
    "人工智能的进步正在重新定义内容创作的方式。"
    "从自然语言处理到计算机视觉，AI正在各个领域展现强大的能力。"
    "这项技术的进步速度之快令人惊叹。\n\n"
    "[VISUAL] 展示AI多模态处理示意图\n"
    "[TIMESTAMP] 00:15\n"
    "多模态AI能同时处理文本、图像和音频数据，内容创作的门槛大幅降低了。"
    "企业可以用多模态AI创建更丰富、更吸引人的内容体验。"
    "从智能客服到智能营销，多模态AI的应用场景非常广泛。\n\n"
    "[VISUAL] 边缘设备示意图\n"
    "[TIMESTAMP] 00:30\n"
    "AI推理正在向边缘设备迁移，延迟更低，隐私也更安全。"
    "边缘AI芯片的性能提升让实时处理成为可能。"
    "在物联网和智能制造场景中，边缘AI发挥着关键作用。\n\n"
    "[弹幕互动] 你们觉得AI会取代人类创作者吗？\n\n"
    "[VISUAL] 展示AI和人类协作场景\n"
    "[TIMESTAMP] 01:00\n"
    "AI不是要取代人类创作者，而是成为强大的辅助工具。"
    "未来的内容创作是人机协作的时代。"
    "掌握AI工具的创作者将拥有更大的竞争优势。\n\n"
    "[VISUAL] 结束画面\n"
    "[TIMESTAMP] 01:30\n"
    "感谢观看！记得一键三连哦！"
    "#AI技术 #内容创作 #科技趋势"
)

_LONG_CONTENT: str = (
    "AI technology continues to evolve rapidly in 2025. "
    "Multimodal AI models can now process text, images, and audio "
    "simultaneously, enabling richer content experiences. "
    "Edge computing brings AI inference closer to users, "
    "reducing latency and improving privacy. "
    "This article explores the key trends shaping the future "
    "of AI-powered content production. "
    "From natural language processing to computer vision, "
    "the advances in AI are transforming how we create and consume media. "
    "Companies across industries are adopting AI tools to streamline "
    "their workflows and deliver more personalized experiences. "
    "The pace of innovation shows no signs of slowing down, "
    "and the next few years promise even more exciting developments."
)


# ---------------------------------------------------------------------------
# Mock helpers for P-gate tests
# ---------------------------------------------------------------------------


@contextmanager
def mock_p1_llm_calls(
    rewrite: str = P1_CANNED_REWRITE,
    fact_check: str = P1_CANNED_FACT_CHECK,
    humanize: str = P1_CANNED_HUMANIZE,
) -> Generator[MagicMock, None, None]:
    """Mock all three LLM calls in P1 (rewrite → fact_check → humanize).

    P1 calls ``llm_complete`` three times sequentially. This mock returns
    different canned responses on each call via ``side_effect``.
    """
    with patch("automedia.gates.sub_pipelines.p1_wechat.llm_complete") as mock:
        mock.side_effect = [rewrite, fact_check, humanize]
        yield mock


@contextmanager
def mock_p1_llm_failure() -> Generator[MagicMock, None, None]:
    """Mock P1's first LLM call (rewrite) to raise LLMError."""
    from automedia.core.llm_client import LLMError

    with patch("automedia.gates.sub_pipelines.p1_wechat.llm_complete") as mock:
        mock.side_effect = LLMError("LLM API timeout (simulated)")
        yield mock


P2_LONG_THREAD: str = (
    "Tweet 1: AI in 2025 is transforming content creation at an unprecedented pace. "
    "Multimodal models now handle text, images, and audio seamlessly. "
    "This changes everything for content creators and marketers everywhere.\n"
    "Tweet 2: Edge computing brings AI inference closer to users - lower latency, "
    "better privacy. Real-time processing on edge devices is now possible thanks "
    "to specialized AI chips that keep getting more powerful.\n"
    "Tweet 3: The future of content is human-AI collaboration. Tools that enhance "
    "creativity rather than replace it will win. Learn to work with AI, not against it. "
    "The next wave of innovation is already here.\n"
    "Tweet 4: Key takeaway: embrace AI tools to stay competitive in 2025. "
    "Content that combines human insight with AI efficiency will stand out. "
    "Start experimenting with multimodal AI today.\n"
)


@contextmanager
def mock_p2_llm_calls() -> Generator[MagicMock, None, None]:
    """Mock all three LLM calls in P2 Twitter thread gate.

    P2 calls: rewrite → fact_check → humanize.
    """
    with patch("automedia.gates.sub_pipelines.p2_twitter.llm_complete") as mock:
        mock.side_effect = [
            P2_LONG_THREAD,
            '{"passed": true, "issues": []}',
            P2_LONG_THREAD,
        ]
        yield mock


@contextmanager
def mock_p2_llm_failure() -> Generator[MagicMock, None, None]:
    """Mock P2's first LLM call to raise LLMError."""
    from automedia.core.llm_client import LLMError

    with patch("automedia.gates.sub_pipelines.p2_twitter.llm_complete") as mock:
        mock.side_effect = LLMError("LLM API timeout (simulated)")
        yield mock


@contextmanager
def mock_p3_llm_calls() -> Generator[MagicMock, None, None]:
    """Mock P3 newsletter gate: patches both ``load_prompt`` and ``llm_complete``.

    P3 uses ``load_prompt("content_writer", platform="newsletter")`` to get
    the prompt, then calls ``llm_complete`` three times (rewrite → review → humanize).
    """
    with (
        patch("automedia.gates.sub_pipelines.p3_newsletter.load_prompt") as mock_prompt,
        patch("automedia.gates.sub_pipelines.p3_newsletter.llm_complete") as mock_llm,
    ):
        mock_prompt.return_value = "Newsletter content writer prompt template."
        mock_llm.side_effect = [
            P3_CANNED_REWRITE,
            '{"passed": true, "issues": [], "summary": "OK"}',
            P3_CANNED_REWRITE,
        ]
        yield mock_llm


@contextmanager
def mock_p3_llm_failure() -> Generator[MagicMock, None, None]:
    """Mock P3's rewrite step to fail."""
    from automedia.core.llm_client import LLMError

    with patch("automedia.gates.sub_pipelines.p3_newsletter.load_prompt") as mock_prompt:
        mock_prompt.return_value = "prompt"
        with patch("automedia.gates.sub_pipelines.p3_newsletter.llm_complete") as mock_llm:
            mock_llm.side_effect = LLMError("LLM API timeout (simulated)")
            yield mock_llm


@contextmanager
def mock_p4_llm_calls() -> Generator[MagicMock, None, None]:
    """Mock P4 Bilibili repurpose gate: patches both ``load_prompt`` and ``llm_complete``.

    P4 calls: rewrite → fact_check → humanize.
    Requires content with [TIMESTAMP] or [SCENE] markers in the final output.
    """
    with (
        patch("automedia.gates.sub_pipelines.p4_bilibili.load_prompt") as mock_prompt,
        patch("automedia.gates.sub_pipelines.p4_bilibili.llm_complete") as mock_llm,
    ):
        mock_prompt.return_value = "Bilibili script prompt."
        mock_llm.side_effect = [
            P4_CANNED_REWRITE,
            '{"passed": true, "issues": [], "summary": "OK"}',
            P4_CANNED_REWRITE,
        ]
        yield mock_llm


@contextmanager
def mock_p4_llm_failure() -> Generator[MagicMock, None, None]:
    """Mock P4's first LLM call to raise LLMError."""
    from automedia.core.llm_client import LLMError

    with patch("automedia.gates.sub_pipelines.p4_bilibili.load_prompt") as mock_prompt:
        mock_prompt.return_value = "prompt"
        with patch("automedia.gates.sub_pipelines.p4_bilibili.llm_complete") as mock_llm:
            mock_llm.side_effect = LLMError("LLM API timeout (simulated)")
            yield mock_llm


@contextmanager
def mock_p1_fact_check_fails() -> Generator[MagicMock, None, None]:
    """Mock P1 with rewrite OK, fact_check raises LLMError, humanize OK."""
    from automedia.core.llm_client import LLMError

    with patch("automedia.gates.sub_pipelines.p1_wechat.llm_complete") as mock:
        mock.side_effect = [
            P1_CANNED_REWRITE,
            LLMError("Fact check API error (simulated)"),
            P1_CANNED_HUMANIZE,
        ]
        yield mock


@contextmanager
def mock_p2_humanize_fails() -> Generator[MagicMock, None, None]:
    """Mock P2 with rewrite OK, fact_check OK, humanize raises LLMError."""
    from automedia.core.llm_client import LLMError

    with patch("automedia.gates.sub_pipelines.p2_twitter.llm_complete") as mock:
        mock.side_effect = [
            P2_LONG_THREAD,
            '{"passed": true, "issues": []}',
            LLMError("Humanize API error (simulated)"),
        ]
        yield mock


@contextmanager
def mock_p3_review_fails() -> Generator[MagicMock, None, None]:
    """Mock P3 with rewrite OK, review raises LLMError, humanize OK."""
    from automedia.core.llm_client import LLMError

    with (
        patch("automedia.gates.sub_pipelines.p3_newsletter.load_prompt") as mock_prompt,
        patch("automedia.gates.sub_pipelines.p3_newsletter.llm_complete") as mock_llm,
    ):
        mock_prompt.return_value = "Newsletter prompt."
        mock_llm.side_effect = [
            P3_CANNED_REWRITE,
            LLMError("Review API error (simulated)"),
            P3_CANNED_REWRITE,
        ]
        yield mock_llm


@contextmanager
def mock_p4_humanize_fails() -> Generator[MagicMock, None, None]:
    """Mock P4 with rewrite OK, fact_check OK, humanize raises LLMError."""
    from automedia.core.llm_client import LLMError

    with (
        patch("automedia.gates.sub_pipelines.p4_bilibili.load_prompt") as mock_prompt,
        patch("automedia.gates.sub_pipelines.p4_bilibili.llm_complete") as mock_llm,
    ):
        mock_prompt.return_value = "prompt"
        mock_llm.side_effect = [
            P4_CANNED_REWRITE,
            '{"passed": true, "issues": []}',
            LLMError("Humanize API error (simulated)"),
        ]
        yield mock_llm


# ---------------------------------------------------------------------------
# Shared fixture: P-gate context
# ---------------------------------------------------------------------------


@pytest.fixture()
def p_gate_context(tmp_path: Any) -> dict[str, Any]:
    """Synthetic gate context suitable for all P1-P4 repurpose gates.

    Provides keys: ``content``, ``project_dir``, ``brand``, ``title``,
    ``config``, ``topic``.
    """
    return {
        "content": _LONG_CONTENT,
        "project_dir": str(tmp_path),
        "brand": "TestBrand",
        "title": "AI Technology Trends 2025",
        "config": {},
        "topic": "AI technology trends in 2025",
    }


@pytest.fixture()
def p_gate_context_empty() -> dict[str, Any]:
    """Gate context with empty content (for failure testing)."""
    return {
        "content": "",
        "project_dir": "/tmp/test",
        "brand": "TestBrand",
        "title": "Test",
        "config": {},
        "topic": "Test topic",
    }
