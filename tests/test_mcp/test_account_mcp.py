"""Tests for MCP account management tools.

Covers all 4 tools: connect_account, list_accounts, get_account_health,
disconnect_account.  Uses mocked AccountRegistry to avoid file-system
and env-var dependencies.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

# Set env var before importing module under test — AccountRegistry
# requires AUTOMEDIA_MASTER_KEY at import time (lazy init, but safe).
os.environ["AUTOMEDIA_MASTER_KEY"] = "test-key"

from automedia.mcp.accounts import (
    connect_account,
    disconnect_account,
    get_account_health,
    list_accounts,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

MOCK_ACCOUNT: dict[str, Any] = {
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

MOCK_ACCOUNTS: list[dict[str, Any]] = [
    MOCK_ACCOUNT,
    {
        "account_id": "acc_zhihu_e5f6g7h8",
        "platform": "zhihu",
        "label": "Zhihu Author",
        "auth_type": "cookie",
        "status": "active",
        "created_at": "2026-07-02T00:00:00",
        "last_used": "2026-07-11T08:00:00",
        "last_health_check": None,
        "fingerprint": "def456",
        "tags": {},
    },
]


# ---------------------------------------------------------------------------
# Tests: connect_account
# ---------------------------------------------------------------------------


class TestConnectAccount:
    """Tests for connect_account MCP tool."""

    @patch("automedia.mcp.accounts._get_registry")
    def test_connect_with_valid_credentials(self, mock_get_registry: MagicMock) -> None:
        """connect_account with valid credentials returns success with account metadata."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.register.return_value = MOCK_ACCOUNT

        result = connect_account(
            platform="wechat",
            credentials={"appid": "wx123", "secret": "s3cret"},
            label="My WeChat",
        )

        assert result["success"] is True
        assert result["account"]["account_id"] == "acc_wechat_a1b2c3d4"
        assert result["account"]["platform"] == "wechat"
        mock_registry.register.assert_called_once_with(
            platform="wechat",
            credentials={"appid": "wx123", "secret": "s3cret"},
            label="My WeChat",
            auth_type="api_key",
        )

    @patch("automedia.mcp.accounts._get_registry")
    def test_connect_with_empty_credentials(self, mock_get_registry: MagicMock) -> None:
        """connect_account with empty credentials returns error."""
        result = connect_account(platform="wechat", credentials=None)

        assert "error" in result
        assert "credentials must be provided" in result["error"]["message"]
        mock_get_registry.assert_not_called()

    @patch("automedia.mcp.accounts._get_registry")
    def test_connect_duplicate_label(self, mock_get_registry: MagicMock) -> None:
        """connect_account returns error when registry raises ValueError (e.g. duplicate label)."""
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
        assert "Label 'My WeChat' already exists" in result["error"]["message"]


# ---------------------------------------------------------------------------
# Tests: list_accounts
# ---------------------------------------------------------------------------


class TestListAccounts:
    """Tests for list_accounts MCP tool."""

    @patch("automedia.mcp.accounts._get_registry")
    def test_list_all(self, mock_get_registry: MagicMock) -> None:
        """list_accounts with no filters returns all accounts."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.list.return_value = MOCK_ACCOUNTS

        result = list_accounts()

        assert result["count"] == 2
        assert len(result["accounts"]) == 2
        assert result["accounts"][0]["platform"] == "wechat"
        assert result["accounts"][1]["platform"] == "zhihu"

    @patch("automedia.mcp.accounts._get_registry")
    def test_list_empty(self, mock_get_registry: MagicMock) -> None:
        """list_accounts returns empty list when no accounts exist."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.list.return_value = []

        result = list_accounts()

        assert result["count"] == 0
        assert result["accounts"] == []

    @patch("automedia.mcp.accounts._get_registry")
    def test_list_with_platform_filter(self, mock_get_registry: MagicMock) -> None:
        """list_accounts with platform filter returns only matching accounts."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        wechat_accounts = [a for a in MOCK_ACCOUNTS if a["platform"] == "wechat"]
        mock_registry.list.return_value = wechat_accounts

        result = list_accounts(platform="wechat")

        assert result["count"] == 1
        assert result["accounts"][0]["platform"] == "wechat"
        mock_registry.list.assert_called_once_with(platform="wechat", status=None)


# ---------------------------------------------------------------------------
# Tests: get_account_health
# ---------------------------------------------------------------------------


class TestGetAccountHealth:
    """Tests for get_account_health MCP tool."""

    @patch("automedia.mcp.accounts._get_registry")
    def test_health_valid_account(self, mock_get_registry: MagicMock) -> None:
        """get_account_health returns health info for a known account."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.get.return_value = MOCK_ACCOUNT

        result = get_account_health("acc_wechat_a1b2c3d4")

        assert result["account_id"] == "acc_wechat_a1b2c3d4"
        assert result["platform"] == "wechat"
        assert result["status"] == "active"
        assert result["last_health_check"] == "2026-07-10T12:00:00"

    @patch("automedia.mcp.accounts._get_registry")
    def test_health_nonexistent_account(self, mock_get_registry: MagicMock) -> None:
        """get_account_health returns error for unknown account."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.get.return_value = None

        result = get_account_health("nonexistent")

        assert "error" in result
        assert "Account not found" in result["error"]["message"]


# ---------------------------------------------------------------------------
# Tests: disconnect_account
# ---------------------------------------------------------------------------


class TestDisconnectAccount:
    """Tests for disconnect_account MCP tool."""

    @patch("automedia.mcp.accounts._get_registry")
    def test_disconnect_valid_account(self, mock_get_registry: MagicMock) -> None:
        """disconnect_account removes a known account and returns success."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.get.return_value = MOCK_ACCOUNT
        mock_registry.delete.return_value = True

        result = disconnect_account("acc_wechat_a1b2c3d4")

        assert result["success"] is True
        assert result["account_id"] == "acc_wechat_a1b2c3d4"
        assert result["platform"] == "wechat"
        mock_registry.delete.assert_called_once_with("acc_wechat_a1b2c3d4")

    @patch("automedia.mcp.accounts._get_registry")
    def test_disconnect_nonexistent_account(self, mock_get_registry: MagicMock) -> None:
        """disconnect_account returns error for unknown account."""
        mock_registry = MagicMock()
        mock_get_registry.return_value = mock_registry
        mock_registry.get.return_value = None

        result = disconnect_account("nonexistent")

        assert "error" in result
        assert "Account not found" in result["error"]["message"]
        mock_registry.delete.assert_not_called()
