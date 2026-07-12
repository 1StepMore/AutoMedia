"""Tests for the Xiaohongshu (小红书 / RED) platform adapter.

These tests verify that:
- :func:`XiaohongshuPublisher.validate` behaves correctly with and
  without the ``XHS_COOKIE`` environment variable.
- :func:`XiaohongshuPublisher.publish` returns the documented
  ``not_implemented`` status.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest

from automedia.adapters.platforms.xiaohongshu_publisher import XiaohongshuPublisher

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ARTIFACT_DIR = "artifacts"  # relative path, no /tmp ambiguity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def adapter() -> XiaohongshuPublisher:
    """Return a fresh adapter instance."""
    return XiaohongshuPublisher()


@pytest.fixture()
def sample_project() -> dict[str, Any]:
    """Return a minimal project dict for publish tests."""
    return {
        "topic": "Test topic",
        "brand": "test-brand",
        "mode": "auto",
    }


# ---------------------------------------------------------------------------
# Platform metadata
# ---------------------------------------------------------------------------


class TestMetadata:
    """Verify basic platform metadata."""

    def test_platform_name(self, adapter: XiaohongshuPublisher) -> None:
        assert adapter.platform_name == "xiaohongshu"


class TestCredentialLoaderIntegration:
    """Verify adapter uses ``load_credential_or_env`` with ``AUTOMEDIA_*`` vars."""

    def test_enabled_with_automedia_env_var(
        self, adapter: XiaohongshuPublisher
    ) -> None:
        with patch.dict(
            os.environ,
            {"AUTOMEDIA_XIAOHONGSHU_COOKIE": "session=abc123"},
            clear=True,
        ):
            assert adapter.enabled is True

    def test_enabled_legacy_takes_precedence(
        self, adapter: XiaohongshuPublisher
    ) -> None:
        with patch.dict(
            os.environ,
            {
                "XHS_COOKIE": "legacy-cookie",
                "AUTOMEDIA_XIAOHONGSHU_COOKIE": "new-cookie",
            },
            clear=True,
        ):
            assert adapter.enabled is True

    def test_validate_with_automedia_env_only(
        self, adapter: XiaohongshuPublisher
    ) -> None:
        with patch.dict(
            os.environ,
            {"AUTOMEDIA_XIAOHONGSHU_COOKIE": "session=abc123"},
            clear=True,
        ):
            assert adapter.validate("artifacts") is True


# ---------------------------------------------------------------------------
# enabled
# ---------------------------------------------------------------------------


class TestEnabled:
    """Verify the ``enabled`` property checks ``XHS_COOKIE``."""

    def test_enabled_when_cookie_set(self, adapter: XiaohongshuPublisher) -> None:
        os.environ["XHS_COOKIE"] = "session=abc123"
        try:
            assert adapter.enabled is True
        finally:
            del os.environ["XHS_COOKIE"]

    def test_disabled_when_cookie_missing(self, adapter: XiaohongshuPublisher) -> None:
        os.environ.pop("XHS_COOKIE", None)
        assert adapter.enabled is False

    def test_disabled_when_cookie_empty(self, adapter: XiaohongshuPublisher) -> None:
        os.environ["XHS_COOKIE"] = ""
        try:
            assert adapter.enabled is False
        finally:
            del os.environ["XHS_COOKIE"]


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


class TestValidate:
    """Verify ``validate()`` behaviour."""

    def test_validate_passes_with_cookie(self, adapter: XiaohongshuPublisher) -> None:
        os.environ["XHS_COOKIE"] = "session=abc123"
        try:
            assert adapter.validate(_ARTIFACT_DIR) is True
        finally:
            del os.environ["XHS_COOKIE"]

    def test_validate_fails_without_cookie(self, adapter: XiaohongshuPublisher) -> None:
        os.environ.pop("XHS_COOKIE", None)
        assert adapter.validate(_ARTIFACT_DIR) is False

    def test_validate_fails_with_empty_cookie(self, adapter: XiaohongshuPublisher) -> None:
        os.environ["XHS_COOKIE"] = ""
        try:
            assert adapter.validate(_ARTIFACT_DIR) is False
        finally:
            del os.environ["XHS_COOKIE"]


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------


class TestPublish:
    """Verify ``publish()`` returns the documented status."""

    def test_publish_returns_not_implemented(
        self,
        adapter: XiaohongshuPublisher,
        sample_project: dict[str, Any],
    ) -> None:
        result = adapter.publish(_ARTIFACT_DIR, sample_project)
        assert result["status"] == "not_implemented"
        assert result["platform"] == "xiaohongshu"
        assert "reason" in result
        assert "public API" in result["reason"]
