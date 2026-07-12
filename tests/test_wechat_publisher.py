"""Tests for WechatPublisher adapter — real API implementation.

Tests cover:
- enabled / validate with and without env vars
- publish success path (token → draft → publish)
- publish error paths (missing creds, httpx missing, HTTP errors, API errors)
- fallback when httpx is not available
- content reading with HTML/MD drafts
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.adapters.platforms.wechat_publisher import WechatPublisher

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def publisher() -> WechatPublisher:
    return WechatPublisher()


@pytest.fixture()
def sample_project() -> dict[str, Any]:
    return {
        "topic": "AI Video Tools",
        "brand": "my-brand",
    }


@pytest.fixture()
def env_vars() -> dict[str, str]:
    return {"WX_APPID": "wx_test_appid", "WX_APPSECRET": "test_secret_123"}


# ---------------------------------------------------------------------------
# enabled / validate — env var detection
# ---------------------------------------------------------------------------


class TestEnabledAndValidate:
    """enabled property and validate() both check WX_APPID / WX_APPSECRET."""

    def test_enabled_false_when_no_env(
        self, publisher: WechatPublisher
    ) -> None:
        assert "WX_APPID" not in os.environ
        assert publisher.enabled is False

    def test_enabled_true_when_env_set(
        self, publisher: WechatPublisher, env_vars: dict[str, str]
    ) -> None:
        with patch.dict(os.environ, env_vars):
            assert publisher.enabled is True

    def test_enabled_false_when_only_appid(
        self, publisher: WechatPublisher
    ) -> None:
        with patch.dict(os.environ, {"WX_APPID": "wx_test_appid"}):
            assert publisher.enabled is False

    def test_enabled_false_when_only_secret(
        self, publisher: WechatPublisher
    ) -> None:
        with patch.dict(os.environ, {"WX_APPSECRET": "test_secret_123"}):
            assert publisher.enabled is False

    def test_validate_false_when_no_env(
        self, publisher: WechatPublisher, tmp_path: Path
    ) -> None:
        assert "WX_APPID" not in os.environ
        assert publisher.validate(str(tmp_path)) is False

    def test_validate_true_when_env_set(
        self, publisher: WechatPublisher, env_vars: dict[str, str], tmp_path: Path
    ) -> None:
        with patch.dict(os.environ, env_vars):
            assert publisher.validate(str(tmp_path)) is True

    def test_validate_false_with_empty_values(
        self, publisher: WechatPublisher, tmp_path: Path
    ) -> None:
        env = {"WX_APPID": "", "WX_APPSECRET": ""}
        with patch.dict(os.environ, env):
            assert publisher.validate(str(tmp_path)) is False

    def test_platform_name(self, publisher: WechatPublisher) -> None:
        assert publisher.platform_name == "wechat"


class TestCredentialLoaderIntegration:
    """Verify adapters use ``load_credential_or_env`` with ``AUTOMEDIA_*`` vars."""

    def test_enabled_with_automedia_env_vars(
        self, publisher: WechatPublisher
    ) -> None:
        with patch.dict(
            os.environ,
            {
                "AUTOMEDIA_WECHAT_APPID": "wx_test_appid",
                "AUTOMEDIA_WECHAT_APPSECRET": "test_secret_123",
            },
            clear=True,
        ):
            assert publisher.enabled is True

    def test_enabled_legacy_takes_precedence(
        self, publisher: WechatPublisher
    ) -> None:
        with patch.dict(
            os.environ,
            {
                "WX_APPID": "legacy-appid",
                "WX_APPSECRET": "legacy-secret",
                "AUTOMEDIA_WECHAT_APPID": "new-appid",
                "AUTOMEDIA_WECHAT_APPSECRET": "new-secret",
            },
            clear=True,
        ):
            assert publisher.enabled is True

    def test_validate_with_automedia_env_only(
        self, publisher: WechatPublisher, tmp_path: Path
    ) -> None:
        with patch.dict(
            os.environ,
            {
                "AUTOMEDIA_WECHAT_APPID": "wx_test_appid",
                "AUTOMEDIA_WECHAT_APPSECRET": "test_secret_123",
            },
            clear=True,
        ):
            assert publisher.validate(str(tmp_path)) is True

    def test_publish_with_automedia_env(
        self,
        publisher: WechatPublisher,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / "content.html").write_text("<p>body</p>", encoding="utf-8")

        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "tk"}

        with patch.dict(
            os.environ,
            {
                "AUTOMEDIA_WECHAT_APPID": "wx_test_appid",
                "AUTOMEDIA_WECHAT_APPSECRET": "test_secret_123",
            },
            clear=True,
        ), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post",
            return_value=mock_response,
        ) as mock_post:
            mock_post.side_effect = [
                MagicMock(json=lambda: {"access_token": "tk"}),
                MagicMock(json=lambda: {"media_id": "draft_123"}),
                MagicMock(json=lambda: {"publish_id": "pub_456"}),
            ]
            result = publisher.publish(str(tmp_path), sample_project)

        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# publish — success path
# ---------------------------------------------------------------------------


class TestPublishSuccess:
    """publish() calls token → draft → publish and returns IDs."""

    def test_full_success(
        self,
        publisher: WechatPublisher,
        sample_project: dict[str, Any],
        env_vars: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Verify the full three-step flow returns ok with IDs."""
        # Create a draft HTML file in the temp artifact directory
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        html_content = "<h1>Test Article</h1><p>Hello WeChat</p>"
        (drafts_dir / "content.html").write_text(html_content, encoding="utf-8")

        # Mock httpx responses for all three calls
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {
            "access_token": "fake_token_abc"
        }

        mock_draft_resp = MagicMock()
        mock_draft_resp.json.return_value = {"media_id": "draft_123"}

        mock_publish_resp = MagicMock()
        mock_publish_resp.json.return_value = {"publish_id": "pub_456"}

        with patch.dict(os.environ, env_vars), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            # Set side_effect to return different responses per call
            mock_post.side_effect = [
                mock_token_resp,
                mock_draft_resp,
                mock_publish_resp,
            ]

            result = publisher.publish(str(tmp_path), sample_project)

        assert result["status"] == "ok"
        assert result["platform"] == "wechat"
        assert result["article_id"] == "draft_123"
        assert result["publish_id"] == "pub_456"

        # Verify the three calls were made in order
        assert mock_post.call_count == 3
        # First call: token endpoint
        token_url = mock_post.call_args_list[0][0][0]
        assert "api.weixin.qq.com/cgi-bin/token" in token_url
        assert "wx_test_appid" in token_url
        assert "test_secret_123" in token_url
        # Second call: draft/add
        draft_url = mock_post.call_args_list[1][0][0]
        assert "draft/add" in draft_url
        assert "fake_token_abc" in draft_url
        # Third call: freepublish/submit
        pub_url = mock_post.call_args_list[2][0][0]
        assert "freepublish/submit" in pub_url
        assert "fake_token_abc" in pub_url
        pub_payload = mock_post.call_args_list[2][1]["json"]
        assert pub_payload["draft_id"] == "draft_123"

    def test_success_with_markdown(
        self,
        publisher: WechatPublisher,
        sample_project: dict[str, Any],
        env_vars: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Verify publish works with Markdown content (converted to HTML)."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        md_content = "# Title\n\n**bold** and *italic* text"
        (drafts_dir / "article.md").write_text(md_content, encoding="utf-8")

        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "tk"}
        mock_draft_resp = MagicMock()
        mock_draft_resp.json.return_value = {"media_id": "draft_md"}
        mock_publish_resp = MagicMock()
        mock_publish_resp.json.return_value = {"publish_id": "pub_md"}

        with patch.dict(os.environ, env_vars), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            mock_post.side_effect = [
                mock_token_resp,
                mock_draft_resp,
                mock_publish_resp,
            ]
            result = publisher.publish(str(tmp_path), sample_project)

        assert result["status"] == "ok"
        # Verify the draft content had HTML (converted from MD)
        draft_payload = mock_post.call_args_list[1][1]["json"]
        draft_body = draft_payload["articles"][0]["content"]
        assert "<h1>" in draft_body
        assert "<strong>" in draft_body
        assert "<em>" in draft_body

    def test_success_with_project_info_title(
        self,
        publisher: WechatPublisher,
        sample_project: dict[str, Any],
        env_vars: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Verify that 00_project_info.json title is preferred."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / "content.html").write_text("<p>body</p>", encoding="utf-8")

        # Write project info with a different title
        info = {"title": "Project Info Title"}
        (tmp_path / "00_project_info.json").write_text(
            json.dumps(info), encoding="utf-8"
        )

        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "tk"}
        mock_draft_resp = MagicMock()
        mock_draft_resp.json.return_value = {"media_id": "draft_proj"}
        mock_publish_resp = MagicMock()
        mock_publish_resp.json.return_value = {"publish_id": "pub_proj"}

        with patch.dict(os.environ, env_vars), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            mock_post.side_effect = [
                mock_token_resp,
                mock_draft_resp,
                mock_publish_resp,
            ]
            result = publisher.publish(str(tmp_path), sample_project)

        assert result["status"] == "ok"
        draft_payload = mock_post.call_args_list[1][1]["json"]
        assert draft_payload["articles"][0]["title"] == "Project Info Title"


