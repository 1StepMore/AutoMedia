"""E2E tests for license check — no license, valid, expired scenarios.

These tests use LicenseManager's test injection hooks to simulate
different license states without requiring filesystem keys or RSA keys.
"""

from __future__ import annotations

import pytest

from automedia.license.manager import LicenseManager, LicenseStatus


@pytest.mark.e2e
class TestLicenseCheck:
    """E2E: License check scenarios."""

    def test_no_license_os_community(self) -> None:
        """Clear any test key, verify OS_COMMUNITY status."""
        LicenseManager._clear_test_key()
        LicenseManager._clear_test_status()
        status = LicenseManager.check()
        assert status == LicenseStatus.OS_COMMUNITY

    def test_valid_license_commercial(self) -> None:
        """Generate valid key, verify COMMERCIAL status."""
        key = _generate_test_key(days_valid=365)
        LicenseManager._set_test_key(key)
        try:
            status = LicenseManager.check()
            assert status == LicenseStatus.COMMERCIAL
            assert LicenseManager.is_commercial_feature_available("tenant") is True
            assert LicenseManager.is_commercial_feature_available("rbac") is True
        finally:
            LicenseManager._clear_test_key()

    def test_expired_license_downgrade(self) -> None:
        """Generate expired key, verify EXPIRED + degraded."""
        key = _generate_test_key(days_valid=-30)
        LicenseManager._set_test_key(key)
        try:
            status = LicenseManager.check()
            assert status == LicenseStatus.EXPIRED
            # Commercial features should be unavailable
            assert LicenseManager.is_commercial_feature_available("tenant") is False
            assert LicenseManager.is_commercial_feature_available("web_ui") is False
        finally:
            LicenseManager._clear_test_key()

    def test_forced_os_community_status(self) -> None:
        """Force OS_COMMUNITY via test injection."""
        LicenseManager._set_test_status(LicenseStatus.OS_COMMUNITY)
        try:
            status = LicenseManager.check()
            assert status == LicenseStatus.OS_COMMUNITY
            assert LicenseManager.is_commercial_feature_available("saml") is False
        finally:
            LicenseManager._clear_test_status()

    def test_forced_expired_status(self) -> None:
        """Force EXPIRED via test injection."""
        LicenseManager._set_test_status(LicenseStatus.EXPIRED)
        try:
            status = LicenseManager.check()
            assert status == LicenseStatus.EXPIRED
            assert LicenseManager.is_commercial_feature_available("audit") is False
        finally:
            LicenseManager._clear_test_status()

    def test_forced_commercial_status(self) -> None:
        """Force COMMERCIAL via test injection."""
        LicenseManager._set_test_status(LicenseStatus.COMMERCIAL)
        try:
            status = LicenseManager.check()
            assert status == LicenseStatus.COMMERCIAL
            assert LicenseManager.is_commercial_feature_available("tenant") is True
        finally:
            LicenseManager._clear_test_status()


def _generate_test_key(days_valid: int = 365) -> str:
    """Generate a test license key valid for *days_valid* days from now."""
    from automedia.license.verifier import LicenseGenerator

    return LicenseGenerator.generate(tenant_id="e2e_test_tenant", days_valid=days_valid)
