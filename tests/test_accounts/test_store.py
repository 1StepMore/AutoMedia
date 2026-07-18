"""Tests for AccountStore — encrypted credential persistence with AES-256-GCM."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from automedia.accounts.store import AccountStore

# ---------------------------------------------------------------------------
# Sample credential payloads (synthetic — no real secrets)
# ---------------------------------------------------------------------------

WECHAT_CREDENTIALS = {
    "appid": "wx_test_appid_12345",
    "secret": "test_secret_value_abc123",
}

ZHIHU_CREDENTIALS = {
    "cookie": "session=test_session_value; token=test_token_value",
}

XHS_CREDENTIALS = {
    "cookie": "xhs_test_session_value",
    "device_id": "test_device_123",
}


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


class TestFingerprint:
    """Fingerprint consistency and determinism."""

    def test_same_input_same_fingerprint(self) -> None:
        """Same credential dict always produces the same fingerprint."""
        fp1 = AccountStore.fingerprint(WECHAT_CREDENTIALS)
        fp2 = AccountStore.fingerprint(WECHAT_CREDENTIALS)
        assert fp1 == fp2

    def test_key_order_independence(self) -> None:
        """Fingerprint is independent of dict key ordering."""
        unordered = {"secret": "xyz", "appid": "wx_test"}
        ordered = {"appid": "wx_test", "secret": "xyz"}
        assert AccountStore.fingerprint(unordered) == AccountStore.fingerprint(ordered)

    def test_different_credentials_different_fingerprint(self) -> None:
        """Different credential payloads produce different fingerprints."""
        fp1 = AccountStore.fingerprint(WECHAT_CREDENTIALS)
        fp2 = AccountStore.fingerprint(ZHIHU_CREDENTIALS)
        assert fp1 != fp2

    def test_fingerprint_is_sha256(self) -> None:
        """Fingerprint is a 64-character hex string (SHA-256)."""
        fp = AccountStore.fingerprint(WECHAT_CREDENTIALS)
        assert len(fp) == 64
        int(fp, 16)  # raises ValueError if not valid hex


# ---------------------------------------------------------------------------
# Generate account ID
# ---------------------------------------------------------------------------


class TestGenerateAccountId:
    """Account ID generation."""

    def test_format(self) -> None:
        """Account ID follows ``acc_{platform}_{hex}`` pattern."""
        acc_id = AccountStore.generate_account_id("wechat")
        assert acc_id.startswith("acc_wechat_")
        assert len(acc_id) == len("acc_wechat_") + 8

    def test_uniqueness(self) -> None:
        """Consecutive calls produce different IDs."""
        ids = {AccountStore.generate_account_id("wechat") for _ in range(100)}
        assert len(ids) == 100


# ---------------------------------------------------------------------------
# Save / Load round-trip
# ---------------------------------------------------------------------------


class TestSaveLoad:
    """Encrypt-then-decrypt round-trip."""

    def test_save_and_load(self, account_store: AccountStore) -> None:
        """Saved credentials can be loaded back and match exactly."""
        acc_id = AccountStore.generate_account_id("wechat")
        account_store.save("wechat", acc_id, WECHAT_CREDENTIALS, label="Test WeChat")

        loaded = account_store.load(acc_id)
        assert loaded == WECHAT_CREDENTIALS

    def test_load_nonexistent_account(self, account_store: AccountStore) -> None:
        """Loading a non-existent account returns ``None``."""
        assert account_store.load("nonexistent_id") is None

    def test_multiple_platforms(self, account_store: AccountStore) -> None:
        """Accounts on different platforms are properly isolated."""
        w_id = AccountStore.generate_account_id("wechat")
        z_id = AccountStore.generate_account_id("zhihu")
        account_store.save("wechat", w_id, WECHAT_CREDENTIALS)
        account_store.save("zhihu", z_id, ZHIHU_CREDENTIALS)

        assert account_store.load(w_id) == WECHAT_CREDENTIALS
        assert account_store.load(z_id) == ZHIHU_CREDENTIALS

    def test_same_platform_multiple_accounts(self, account_store: AccountStore) -> None:
        """Multiple accounts on the same platform co-exist."""
        a_id = AccountStore.generate_account_id("xhs")
        b_id = AccountStore.generate_account_id("xhs")
        account_store.save("xhs", a_id, {"cookie": "session_a"})
        account_store.save("xhs", b_id, {"cookie": "session_b"})

        assert account_store.load(a_id) == {"cookie": "session_a"}
        assert account_store.load(b_id) == {"cookie": "session_b"}


# ---------------------------------------------------------------------------
# Nonce randomisation
# ---------------------------------------------------------------------------


class TestNonceRandomisation:
    """Same credentials produce different ciphertext per save."""

    def test_different_nonce_each_save(self, temp_store_dir: Path) -> None:
        """Re-saving the same credentials yields different encrypted files."""
        store1 = AccountStore(store_dir=str(temp_store_dir), master_key="test-key")
        store2 = AccountStore(store_dir=str(temp_store_dir), master_key="test-key")

        a_id = AccountStore.generate_account_id("wechat")
        store1.save("wechat", a_id, WECHAT_CREDENTIALS)

        # Re-save with same credentials (different account ID to avoid conflict)
        b_id = AccountStore.generate_account_id("wechat")
        store2.save("wechat", b_id, WECHAT_CREDENTIALS)

        # Read the raw encrypted files and compare ciphertexts
        enc_a = store1._account_path("wechat", a_id)
        enc_b = store2._account_path("wechat", b_id)

        with open(enc_a, encoding="utf-8") as f:
            payload_a = json.load(f)
        with open(enc_b, encoding="utf-8") as f:
            payload_b = json.load(f)

        # Nonces MUST differ (otherwise ciphertext comparison is meaningless)
        assert payload_a["nonce"] != payload_b["nonce"], (
            "Nonces should be unique per encryption — same credentials produced "
            "the same nonce, defeating GCM security."
        )
        # Ciphertexts MUST differ (different nonce → different ciphertext)
        assert payload_a["ciphertext"] != payload_b["ciphertext"], (
            "Ciphertexts should differ even for identical plaintext — nonce randomisation failed."
        )


# ---------------------------------------------------------------------------
# Atomic write resilience
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    """Index atomic write and backup creation."""

    def test_backup_file_created(self, account_store: AccountStore) -> None:
        """After saving an account, a ``.bak`` file exists alongside the index."""
        acc_id = AccountStore.generate_account_id("wechat")
        account_store.save("wechat", acc_id, WECHAT_CREDENTIALS)

        bak_path = account_store._index_path().with_suffix(".json.bak")
        assert bak_path.is_file(), "Backup file should exist after first save"

        # The backup should contain the same data as the index
        with open(bak_path, encoding="utf-8") as f:
            backup_data = json.load(f)
        assert acc_id in backup_data["accounts"]

    def test_index_readable_after_corrupt_tmp(self, account_store: AccountStore) -> None:
        """The index remains valid even if a previous ``.tmp`` write was interrupted."""
        acc_id = AccountStore.generate_account_id("wechat")
        account_store.save("wechat", acc_id, WECHAT_CREDENTIALS)

        # Write garbage to the .tmp file to simulate a crash
        tmp_path = account_store._index_path().with_suffix(".json.tmp")
        tmp_path.write_text("{{{ corrupt json ", encoding="utf-8")

        # A subsequent save should succeed (it overwrites .tmp then renames)
        acc_id2 = AccountStore.generate_account_id("zhihu")
        account_store.save("zhihu", acc_id2, ZHIHU_CREDENTIALS)

        # Both accounts should still be loadable
        assert account_store.load(acc_id) == WECHAT_CREDENTIALS
        assert account_store.load(acc_id2) == ZHIHU_CREDENTIALS


# ---------------------------------------------------------------------------
# List with filters
# ---------------------------------------------------------------------------


class TestListAccounts:
    """Listing accounts with platform and status filters."""

    def test_list_all(self, account_store: AccountStore) -> None:
        """Listing with no filters returns all accounts."""
        ids = []
        for plat, creds in [("wechat", WECHAT_CREDENTIALS), ("zhihu", ZHIHU_CREDENTIALS)]:
            aid = AccountStore.generate_account_id(plat)
            account_store.save(plat, aid, creds)
            ids.append(aid)

        accounts = account_store.list_accounts()
        assert len(accounts) == 2
        returned_ids = {a["account_id"] for a in accounts}
        assert returned_ids == set(ids)

    def test_list_by_platform(self, account_store: AccountStore) -> None:
        """Filtering by platform returns only matching accounts."""
        for plat, creds in [("wechat", WECHAT_CREDENTIALS), ("zhihu", ZHIHU_CREDENTIALS)]:
            account_store.save(plat, AccountStore.generate_account_id(plat), creds)

        wechat_accounts = account_store.list_accounts(platform="wechat")
        assert len(wechat_accounts) == 1
        assert wechat_accounts[0]["platform"] == "wechat"

    def test_list_by_status(self, account_store: AccountStore) -> None:
        """Filtering by status returns only accounts with that status."""
        active_id = AccountStore.generate_account_id("wechat")
        account_store.save("wechat", active_id, WECHAT_CREDENTIALS)

        inactive_id = AccountStore.generate_account_id("zhihu")
        account_store.save("zhihu", inactive_id, ZHIHU_CREDENTIALS)
        account_store.update_status(inactive_id, "inactive")

        active = account_store.list_accounts(status="active")
        assert len(active) == 1
        assert active[0]["account_id"] == active_id

        inactive = account_store.list_accounts(status="inactive")
        assert len(inactive) == 1
        assert inactive[0]["account_id"] == inactive_id

    def test_list_with_platform_and_status(self, account_store: AccountStore) -> None:
        """Combined platform + status filtering works."""
        w_id = AccountStore.generate_account_id("wechat")
        account_store.save("wechat", w_id, WECHAT_CREDENTIALS)
        account_store.save("wechat", AccountStore.generate_account_id("wechat"), {"key": "other"})

        result = account_store.list_accounts(platform="wechat", status="active")
        assert len(result) == 2

    def test_empty_store(self, account_store: AccountStore) -> None:
        """Listing accounts on an empty store returns an empty list."""
        assert account_store.list_accounts() == []
        assert account_store.list_accounts(platform="wechat") == []
        assert account_store.list_accounts(status="active") == []


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDelete:
    """Account deletion."""

    def test_delete_removes_index_entry(self, account_store: AccountStore) -> None:
        """After deletion, the account no longer appears in the index."""
        acc_id = AccountStore.generate_account_id("wechat")
        account_store.save("wechat", acc_id, WECHAT_CREDENTIALS)
        assert account_store.get_account_info(acc_id) is not None

        deleted = account_store.delete(acc_id)
        assert deleted is True
        assert account_store.get_account_info(acc_id) is None

    def test_delete_removes_encrypted_file(self, account_store: AccountStore) -> None:
        """After deletion, the encrypted file on disk is removed."""
        acc_id = AccountStore.generate_account_id("wechat")
        account_store.save("wechat", acc_id, WECHAT_CREDENTIALS)

        enc_path = account_store._account_path("wechat", acc_id)
        assert enc_path.is_file()

        account_store.delete(acc_id)
        assert not enc_path.exists()

    def test_delete_nonexistent(self, account_store: AccountStore) -> None:
        """Deleting a non-existent account returns ``False``."""
        assert account_store.delete("nonexistent") is False

    def test_delete_preserves_other_accounts(self, account_store: AccountStore) -> None:
        """Deleting one account does not affect others."""
        w_id = AccountStore.generate_account_id("wechat")
        z_id = AccountStore.generate_account_id("zhihu")
        account_store.save("wechat", w_id, WECHAT_CREDENTIALS)
        account_store.save("zhihu", z_id, ZHIHU_CREDENTIALS)

        account_store.delete(w_id)
        assert account_store.load(z_id) == ZHIHU_CREDENTIALS


# ---------------------------------------------------------------------------
# Get account info
# ---------------------------------------------------------------------------


class TestGetAccountInfo:
    """Account metadata retrieval (unencrypted)."""

    def test_get_info(self, account_store: AccountStore) -> None:
        """Getting account info returns metadata from the index."""
        acc_id = AccountStore.generate_account_id("wechat")
        account_store.save("wechat", acc_id, WECHAT_CREDENTIALS, label="My WeChat")

        info = account_store.get_account_info(acc_id)
        assert info is not None
        assert info["account_id"] == acc_id
        assert info["platform"] == "wechat"
        assert info["label"] == "My WeChat"
        assert info["auth_type"] == "api_key"
        assert info["status"] == "active"
        assert "fingerprint" in info
        assert "created_at" in info

    def test_get_info_nonexistent(self, account_store: AccountStore) -> None:
        """Getting info for a non-existent account returns ``None``."""
        assert account_store.get_account_info("nonexistent") is None

    def test_info_does_not_contain_credentials(self, account_store: AccountStore) -> None:
        """Getting account info does not expose credentials."""
        acc_id = AccountStore.generate_account_id("wechat")
        account_store.save("wechat", acc_id, WECHAT_CREDENTIALS)

        info = account_store.get_account_info(acc_id)
        assert info is not None
        # Verify that none of the credential fields leak into the index
        for cred_key in WECHAT_CREDENTIALS:
            assert cred_key not in info, (
                f"Credential key '{cred_key}' leaked into account index info"
            )


# ---------------------------------------------------------------------------
# Key mismatch
# ---------------------------------------------------------------------------


class TestKeyMismatch:
    """Decryption with a wrong master key."""

    def test_wrong_key_raises_invalid_tag(self, temp_store_dir: Path) -> None:
        """Decrypting with a different key raises ``InvalidTag``."""
        store_a = AccountStore(store_dir=str(temp_store_dir), master_key="correct-key")
        store_b = AccountStore(store_dir=str(temp_store_dir), master_key="wrong-key-12345678")

        acc_id = AccountStore.generate_account_id("wechat")
        store_a.save("wechat", acc_id, WECHAT_CREDENTIALS)

        with pytest.raises(InvalidTag):
            store_b.load(acc_id)

    def test_different_key_lengths(self, temp_store_dir: Path) -> None:
        """Keys of various lengths all work (AES-256 via SHA-256 derivation)."""
        store = AccountStore(store_dir=str(temp_store_dir), master_key="short")
        acc_id = AccountStore.generate_account_id("wechat")
        store.save("wechat", acc_id, WECHAT_CREDENTIALS)

        loaded = store.load(acc_id)
        assert loaded == WECHAT_CREDENTIALS


# ---------------------------------------------------------------------------
# Update status
# ---------------------------------------------------------------------------


class TestUpdateStatus:
    """Account status transitions."""

    def test_update_status(self, account_store: AccountStore) -> None:
        """Updating an account's status persists correctly."""
        acc_id = AccountStore.generate_account_id("wechat")
        account_store.save("wechat", acc_id, WECHAT_CREDENTIALS)

        result = account_store.update_status(acc_id, "inactive")
        assert result is True

        info = account_store.get_account_info(acc_id)
        assert info is not None
        assert info["status"] == "inactive"

    def test_update_status_nonexistent(self, account_store: AccountStore) -> None:
        """Updating status for a non-existent account returns ``False``."""
        assert account_store.update_status("nonexistent", "inactive") is False

    def test_status_filter_after_update(self, account_store: AccountStore) -> None:
        """After status update, listing by new status returns the account."""
        acc_id = AccountStore.generate_account_id("wechat")
        account_store.save("wechat", acc_id, WECHAT_CREDENTIALS)
        account_store.update_status(acc_id, "stale")

        stale = account_store.list_accounts(status="stale")
        assert len(stale) == 1
        assert stale[0]["account_id"] == acc_id

        active = account_store.list_accounts(status="active")
        assert len(active) == 0


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestInitialisation:
    """Store initialisation and edge cases."""

    def test_no_key_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Creating a store without a key raises ``ValueError``."""
        monkeypatch.delenv("AUTOMEDIA_MASTER_KEY", raising=False)
        with pytest.raises(ValueError, match="AUTOMEDIA_MASTER_KEY"):
            AccountStore(store_dir="/tmp/no-key-test", master_key="")

    def test_store_dir_created(self, temp_store_dir: Path) -> None:
        """The store directory is created on init if it doesn't exist."""
        nested = temp_store_dir / "a" / "b" / "c"
        assert not nested.exists()

        store = AccountStore(store_dir=str(nested), master_key="test-key")
        assert nested.is_dir()
        # Cleanup
        import shutil

        shutil.rmtree(temp_store_dir, ignore_errors=True)

    def test_re_init_uses_existing_dir(self, temp_store_dir: Path) -> None:
        """Initialising a store on an existing directory works."""
        store1 = AccountStore(store_dir=str(temp_store_dir), master_key="test-key")
        acc_id = AccountStore.generate_account_id("wechat")
        store1.save("wechat", acc_id, WECHAT_CREDENTIALS)

        # Second store instance with same directory
        store2 = AccountStore(store_dir=str(temp_store_dir), master_key="test-key")
        loaded = store2.load(acc_id)
        assert loaded == WECHAT_CREDENTIALS


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Unusual but valid inputs."""

    def test_empty_credentials(self, account_store: AccountStore) -> None:
        """Empty credential dicts can be saved and loaded."""
        acc_id = AccountStore.generate_account_id("test")
        account_store.save("test", acc_id, {})
        loaded = account_store.load(acc_id)
        assert loaded == {}

    def test_unicode_credentials(self, account_store: AccountStore) -> None:
        """Credentials containing Unicode characters round-trip correctly."""
        creds = {"token": "アクセストークン", "name": "Zoë"}
        acc_id = AccountStore.generate_account_id("test")
        account_store.save("test", acc_id, creds)
        loaded = account_store.load(acc_id)
        assert loaded == creds

    def test_large_credential_payload(self, account_store: AccountStore) -> None:
        """Large credential payloads (100K+) encrypt and decrypt correctly."""
        large_creds = {"data": "x" * 100_000}
        acc_id = AccountStore.generate_account_id("test")
        account_store.save("test", acc_id, large_creds)
        loaded = account_store.load(acc_id)
        assert loaded == large_creds