# ---------------------------------------------------------------------------
# publish — error paths
# ---------------------------------------------------------------------------


class TestPublishErrors:
    """publish() error handling for various failure modes."""

    def test_missing_credentials(
        self,
        publisher: WechatPublisher,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        assert "WX_APPID" not in os.environ
        result = publisher.publish(str(tmp_path), sample_project)
        assert result["status"] == "error"
        assert result["platform"] == "wechat"
        assert "credentials not set" in result["reason"]

    def test_httpx_not_available(
        self,
        publisher: WechatPublisher,
        sample_project: dict[str, Any],
        env_vars: dict[str, str],
        tmp_path: Path,
    ) -> None:
        with (
            patch.dict(os.environ, env_vars),
            patch(
                "automedia.adapters.platforms.wechat_publisher._HAS_HTTPX",
                False,
            ),
        ):
            result = publisher.publish(str(tmp_path), sample_project)

        assert result["status"] == "error"
        assert result["platform"] == "wechat"
        assert "httpx is not installed" in result["reason"]

    def test_token_http_error(
        self,
        publisher: WechatPublisher,
        sample_project: dict[str, Any],
        env_vars: dict[str, str],
        tmp_path: Path,
    ) -> None:
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / "content.html").write_text("<p>body</p>", encoding="utf-8")

        with patch.dict(os.environ, env_vars), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            import httpx

            error_response = MagicMock(spec=httpx.Response)
            error_response.status_code = 403
            mock_post.side_effect = httpx.HTTPStatusError(
                "403 Forbidden",
                request=MagicMock(),
                response=error_response,
            )
            result = publisher.publish(str(tmp_path), sample_project)

        assert result["status"] == "error"
        assert "HTTP 403" in result["reason"]

    def test_token_connection_error(
        self,
        publisher: WechatPublisher,
        sample_project: dict[str, Any],
        env_vars: dict[str, str],
        tmp_path: Path,
    ) -> None:
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / "content.html").write_text("<p>body</p>", encoding="utf-8")

        with patch.dict(os.environ, env_vars), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            import httpx

            mock_post.side_effect = httpx.ConnectTimeout(
                "Connection timed out", request=MagicMock()
            )
            result = publisher.publish(str(tmp_path), sample_project)

        assert result["status"] == "error"
        assert "token request failed" in result["reason"]
        assert "ConnectTimeout" in result["reason"]

    def test_token_api_error(
        self,
        publisher: WechatPublisher,
        sample_project: dict[str, Any],
        env_vars: dict[str, str],
        tmp_path: Path,
    ) -> None:
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / "content.html").write_text("<p>body</p>", encoding="utf-8")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "errcode": 40013,
            "errmsg": "invalid appid",
        }

        with patch.dict(os.environ, env_vars), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            mock_post.return_value = mock_response
            result = publisher.publish(str(tmp_path), sample_project)

        assert result["status"] == "error"
        assert "invalid appid" in result["reason"]

    def test_draft_api_error(
        self,
        publisher: WechatPublisher,
        sample_project: dict[str, Any],
        env_vars: dict[str, str],
        tmp_path: Path,
    ) -> None:
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / "content.html").write_text("<p>body</p>", encoding="utf-8")

        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "tk"}
        mock_draft_resp = MagicMock()
        mock_draft_resp.json.return_value = {
            "errcode": 40125,
            "errmsg": "invalid credential",
        }

        with patch.dict(os.environ, env_vars), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            mock_post.side_effect = [mock_token_resp, mock_draft_resp]
            result = publisher.publish(str(tmp_path), sample_project)

        assert result["status"] == "error"
        assert "invalid credential" in result["reason"]

    def test_publish_api_error(
        self,
        publisher: WechatPublisher,
        sample_project: dict[str, Any],
        env_vars: dict[str, str],
        tmp_path: Path,
    ) -> None:
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / "content.html").write_text("<p>body</p>", encoding="utf-8")

        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "tk"}
        mock_draft_resp = MagicMock()
        mock_draft_resp.json.return_value = {"media_id": "draft_ok"}
        mock_publish_resp = MagicMock()
        mock_publish_resp.json.return_value = {
            "errcode": -1,
            "errmsg": "system error",
        }

        with patch.dict(os.environ, env_vars), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            mock_post.side_effect = [
                mock_token_resp,
                mock_draft_resp,
                mock_publish_resp,
            ]
            result = publisher.publish(str(tmp_path), sample_project)

        assert result["status"] == "error"
        assert "system error" in result["reason"]


