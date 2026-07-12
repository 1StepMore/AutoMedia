"""Tests for SessionManager — token caching, TTL refresh, rate-limit backoff."""

from __future__ import annotations

import time
import threading
from collections.abc import Iterator
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from automedia.accounts.models import HealthStatus, SessionToken
from automedia.accounts.session import CachedSession, SessionManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SYNC_THREAD = False


@pytest.fixture(autouse=True)
def _sync_threads() -> Iterator[None]:
    """Make ``threading.Thread.start`` call ``run()`` synchronously.

    This is the cleanest way to test async refresh behaviour without
    introducing real thread races.
    """
    global _SYNC_THREAD
    original = threading.Thread.start

    def _sync_start(self: threading.Thread) -> None:
        self.run()

    threading.Thread.start = _sync_start  # type: ignore[assignment]
    yield
    threading.Thread.start = original  # type: ignore[assignment]


def make_token(
    access_token: str = "test_access_token",
    expires_in_seconds: int | None = 3600,
    refresh_token: str | None = "test_refresh_token",
) -> SessionToken:
    """Create a :class:`SessionToken` with a deterministic expiry."""
    expires_at: datetime | None = None
    if expires_in_seconds is not None:
        expires_at = datetime.now() + timedelta(seconds=expires_in_seconds)
    return SessionToken(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


def expiry_time(delta: timedelta | None = None) -> datetime:
    """Return a future expiry time, optionally offset by *delta*."""
    base = datetime.now()
    if delta:
        base += delta
    return base


# ---------------------------------------------------------------------------
# Set / Get round-trip
# ---------------------------------------------------------------------------


class TestSetAndGetToken:
    """Basic cache round-trip and isolation."""

    def test_set_and_get(self) -> None:
        """A token set in the cache can be retrieved."""
        manager = SessionManager()
        token = make_token()
        manager.set_token("acc_1", token)

        result = manager.get_token("acc_1")
        assert result is token

    def test_get_returns_same_object(self) -> None:
        """Multiple calls to get_token return the same cached object."""
        manager = SessionManager()
        token = make_token()
        manager.set_token("acc_1", token)

        assert manager.get_token("acc_1") is token
        assert manager.get_token("acc_1") is token

    def test_different_accounts_isolated(self) -> None:
        """Tokens for different accounts do not interfere."""
        manager = SessionManager()
        token_a = make_token(access_token="token_a")
        token_b = make_token(access_token="token_b")
        manager.set_token("acc_a", token_a)
        manager.set_token("acc_b", token_b)

        assert manager.get_token("acc_a") is token_a
        assert manager.get_token("acc_b") is token_b

    def test_set_token_overwrites(self) -> None:
        """Setting a new token for an existing account overwrites the old one."""
        manager = SessionManager()
        old_token = make_token(access_token="old")
        new_token = make_token(access_token="new")
        manager.set_token("acc_1", old_token)
        manager.set_token("acc_1", new_token)

        result = manager.get_token("acc_1")
        assert result is new_token
        assert result is not old_token


# ---------------------------------------------------------------------------
# TTL-based expiry
# ---------------------------------------------------------------------------


class TestTTLExpiry:
    """Token expiration based on TTL."""

    def test_token_expired_returns_none(self) -> None:
        """get_token returns None after the token's TTL has elapsed."""
        manager = SessionManager()

        # Set cached_at 2 hours ago, expires_at 10 seconds after cached_at
        cached_at = datetime.now() - timedelta(hours=2)
        expires_at = cached_at + timedelta(seconds=10)

        token = SessionToken(access_token="expiring_soon", expires_at=expires_at)
        manager.set_token("acc_1", token)
        manager._sessions["acc_1"].cached_at = cached_at

        # Now elapsed (2h) > TTL (10s) → token is expired
        result = manager.get_token("acc_1")
        assert result is None

    def test_token_expired_with_refresh_fn(self) -> None:
        """When token is expired and *refresh_fn* is given, it is called."""
        manager = SessionManager()

        cached_at = datetime.now() - timedelta(hours=2)
        expires_at = cached_at + timedelta(seconds=10)

        token = SessionToken(access_token="expired_token", expires_at=expires_at)
        manager.set_token("acc_1", token)
        manager._sessions["acc_1"].cached_at = cached_at

        new_token = make_token(access_token="refreshed_token")
        refresh_fn = MagicMock(return_value=new_token)

        result = manager.get_token("acc_1", refresh_fn=refresh_fn)

        # Should return the newly refreshed token
        assert result is not None
        assert result.access_token == "refreshed_token"
        refresh_fn.assert_called_once()

    def test_token_not_yet_expired(self) -> None:
        """A token that is still within its TTL is returned as-is."""
        manager = SessionManager()
        token = make_token(expires_in_seconds=3600)
        manager.set_token("acc_1", token)

        result = manager.get_token("acc_1")
        assert result is token


# ---------------------------------------------------------------------------
# TTL threshold refresh
# ---------------------------------------------------------------------------


class TestTTLThresholdRefresh:
    """Async refresh triggered when token is past the threshold but not expired."""

    def test_threshold_triggers_async_refresh(self) -> None:
        """When elapsed >= threshold, a refresh is fired and old token is still returned."""
        manager = SessionManager(refresh_threshold=0.75)

        # Token valid for 120s, cached 90s ago → elapsed exactly at 75% threshold
        token = SessionToken(
            access_token="about_to_expire",
            expires_at=datetime.now() + timedelta(seconds=30),
        )
        manager.set_token("acc_1", token)
        manager._sessions["acc_1"].cached_at = datetime.now() - timedelta(seconds=90)

        new_token = make_token(access_token="fresh_token")
        refresh_fn = MagicMock(return_value=new_token)

        # Should return old token but trigger refresh (sync in test)
        result = manager.get_token("acc_1", refresh_fn=refresh_fn)

        assert result is token  # old token returned
        refresh_fn.assert_called_once()

        # Cache should now have the new token (refresh ran synchronously)
        updated = manager._sessions["acc_1"]
        assert updated.token.access_token == "fresh_token"
        assert updated.refresh_count == 1

    def test_threshold_does_not_fire_for_fresh_token(self) -> None:
        """A token far from its threshold is returned without triggering refresh."""
        manager = SessionManager(refresh_threshold=0.75)

        # Token valid for 1 hour, just cached → elapsed is near zero
        token = SessionToken(
            access_token="fresh",
            expires_at=datetime.now() + timedelta(hours=1),
        )
        manager.set_token("acc_1", token)
        manager._sessions["acc_1"].cached_at = datetime.now()

        refresh_fn = MagicMock()

        result = manager.get_token("acc_1", refresh_fn=refresh_fn)
        assert result is token
        refresh_fn.assert_not_called()

    def test_threshold_no_duplicate_refresh(self) -> None:
        """Multiple calls past threshold only fire one refresh."""
        manager = SessionManager(refresh_threshold=0.75)
        token = SessionToken(
            access_token="stale",
            expires_at=datetime.now() + timedelta(seconds=30),
        )
        manager.set_token("acc_1", token)
        manager._sessions["acc_1"].cached_at = datetime.now() - timedelta(seconds=90)

        new_token = make_token(access_token="refreshed")
        refresh_fn = MagicMock(return_value=new_token)

        # First call — triggers refresh
        r1 = manager.get_token("acc_1", refresh_fn=refresh_fn)
        assert r1 is token

        # Second call — should NOT trigger a second refresh because is_refreshing is True
        # (After sync mock, is_refreshing is already False, but the second call sees
        #  the new token which is not past threshold, so it won't refresh anyway)
        r2 = manager.get_token("acc_1", refresh_fn=refresh_fn)
        assert r2 is not None
        assert r2.access_token == "refreshed"  # new token

        # Only one refresh call
        refresh_fn.assert_called_once()

    def test_token_without_expiry_not_refreshed(self) -> None:
        """A token with no expires_at is never stale and never triggers refresh."""
        manager = SessionManager()
        token = SessionToken(
            access_token="perpetual",
            expires_at=None,
        )
        manager.set_token("acc_1", token)
        manager._sessions["acc_1"].cached_at = datetime.now() - timedelta(days=365)

        refresh_fn = MagicMock()

        result = manager.get_token("acc_1", refresh_fn=refresh_fn)
        assert result is token
        refresh_fn.assert_not_called()


# ---------------------------------------------------------------------------
# Rate-limit cooldown
# ---------------------------------------------------------------------------


class TestRateLimitCooldown:
    """Rate-limit backoff behaviour."""

    def test_cooldown_blocks_and_returns_stale_token(self) -> None:
        """After handle_rate_limit, get_token returns stale token with a warning."""
        manager = SessionManager()
        token = make_token()
        manager.set_token("acc_1", token)

        # Apply rate limit with a long cooldown
        manager.handle_rate_limit("acc_1", retry_after=99999)

        # get_token should return stale token (not block)
        result = manager.get_token("acc_1")
        assert result is token

    def test_cooldown_no_token_returns_none(self) -> None:
        """When in cooldown and no cached token, get_token returns None."""
        manager = SessionManager()
        manager.handle_rate_limit("acc_1", retry_after=99999)

        result = manager.get_token("acc_1")
        assert result is None

    def test_cooldown_expires_naturally(self) -> None:
        """After cooldown expires, normal token retrieval works."""
        manager = SessionManager()
        token = make_token()
        manager.set_token("acc_1", token)

        # Apply a very short cooldown
        manager.handle_rate_limit("acc_1", retry_after=0.01)

        # Wait for cooldown to expire
        time.sleep(0.05)

        result = manager.get_token("acc_1")
        assert result is token

    def test_handle_rate_limit_logs_warning(self) -> None:
        """handle_rate_limit emits a warning log."""
        manager = SessionManager()

        with patch("automedia.accounts.session.logger") as mock_logger:
            manager.handle_rate_limit("acc_1", retry_after=60.0)

            mock_logger.warning.assert_called_once()
            args, _ = mock_logger.warning.call_args
            assert "acc_1" in args[1]


# ---------------------------------------------------------------------------
# Invalidate
# ---------------------------------------------------------------------------


class TestInvalidate:
    """Cache invalidation."""

    def test_invalidate_removes_token(self) -> None:
        """After invalidate, get_token returns None (unless refresh_fn provided)."""
        manager = SessionManager()
        token = make_token()
        manager.set_token("acc_1", token)

        manager.invalidate("acc_1")

        result = manager.get_token("acc_1")
        assert result is None

    def test_invalidate_removes_cooldown(self) -> None:
        """Invalidate also clears any rate-limit cooldown."""
        manager = SessionManager()
        token = make_token()
        manager.set_token("acc_1", token)
        manager.handle_rate_limit("acc_1", retry_after=99999)

        # Verify cooldown is active
        assert manager._is_in_cooldown("acc_1") is True

        manager.invalidate("acc_1")

        # Cooldown cleared
        assert manager._is_in_cooldown("acc_1") is False

    def test_invalidate_only_target_account(self) -> None:
        """Invalidating one account does not affect others."""
        manager = SessionManager()
        token_a = make_token(access_token="a")
        token_b = make_token(access_token="b")
        manager.set_token("acc_a", token_a)
        manager.set_token("acc_b", token_b)

        manager.invalidate("acc_a")

        assert manager.get_token("acc_a") is None
        assert manager.get_token("acc_b") is token_b

    def test_invalidate_nonexistent_does_not_raise(self) -> None:
        """Invalidating a non-existent account is a no-op."""
        manager = SessionManager()
        # Should not raise
        manager.invalidate("nonexistent")


# ---------------------------------------------------------------------------
# Missing token scenarios
# ---------------------------------------------------------------------------


class TestMissingToken:
    """Behaviour when no token is cached."""

    def test_no_refresh_fn_returns_none(self) -> None:
        """With no cached token and no refresh_fn, get_token returns None."""
        manager = SessionManager()
        result = manager.get_token("acc_1")
        assert result is None

    def test_with_refresh_fn_calls_and_caches(self) -> None:
        """With refresh_fn, get_token calls it, caches the result, and returns it."""
        manager = SessionManager()
        new_token = make_token(access_token="brand_new")
        refresh_fn = MagicMock(return_value=new_token)

        result = manager.get_token("acc_1", refresh_fn=refresh_fn)

        assert result is not None
        assert result.access_token == "brand_new"
        refresh_fn.assert_called_once()

        # Verify it was cached
        cached = manager._sessions.get("acc_1")
        assert cached is not None
        assert cached.token.access_token == "brand_new"
        assert cached.refresh_count == 1

    def test_refresh_fn_failure_still_returns_none(self) -> None:
        """When refresh_fn raises, get_token returns None and logs error."""
        manager = SessionManager()

        def failing_refresh() -> SessionToken:
            msg = "Network error"
            raise ConnectionError(msg)

        with patch("automedia.accounts.session.logger") as mock_logger:
            result = manager.get_token("acc_1", refresh_fn=failing_refresh)

            assert result is None
            mock_logger.error.assert_called_once()
            args, _ = mock_logger.error.call_args
            assert "acc_1" in args[1]


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Health monitoring via check_health()."""

    def test_valid_token_returns_healthy(self) -> None:
        """A valid, non-expired token returns healthy=True."""
        manager = SessionManager()
        token = make_token(expires_in_seconds=3600)
        manager.set_token("acc_1", token)

        status = manager.check_health("acc_1")
        assert status.healthy is True
        assert status.status_message == "Session valid"

    def test_expired_token_returns_unhealthy(self) -> None:
        """An expired token returns healthy=False."""
        manager = SessionManager()

        cached_at = datetime.now() - timedelta(hours=2)
        expires_at = cached_at + timedelta(seconds=10)

        token = SessionToken(access_token="expired", expires_at=expires_at)
        manager.set_token("acc_1", token)
        manager._sessions["acc_1"].cached_at = cached_at

        status = manager.check_health("acc_1")
        assert status.healthy is False
        assert "expired" in status.status_message.lower()

    def test_no_token_returns_unhealthy(self) -> None:
        """No cached session returns healthy=False."""
        manager = SessionManager()

        status = manager.check_health("nonexistent")
        assert status.healthy is False
        assert status.status_message == "No cached session"

    def test_rate_limited_token_returns_unhealthy(self) -> None:
        """A token in cooldown returns healthy=False."""
        manager = SessionManager()
        token = make_token()
        manager.set_token("acc_1", token)
        manager.handle_rate_limit("acc_1", retry_after=99999)

        status = manager.check_health("acc_1")
        assert status.healthy is False
        assert "rate" in status.status_message.lower()

    def test_health_status_contains_timestamp(self) -> None:
        """HealthStatus.last_checked is populated."""
        manager = SessionManager()
        token = make_token()
        manager.set_token("acc_1", token)

        status = manager.check_health("acc_1")
        assert isinstance(status.last_checked, datetime)

    def test_no_expiry_returns_healthy(self) -> None:
        """A token with no expires_at is always healthy."""
        manager = SessionManager()
        token = SessionToken(access_token="perpetual", expires_at=None)
        manager.set_token("acc_1", token)

        status = manager.check_health("acc_1")
        assert status.healthy is True

    def test_health_status_is_healthstatus_instance(self) -> None:
        """check_health returns a HealthStatus object."""
        manager = SessionManager()
        result = manager.check_health("acc_1")
        assert isinstance(result, HealthStatus)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and defensive behaviour."""

    def test_custom_refresh_threshold(self) -> None:
        """A custom refresh threshold changes when async refresh triggers."""
        manager = SessionManager(refresh_threshold=0.5)

        token = SessionToken(
            access_token="half_life",
            expires_at=datetime.now() + timedelta(seconds=50),
        )
        manager.set_token("acc_1", token)
        manager._sessions["acc_1"].cached_at = datetime.now() - timedelta(seconds=50)
        # TTL = 100s, elapsed = 50s → at 50% threshold, triggers refresh

        new_token = make_token(access_token="new_half")
        refresh_fn = MagicMock(return_value=new_token)

        result = manager.get_token("acc_1", refresh_fn=refresh_fn)
        assert result is token  # old token returned
        refresh_fn.assert_called_once()

    def test_cached_session_dataclass(self) -> None:
        """CachedSession fields are correctly initialised."""
        token = make_token()
        session = CachedSession(token=token)

        assert session.token is token
        assert isinstance(session.cached_at, datetime)
        assert session.refresh_count == 0
        assert session.is_refreshing is False

    def test_get_token_refresh_fn_none_with_stale_token(self) -> None:
        """No refresh_fn with a stale token returns None (no way to refresh)."""
        manager = SessionManager()

        cached_at = datetime.now() - timedelta(hours=2)
        expires_at = cached_at + timedelta(seconds=10)

        token = SessionToken(access_token="stale", expires_at=expires_at)
        manager.set_token("acc_1", token)
        manager._sessions["acc_1"].cached_at = cached_at

        # Token is expired, no refresh_fn → None
        result = manager.get_token("acc_1")
        assert result is None

    def test_lock_is_per_account(self) -> None:
        """Each account gets its own lock — different accounts are independent."""
        manager = SessionManager()
        lock_a = manager._get_lock("acc_a")
        lock_b = manager._get_lock("acc_b")

        assert lock_a is not lock_b
        assert isinstance(lock_a, threading.Lock)

    def test_get_lock_is_reentrant(self) -> None:
        """Calling _get_lock for the same account returns the same lock."""
        manager = SessionManager()
        lock_1 = manager._get_lock("acc_1")
        lock_2 = manager._get_lock("acc_1")

        assert lock_1 is lock_2

    def test_initial_cooldown_dict_empty(self) -> None:
        """Fresh SessionManager has no cooldowns."""
        manager = SessionManager()
        assert manager._cooldowns == {}
