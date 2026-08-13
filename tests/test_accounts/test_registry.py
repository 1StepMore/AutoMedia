"""Tests for AccountRegistry — high-level CRUD and label uniqueness enforcement."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from automedia.accounts.registry import AccountRegistry
from automedia.accounts.store import AccountStore
from automedia.core.credential_loader import load_credential_with_account_fallback

# ---------------------------------------------------------------------------
# Sample credential payloads (synthetic — no real secrets)
# ---------------------------------------------------------------------------

WECHAT_CREDENTIALS = {"appid": "wx_test_appid_12345", "secret": "test_secret_value_abc123"}
ZHIHU_CREDENTIALS = {"cookie": "session=test_session_value; token=test_token_value"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry(account_store: AccountStore) -> AccountRegistry:
    """Create an AccountRegistry backed by the test AccountStore."""
    return AccountRegistry(store=account_store)


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


class TestRegister:
    """Account registration."""

    def test_register_and_list(self, registry: AccountRegistry) -> None:
        """Register two accounts, list all, verify both appear."""
        meta_a = registry.register("wechat", WECHAT_CREDENTIALS, label="WeChat A")
        meta_b = registry.register("zhihu", ZHIHU_CREDENTIALS, label="Zhihu B")

        accounts = registry.list()
        assert len(accounts) == 2
        ids = {a["account_id"] for a in accounts}
        assert ids == {meta_a["account_id"], meta_b["account_id"]}

    def test_register_with_label(self, registry: AccountRegistry) -> None:
        """Register with a label stores the label correctly."""
        meta = registry.register("wechat", WECHAT_CREDENTIALS, label="My WeChat")
        info = registry.get(meta["account_id"])
        assert info is not None
        assert info["label"] == "My WeChat"

    def test_register_empty_credentials_raises(self, registry: AccountRegistry) -> None:
        """Registering with an empty credentials dict raises ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            registry.register("wechat", {})

    def test_register_duplicate_label_raises(self, registry: AccountRegistry) -> None:
        """Registering with a duplicate label on the same platform raises."""
        registry.register("wechat", WECHAT_CREDENTIALS, label="My WeChat")
        with pytest.raises(ValueError, match="already exists"):
            registry.register("wechat", {"key": "other"}, label="My WeChat")

    def test_same_label_different_platform_allowed(self, registry: AccountRegistry) -> None:
        """Same label on different platforms is allowed."""
        registry.register("wechat", WECHAT_CREDENTIALS, label="Primary")
        meta = registry.register("zhihu", ZHIHU_CREDENTIALS, label="Primary")
        assert meta is not None


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


class TestGet:
    """Retrieving account metadata."""

    def test_get_by_id(self, registry: AccountRegistry) -> None:
        """Get returns metadata with correct fields."""
        meta = registry.register("wechat", WECHAT_CREDENTIALS, label="My WeChat")
        info = registry.get(meta["account_id"])

        assert info is not None
        assert info["account_id"] == meta["account_id"]
        assert info["platform"] == "wechat"
        assert info["label"] == "My WeChat"
        assert info["auth_type"] == "api_key"
        assert info["status"] == "active"
        assert "fingerprint" in info
        assert "created_at" in info

    def test_get_nonexistent(self, registry: AccountRegistry) -> None:
        """Get returns None for non-existent account."""
        assert registry.get("nonexistent") is None


# ---------------------------------------------------------------------------
# Get credentials
# ---------------------------------------------------------------------------


class TestGetCredentials:
    """Retrieving decrypted credentials."""

    def test_get_credentials(self, registry: AccountRegistry) -> None:
        """Get credentials returns decrypted payload."""
        meta = registry.register("wechat", WECHAT_CREDENTIALS, label="Test")
        creds = registry.get_credentials(meta["account_id"])
        assert creds == WECHAT_CREDENTIALS

    def test_get_credentials_nonexistent(self, registry: AccountRegistry) -> None:
        """Get credentials returns None for non-existent account."""
        assert registry.get_credentials("nonexistent") is None


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDelete:
    """Account deletion."""

    def test_delete_removes_from_list(self, registry: AccountRegistry) -> None:
        """After deletion, account no longer appears in list."""
        meta = registry.register("wechat", WECHAT_CREDENTIALS)
        assert len(registry.list()) == 1

        result = registry.delete(meta["account_id"])
        assert result is True
        assert len(registry.list()) == 0

    def test_delete_nonexistent(self, registry: AccountRegistry) -> None:
        """Deleting a non-existent account returns False."""
        assert registry.delete("nonexistent") is False

    def test_delete_preserves_others(self, registry: AccountRegistry) -> None:
        """Deleting one account does not affect others."""
        meta_a = registry.register("wechat", WECHAT_CREDENTIALS)
        meta_b = registry.register("zhihu", ZHIHU_CREDENTIALS)

        registry.delete(meta_a["account_id"])
        accounts = registry.list()
        assert len(accounts) == 1
        assert accounts[0]["account_id"] == meta_b["account_id"]