# ---------------------------------------------------------------------------
# publish — edge cases
# ---------------------------------------------------------------------------


class TestPublishEdgeCases:
    """publish() handles edge cases gracefully."""

    def test_empty_drafts_dir(
        self,
        publisher: WechatPublisher,
        sample_project: dict[str, Any],
        env_vars: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Fall back to a simple <p> tag when no content files exist."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()  # empty directory

        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "tk"}
        mock_draft_resp = MagicMock()
        mock_draft_resp.json.return_value = {"media_id": "draft_empty"}
        mock_publish_resp = MagicMock()
        mock_publish_resp.json.return_value = {"publish_id": "pub_empty"}

        with patch.dict(os.environ, env_vars), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            mock_post.side_effect = [
                mock_token_resp,
                mock_draft_resp,
                mock_publish_resp,
            ]
            result = publisher.publish(str(tmp_path), sample_project)

        assert result["status"] == "ok"
        # Verify draft content is the fallback <p> tag
        draft_payload = mock_post.call_args_list[1][1]["json"]
        assert "<p>AI Video Tools</p>" in draft_payload["articles"][0]["content"]

    def test_no_drafts_dir(
        self,
        publisher: WechatPublisher,
        sample_project: dict[str, Any],
        env_vars: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Fall back when no drafts/ directory exists at all."""
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "tk"}
        mock_draft_resp = MagicMock()
        mock_draft_resp.json.return_value = {"media_id": "draft_nodir"}
        mock_publish_resp = MagicMock()
        mock_publish_resp.json.return_value = {"publish_id": "pub_nodir"}

        with patch.dict(os.environ, env_vars), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            mock_post.side_effect = [
                mock_token_resp,
                mock_draft_resp,
                mock_publish_resp,
            ]
            result = publisher.publish(str(tmp_path), sample_project)

        assert result["status"] == "ok"
        draft_payload = mock_post.call_args_list[1][1]["json"]
        assert "<p>AI Video Tools</p>" in draft_payload["articles"][0]["content"]

    def test_draft_includes_author(
        self,
        publisher: WechatPublisher,
        sample_project: dict[str, Any],
        env_vars: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Author field is set from project brand."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / "content.html").write_text("<p>body</p>", encoding="utf-8")

        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "tk"}
        mock_draft_resp = MagicMock()
        mock_draft_resp.json.return_value = {"media_id": "draft_auth"}
        mock_publish_resp = MagicMock()
        mock_publish_resp.json.return_value = {"publish_id": "pub_auth"}

        with patch.dict(os.environ, env_vars), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            mock_post.side_effect = [
                mock_token_resp,
                mock_draft_resp,
                mock_publish_resp,
            ]
            result = publisher.publish(str(tmp_path), sample_project)

        assert result["status"] == "ok"
        draft_payload = mock_post.call_args_list[1][1]["json"]
        assert draft_payload["articles"][0]["author"] == "my-brand"

    def test_no_author_when_no_brand(
        self,
        publisher: WechatPublisher,
        env_vars: dict[str, str],
        tmp_path: Path,
    ) -> None:
        """Author is omitted when project has no brand."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / "content.html").write_text("<p>body</p>", encoding="utf-8")

        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "tk"}
        mock_draft_resp = MagicMock()
        mock_draft_resp.json.return_value = {"media_id": "draft_noauth"}
        mock_publish_resp = MagicMock()
        mock_publish_resp.json.return_value = {"publish_id": "pub_noauth"}

        with patch.dict(os.environ, env_vars), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            mock_post.side_effect = [
                mock_token_resp,
                mock_draft_resp,
                mock_publish_resp,
            ]
            result = publisher.publish(
                str(tmp_path), {"topic": "No Brand"}
            )

        assert result["status"] == "ok"
        draft_payload = mock_post.call_args_list[1][1]["json"]
        assert "author" not in draft_payload["articles"][0]


