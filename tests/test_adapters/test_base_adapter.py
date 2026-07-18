"""Tests for BasePlatformAdapter default implementations."""

from __future__ import annotations

from typing import Any

from automedia.adapters.base import BasePlatformAdapter

# ---------------------------------------------------------------------------
# Stub — concrete subclass required because BasePlatformAdapter has
# abstract methods (platform_name, publish).
# ---------------------------------------------------------------------------


class _StubAdapter(BasePlatformAdapter):
    """Minimal concrete adapter for testing default behaviour."""

    @property
    def platform_name(self) -> str:
        return "stub"

    def publish(self, artifact_dir: str, project: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return {"status": "ok"}


# ---------------------------------------------------------------------------
# Default-method tests
# ---------------------------------------------------------------------------


class TestAuthenticateDefault:
    def test_authenticate_returns_not_implemented(self) -> None:
        adapter = _StubAdapter()
        result = adapter.authenticate()
        assert result["status"] == "not_implemented"
        assert "reason" in result

    def test_authenticate_accepts_account_id(self) -> None:
        adapter = _StubAdapter()
        result = adapter.authenticate(account_id="acc_test_001")
        assert result["status"] == "not_implemented"


class TestRefreshSessionDefault:
    def test_refresh_session_returns_not_implemented(self) -> None:
        adapter = _StubAdapter()
        result = adapter.refresh_session(account_id="acc_test_001")
        assert result["status"] == "not_implemented"
        assert "reason" in result

    def test_refresh_session_requires_account_id(self) -> None:
        adapter = _StubAdapter()
        result = adapter.refresh_session("acc_test_001")
        assert result["status"] == "not_implemented"


class TestCheckHealthDefault:
    def test_check_health_returns_not_implemented(self) -> None:
        adapter = _StubAdapter()
        result = adapter.check_health()
        assert result["status"] == "not_implemented"
        assert result["healthy"] is False
        assert "reason" in result

    def test_check_health_accepts_account_id(self) -> None:
        adapter = _StubAdapter()
        result = adapter.check_health(account_id="acc_test_001")
        assert result["status"] == "not_implemented"


class TestGetAnalyticsDefault:
    def test_get_analytics_returns_not_implemented(self) -> None:
        adapter = _StubAdapter()
        result = adapter.get_analytics(account_id="acc_test_001")
        assert result["status"] == "not_implemented"
        assert "reason" in result

    def test_get_analytics_accepts_period(self) -> None:
        adapter = _StubAdapter()
        result = adapter.get_analytics(account_id="acc_test_001", period="30d")
        assert result["status"] == "not_implemented"


class TestAccountIdConstructor:
    def test_default_account_id_is_none(self) -> None:
        adapter = _StubAdapter()
        assert adapter._account_id is None

    def test_constructor_stores_account_id(self) -> None:
        adapter = _StubAdapter(account_id="acc_wechat_abc123")
        assert adapter._account_id == "acc_wechat_abc123"

    def test_constructor_accepts_none_explicitly(self) -> None:
        adapter = _StubAdapter(account_id=None)
        assert adapter._account_id is None
