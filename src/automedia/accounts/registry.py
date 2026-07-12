"""AccountRegistry — high-level CRUD for platform accounts.

Wraps :class:`AccountStore` with validation, label uniqueness enforcement,
and business-level operations beyond raw CRUD.
"""

from __future__ import annotations

import logging
from typing import Any

from automedia.accounts.store import AccountStore

logger = logging.getLogger(__name__)


class AccountRegistry:
    """High-level account management on top of AccountStore.

    Provides validation, label uniqueness enforcement per platform,
    and convenience methods for common query patterns.

    Usage::

        registry = AccountRegistry()
        meta = registry.register("wechat", {"appid": "...", "secret": "..."}, label="My WeChat")
        acc = registry.get(meta["account_id"])
        creds = registry.get_credentials(meta["account_id"])
        registry.update(meta["account_id"], label="Renamed")
        registry.delete(meta["account_id"])
    """

    def __init__(self, store: AccountStore | None = None) -> None:
        """Initialise the registry with an optional pre-configured store.

        Parameters
        ----------
        store:
            An existing :class:`AccountStore` instance.  When ``None``, a
            default store is created (which reads ``AUTOMEDIA_MASTER_KEY``
            from the environment).
        """
        self._store = store or AccountStore()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(
        self,
        platform: str,
        credentials: dict[str, Any],
        label: str = "",
        auth_type: str = "api_key",
        tags: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Register a new platform account.

        Validates:

        - Credential payload is non-empty.
        - Label uniqueness per platform (when a non-empty label is provided).

        Parameters
        ----------
        platform:
            Platform identifier (e.g. ``"wechat"``, ``"zhihu"``).
        credentials:
            Plaintext credential payload.
        label:
            Human-readable display name.  Empty string means the store
            will use the account ID as the label.
        auth_type:
            Authentication type (default ``"api_key"``).
        tags:
            Optional key/value metadata.

        Returns
        -------
        dict
            Account metadata entry as stored in the index.

        Raises
        ------
        ValueError
            When *credentials* is empty, or when a duplicate label already
            exists for the same platform.
        """
        if not credentials:
            raise ValueError("Credentials payload must be non-empty.")

        if label:
            if self._label_exists(platform, label):
                raise ValueError(
                    f"Label '{label}' already exists for platform '{platform}'. "
                    "Labels must be unique per platform."
                )

        account_id = AccountStore.generate_account_id(platform)
        meta = self._store.save(platform, account_id, credentials, label, auth_type, tags)
        # Enrich with account_id — the store's save() does not include it
        return {"account_id": account_id, **meta}

    def list(self, platform: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        """List registered accounts, optionally filtered by platform and/or status.

        Parameters
        ----------
        platform:
            If provided, only accounts for this platform are returned.
        status:
            If provided, only accounts with this status are returned.

        Returns
        -------
        list[dict]
            A list of account metadata dicts (not decrypted credentials).
        """
        return self._store.list_accounts(platform, status)

    def get(self, account_id: str) -> dict[str, Any] | None:
        """Get account metadata (not decrypted credentials).

        Parameters
        ----------
        account_id:
            The unique account identifier.

        Returns
        -------
        dict | None
            Account metadata, or ``None`` if the account does not exist.
        """
        return self._store.get_account_info(account_id)

    def get_credentials(self, account_id: str) -> dict[str, Any] | None:
        """Get decrypted credentials for an account.

        Parameters
        ----------
        account_id:
            The unique account identifier.

        Returns
        -------
        dict | None
            Decrypted credential payload, or ``None`` if the account
            does not exist.
        """
        return self._store.load(account_id)

    def update(
        self,
        account_id: str,
        label: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> bool:
        """Update account metadata (label, tags).

        Parameters
        ----------
        account_id:
            The unique account identifier.
        label:
            New human-readable label.  When ``None``, the label is not
            changed.
        tags:
            New tags dict.  When ``None``, the tags are not changed.

        Returns
        -------
        bool
            ``True`` on success, ``False`` if *account_id* does not exist.

        Raises
        ------
        ValueError
            When the requested label already exists on another account
            for the same platform.
        """
        index = self._store._load_index()
        if account_id not in index["accounts"]:
            return False

        info = index["accounts"][account_id]

        if label is not None:
            # Check label uniqueness (excluding self)
            platform = info["platform"]
            if label and self._label_exists(platform, label, exclude=account_id):
                raise ValueError(
                    f"Label '{label}' already exists for platform '{platform}'. "
                    "Labels must be unique per platform."
                )
            info["label"] = label

        if tags is not None:
            info["tags"] = tags

        self._store._save_index_atomic(index)
        return True

    def delete(self, account_id: str) -> bool:
        """Remove an account.

        Parameters
        ----------
        account_id:
            The unique account identifier.

        Returns
        -------
        bool
            ``True`` on successful removal, ``False`` if the account does
            not exist.
        """
        return self._store.delete(account_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_by_label(self, platform: str, label: str) -> dict[str, Any] | None:
        """Find an account by platform + label combination.

        Parameters
        ----------
        platform:
            Platform to search within.
        label:
            Label to match (case-sensitive).

        Returns
        -------
        dict | None
            Account metadata for the matching account, or ``None`` if no
            account with that label exists on the platform.
        """
        accounts = self._store.list_accounts(platform=platform)
        for acc in accounts:
            if acc.get("label") == label:
                return acc
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _label_exists(self, platform: str, label: str, exclude: str | None = None) -> bool:
        """Check if *label* is already taken on *platform*.

        Parameters
        ----------
        platform:
            Platform to check.
        label:
            Label to check for.
        exclude:
            Optional account ID to exclude from the check (used during
            ``update()`` to allow keeping the same label).

        Returns
        -------
        bool
        """
        accounts = self._store.list_accounts(platform=platform)
        for acc in accounts:
            if acc.get("label") == label:
                if exclude is None or acc["account_id"] != exclude:
                    return True
        return False


__all__ = [
    "AccountRegistry",
]
