"""Tests for env-gated external detector adapters (B3).

The adapter contract pinned here:

- Without ``AUTOMEDIA_DETECTOR_GPTZERO_API_KEY``: ``available()`` is
  False and ``detect()`` raises a RuntimeError naming the missing env var.
- With the env var set: ``available()`` is True, but ``detect()`` still
  raises a "not configured in this build" RuntimeError — the adapter never
  fabricates a score and never makes a real network call.

Registration is unconditional: the adapter is registered in the registry
even when its env var is unset (availability is gated, registration is not).
"""

from __future__ import annotations

import pytest

from automedia.detectors import BaseDetector, DetectorRegistry, GPTZeroStyleApiDetector

_ENV_KEY = "AUTOMEDIA_DETECTOR_GPTZERO_API_KEY"


class TestGPTZeroStyleApiDetector:
    """Env-gating behaviour of the external API adapter."""

    def test_detector_name(self) -> None:
        """detector_name returns the class-level identifier."""
        assert GPTZeroStyleApiDetector().detector_name == "gptzero_style_api"

    def test_env_required_is_documented_var(self) -> None:
        """_env_required names the AUTOMEDIA_* env var that gates the adapter."""
        assert GPTZeroStyleApiDetector().env_required == _ENV_KEY

    def test_is_base_detector_subclass(self) -> None:
        """The adapter implements the BaseDetector contract."""
        assert issubclass(GPTZeroStyleApiDetector, BaseDetector)

    def test_registered_even_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Registration is unconditional — a missing env var does not block it."""
        monkeypatch.delenv(_ENV_KEY, raising=False)
        assert "gptzero_style_api" in DetectorRegistry()
        assert DetectorRegistry().get("gptzero_style_api") is GPTZeroStyleApiDetector

    def test_not_available_without_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """available() is False when the required env var is unset."""
        monkeypatch.delenv(_ENV_KEY, raising=False)
        assert GPTZeroStyleApiDetector().available() is False

    def test_detect_raises_unavailable_without_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """detect() raises a RuntimeError naming the missing env var."""
        monkeypatch.delenv(_ENV_KEY, raising=False)
        with pytest.raises(RuntimeError, match=_ENV_KEY):
            GPTZeroStyleApiDetector().detect("Some text to check.")

    def test_available_with_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """available() is True when the required env var is set."""
        monkeypatch.setenv(_ENV_KEY, "test-key-only-for-unittest")
        assert GPTZeroStyleApiDetector().available() is True

    def test_detect_raises_not_configured_with_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With the env var set, detect() raises the not-configured error.

        The adapter never makes a real network call and never returns a
        fabricated score — the honest contract for an unwired external API.
        """
        monkeypatch.setenv(_ENV_KEY, "test-key-only-for-unittest")
        with pytest.raises(RuntimeError, match="not configured"):
            GPTZeroStyleApiDetector().detect("Some text to check.")
