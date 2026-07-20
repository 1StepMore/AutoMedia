"""Tests for D6 YouTube Standalone Rewrite Gate (D6YouTubeGate).

Covers output format verification (intro/body/outro/CTA), empty content
handling, file output creation, and YouTube script quality check validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from automedia.gates.distribution.d6_youtube import D6YouTubeGate
from tests.test_distribution.test_d_gate_base import (
    DGateTestBase,
    patch_llm_complete,
    patch_llm_failure,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock


# Canned response: >500 chars with ## Intro, ## Section, ## Outro, and CTA
_D6_CANNED: str = (
    "## Intro\n\n"
    "Hey everyone, welcome back to the channel! "
    "Today we're diving into the biggest AI trends of 2025 "
    "that are reshaping how we create, work, and live. "
    "By the end of this video, you'll know exactly which "
    "trends to watch and how to prepare for them. "
    "Let's get started!\n\n"
    "## Section 1: Multimodal AI\n\n"
    "First up is multimodal AI. This is a game-changer. "
    "Instead of separate models for text, images, and audio, "
    "we now have unified models that handle all of them at once. "
    "Think about what that means for content creators — "
    "you can generate a full video from a single text prompt. "
    "Companies like OpenAI, Google, and Meta are all racing "
    "in this space, and the results are stunning.\n\n"
    "## Section 2: Edge AI Revolution\n\n"
    "Next, let's talk about edge AI. "
    "For years, AI processing happened in the cloud. "
    "But 2025 is the year AI moves to your devices. "
    "New smartphone chips can run large language models locally, "
    "which means faster response times and better privacy. "
    "Apple's Neural Engine, Qualcomm's AI Engine, and "
    "MediaTek's APU are all pushing this boundary.\n\n"
    "## Section 3: Generative AI for Everyone\n\n"
    "Generative AI tools are becoming more accessible than ever. "
    "You don't need a PhD in machine learning to use them. "
    "From video creation to copywriting, AI handles the heavy lifting. "
    "The key is learning how to prompt effectively and "
    "integrating these tools into your workflow.\n\n"
    "## Outro\n\n"
    "Thanks for watching! If you found this helpful, "
    "please hit that like button and subscribe for more "
    "AI content every week. Drop a comment below telling me "
    "which AI trend excites you the most. See you in the next video!"
)


class TestD6(DGateTestBase):
    """D6 YouTube gate tests."""

    GATE_CLASS = D6YouTubeGate
    GATE_NAME = "D6"
    mock_llm_target = "automedia.gates.distribution.d6_youtube.llm_complete"
    MIN_OUTPUT_LENGTH = 500

    # ------------------------------------------------------------------
    # Override inherited tests — the default _CANNED_RESPONSE does NOT
    # have YouTube section headings (Intro/Body/Outro/CTA), so success-
    # path tests must use _D6_CANNED instead.
    # ------------------------------------------------------------------

    def test_llm_success_returns_passed(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        gate = D6YouTubeGate()
        with patch_llm_complete(self.mock_llm_target, _D6_CANNED):
            result = gate.execute(d_gate_context)

        assert result["passed"] is True
        assert result["gate"] == self.GATE_NAME
        assert result["error"] is None

    def test_llm_success_produces_checks(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        gate = D6YouTubeGate()
        with patch_llm_complete(self.mock_llm_target, _D6_CANNED):
            result = gate.execute(d_gate_context)

        assert len(result["checks"]) >= self.MIN_OUTPUT_CHECKS
        for check in result["checks"]:
            assert check["passed"] is True, f"Check {check['name']!r} failed"

    def test_llm_success_stores_output_path(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        gate = D6YouTubeGate()
        with patch_llm_complete(self.mock_llm_target, _D6_CANNED):
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

    def test_context_extra_d6_output(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Successful gate sets gate_context.extra['d6_output']. """
        gate = D6YouTubeGate()
        with patch_llm_complete(self.mock_llm_target, _D6_CANNED):
            gate.execute(d_gate_context)

        extra = d_gate_context.get("extra", {})
        d6_output = extra.get("d6_output", "")
        assert d6_output, "gate_context.extra['d6_output'] was not set"

    def test_output_file_in_youtube_dir(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Output file is created under 04_distribution/youtube/."""
        import os

        gate = D6YouTubeGate()
        with patch_llm_complete(self.mock_llm_target, _D6_CANNED):
            result = gate.execute(d_gate_context)

        output_path = result.get("output_path", "")
        assert output_path, "No output_path in result"
        assert "04_distribution" in output_path
        assert "youtube" in output_path
        assert os.path.isfile(output_path)

    def test_quality_fails_missing_sections(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Response missing intro/body/outro sections fails quality check."""
        no_sections = (
            "Just some plain text without any section headings. "
            "It's long enough but lacks structure. " * 20
        )
        assert len(no_sections) > 500
        gate = D6YouTubeGate()
        with patch_llm_complete(self.mock_llm_target, no_sections):
            result = gate.execute(d_gate_context)

        assert result["passed"] is False
        quality_checks = [
            c for c in result["checks"] if "youtube" in c["name"].lower()
        ]
        assert len(quality_checks) >= 1
        assert quality_checks[0]["passed"] is False

    def test_quality_fails_missing_project_dir(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Missing 'project_dir' → gate fails."""
        ctx = {k: v for k, v in d_gate_context.items() if k != "project_dir"}
        gate = D6YouTubeGate()
        result = gate.execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == "D6"
        assert "project_dir" in result.get("error", "").lower()
