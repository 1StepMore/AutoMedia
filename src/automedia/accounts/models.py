"""PRD-4: Account data models — platform account representation, credential wrapper, index, and session tokens."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict

from structlog import get_logger

log = get_logger(__name__)


class AuthType(enum.StrEnum):
    """Authentication methods supported by platform accounts."""

    OAUTH2_AUTH_CODE = "oauth2_auth_code"
    OAUTH2_CLIENT_CRED = "oauth2_client_cred"
    COOKIE = "cookie"
    API_KEY = "api_key"
    WEBHOOK_URL = "webhook_url"
    QR_CODE = "qr_code"  # Commercial platform QR login


@dataclass
class Account:
    """Represents a platform account with its metadata.

    The ``fingerprint`` is a SHA-256 hash of canonical credential payload,
    enabling deduplication.  The ``id`` is a UUID4 string assigned at creation.
    """

    id: str  # UUID4
    platform: str  # "wechat", "zhihu", "xiaohongshu", etc.
    label: str  # Human-readable display name
    auth_type: AuthType
    fingerprint: str  # SHA-256 of canonical credentials
    status: str = "active"  # active | inactive | stale
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime | None = None
    last_health_check: datetime | None = None
    tags: dict[str, str] = field(default_factory=dict)  # Commercial — arbitrary key/value metadata


@dataclass
class AccountCredentials:
    """Encrypted wrapper for platform-specific credential payload.

    The actual credential data (API keys, cookies, OAuth tokens, etc.) is
    AES-256-GCM encrypted.  Only the ``account_id`` and algorithm identifier
    are stored in plaintext alongside the ciphertext.
    """

    account_id: str
    encrypted_data: bytes  # AES-256-GCM ciphertext
    nonce: bytes  # 12-byte GCM nonce
    auth_tag: bytes  # 16-byte GCM authentication tag
    created_at: datetime = field(default_factory=datetime.now)
    algorithm: str = "AES-256-GCM"


class AccountInfo(TypedDict, total=False):
    """Metadata entry for a platform account in the index.

    ``account_id``, ``platform``, ``label``, ``auth_type``,
    ``fingerprint``, and ``status`` are always present.
    """

    account_id: str
    platform: str
    label: str
    auth_type: str
    fingerprint: str
    status: str
    created_at: str
    last_used: str | None
    last_health_check: str | None
    tags: dict[str, str]


# Type alias for backward compatibility
IndexEntry = AccountInfo


@dataclass
class AccountIndex:
    """Lightweight in-memory index mapping ``account_id`` → metadata.

    The index contains **unencrypted** metadata only (platform, label,
    auth_type, status, timestamps).  Credential payloads are never stored
    in the index — they live in per-account encrypted files.
    """

    accounts: dict[str, IndexEntry] = field(default_factory=dict)


@dataclass
class HealthStatus:
    """Result of a health-check probe against a platform account."""

    healthy: bool
    status_message: str
    last_checked: datetime = field(default_factory=datetime.now)


@dataclass
class SessionToken:
    """OAuth / session token with optional refresh token and expiry."""

    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    token_type: str = "bearer"  # noqa: S105  — RFC 6750 standard token type, not a credential

    def __repr__(self) -> str:
        at = (
            self.access_token[:8] + "..."
            if self.access_token and len(self.access_token) > 8
            else "***"
        )
        rt = (
            self.refresh_token[:8] + "..."
            if self.refresh_token and len(self.refresh_token) > 8
            else "***"
        )
        return (
            f"SessionToken(access_token='{at}', refresh_token='{rt}', "
            f"expires_at={self.expires_at!r}, token_type='{self.token_type}')"
        )


__all__ = [
    "Account",
    "AccountCredentials",
    "AccountIndex",
    "AuthType",
    "HealthStatus",
    "HealthStatus",
    "SessionToken",
]
