"""LicenseManager — open-core license check and feature gating.

Provides a singleton-like API for checking license status and
determining commercial feature availability.
"""

from __future__ import annotations

import enum
import os
from pathlib import Path


class LicenseStatus(enum.Enum):
    OS_COMMUNITY = "os_community"
    COMMERCIAL = "commercial"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# Commercial feature definitions
# ---------------------------------------------------------------------------

COMMERCIAL_FEATURES: list[str] = [
    "tenant",
    "rbac",
    "audit",
    "saml",
    "web_ui",
]
"""List of features that require a commercial license.

Adding or removing features here changes what ``is_commercial_feature_available``
reports.  The actual runtime check still depends on the license status.
"""


class LicenseManager:
    """License status checker and feature gate.

    Usage
    -----
    >>> LicenseManager.check()
    <LicenseStatus.OS_COMMUNITY>
    >>> LicenseManager.is_commercial_feature_available("tenant")
    False
    """

    _test_key: str | None = None
    _test_status: LicenseStatus | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def check(cls) -> LicenseStatus:
        """Check the current license status.

        Reads the license key from ``~/.automedia/license/license.key``
        (or the ``AUTOMEDIA_LICENSE_KEY`` environment variable), verifies
        it, and returns the status.
        """
        if cls._test_status is not None:
            return cls._test_status

        key = cls._get_key()
        if not key:
            return LicenseStatus.OS_COMMUNITY

        from automedia.license.verifier import RSAVerifier

        result = RSAVerifier.verify(key)
        if not result.get("valid"):
            return LicenseStatus.OS_COMMUNITY
        if result.get("expired"):
            return LicenseStatus.EXPIRED
        return LicenseStatus.COMMERCIAL

    @classmethod
    def is_commercial_feature_available(cls, feature: str = "") -> bool:
        """Check whether a commercial *feature* is available under the
        current license.

        Returns ``True`` only when the license is valid (not expired)
        *and* the feature is listed in ``COMMERCIAL_FEATURES``.
        """
        status = cls.check()
        if status != LicenseStatus.COMMERCIAL:
            return False
        if feature and feature not in COMMERCIAL_FEATURES:
            return False
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _get_key(cls) -> str | None:
        """Read the license key from env var or file."""
        if cls._test_key is not None:
            return cls._test_key

        env_key = os.environ.get("AUTOMEDIA_LICENSE_KEY")
        if env_key:
            return env_key

        key_path = Path.home() / ".automedia" / "license" / "license.key"
        if key_path.is_file():
            return key_path.read_text(encoding="utf-8").strip()

        return None

    @classmethod
    def _set_test_key(cls, key: str) -> None:
        """Inject a test key (bypasses file/env)."""
        cls._test_key = key

    @classmethod
    def _clear_test_key(cls) -> None:
        """Clear injected test key."""
        cls._test_key = None

    @classmethod
    def _set_test_status(cls, status: LicenseStatus) -> None:
        """Force a license status for testing (bypasses verification)."""
        cls._test_status = status

    @classmethod
    def _clear_test_status(cls) -> None:
        cls._test_status = None
