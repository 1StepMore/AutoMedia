"""Tests for ``automedia account`` CLI commands."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from automedia.cli.app import app

runner = CliRunner()


# =========================================================================
# 1. automedia account list
# =========================================================================


class TestAccountList:
    """Tests for ``automedia account list``."""

    MOCK_ACCOUNTS: ClassVar[list[dict[str, Any]]] = [
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

        result = runner.invoke(app, ["account", "disconnect", "acc_wechat_a1b2c3d4", "--yes"])
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


# =========================================================================
# login-capture: interactive browser login → encrypted cookie store (#353)
# =========================================================================


class TestLoginCaptureHelpers:
    """Pure helpers behind ``automedia account login-capture``."""

    def test_login_targets_cover_xiaohongshu(self) -> None:
        from automedia.cli.commands.account import _LOGIN_TARGETS

        assert _LOGIN_TARGETS["xiaohongshu"]["session_cookie"] == "web_session"
        assert _LOGIN_TARGETS["xiaohongshu"]["url"].startswith("https://")

    def test_cookie_string_serialization(self) -> None:
        from automedia.cli.commands.account import _cookie_string

        cookies = [
            {"name": "a", "value": "1", "domain": ".x.com"},
            {"name": "b", "value": "2", "domain": ".x.com"},
            {"name": "", "value": "skip-me"},
        ]
        assert _cookie_string(cookies) == "a=1; b=2"

    def test_login_signal_detects_session_cookie(self) -> None:
        from automedia.cli.commands.account import _login_signal

        hit = [{"name": "web_session", "value": "04009..."}]
        assert _login_signal("xiaohongshu", hit) is True
        assert _login_signal("xiaohongshu", [{"name": "other", "value": "x"}]) is False
        # empty session value does not count as logged in
        assert _login_signal("xiaohongshu", [{"name": "web_session", "value": ""}]) is False
        # unknown platform has no signal — relies on the Enter fallback
        assert _login_signal("unknown-platform", hit) is False

    def test_login_confirmed_needs_cookie_and_modal_gone(self) -> None:
        """XHS hands web_session to anonymous visitors too — the login modal
        must be gone before we treat the capture as a real login (#353)."""
        from automedia.cli.commands.account import _login_confirmed

        hit = [{"name": "web_session", "value": "04009..."}]

        class _Page:
            def __init__(self, modal_present: bool) -> None:
                self._modal_present = modal_present

            def evaluate(self, _script: str) -> bool:
                return not self._modal_present

        # cookie present + modal gone → confirmed
        assert _login_confirmed("xiaohongshu", _Page(modal_present=False), hit) is True
        # cookie present but login modal still on screen → NOT confirmed
        # (this is exactly the anonymous-visitor web_session trap)
        assert _login_confirmed("xiaohongshu", _Page(modal_present=True), hit) is False
        # cookie absent → never confirmed
        assert _login_confirmed("xiaohongshu", _Page(modal_present=False), []) is False

        # page evaluation blowing up degrades to the cookie-only signal
        class _BrokenPage:
            def evaluate(self, _script: str) -> bool:
                raise RuntimeError("page navigated away")

        assert _login_confirmed("xiaohongshu", _BrokenPage(), hit) is True


class TestLoginCaptureCommand:
    def test_captured_storage_state_registered_encrypted(self) -> None:
        import automedia.cli.commands.account as account_mod

        fake_cookies = [
            {"name": "web_session", "value": "04009abc", "domain": ".xiaohongshu.com"},
            {"name": "a1", "value": "5", "domain": ".xiaohongshu.com"},
        ]
        fake_state = {
            "cookies": fake_cookies,
            "origins": [{"origin": "https://www.xiaohongshu.com", "localStorage": []}],
        }
        registry = MagicMock()
        registry.register.return_value = {"account_id": "acc_xhs_test", "platform": "xiaohongshu"}
        # everything mocked — this test must never open a real browser or
        # touch the real account store
        with (
            patch.object(account_mod, "_capture_browser_cookies", return_value=fake_state) as cap,
            patch.object(account_mod, "_get_registry", return_value=registry),
        ):
            result = runner.invoke(
                app,
                ["account", "login-capture", "xiaohongshu", "--label", "test-capture"],
            )

        assert result.exit_code == 0, result.output
        cap.assert_called_once()
        registry.register.assert_called_once()
        args, kwargs = registry.register.call_args
        assert args[0] == "xiaohongshu"
        assert kwargs["auth_type"] == "cookie"
        assert kwargs["label"] == "test-capture"
        creds = args[1]
        assert creds["storage_state"] == fake_state
        assert creds["cookies"] == fake_cookies
        assert creds["cookie_string"] == "web_session=04009abc; a1=5"
        assert "user_agent" in creds and "captured_at" in creds
        # cookie values must never appear in the output
        assert "04009abc" not in result.output

    def test_unknown_platform_without_url_refused(self) -> None:
        result = runner.invoke(app, ["account", "login-capture", "no-such-platform", "--url", ""])
        assert result.exit_code == 1
        assert "No known login URL" in result.output

    def test_playwright_missing_prints_install_hint(self) -> None:
        import automedia.cli.commands.account as account_mod

        with patch.object(
            account_mod,
            "_capture_browser_cookies",
            side_effect=ImportError("No module named 'playwright'"),
        ):
            result = runner.invoke(app, ["account", "login-capture", "xiaohongshu"])
        assert result.exit_code == 1
        assert "playwright install chromium" in result.output


# =========================================================================
# account add / rotate / remove (#354)
# =========================================================================


class TestAccountAdd:
    def test_add_registers_with_cred_pairs(self) -> None:
        import automedia.cli.commands.account as account_mod

        registry = MagicMock()
        registry.register.return_value = {"account_id": "acc_zhihu_new", "platform": "zhihu"}
        with (
            patch.object(account_mod, "_get_registry", return_value=registry),
        ):
            result = runner.invoke(
                app,
                [
                    "account", "add", "zhihu",
                    "--cred", "token=abc123",
                    "--cred", "secret=xyz",
                    "--auth-type", "api_key",
                    "--label", "Main",
                ],
            )
        assert result.exit_code == 0, result.output
        args, kwargs = registry.register.call_args
        assert args[0] == "zhihu" and args[1] == {"token": "abc123", "secret": "xyz"}
        assert kwargs["auth_type"] == "api_key" and kwargs["label"] == "Main"
        # values must not be echoed — only keys
        assert "abc123" not in result.output

    def test_add_rejects_malformed_cred(self) -> None:
        result = runner.invoke(app, ["account", "add", "zhihu", "--cred", "novalue"])
        assert result.exit_code == 1
        assert "key=value" in result.output

    def test_add_rejects_both_cred_and_json(self, tmp_path: Path) -> None:
        json_file = tmp_path / "creds.json"
        json_file.write_text('{"token": "t"}', encoding="utf-8")
        result = runner.invoke(
            app,
            ["account", "add", "zhihu", "--cred", "a=b", "--from-json", str(json_file)],
        )
        assert result.exit_code == 1
        assert "not both" in result.output

    def test_add_from_json(self, tmp_path: Path) -> None:
        import automedia.cli.commands.account as account_mod

        json_file = tmp_path / "creds.json"
        json_file.write_text('{"cookie": "a=1; b=2"}', encoding="utf-8")
        registry = MagicMock()
        registry.register.return_value = {"account_id": "acc_x", "platform": "xiaohongshu"}
        with patch.object(account_mod, "_get_registry", return_value=registry):
            result = runner.invoke(
                app, ["account", "add", "xiaohongshu", "--from-json", str(json_file)]
            )
        assert result.exit_code == 0, result.output
        assert registry.register.call_args[0][1] == {"cookie": "a=1; b=2"}


class TestAccountRotate:
    def test_rotate_replaces_credentials_keeps_identity(self) -> None:
        import automedia.cli.commands.account as account_mod

        registry = MagicMock()
        registry.rotate_credentials.return_value = {"fingerprint": "cafe1234567890abcd"}
        with patch.object(account_mod, "_get_registry", return_value=registry):
            result = runner.invoke(
                app,
                ["account", "rotate", "acc_xiaohongshu_1", "--cred", "web_session=newsession"],
            )
        assert result.exit_code == 0, result.output
        registry.rotate_credentials.assert_called_once_with(
            "acc_xiaohongshu_1", {"web_session": "newsession"}
        )
        # the new credential value is never echoed
        assert "newsession" not in result.output
        # the (short) fingerprint prefix is shown for audit
        assert "cafe12345678" in result.output

    def test_rotate_unknown_account(self) -> None:
        import automedia.cli.commands.account as account_mod

        registry = MagicMock()
        registry.rotate_credentials.return_value = None
        with patch.object(account_mod, "_get_registry", return_value=registry):
            result = runner.invoke(app, ["account", "rotate", "acc_missing", "--cred", "a=b"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestAccountRemove:
    def test_remove_deletes_with_yes(self) -> None:
        import automedia.cli.commands.account as account_mod

        registry = MagicMock()
        registry.get.return_value = {"platform": "zhihu", "label": "L"}
        with patch.object(account_mod, "_get_registry", return_value=registry):
            result = runner.invoke(app, ["account", "remove", "acc_z", "--yes"])
        assert result.exit_code == 0, result.output
        registry.delete.assert_called_once_with("acc_z")

    def test_remove_unknown_account(self) -> None:
        import automedia.cli.commands.account as account_mod

        registry = MagicMock()
        registry.get.return_value = None
        with patch.object(account_mod, "_get_registry", return_value=registry):
            result = runner.invoke(app, ["account", "remove", "acc_missing", "--yes"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestRotateRealStore:
    """End-to-end against a real (tmp) encrypted store — ciphertext only."""

    def test_rotate_reencrypts_never_plaintext(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import automedia.cli.commands.account as account_mod

        monkeypatch.setenv("AUTOMEDIA_MASTER_KEY", "test-master-key-rotate")
        # store.py binds get_user_config_dir at import — patch its namespace too
        monkeypatch.setattr("automedia.core.paths.get_user_config_dir", lambda: tmp_path)
        monkeypatch.setattr("automedia.accounts.store.get_user_config_dir", lambda: tmp_path)
        monkeypatch.setattr(account_mod, "_registry", None)  # reset the lazy singleton

        result = runner.invoke(
            app,
            ["account", "add", "zhihu", "--cred", "token=old-secret-value"],
        )
        assert result.exit_code == 0, result.output
        listing = runner.invoke(app, ["account", "list"]).output
        assert "acc_zhihu_" in listing

        # find the account id and rotate
        import yaml as _yaml

        idx = _yaml.safe_load((tmp_path / "accounts" / "accounts.index.json").read_text(encoding="utf-8"))
        account_id = next(iter(idx["accounts"]))
        enc_file = tmp_path / "accounts" / "zhihu" / f"{account_id}.json.enc"
        assert enc_file.is_file()
        blob = enc_file.read_text(encoding="utf-8")
        assert "old-secret-value" not in blob  # ciphertext at rest

        result = runner.invoke(
            app, ["account", "rotate", account_id, "--cred", "token=new-secret-value"]
        )
        assert result.exit_code == 0, result.output
        blob2 = enc_file.read_text(encoding="utf-8")
        assert "new-secret-value" not in blob2

        # the registry decrypts back the rotated payload
        from automedia.accounts.registry import AccountRegistry

        creds = AccountRegistry().get_credentials(account_id)
        assert creds == {"token": "new-secret-value"}