# ---------------------------------------------------------------------------
# List with filters
# ---------------------------------------------------------------------------


class TestList:
    """Listing accounts with filters."""

    def test_list_all(self, registry: AccountRegistry) -> None:
        """List with no filters returns all accounts."""
        registry.register("wechat", WECHAT_CREDENTIALS)
        registry.register("zhihu", ZHIHU_CREDENTIALS)
        assert len(registry.list()) == 2

    def test_list_by_platform(self, registry: AccountRegistry) -> None:
        """Filtering by platform returns only matching accounts."""
        registry.register("wechat", WECHAT_CREDENTIALS)
        registry.register("zhihu", ZHIHU_CREDENTIALS)

        wechat = registry.list(platform="wechat")
        assert len(wechat) == 1
        assert wechat[0]["platform"] == "wechat"

    def test_list_by_status(self, registry: AccountRegistry) -> None:
        """Filtering by status returns only accounts with that status."""
        meta = registry.register("wechat", WECHAT_CREDENTIALS)
        registry._store.update_status(meta["account_id"], "inactive")

        active = registry.list(status="active")
        assert len(active) == 0

        inactive = registry.list(status="inactive")
        assert len(inactive) == 1
        assert inactive[0]["account_id"] == meta["account_id"]

    def test_list_by_platform_and_status(self, registry: AccountRegistry) -> None:
        """Combined platform + status filtering works."""
        meta = registry.register("wechat", WECHAT_CREDENTIALS)
        registry.register("zhihu", ZHIHU_CREDENTIALS)
        registry._store.update_status(meta["account_id"], "inactive")

        result = registry.list(platform="wechat", status="inactive")
        assert len(result) == 1

    def test_empty_registry(self, registry: AccountRegistry) -> None:
        """List returns empty list for empty registry."""
        assert registry.list() == []
        assert registry.list(platform="wechat") == []
        assert registry.list(status="active") == []


# ---------------------------------------------------------------------------
# Get by label
# ---------------------------------------------------------------------------


class TestGetByLabel:
    """Finding accounts by platform + label combination."""

    def test_get_by_label_found(self, registry: AccountRegistry) -> None:
        """Get by label returns matching account."""
        meta = registry.register("wechat", WECHAT_CREDENTIALS, label="My WeChat")
        result = registry.get_by_label("wechat", "My WeChat")
        assert result is not None
        assert result["account_id"] == meta["account_id"]

    def test_get_by_label_not_found(self, registry: AccountRegistry) -> None:
        """Get by label returns None when no match."""
        registry.register("wechat", WECHAT_CREDENTIALS, label="My WeChat")
        assert registry.get_by_label("wechat", "Does Not Exist") is None

    def test_get_by_label_wrong_platform(self, registry: AccountRegistry) -> None:
        """Get by label returns None when label exists on different platform."""
        registry.register("wechat", WECHAT_CREDENTIALS, label="Primary")
        registry.register("zhihu", ZHIHU_CREDENTIALS, label="Primary")

        result = registry.get_by_label("wechat", "Primary")
        assert result is not None
        assert result["platform"] == "wechat"

    def test_get_by_label_case_sensitive(self, registry: AccountRegistry) -> None:
        """Get by label is case-sensitive."""
        registry.register("wechat", WECHAT_CREDENTIALS, label="My WeChat")
        assert registry.get_by_label("wechat", "my wechat") is None


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class TestUpdate:
    """Updating account metadata."""

    def test_update_label(self, registry: AccountRegistry) -> None:
        """Update changes the label."""
        meta = registry.register("wechat", WECHAT_CREDENTIALS, label="Old Label")
        result = registry.update(meta["account_id"], label="New Label")
        assert result is True

        info = registry.get(meta["account_id"])
        assert info is not None
        assert info["label"] == "New Label"

    def test_update_tags(self, registry: AccountRegistry) -> None:
        """Update changes tags."""
        meta = registry.register("wechat", WECHAT_CREDENTIALS, tags={"env": "prod"})
        result = registry.update(meta["account_id"], tags={"env": "staging", "region": "us"})
        assert result is True

        info = registry.get(meta["account_id"])
        assert info is not None
        assert info["tags"] == {"env": "staging", "region": "us"}

    def test_update_nonexistent(self, registry: AccountRegistry) -> None:
        """Updating a non-existent account returns False."""
        assert registry.update("nonexistent", label="New Label") is False

    def test_update_duplicate_label_raises(self, registry: AccountRegistry) -> None:
        """Updating to a label that already exists on the same platform raises."""
        registry.register("wechat", WECHAT_CREDENTIALS, label="Alpha")
        meta = registry.register("wechat", {"key": "beta"}, label="Beta")

        with pytest.raises(ValueError, match="already exists"):
            registry.update(meta["account_id"], label="Alpha")

    def test_update_same_label_allowed(self, registry: AccountRegistry) -> None:
        """Updating to the same label (no change) is allowed."""
        meta = registry.register("wechat", WECHAT_CREDENTIALS, label="My Label")
        result = registry.update(meta["account_id"], label="My Label")
        assert result is True

    def test_update_label_only(self, registry: AccountRegistry) -> None:
        """Updating only label leaves tags unchanged."""
        meta = registry.register("wechat", WECHAT_CREDENTIALS, label="Label", tags={"env": "prod"})
        registry.update(meta["account_id"], label="New Label")

        info = registry.get(meta["account_id"])
        assert info is not None
        assert info["label"] == "New Label"
        assert info["tags"] == {"env": "prod"}

    def test_update_tags_only(self, registry: AccountRegistry) -> None:
        """Updating only tags leaves label unchanged."""
        meta = registry.register(
            "wechat", WECHAT_CREDENTIALS, label="My Label", tags={"env": "prod"}
        )
        registry.update(meta["account_id"], tags={"region": "us"})

        info = registry.get(meta["account_id"])
        assert info is not None
        assert info["label"] == "My Label"
        assert info["tags"] == {"region": "us"}


