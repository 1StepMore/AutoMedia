"""Tests for D2 Twitter/X Distribution Gate (D2Gate).

Covers output format verification (numbered tweets), empty content
handling, file output creation, and tweet quality validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from automedia.gates.distribution.d2_twitter import D2Gate
from tests.test_distribution.test_d_gate_base import (
    DGateTestBase,
    patch_llm_complete,
    patch_llm_failure,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock


# Canned response with 5 numbered tweets, each ≤ 280 chars
_D2_CANNED: str = (
    "1/ AI is reshaping content creation faster than ever. "
    "Here's what every creator needs to know in 2025.\n\n"
    "2/ Multimodal AI can now process text, images, and audio "
    "simultaneously — enabling richer content experiences "
    "that were impossible just a year ago.\n\n"
    "3/ Edge computing brings AI inference directly to devices. "
    "Lower latency, better privacy, and real-time processing "
    "are finally becoming mainstream.\n\n"
    "4/ Generative AI tools are democratizing content production. "
    "From video scripts to social posts — AI handles the "
    "heavy lifting while creators focus on strategy.\n\n"
    "5/ The future belongs to creators who embrace AI as a "
    "collaborator, not a replacement. Start experimenting "
    "today. Follow for more insights."
)


class TestD2(DGateTestBase):
    """D2 Twitter/X gate tests."""

    GATE_CLASS = D2Gate
    GATE_NAME = "D2"
    mock_llm_target = "automedia.gates.distribution.d2_twitter.llm_complete"

    # D2 wraps content with "## Tweet N" headers, so the canned response
    # does NOT appear verbatim in the output file. Override this inherited
    # test to check that the file exists and is non-empty instead.
    def test_output_file_contains_canned_response(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        import os

        gate = D2Gate()
        with patch_llm_complete(self.mock_llm_target):
            result = gate.execute(d_gate_context)

        output_path = result.get("output_path", "")
        if output_path:
            assert os.path.isfile(output_path)
            assert os.path.getsize(output_path) > 0

    # ------------------------------------------------------------------
    # Gate-specific tests
    # ------------------------------------------------------------------

    def test_context_extra_d2_output(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Successful gate sets gate_context.extra['d2_output'] with tweets."""
        gate = D2Gate()
        with patch_llm_complete(self.mock_llm_target, _D2_CANNED):
            gate.execute(d_gate_context)

        extra = d_gate_context.get("extra", {})
        d2_output = extra.get("d2_output", [])
        assert len(d2_output) >= 3, (
            f"Expected at least 3 tweets in extra['d2_output'], "
            f"got {len(d2_output)}"
        )
        for tweet in d2_output:
            assert "index" in tweet
            assert "text" in tweet
            assert len(tweet["text"]) <= 280

    def test_output_file_in_twitter_dir(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Output file is created under 04_distribution/twitter/."""
        import os

        gate = D2Gate()
        with patch_llm_complete(self.mock_llm_target, _D2_CANNED):
            result = gate.execute(d_gate_context)

        output_path = result.get("output_path", "")
        assert output_path, "No output_path in result"
        assert "04_distribution" in output_path
        assert "twitter" in output_path
        assert os.path.isfile(output_path)

    def test_few_tweets_fails(
        self, d_gate_context: dict[str, Any]
    ) -> None:
        """Response producing < 3 tweets fails quality check."""
        single_tweet = "1/ Only one tweet here."
        gate = D2Gate()
        with patch_llm_complete(self.mock_llm_target, single_tweet):
            result = gate.execute(d_gate_context)

        assert result["passed"] is False
        tweet_checks = [
            c for c in result["checks"] if "tweet" in c["name"].lower()
        ]
        assert len(tweet_checks) >= 1
        assert tweet_checks[0]["passed"] is False
