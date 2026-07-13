"""Tests for MCP account management tools.

Covers all 4 tools exposed by ``automedia.mcp.accounts``:
connect_account, list_accounts, get_account_health, disconnect_account.

Uses ``AccountRegistry`` via mock (``_get_registry``) to avoid file-system
and encryption-key dependencies.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

# Set env var before importing module under test — AccountRegistry
# reads AUTOMEDIA_MASTER_KEY at import time.
os.environ["AUTOMEDIA_MASTER_KEY"] = "test-key-for-accounts-tests"

from automedia.mcp.accounts import (
    connect_account,
    disconnect_account,
    get_account_health,
    list_accounts,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

HEALTHY_ACCOUNT: dict[str, Any] = {
    "account_id": "acc_wechat_a1b2c3d4",
    "platform": "wechat",
    "label": "My WeChat",
    "auth_type": "api_key",
    "status": "active",
    "created_at": "2026-07-01T00:00:00",
    "last_used": "2026-07-10T12:00:00",
    "last_health_check": "2026-07-10T12:00:00",
    "fingerprint": "abc123",
    "tags": {},
}

UNREACHABLE_ACCOUNT: dict[str, Any] = {
    "account_id": "acc_zhihu_e5f6g7h8",
    "platform": "zhihu",
    "label": "Zhihu Author",
    "auth_type": "cookie",
    "status": "inactive",
    "created_at": "2026-07-02T00:00:00",
    "last_used": "2026-07-11T08:00:00",
    "last_health_check": None,
    "fingerprint": "def456",
    "tags": {},
}

MOCK_ACCOUNTS: list[dict[str, Any]] = [HEALTHY_ACCOUNT, UNREACHABLE_ACCOUNT]


# ===================================================================
# Tests: connect_account
# ===================================================================


class TestConnectAccount:
    """Tests for the ``connect_account`` MCP tool."""

    @patch("automedia.mcp.accounts._get_registry")
    def test_valid_credentials(self, mock_get_registry: MagicMock) -> None:
        """connect_account with valid credentials returns success + account metadata."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.register.return_value = HEALTHY_ACCOUNT

        result = connect_account(
            platform="wechat",
            credentials={"appid": "wx123", "secret": "s3cret"},
            label="My WeChat",
        )

        assert result["success"] is True
        assert result["account"]["account_id"] == "acc_wechat_a1b2c3d4"
        assert result["account"]["platform"] == "wechat"
        assert result["account"]["status"] == "active"
        mock_registry.register.assert_called_once_with(
            platform="wechat",
            credentials={"appid": "wx123", "secret": "s3cret"},
            label="My WeChat",
            auth_type="api_key",
        )

    @patch("automedia.mcp.accounts._get_registry")
    def test_duplicate_label(self, mock_get_registry: MagicMock) -> None:
        """connect_account returns error when registry rejects duplicate label."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.register.side_effect = ValueError(
            "Label 'My WeChat' already exists for platform 'wechat'"
        )

        result = connect_account(
            platform="wechat",
            credentials={"appid": "wx123"},
            label="My WeChat",
        )

        assert "error" in result
        assert "Label 'My WeChat' already exists" in result["error"]

    @patch("automedia.mcp.accounts._get_registry")
    def test_invalid_auth_type(self, mock_get_registry: MagicMock) -> None:
        """connect_account returns error when registry raises ValueError for invalid auth type."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.register.side_effect = ValueError(
            "Invalid auth_type: 'unsupported_auth'. Must be one of: "
            "api_key, cookie, oauth2_client_cred, oauth2_auth_code, "
            "webhook_url, qr_code"
        )

        result = connect_account(
            platform="wechat",
            credentials={"appid": "wx123"},
            label="Bad Auth",
            auth_type="unsupported_auth",
        )

        assert "error" in result
        assert "Invalid auth_type" in result["error"]


# ===================================================================
# Tests: list_accounts
# ===================================================================