# ---------------------------------------------------------------------------
# Credential loader fallback
# ---------------------------------------------------------------------------


class TestCredentialLoaderFallback:
    """load_credential_with_account_fallback bridging layer."""

    def test_uses_account_store_when_found(self) -> None:
        """When account_id exists and has the key, returns from store."""
        with patch("automedia.accounts.store.AccountStore") as mock_cls:
            mock_store = MagicMock()
            mock_store.load.return_value = {"appid": "from_store", "secret": "s3cret"}
            mock_cls.return_value = mock_store

            result = load_credential_with_account_fallback(
                "appid", account_id="acc_wechat_test1234"
            )
            assert result == "from_store"

    def test_falls_back_when_key_missing(self) -> None:
        """When account_id exists but key is missing, falls back with warning."""
        with (
            patch("automedia.accounts.store.AccountStore") as mock_cls,
            patch("automedia.core.credential_loader.load_credential", return_value="from_legacy"),
        ):
            mock_store = MagicMock()
            mock_store.load.return_value = {"secret": "s3cret"}
            mock_cls.return_value = mock_store

            with pytest.warns(DeprecationWarning, match="legacy credential path"):
                result = load_credential_with_account_fallback(
                    "appid", account_id="acc_wechat_test1234"
                )
            assert result == "from_legacy"

    def test_falls_back_when_account_nonexistent(self) -> None:
        """When account_id is provided but store returns None, falls back."""
        with (
            patch("automedia.accounts.store.AccountStore") as mock_cls,
            patch("automedia.core.credential_loader.load_credential", return_value="from_legacy"),
        ):
            mock_store = MagicMock()
            mock_store.load.return_value = None
            mock_cls.return_value = mock_store

            with pytest.warns(DeprecationWarning, match="legacy credential path"):
                result = load_credential_with_account_fallback(
                    "appid", account_id="acc_wechat_test1234"
                )
            assert result == "from_legacy"

    def test_falls_back_when_store_raises(self) -> None:
        """When AccountStore raises, falls back gracefully with warning."""
        with (
            patch("automedia.accounts.store.AccountStore") as mock_cls,
            patch("automedia.core.credential_loader.load_credential", return_value="from_legacy"),
        ):
            mock_store = MagicMock()
            mock_store.load.side_effect = Exception("Store error")
            mock_cls.return_value = mock_store

            with pytest.warns(DeprecationWarning, match="legacy credential path"):
                result = load_credential_with_account_fallback(
                    "appid", account_id="acc_wechat_test1234"
                )
            assert result == "from_legacy"

    def test_no_account_id_falls_back(self) -> None:
        """When no account_id provided, falls back with warning."""
        with (
            patch("automedia.core.credential_loader.load_credential", return_value="from_legacy"),
        ):
            with pytest.warns(DeprecationWarning, match="legacy credential path"):
                result = load_credential_with_account_fallback("wechat_appid")
            assert result == "from_legacy"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Unusual but valid inputs."""

    def test_unicode_credentials(self, registry: AccountRegistry) -> None:
        """Credentials containing Unicode characters round-trip correctly."""
        creds = {"token": "アクセストークン", "name": "Zoë"}
        meta = registry.register("test", creds, label="Unicode Test")
        loaded = registry.get_credentials(meta["account_id"])
        assert loaded == creds

    def test_large_tags(self, registry: AccountRegistry) -> None:
        """Tags with many entries are stored correctly."""
        tags = {f"key_{i}": f"val_{i}" for i in range(50)}
        meta = registry.register("wechat", WECHAT_CREDENTIALS, tags=tags)

        info = registry.get(meta["account_id"])
        assert info is not None
        assert info["tags"] == tags

    def test_registry_default_store(self) -> None:
        """Registry creates a default AccountStore when none is provided."""
        with patch("automedia.accounts.registry.AccountStore") as mock_cls:
            mock_store = MagicMock()
            mock_cls.return_value = mock_store

            reg = AccountRegistry()
            assert reg._store is mock_store
            mock_cls.assert_called_once_with()
