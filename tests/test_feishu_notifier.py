"""Tests for FeishuNotifier adapter — webhook POST with interactive card."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.adapters.platforms.feishu_notifier import FeishuNotifier

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def notifier() -> FeishuNotifier:
    return FeishuNotifier()


@pytest.fixture()
def sample_project() -> dict[str, Any]:
    return {
        "topic": "AI Video Tools",
        "brand": "my-brand",
        "status": "published",
    }


# ---------------------------------------------------------------------------
# enabled / validate – env var detection
# ---------------------------------------------------------------------------


class TestEnabledAndValidate:
    """enabled property and validate() both check FEISHU_WEBHOOK_URL."""

    def test_enabled_false_when_no_env(self, notifier: FeishuNotifier) -> None:
        assert "FEISHU_WEBHOOK_URL" not in os.environ
        assert notifier.enabled is False

    def test_enabled_true_when_env_set(self, notifier: FeishuNotifier) -> None:
        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": "https://example.com/hook"}):
            assert notifier.enabled is True

    def test_validate_false_when_no_env(self, notifier: FeishuNotifier, tmp_path: Path) -> None:
        assert "FEISHU_WEBHOOK_URL" not in os.environ
        assert notifier.validate(str(tmp_path)) is False

    def test_validate_true_when_env_set(self, notifier: FeishuNotifier, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": "https://example.com/hook"}):
            assert notifier.validate(str(tmp_path)) is True


# ---------------------------------------------------------------------------
# publish – success path
# ---------------------------------------------------------------------------


class TestPublishSuccess:
    """publish() POSTs a card and returns message_id."""

    def test_publish_sends_card(
        self,
        notifier: FeishuNotifier,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 0,
            "data": {"message_id": "om_abc123"},
        }

        env = {"FEISHU_WEBHOOK_URL": "https://example.com/hook"}
        with (
            patch.dict(os.environ, env),
            patch(
                "automedia.adapters.platforms.feishu_notifier._httpx_module.post",
                return_value=mock_response,
            ) as mock_post,
        ):
            result = notifier.publish(str(tmp_path), sample_project)

        assert result["status"] == "ok"
        assert result["platform"] == "feishu"
        assert result["message_id"] == "om_abc123"

        mock_post.assert_called_once()
        call_args, call_kwargs = mock_post.call_args
        assert call_args[0] == "https://example.com/hook"
        payload = call_kwargs["json"]
        assert payload["msg_type"] == "interactive"
        assert payload["card"]["header"]["title"]["content"] == "AutoMedia Publish Notification"
        elements = payload["card"]["elements"]
        assert len(elements) == 1
        assert elements[0]["tag"] == "div"
        assert "AI Video Tools" in elements[0]["text"]["content"]
        assert "my-brand" in elements[0]["text"]["content"]
        assert "published" in elements[0]["text"]["content"]


# ---------------------------------------------------------------------------
# publish – error paths
# ---------------------------------------------------------------------------


class TestPublishErrors:
    """publish() error handling for various failure modes."""

    def test_missing_webhook_url(
        self,
        notifier: FeishuNotifier,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        assert "FEISHU_WEBHOOK_URL" not in os.environ
        result = notifier.publish(str(tmp_path), sample_project)
        assert result["status"] == "error"
        assert result["platform"] == "feishu"
        assert "FEISHU_WEBHOOK_URL is not set" in result["reason"]

    def test_httpx_not_available(
        self,
        notifier: FeishuNotifier,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        env = {"FEISHU_WEBHOOK_URL": "https://example.com/hook"}
        with (
            patch.dict(os.environ, env),
            patch("automedia.adapters.platforms.feishu_notifier._has_httpx", False),
        ):
            result = notifier.publish(str(tmp_path), sample_project)

        assert result["status"] == "error"
        assert result["platform"] == "feishu"
        assert "httpx is not available" in result["reason"]

    def test_http_error_response(
        self,
        notifier: FeishuNotifier,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 403 Forbidden")

        env = {"FEISHU_WEBHOOK_URL": "https://example.com/hook"}
        with (
            patch.dict(os.environ, env),
            patch(
                "automedia.adapters.platforms.feishu_notifier._httpx_module.post",
                return_value=mock_response,
            ),
        ):
            result = notifier.publish(str(tmp_path), sample_project)

        assert result["status"] == "error"
        assert result["platform"] == "feishu"
        assert "HTTP 403 Forbidden" in result["reason"]

    def test_timeout(
        self,
        notifier: FeishuNotifier,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        env = {"FEISHU_WEBHOOK_URL": "https://example.com/hook"}
        with (
            patch.dict(os.environ, env),
            patch("automedia.adapters.platforms.feishu_notifier._httpx_module.post") as mock_post,
        ):
            mock_post.side_effect = Exception("timeout after 30s")
            result = notifier.publish(str(tmp_path), sample_project)

        assert result["status"] == "error"
        assert result["platform"] == "feishu"
        assert "timeout after 30s" in result["reason"]


# ---------------------------------------------------------------------------
# publish – edge cases
# ---------------------------------------------------------------------------


class TestPublishEdgeCases:
    """publish() handles missing/unknown project fields gracefully."""

    def test_empty_project_dict(self, notifier: FeishuNotifier, tmp_path: Path) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 0,
            "data": {"message_id": "om_xyz"},
        }

        env = {"FEISHU_WEBHOOK_URL": "https://example.com/hook"}
        with (
            patch.dict(os.environ, env),
            patch(
                "automedia.adapters.platforms.feishu_notifier._httpx_module.post",
                return_value=mock_response,
            ) as mock_post,
        ):
            result = notifier.publish(str(tmp_path), {})

        assert result["status"] == "ok"
        payload = mock_post.call_args[1]["json"]
        assert "unknown" in payload["card"]["elements"][0]["text"]["content"]

    def test_platform_name(self, notifier: FeishuNotifier) -> None:
        assert notifier.platform_name == "feishu"


class TestCredentialLoaderIntegration:
    """Verify adapter uses ``load_credential_or_env`` with ``AUTOMEDIA_*`` vars."""

    def test_enabled_with_automedia_env_var(self, notifier: FeishuNotifier) -> None:
        with patch.dict(
            os.environ,
            {"AUTOMEDIA_FEISHU_WEBHOOK_URL": "https://example.com/hook"},
            clear=True,
        ):
            assert notifier.enabled is True

    def test_enabled_legacy_takes_precedence(self, notifier: FeishuNotifier) -> None:
        with patch.dict(
            os.environ,
            {
                "FEISHU_WEBHOOK_URL": "https://legacy.example.com/hook",
                "AUTOMEDIA_FEISHU_WEBHOOK_URL": "https://new.example.com/hook",
            },
            clear=True,
        ):
            assert notifier.enabled is True

    def test_validate_with_automedia_env_only(
        self, notifier: FeishuNotifier, tmp_path: Path
    ) -> None:
        with patch.dict(
            os.environ,
            {"AUTOMEDIA_FEISHU_WEBHOOK_URL": "https://example.com/hook"},
            clear=True,
        ):
            assert notifier.validate(str(tmp_path)) is True

    def test_publish_with_automedia_env(
        self,
        notifier: FeishuNotifier,
        sample_project: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 0,
            "data": {"message_id": "om_abc123"},
        }

        with (
            patch.dict(
                os.environ,
                {"AUTOMEDIA_FEISHU_WEBHOOK_URL": "https://example.com/hook"},
                clear=True,
            ),
            patch(
                "automedia.adapters.platforms.feishu_notifier._httpx_module.post",
                return_value=mock_response,
            ) as mock_post,
        ):
            result = notifier.publish(str(tmp_path), sample_project)

        assert result["status"] == "ok"
        assert result["platform"] == "feishu"
        assert result["message_id"] == "om_abc123"
        mock_post.assert_called_once_with(
            "https://example.com/hook", json=mock_post.call_args[1]["json"], timeout=30.0
        )
