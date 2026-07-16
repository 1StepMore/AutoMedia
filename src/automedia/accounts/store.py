"""Encrypted per-account credential store using AES-256-GCM.

Storage layout::

    ~/.automedia/accounts/
        {platform}/
            {account_id}.json.enc    ← AES-256-GCM encrypted payload
        accounts.index.json          ← unencrypted index (fingerprints, metadata)
        accounts.index.json.bak      ← backup of previous index (atomic write safety)

Key derivation
--------------
SHA-256(AUTOMEDIA_MASTER_KEY) → 32-byte AES-256 key

Usage::

    store = AccountStore(master_key="...")
    meta = store.save("wechat", "acc_wechat_a1b2c3d4", {"appid": "...", "secret": "..."},
                       label="My WeChat Account")
    creds = store.load("acc_wechat_a1b2c3d4")
    store.delete("acc_wechat_a1b2c3d4")
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from structlog import get_logger

from automedia.accounts.models import AccountInfo

log = get_logger(__name__)


class AccountStore:
    """Encrypted per-account credential store.

    Provides CRUD operations with AES-256-GCM encryption, atomic index
    writes, fingerprint-based deduplication, and platform-level isolation
    via subdirectories.
    """

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def __init__(self, store_dir: str | None = None, master_key: str | None = None) -> None:
        """Initialise the account store.

        Parameters
        ----------
        store_dir:
            Path to the accounts store directory.  Defaults to
            ``~/.automedia/accounts/``.
        master_key:
            Encryption master key.  Defaults to the ``AUTOMEDIA_MASTER_KEY``
            environment variable.  At least one must be provided.

        Raises
        ------
        ValueError
            When no master key is available via either argument or environment.
        """
        self._store_dir: Path = Path(store_dir or Path.home() / ".automedia" / "accounts")
        key_str = master_key or os.environ.get("AUTOMEDIA_MASTER_KEY", "")
        if not key_str:
            raise ValueError(
                "AUTOMEDIA_MASTER_KEY environment variable must be set, "
                "or a master_key must be provided."
            )
        # Derive 32-byte AES-256 key via SHA-256
        self._key: bytes = hashlib.sha256(key_str.encode()).digest()
        self._aesgcm: AESGCM = AESGCM(self._key)
        self._store_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def fingerprint(credentials: dict[str, Any]) -> str:
        """Generate a SHA-256 fingerprint of canonical credential payload.

        The fingerprint is computed over the JSON representation with sorted
        keys, guaranteeing that semantically identical credentials always
        produce the same fingerprint regardless of key ordering.
        """
        canonical = json.dumps(credentials, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def generate_account_id(platform: str) -> str:
        """Generate a display-friendly, unique account ID.

        Format: ``acc_{platform}_{8-hex-chars}``
        """
        short = uuid.uuid4().hex[:8]
        return f"acc_{platform}_{short}"

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _platform_dir(self, platform: str) -> Path:
        """Return (and create if needed) the platform subdirectory."""
        path = self._store_dir / platform
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _account_path(self, platform: str, account_id: str) -> Path:
        """Return the encrypted file path for *account_id*."""
        return self._platform_dir(platform) / f"{account_id}.json.enc"

    def _index_path(self) -> Path:
        """Return the path to the unencrypted accounts index JSON."""
        return self._store_dir / "accounts.index.json"

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _load_index(self) -> dict[str, Any]:
        """Load the index JSON from disk, returning a fresh dict if missing."""
        path = self._index_path()
        if path.is_file():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return {"accounts": {}}

    def _save_index_atomic(self, index: dict[str, Any]) -> None:
        """Atomically write the index: write to ``.tmp``, then rename.

        A backup (``.bak``) is also created for resilience.
        """
        path = self._index_path()
        tmp_path = path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False, default=str)
        # Backup — overwrites previous backup
        bak_path = path.with_suffix(".json.bak")
        shutil.copy2(tmp_path, bak_path)
        tmp_path.replace(path)

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def save(
        self,
        platform: str,
        account_id: str,
        credentials: dict[str, Any],
        label: str = "",
        auth_type: str = "api_key",
        tags: dict[str, str] | None = None,
    ) -> AccountInfo:
        """Encrypt and store credentials for an account.

        Parameters
        ----------
        platform:
            Platform identifier (e.g. ``"wechat"``, ``"zhihu"``).
        account_id:
            Unique account identifier (e.g. from :meth:`generate_account_id`).
        credentials:
            Plaintext credential payload (API keys, cookies, OAuth tokens).
        label:
            Human-readable display name.  Falls back to *account_id* when empty.
        auth_type:
            Authentication type string (matches :class:`AuthType` values).
        tags:
            Optional key/value metadata.

        Returns
        -------
        dict
            Account metadata entry as stored in the index.
        """
        fp = self.fingerprint(credentials)

        # --- Encrypt ---
        nonce = os.urandom(12)
        plaintext = json.dumps(credentials, ensure_ascii=False).encode()
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)

        # --- Write encrypted file ---
        payload: dict[str, Any] = {
            "account_id": account_id,
            "nonce": nonce.hex(),
            "ciphertext": ciphertext.hex(),
            "algorithm": "AES-256-GCM",
        }
        enc_path = self._account_path(platform, account_id)
        with open(enc_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        # --- Update index ---
        index = self._load_index()
        index["accounts"][account_id] = {
            "platform": platform,
            "label": label or account_id,
            "auth_type": auth_type,
            "fingerprint": fp,
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "last_used": None,
            "last_health_check": None,
            "tags": tags or {},
        }
        self._save_index_atomic(index)

        return {"account_id": account_id, **index["accounts"][account_id]}

    def load(self, account_id: str) -> dict[str, Any] | None:
        """Decrypt and return the credentials for *account_id*.

        Returns ``None`` when the account does not exist in the index or
        the encrypted file is missing.

        Raises
        ------
        cryptography.exceptions.InvalidTag
            When the decryption key is wrong or the ciphertext is corrupted.
        """
        index = self._load_index()
        info = index["accounts"].get(account_id)
        if not info:
            return None

        enc_path = self._account_path(info["platform"], account_id)
        if not enc_path.is_file():
            return None

        with open(enc_path, encoding="utf-8") as f:
            payload = json.load(f)

        nonce = bytes.fromhex(payload["nonce"])
        ciphertext = bytes.fromhex(payload["ciphertext"])
        plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
        credentials: dict[str, Any] = json.loads(plaintext.decode())

        return credentials

    def delete(self, account_id: str) -> bool:
        """Remove an account and its encrypted file.

        Returns ``True`` on successful removal, ``False`` if the account
        does not exist in the index.
        """
        index = self._load_index()
        info = index["accounts"].pop(account_id, None)
        if not info:
            return False

        enc_path = self._account_path(info["platform"], account_id)
        if enc_path.is_file():
            enc_path.unlink()

        self._save_index_atomic(index)
        return True

    def list_accounts(
        self,
        platform: str | None = None,
        status: str | None = None,
    ) -> list[AccountInfo]:
        """List all accounts, optionally filtered by platform and/or status.

        Returns account metadata (not decrypted credentials).
        """
        index = self._load_index()
        accounts: list[AccountInfo] = []
        for acc_id, info in index["accounts"].items():
            if platform and info["platform"] != platform:
                continue
            if status and info["status"] != status:
                continue
            entry: AccountInfo = {"account_id": acc_id, **info}
            accounts.append(entry)
        return accounts

    def get_account_info(self, account_id: str) -> AccountInfo | None:
        """Get unencrypted account metadata from the index.

        Returns ``None`` when *account_id* is not found.
        """
        index = self._load_index()
        info = index["accounts"].get(account_id)
        if info:
            return {"account_id": account_id, **info}
        return None

    def update_status(self, account_id: str, status: str) -> bool:
        """Update an account's status (e.g. ``"inactive"``, ``"stale"``).

        Returns ``False`` when *account_id* is not found.
        """
        index = self._load_index()
        if account_id not in index["accounts"]:
            return False
        index["accounts"][account_id]["status"] = status
        self._save_index_atomic(index)
        return True


__all__ = [
    "AccountStore",
]
