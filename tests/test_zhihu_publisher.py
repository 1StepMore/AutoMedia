"""Tests for the Zhihu (知乎) platform adapter.

These tests verify that:
- :func:`ZhihuPublisher.validate` behaves correctly with and without
  the ``ZHIHU_COOKIE`` environment variable.
- :func:`ZhihuPublisher.publish` handles HTTP success, HTTP errors, and
  missing httpx gracefully.
- Content is read from the artifact directory when available.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.adapters.platforms.zhihu_publisher import ZhihuPublisher

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def adapter() -> ZhihuPublisher:
    """Return a fresh adapter instance."""
    return ZhihuPublisher()


@pytest.fixture()
def sample_project() -> dict[str, Any]:
    """Return a minimal project dict for publish tests."""
    return {
        "topic": "Test topic",
        "brand": "test-brand",
        "mode": "auto",
    }


@pytest.fixture()
def mock_path(tmp_path: Path) -> Path:
    """Return a temporary path for artifact operations."""
    return tmp_path


@pytest.fixture()
def unused_path() -> str:
    """A path string for tests that check preconditions only (no I/O)."""
    return str(Path.cwd() / ".pytest-tmp" / "zhihu")


# ---------------------------------------------------------------------------
# Platform metadata
# ---------------------------------------------------------------------------


class TestMetadata:
    """Verify basic platform metadata."""

    def test_platform_name(self, adapter: ZhihuPublisher) -> None:
        assert adapter.platform_name == "zhihu"


class TestCredentialLoaderIntegration:
    """Verify adapter uses ``load_credential_or_env`` with ``AUTOMEDIA_*`` vars."""

    def test_enabled_with_automedia_env_var(
        self, adapter: ZhihuPublisher
    ) -> None:
        with patch.dict(
            os.environ,
            {"AUTOMEDIA_ZHIHU_COOKIE": "session=abc123;"},
            clear=True,
        ):
            assert adapter.enabled is True

    def test_enabled_legacy_takes_precedence(
        self, adapter: ZhihuPublisher
    ) -> None:
        with patch.dict(
            os.environ,
            {
                "ZHIHU_COOKIE": "legacy-cookie",
                "AUTOMEDIA_ZHIHU_COOKIE": "new-cookie",
            },
            clear=True,
        ):
            assert adapter.enabled is True

    def test_validate_with_automedia_env_only(
        self, adapter: ZhihuPublisher, unused_path: str
    ) -> None:
        with patch.dict(
            os.environ,
            {"AUTOMEDIA_ZHIHU_COOKIE": "session=abc123;"},
            clear=True,
        ):
            assert adapter.validate(unused_path) is True


# ---------------------------------------------------------------------------
# enabled
# ---------------------------------------------------------------------------


class TestEnabled:
    """Verify the ``enabled`` property checks ``ZHIHU_COOKIE``."""

    def test_enabled_when_cookie_set(self, adapter: ZhihuPublisher) -> None:
        os.environ["ZHIHU_COOKIE"] = "session=abc123; "
        try:
            assert adapter.enabled is True
        finally:
            del os.environ["ZHIHU_COOKIE"]

    def test_disabled_when_cookie_missing(self, adapter: ZhihuPublisher) -> None:
        os.environ.pop("ZHIHU_COOKIE", None)
        assert adapter.enabled is False

    def test_disabled_when_cookie_empty(self, adapter: ZhihuPublisher) -> None:
        os.environ["ZHIHU_COOKIE"] = ""
        try:
            assert adapter.enabled is False
        finally:
            del os.environ["ZHIHU_COOKIE"]


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


class TestValidate:
    """Verify ``validate()`` behaviour."""

    def test_validate_passes_with_cookie(
        self, adapter: ZhihuPublisher, unused_path: str
    ) -> None:
        os.environ["ZHIHU_COOKIE"] = "session=abc123; "
        try:
            assert adapter.validate(unused_path) is True
        finally:
            del os.environ["ZHIHU_COOKIE"]

    def test_validate_fails_without_cookie(
        self, adapter: ZhihuPublisher, unused_path: str
    ) -> None:
        os.environ.pop("ZHIHU_COOKIE", None)
        assert adapter.validate(unused_path) is False

    def test_validate_fails_with_empty_cookie(
        self, adapter: ZhihuPublisher, unused_path: str
    ) -> None:
        os.environ["ZHIHU_COOKIE"] = ""
        try:
            assert adapter.validate(unused_path) is False
        finally:
            del os.environ["ZHIHU_COOKIE"]


# ---------------------------------------------------------------------------
# publish — error scenarios (no HTTP call needed)
# ---------------------------------------------------------------------------


class TestPublishErrors:
    """Verify error handling in ``publish()``."""

    def test_publish_fails_without_cookie(
        self,
        adapter: ZhihuPublisher,
        sample_project: dict[str, Any],
        unused_path: str,
    ) -> None:
        os.environ.pop("ZHIHU_COOKIE", None)
        result = adapter.publish(unused_path, sample_project)
        assert result["status"] == "error"
        assert result["platform"] == "zhihu"
        assert "cookie" in result["reason"].lower()

    def test_publish_fails_without_httpx(
        self,
        adapter: ZhihuPublisher,
        sample_project: dict[str, Any],
        unused_path: str,
    ) -> None:
        os.environ["ZHIHU_COOKIE"] = "session=abc123; "
        try:
            with patch(
                "automedia.adapters.platforms.zhihu_publisher._HAS_HTTPX", False
            ):
                result = adapter.publish(unused_path, sample_project)
                assert result["status"] == "error"
                assert result["platform"] == "zhihu"
                assert "httpx" in result["reason"].lower()
        finally:
            del os.environ["ZHIHU_COOKIE"]


# ---------------------------------------------------------------------------
# publish — content reading
# ---------------------------------------------------------------------------


class TestPublishContentReading:
    """Verify that ``publish()`` reads content from the artifact directory."""

    def test_publish_reads_html_draft(
        self,
        adapter: ZhihuPublisher,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """When a ``.html`` file exists it is used as the body."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir(parents=True)
        html_draft = drafts_dir / "article.html"
        html_draft.write_text("<h1>Test Article</h1><p>Hello Zhihu!</p>", encoding="utf-8")

        result = adapter._read_content(str(tmp_path), sample_project)
        assert result["status"] == "ok"
        assert "<h1>Test Article</h1>" in result["body_html"]
        assert result["title"] == "Test topic"

    def test_publish_reads_md_draft(
        self,
        adapter: ZhihuPublisher,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """When only a ``.md`` file exists it is used as the body."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir(parents=True)
        md_draft = drafts_dir / "article.md"
        md_draft.write_text("# Test\n\nHello Zhihu!", encoding="utf-8")

        result = adapter._read_content(str(tmp_path), sample_project)
        assert result["status"] == "ok"
        assert "# Test" in result["body_html"]
        assert result["title"] == "Test topic"

    def test_publish_empty_artifact_fallback(
        self,
        adapter: ZhihuPublisher,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """When no drafts exist a minimal HTML body is created."""
        result = adapter._read_content(str(tmp_path), sample_project)
        assert result["status"] == "ok"
        assert result["title"] == "Test topic"
        assert "<p>Test topic</p>" in result["body_html"]

    def test_publish_uses_project_title(
        self,
        adapter: ZhihuPublisher,
        tmp_path: Path,
    ) -> None:
        """``project["title"]`` takes priority over ``project["topic"]``."""
        project = {"title": "Explicit Title", "topic": "Fallback Topic"}
        result = adapter._read_content(str(tmp_path), project)
        assert result["title"] == "Explicit Title"

    def test_publish_info_file_title(
        self,
        adapter: ZhihuPublisher,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        info = {"title": "Info File Title"}
        info_file = tmp_path / "00_project_info.json"
        info_file.write_text(json.dumps(info), encoding="utf-8")

        result = adapter._read_content(str(tmp_path), sample_project)
        assert result["title"] == "Info File Title"


# ---------------------------------------------------------------------------
# publish — HTTP mocking
# ---------------------------------------------------------------------------


class TestPublishHttpCalls:
    """Verify HTTP call behaviour using mocked httpx."""

    def test_publish_success(
        self,
        adapter: ZhihuPublisher,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """A successful API call returns ``draft_id``."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir(parents=True)
        html_draft = drafts_dir / "article.html"
        html_draft.write_text("<h1>Test</h1>", encoding="utf-8")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 12345}
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response

        os.environ["ZHIHU_COOKIE"] = "session=abc123; "
        try:
            with patch(
                "automedia.adapters.platforms.zhihu_publisher._httpx.post",
                return_value=mock_response,
            ):
                result = adapter.publish(str(tmp_path), sample_project)
                assert result["status"] == "ok"
                assert result["platform"] == "zhihu"
                assert result["draft_id"] == "12345"
        finally:
            del os.environ["ZHIHU_COOKIE"]

    def test_publish_http_400(
        self,
        adapter: ZhihuPublisher,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """An HTTP 400 error is reported gracefully."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir(parents=True)
        html_draft = drafts_dir / "article.html"
        html_draft.write_text("<h1>Test</h1>", encoding="utf-8")

        import httpx

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "Bad request"}
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad request", request=MagicMock(), response=mock_response
        )

        os.environ["ZHIHU_COOKIE"] = "session=abc123; "
        try:
            with patch(
                "automedia.adapters.platforms.zhihu_publisher._httpx.post",
                side_effect=httpx.HTTPStatusError(
                    "Bad request", request=MagicMock(), response=mock_response
                ),
            ):
                result = adapter.publish(str(tmp_path), sample_project)
                assert result["status"] == "error"
                assert result["platform"] == "zhihu"
                assert "400" in result["reason"]
        finally:
            del os.environ["ZHIHU_COOKIE"]

    def test_publish_connection_error(
        self,
        adapter: ZhihuPublisher,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """A connection error is reported gracefully."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir(parents=True)
        html_draft = drafts_dir / "article.html"
        html_draft.write_text("<h1>Test</h1>", encoding="utf-8")

        import httpx

        os.environ["ZHIHU_COOKIE"] = "session=abc123; "
        try:
            with patch(
                "automedia.adapters.platforms.zhihu_publisher._httpx.post",
                side_effect=httpx.ConnectError("Connection refused"),
            ):
                result = adapter.publish(str(tmp_path), sample_project)
                assert result["status"] == "error"
                assert result["platform"] == "zhihu"
                assert "Connection refused" in result["reason"]
        finally:
            del os.environ["ZHIHU_COOKIE"]