# ---------------------------------------------------------------------------
# Credential sanitization — Issue #4
# ---------------------------------------------------------------------------


class TestSanitizeUrl:
    """_sanitize_url redacts appid, secret, and access_token query params."""

    def test_redacts_appid_and_secret(self) -> None:
        from automedia.adapters.platforms.wechat_publisher import _sanitize_url

        url = "https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=SECRET_APPID&secret=SECRET_KEY"
        sanitized = _sanitize_url(url)
        assert "SECRET_APPID" not in sanitized
        assert "SECRET_KEY" not in sanitized
        assert "appid=***" in sanitized
        assert "secret=***" in sanitized

    def test_redacts_access_token(self) -> None:
        from automedia.adapters.platforms.wechat_publisher import _sanitize_url

        url = "https://api.weixin.qq.com/cgi-bin/draft/add?access_token=SENSITIVE_TOKEN_12345"
        sanitized = _sanitize_url(url)
        assert "SENSITIVE_TOKEN_12345" not in sanitized
        assert "access_token=***" in sanitized

    def test_preserves_non_credential_params(self) -> None:
        from automedia.adapters.platforms.wechat_publisher import _sanitize_url

        url = "https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=X&secret=Y"
        sanitized = _sanitize_url(url)
        assert "grant_type=client_credential" in sanitized

    def test_case_insensitive(self) -> None:
        from automedia.adapters.platforms.wechat_publisher import _sanitize_url

        url = "https://example.com?APPID=val1&Secret=val2&ACCESS_TOKEN=val3"
        sanitized = _sanitize_url(url)
        assert "val1" not in sanitized
        assert "val2" not in sanitized
        assert "val3" not in sanitized

    def test_no_params_unchanged(self) -> None:
        from automedia.adapters.platforms.wechat_publisher import _sanitize_url

        url = "https://api.weixin.qq.com/cgi-bin/token"
        assert _sanitize_url(url) == url


