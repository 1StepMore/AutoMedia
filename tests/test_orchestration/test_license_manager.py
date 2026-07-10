"""RED tests for LicenseManager — key validation and feature gating.

Scenarios
---------
1. No license key → OS_COMMUNITY status, commercial features unavailable
2. Valid license key → COMMERCIAL status, commercial features available
3. Expired key → EXPIRED status, automatic degradation
4. Invalid/tampered key → OS_COMMUNITY (safe fallback)
"""

from __future__ import annotations

from automedia.license.manager import LicenseManager, LicenseStatus


class TestNoLicense:
    """No license key installed."""

    def test_no_key_returns_os_community(self) -> None:
        status = LicenseManager.check()
        assert status == LicenseStatus.OS_COMMUNITY

    def test_no_key_commercial_unavailable(self) -> None:
        assert LicenseManager.is_commercial_feature_available("tenant") is False
        assert LicenseManager.is_commercial_feature_available("rbac") is False
        assert LicenseManager.is_commercial_feature_available("audit") is False


class TestValidLicense:
    """Valid license key installed."""

    def test_valid_key_returns_commercial(self) -> None:
        key = _generate_test_key(days_valid=365)
        LicenseManager._set_test_key(key)
        try:
            status = LicenseManager.check()
            assert status == LicenseStatus.COMMERCIAL
        finally:
            LicenseManager._clear_test_key()

    def test_valid_key_commercial_available(self) -> None:
        key = _generate_test_key(days_valid=365)
        LicenseManager._set_test_key(key)
        try:
            assert LicenseManager.is_commercial_feature_available("tenant") is True
        finally:
            LicenseManager._clear_test_key()


class TestExpiredLicense:
    """Expired license key."""

    def test_expired_key_returns_expired(self) -> None:
        key = _generate_test_key(days_valid=-30)
        LicenseManager._set_test_key(key)
        try:
            status = LicenseManager.check()
            assert status == LicenseStatus.EXPIRED
        finally:
            LicenseManager._clear_test_key()

    def test_expired_key_commercial_unavailable(self) -> None:
        key = _generate_test_key(days_valid=-30)
        LicenseManager._set_test_key(key)
        try:
            assert LicenseManager.is_commercial_feature_available("tenant") is False
        finally:
            LicenseManager._clear_test_key()


class TestInvalidLicense:
    """Tampered or malformed license key."""

    def test_tampered_key_returns_os_community(self) -> None:
        LicenseManager._set_test_key("INVALID_TAMPERED_KEY_12345")
        try:
            status = LicenseManager.check()
            assert status == LicenseStatus.OS_COMMUNITY
        finally:
            LicenseManager._clear_test_key()

    def test_malformed_key_safe_fallback(self) -> None:
        LicenseManager._set_test_key("")
        try:
            assert LicenseManager.is_commercial_feature_available("tenant") is False
        finally:
            LicenseManager._clear_test_key()


class TestCommercialFeatureList:
    """COMMERCIAL_FEATURES list contains all expected features."""

    def test_commercial_feature_list(self) -> None:
        from automedia.license.manager import COMMERCIAL_FEATURES

        for f in ["tenant", "rbac", "audit", "saml", "web_ui"]:
            assert f in COMMERCIAL_FEATURES

    def test_commercial_feature_list_exhaustive(self) -> None:
        """The COMMERCIAL_FEATURES list has exactly the 5 expected items."""
        from automedia.license.manager import COMMERCIAL_FEATURES

        assert set(COMMERCIAL_FEATURES) == {"tenant", "rbac", "audit", "saml", "web_ui"}


class TestUnknownFeatureIsUnavailable:
    """Unknown (non-commercial) features are never available even with a valid license."""

    def test_unknown_feature_returns_false(self) -> None:
        key = _generate_test_key(days_valid=365)
        LicenseManager._set_test_key(key)
        try:
            assert LicenseManager.is_commercial_feature_available("unknown_feature") is False
        finally:
            LicenseManager._clear_test_key()

    def test_empty_feature_returns_true(self) -> None:
        """Empty feature string is treated as a general commercial check."""
        key = _generate_test_key(days_valid=365)
        LicenseManager._set_test_key(key)
        try:
            assert LicenseManager.is_commercial_feature_available("") is True
        finally:
            LicenseManager._clear_test_key()


# ---------------------------------------------------------------------------
# Helper: generate a test license key with the built-in generator
# ---------------------------------------------------------------------------


def _generate_test_key(days_valid: int = 365) -> str:
    """Generate a test license key valid for *days_valid* days from now
    (or expired if negative)."""
    from automedia.license.verifier import LicenseGenerator

    gen = LicenseGenerator()
    expiry = days_valid  # relative days
    key = gen.generate(tenant_id="test_tenant", days_valid=expiry)
    return key