class TestListAccounts:
    """Tests for the ``list_accounts`` MCP tool."""

    @patch("automedia.mcp.accounts._get_registry")
    def test_no_filter(self, mock_get_registry: MagicMock) -> None:
        """list_accounts with no filters returns all accounts."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.list.return_value = MOCK_ACCOUNTS

        result = list_accounts()

        assert result["count"] == 2
        assert len(result["accounts"]) == 2
        assert result["accounts"][0]["platform"] == "wechat"
        assert result["accounts"][1]["platform"] == "zhihu"
        mock_registry.list.assert_called_once_with(platform=None, status=None)

    @patch("automedia.mcp.accounts._get_registry")
    def test_platform_filter(self, mock_get_registry: MagicMock) -> None:
        """list_accounts with platform filter returns only matching accounts."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        wechat_accounts = [a for a in MOCK_ACCOUNTS if a["platform"] == "wechat"]
        mock_registry.list.return_value = wechat_accounts

        result = list_accounts(platform="wechat")

        assert result["count"] == 1
        assert len(result["accounts"]) == 1
        assert result["accounts"][0]["platform"] == "wechat"
        mock_registry.list.assert_called_once_with(platform="wechat", status=None)

    @patch("automedia.mcp.accounts._get_registry")
    def test_status_filter(self, mock_get_registry: MagicMock) -> None:
        """list_accounts with status filter returns only accounts with that status."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        inactive_accounts = [a for a in MOCK_ACCOUNTS if a["status"] == "inactive"]
        mock_registry.list.return_value = inactive_accounts

        result = list_accounts(status="inactive")

        assert result["count"] == 1
        assert len(result["accounts"]) == 1
        assert result["accounts"][0]["status"] == "inactive"
        assert result["accounts"][0]["platform"] == "zhihu"
        mock_registry.list.assert_called_once_with(platform=None, status="inactive")


# ===================================================================
# Tests: get_account_health
# ===================================================================


class TestGetAccountHealth:
    """Tests for the ``get_account_health`` MCP tool."""

    @patch("automedia.mcp.accounts._get_registry")
    def test_healthy_account(self, mock_get_registry: MagicMock) -> None:
        """get_account_health returns health info for a known, active account."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.get.return_value = HEALTHY_ACCOUNT

        result = get_account_health("acc_wechat_a1b2c3d4")

        assert result["account_id"] == "acc_wechat_a1b2c3d4"
        assert result["platform"] == "wechat"
        assert result["status"] == "active"
        assert result["last_health_check"] == "2026-07-10T12:00:00"
        assert result["label"] == "My WeChat"

    @patch("automedia.mcp.accounts._get_registry")
    def test_unreachable_account(self, mock_get_registry: MagicMock) -> None:
        """get_account_health returns info including inactive status for unreachable account."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.get.return_value = UNREACHABLE_ACCOUNT

        result = get_account_health("acc_zhihu_e5f6g7h8")

        assert result["account_id"] == "acc_zhihu_e5f6g7h8"
        assert result["platform"] == "zhihu"
        assert result["status"] == "inactive"
        # The account exists but is unreachable — status reflects that
        assert "error" not in result

    @patch("automedia.mcp.accounts._get_registry")
    def test_nonexistent_account(self, mock_get_registry: MagicMock) -> None:
        """get_account_health returns error for unknown account ID."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.get.return_value = None

        result = get_account_health("nonexistent")

        assert "error" in result
        assert "Account not found" in result["error"]


# ===================================================================
# Tests: disconnect_account
# ===================================================================


class TestDisconnectAccount:
    """Tests for the ``disconnect_account`` MCP tool."""

    @patch("automedia.mcp.accounts._get_registry")
    def test_existing_account(self, mock_get_registry: MagicMock) -> None:
        """disconnect_account removes a known account and returns success."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.get.return_value = HEALTHY_ACCOUNT
        mock_registry.delete.return_value = True

        result = disconnect_account("acc_wechat_a1b2c3d4")

        assert result["success"] is True
        assert result["account_id"] == "acc_wechat_a1b2c3d4"
        assert result["platform"] == "wechat"
        mock_registry.delete.assert_called_once_with("acc_wechat_a1b2c3d4")

    @patch("automedia.mcp.accounts._get_registry")
    def test_nonexistent_account(self, mock_get_registry: MagicMock) -> None:
        """disconnect_account returns error for unknown account ID."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.get.return_value = None

        result = disconnect_account("nonexistent")

        assert "error" in result
        assert "Account not found" in result["error"]
        mock_registry.delete.assert_not_called()