class TestCredentialLeakPrevention:
    """Credentials must never appear in log output or error dicts (Issue #4)."""

    APPID = "wx_SUPERSECRET_appid"
    SECRET = "super_secret_value_999"
    TOKEN = "access_token_SENSITIVE_xyz"

    def _assert_no_credentials(
        self, text: str, *values: str, label: str = ""
    ) -> None:
        for val in values:
            assert val not in text, (
                f"Credential '{val}' leaked in {label}: {text}"
            )

    def test_token_request_error_no_leak_in_logs(
        self, publisher: WechatPublisher, tmp_path: Path, capsys: Any
    ) -> None:
        """RequestError logs and reason must not contain appid/secret."""
        import logging

        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / "c.html").write_text("<p>hi</p>", encoding="utf-8")

        env = {"WX_APPID": self.APPID, "WX_APPSECRET": self.SECRET}

        with patch.dict(os.environ, env), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            import httpx

            mock_post.side_effect = httpx.ConnectTimeout(
                "Connection timed out",
                request=MagicMock(),
            )
            with capsys.disabled():
                import io

                log_capture = io.StringIO()
                handler = logging.StreamHandler(log_capture)
                handler.setLevel(logging.DEBUG)
                logger = logging.getLogger(
                    "automedia.adapters.platforms.wechat_publisher"
                )
                logger.addHandler(handler)
                try:
                    result = publisher.publish(str(tmp_path), {"topic": "t"})
                finally:
                    logger.removeHandler(handler)

        log_output = log_capture.getvalue()
        self._assert_no_credentials(
            log_output, self.APPID, self.SECRET, label="log output"
        )
        reason = result.get("reason", "")
        self._assert_no_credentials(
            reason, self.APPID, self.SECRET, label="reason dict"
        )
        assert "appid=***" in reason or "token request failed" in reason

    def test_draft_request_error_no_leak_in_reason(
        self, publisher: WechatPublisher, tmp_path: Path
    ) -> None:
        """Draft RequestError reason must not contain access_token."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / "c.html").write_text("<p>hi</p>", encoding="utf-8")

        env = {"WX_APPID": self.APPID, "WX_APPSECRET": self.SECRET}
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": self.TOKEN}

        with patch.dict(os.environ, env), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            import httpx

            mock_post.side_effect = [
                mock_token_resp,
                httpx.ConnectTimeout(
                    "timeout", request=MagicMock()
                ),
            ]
            result = publisher.publish(str(tmp_path), {"topic": "t"})

        reason = result.get("reason", "")
        self._assert_no_credentials(
            reason, self.TOKEN, label="draft error reason"
        )
        assert "access_token=***" in reason

    def test_publish_request_error_no_leak_in_reason(
        self, publisher: WechatPublisher, tmp_path: Path
    ) -> None:
        """Publish RequestError reason must not contain access_token."""
        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / "c.html").write_text("<p>hi</p>", encoding="utf-8")

        env = {"WX_APPID": self.APPID, "WX_APPSECRET": self.SECRET}
        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": self.TOKEN}
        mock_draft_resp = MagicMock()
        mock_draft_resp.json.return_value = {"media_id": "d1"}

        with patch.dict(os.environ, env), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            import httpx

            mock_post.side_effect = [
                mock_token_resp,
                mock_draft_resp,
                httpx.ConnectTimeout(
                    "timeout", request=MagicMock()
                ),
            ]
            result = publisher.publish(str(tmp_path), {"topic": "t"})

        reason = result.get("reason", "")
        self._assert_no_credentials(
            reason, self.TOKEN, label="publish error reason"
        )
        assert "access_token=***" in reason

    def test_success_path_no_credential_leak_in_logs(
        self, publisher: WechatPublisher, tmp_path: Path
    ) -> None:
        """Happy-path logs must not contain appid, secret, or access_token."""
        import io
        import logging

        drafts_dir = tmp_path / "drafts"
        drafts_dir.mkdir()
        (drafts_dir / "c.html").write_text("<p>hi</p>", encoding="utf-8")

        env = {"WX_APPID": self.APPID, "WX_APPSECRET": self.SECRET}

        mock_token_resp = MagicMock()
        mock_token_resp.json.return_value = {"access_token": self.TOKEN}
        mock_draft_resp = MagicMock()
        mock_draft_resp.json.return_value = {"media_id": "d1"}
        mock_publish_resp = MagicMock()
        mock_publish_resp.json.return_value = {"publish_id": "p1"}

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger(
            "automedia.adapters.platforms.wechat_publisher"
        )
        logger.addHandler(handler)

        with patch.dict(os.environ, env), patch(
            "automedia.adapters.platforms.wechat_publisher._httpx.post"
        ) as mock_post:
            mock_post.side_effect = [
                mock_token_resp,
                mock_draft_resp,
                mock_publish_resp,
            ]
            try:
                result = publisher.publish(str(tmp_path), {"topic": "t"})
            finally:
                logger.removeHandler(handler)

        assert result["status"] == "ok"
        log_output = log_capture.getvalue()
        self._assert_no_credentials(
            log_output,
            self.APPID,
            self.SECRET,
            self.TOKEN,
            label="success log output",
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestMdToHtml:
    """_md_to_html and _inline_md conversion utilities."""

    def test_headings(self) -> None:
        from automedia.adapters.platforms.wechat_publisher import _md_to_html

        md = "# H1\n## H2\n### H3"
        html = _md_to_html(md)
        assert "<h1>H1</h1>" in html
        assert "<h2>H2</h2>" in html
        assert "<h3>H3</h3>" in html

    def test_bold_and_italic(self) -> None:
        from automedia.adapters.platforms.wechat_publisher import _md_to_html

        md = "**bold** and *italic*"
        html = _md_to_html(md)
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    def test_inline_code(self) -> None:
        from automedia.adapters.platforms.wechat_publisher import _md_to_html

        md = "Use `code` here"
        html = _md_to_html(md)
        assert "<code>code</code>" in html

    def test_links_and_images(self) -> None:
        from automedia.adapters.platforms.wechat_publisher import _md_to_html

        md = "[link](https://example.com) and ![img](https://example.com/pic.png)"
        html = _md_to_html(md)
        assert '<a href="https://example.com">link</a>' in html
        assert '<img src="https://example.com/pic.png"' in html

    def test_unordered_list(self) -> None:
        from automedia.adapters.platforms.wechat_publisher import _md_to_html

        md = "- item 1\n- item 2\n- item 3"
        html = _md_to_html(md)
        assert "<ul>" in html
        assert "<li>item 1</li>" in html
        assert "<li>item 2</li>" in html
        assert "<li>item 3</li>" in html
        assert "</ul>" in html

    def test_html_escaping(self) -> None:
        from automedia.adapters.platforms.wechat_publisher import _md_to_html

        md = "<script>alert('xss')</script>"
        html = _md_to_html(md)
        assert "&lt;" in html
        assert "<script>" not in html
