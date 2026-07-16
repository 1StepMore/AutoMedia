"""Tests for ``automedia account`` CLI commands."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from automedia.cli.app import app

runner = CliRunner()


# =========================================================================
# 1. automedia account list
# =========================================================================


class TestAccountList:
    """Tests for ``automedia account list``."""

    MOCK_ACCOUNTS: list[dict[str, Any]] = [
        {
            "account_id": "acc_wechat_a1b2c3d4",
            "platform": "wechat",
            "label": "My WeChat",
            "auth_type": "api_key",
            "status": "active",
            "last_used": "2026-07-10T12:00:00",
            "created_at": "2026-07-01T00:00:00",
            "fingerprint": "abc123",
            "tags": {},
            "last_health_check": None,
        },
        {
            "account_id": "acc_zhihu_e5f6g7h8",
            "platform": "zhihu",
            "label": "Zhihu Author",
            "auth_type": "cookie",
            "status": "active",
            "last_used": "2026-07-11T08:00:00",
            "created_at": "2026-07-02T00:00:00",
            "fingerprint": "def456",
            "tags": {},
            "last_health_check": None,
        },
        {
            "account_id": "acc_wechat_i9j0k1l2",
            "platform": "wechat",
            "label": "WeChat Backup",
            "auth_type": "api_key",
            "status": "inactive",
            "last_used": None,
            "created_at": "2026-07-03T00:00:00",
            "fingerprint": "ghi789",
            "tags": {},
            "last_health_check": None,
        },
    ]

    @patch("automedia.cli.commands.account._get_registry")
    def test_list_returns_table_output(self, mock_get_registry: MagicMock) -> None:
        """List returns a Rich table with account details."""
        mock_registry = mock_get_registry.return_value
        mock_registry.list.return_value = self.MOCK_ACCOUNTS

        result = runner.invoke(app, ["account", "list"])
        assert result.exit_code == 0
        assert "Platform Accounts" in result.output
        assert "acc_wechat_a1b2c3d4" in result.output
        assert "My WeChat" in result.output
        assert "Zhihu Author" in result.output
        assert mock_registry.list.called

    @patch("automedia.cli.commands.account._get_registry")
    def test_list_empty(self, mock_get_registry: MagicMock) -> None:
        """List with no accounts shows 'No accounts found'."""
        mock_registry = mock_get_registry.return_value
        mock_registry.list.return_value = []

        result = runner.invoke(app, ["account", "list"])
        assert result.exit_code == 0
        assert "No accounts found" in result.output

    @patch("automedia.cli.commands.account._get_registry")
    def test_list_filters_by_platform(self, mock_get_registry: MagicMock) -> None:
        """List with --platform wechat returns only wechat accounts."""
        mock_registry = mock_get_registry.return_value
        mock_registry.list.return_value = [
            a for a in self.MOCK_ACCOUNTS if a["platform"] == "wechat"
        ]

        result = runner.invoke(app, ["account", "list", "--platform", "wechat"])
        assert result.exit_code == 0
        assert "acc_wechat_a1b2c3d4" in result.output
        assert "acc_zhihu_e5f6g7h8" not in result.output
        mock_registry.list.assert_called_once_with(platform="wechat", status=None)

    @patch("automedia.cli.commands.account._get_registry")
    def test_list_filters_by_status(self, mock_get_registry: MagicMock) -> None:
        """List with --status inactive returns only inactive accounts."""
        mock_registry = mock_get_registry.return_value
        mock_registry.list.return_value = [
            a for a in self.MOCK_ACCOUNTS if a["status"] == "inactive"
        ]

        result = runner.invoke(app, ["account", "list", "--status", "inactive"])
        assert result.exit_code == 0
        assert "WeChat Backup" in result.output
        assert "My WeChat" not in result.output
        mock_registry.list.assert_called_once_with(platform=None, status="inactive")


# =========================================================================
# 2. automedia account health
# =========================================================================


class TestAccountHealth:
    """Tests for ``automedia account health``."""

    @patch("automedia.cli.commands.account._get_registry")
    def test_health_active(self, mock_get_registry: MagicMock) -> None:
        """Health for an active account shows active status."""
        mock_registry = mock_get_registry.return_value
        mock_registry.get.return_value = {
            "account_id": "acc_wechat_a1b2c3d4",
            "platform": "wechat",
            "label": "My WeChat",
            "status": "active",
            "last_health_check": "2026-07-10T12:00:00",
        }

        result = runner.invoke(app, ["account", "health", "acc_wechat_a1b2c3d4"])
        assert result.exit_code == 0
        assert "Account is active" in result.output
        assert "acc_wechat_a1b2c3d4" in result.output

    @patch("automedia.cli.commands.account._get_registry")
    def test_health_nonexistent_returns_error(self, mock_get_registry: MagicMock) -> None:
        """Health for a nonexistent account exits with error."""
        mock_registry = mock_get_registry.return_value
        mock_registry.get.return_value = None

        result = runner.invoke(app, ["account", "health", "nonexistent"])
        assert result.exit_code == 1
        assert "Account not found" in result.output

    @patch("automedia.cli.commands.account._get_registry")
    def test_health_inactive_shows_warning(self, mock_get_registry: MagicMock) -> None:
        """Health for an inactive account shows a warning."""
        mock_registry = mock_get_registry.return_value
        mock_registry.get.return_value = {
            "account_id": "acc_wechat_i9j0k1l2",
            "platform": "wechat",
            "label": "WeChat Backup",
            "status": "inactive",
            "last_health_check": None,
        }

        result = runner.invoke(app, ["account", "health", "acc_wechat_i9j0k1l2"])
        assert result.exit_code == 0
        assert "Account status: inactive" in result.output


# =========================================================================
# 3. automedia account connect
# =========================================================================


class TestAccountConnect:
    """Tests for ``automedia account connect``.

    The connect command prompts interactively for credentials. We provide
    input via CliRunner's ``input`` parameter.
    """

    @patch("automedia.cli.commands.account._get_registry")
    def test_connect_with_credentials(self, mock_get_registry: MagicMock) -> None:
        """Connect with valid credentials registers the account."""
        mock_registry = mock_get_registry.return_value
        mock_registry.register.return_value = {
            "account_id": "acc_wechat_a1b2c3d4",
            "platform": "wechat",
            "label": "My WeChat",
            "auth_type": "api_key",
        }

        result = runner.invoke(
            app,
            ["account", "connect", "wechat", "--label", "My WeChat"],
            input="appid=wx123\ntoken=abc123\n\n",
        )
        assert result.exit_code == 0
        assert "Account registered" in result.output
        assert "acc_wechat_a1b2c3d4" in result.output
        mock_registry.register.assert_called_once_with(
            "wechat", {"appid": "wx123", "token": "abc123"}, label="My WeChat", auth_type="api_key"
        )

    @patch("automedia.cli.commands.account._get_registry")
    def test_connect_empty_credentials_aborts(self, mock_get_registry: MagicMock) -> None:
        """Connect with empty credentials shows error and exits."""
        result = runner.invoke(app, ["account", "connect", "wechat"], input="\n")
        assert result.exit_code == 1
        assert "No credentials provided" in result.output
        mock_get_registry.return_value.register.assert_not_called()

    @patch("automedia.cli.commands.account._get_registry")
    def test_connect_value_error_handled(self, mock_get_registry: MagicMock) -> None:
        """Connect when registry raises ValueError shows the error."""
        mock_registry = mock_get_registry.return_value
        mock_registry.register.side_effect = ValueError("Duplicate label")

        result = runner.invoke(
            app,
            ["account", "connect", "wechat", "--label", "Duplicate"],
            input="key=val\n\n",
        )
        assert result.exit_code == 1
        assert "Duplicate label" in result.output


# =========================================================================
# 4. automedia account disconnect
# =========================================================================


class TestAccountDisconnect:
    """Tests for ``automedia account disconnect``."""

    @patch("automedia.cli.commands.account._get_registry")
    def test_disconnect_with_yes_flag(self, mock_get_registry: MagicMock) -> None:
        """Disconnect with --yes flag removes the account without prompting."""
        mock_registry = mock_get_registry.return_value
        mock_registry.get.return_value = {
            "account_id": "acc_wechat_a1b2c3d4",
            "platform": "wechat",
            "label": "My WeChat",
        }
        mock_registry.delete.return_value = True

        result = runner.invoke(
            app, ["account", "disconnect", "acc_wechat_a1b2c3d4", "--yes"]
        )
        assert result.exit_code == 0
        assert "Account disconnected" in result.output
        mock_registry.delete.assert_called_once_with("acc_wechat_a1b2c3d4")

    @patch("automedia.cli.commands.account._get_registry")
    def test_disconnect_nonexistent_returns_error(self, mock_get_registry: MagicMock) -> None:
        """Disconnect for a nonexistent account exits with error."""
        mock_registry = mock_get_registry.return_value
        mock_registry.get.return_value = None

        result = runner.invoke(app, ["account", "disconnect", "nonexistent", "--yes"])
        assert result.exit_code == 1
        assert "Account not found" in result.output
        mock_registry.delete.assert_not_called()


# =========================================================================
# 5. Integration: account appears in help
# =========================================================================


class TestAccountHelp:
    """Tests that the account command is properly registered."""

    def test_help_lists_account(self) -> None:
        """The account command group appears in help output."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "account" in result.output
        assert "Manage platform accounts" in result.output
