"""SessionManager — token caching, TTL refresh, rate-limit backoff."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from automedia.accounts.models import HealthStatus, SessionToken

logger = logging.getLogger(__name__)


@dataclass
class CachedSession:
    """An in-memory cached session with TTL tracking."""

    token: SessionToken
    cached_at: datetime = field(default_factory=datetime.now)
    refresh_count: int = 0
    is_refreshing: bool = False


class SessionManager:
    """Manages platform sessions with token caching and TTL-aware refresh.

    Features:
    - In-memory token cache per account_id
    - TTL-aware refresh at configurable threshold (default 75%)
    - Per-account threading.Lock for concurrent safety
    - Rate-limit backoff with cooldown
    - Health monitoring
    """

    def __init__(self, refresh_threshold: float = 0.75) -> None:
        """Initialize the session manager.

        Args:
            refresh_threshold: Fraction of TTL at which to refresh (0.0-1.0).
                Default 0.75 = refresh when 75% of TTL has elapsed.
        """
        self._sessions: dict[str, CachedSession] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._cooldowns: dict[str, float] = {}  # account_id → unix monotonic time
        self._lock: threading.Lock = threading.Lock()  # protects _locks dict
        self._refresh_threshold: float = refresh_threshold

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_lock(self, account_id: str) -> threading.Lock:
        """Get or create a per-account lock."""
        with self._lock:
            if account_id not in self._locks:
                self._locks[account_id] = threading.Lock()
            return self._locks[account_id]

    def _is_in_cooldown(self, account_id: str) -> bool:
        """Check if account is in rate-limit cooldown."""
        cooldown_until = self._cooldowns.get(account_id)
        if cooldown_until is None:
            return False
        if time.monotonic() >= cooldown_until:
            _ = self._cooldowns.pop(account_id, None)
            return False

    # ------------------------------------------------------------------
    # Rate-limit handling
    # ------------------------------------------------------------------
        return True

    # ------------------------------------------------------------------
    # Rate-limit handling
    # ------------------------------------------------------------------

    def handle_rate_limit(self, account_id: str, retry_after: float = 60.0) -> None:
        """Mark an account as rate-limited with a cooldown period."""
        self._cooldowns[account_id] = time.monotonic() + retry_after
        logger.warning(
            "Rate-limit applied to %s, cooldown %ss",
            account_id,
            retry_after,
        )

    # ------------------------------------------------------------------
    # Cache operations
    # ------------------------------------------------------------------

    def set_token(self, account_id: str, token: SessionToken) -> None:
        """Set or update a cached token for an account."""
        self._sessions[account_id] = CachedSession(token=token)
        logger.debug("Token cached for %s (expires at %s)", account_id, token.expires_at)

    def invalidate(self, account_id: str) -> None:
        """Invalidate cached token for an account."""
        _ = self._sessions.pop(account_id, None)
        _ = self._cooldowns.pop(account_id, None)
        logger.debug("Session invalidated for %s", account_id)

    def get_token(
        self,
        account_id: str,
        refresh_fn: Callable[[], SessionToken] | None = None,
    ) -> SessionToken | None:
        """Get a valid token, optionally refreshing if stale.

        Returns None if no token is cached and no refresh_fn is provided.
        If token is past refresh_threshold, triggers async refresh via refresh_fn.
        If token is expired, blocks until refresh completes.
        If account is in cooldown, returns the stale token (with a warning).

        Thread-safe: per-account lock prevents concurrent refresh.
        """
        # Check cooldown
        if self._is_in_cooldown(account_id):
            cached = self._sessions.get(account_id)
            if cached:
                logger.warning("Returning stale token for %s (in cooldown)", account_id)
                return cached.token
            return None

        cached = self._sessions.get(account_id)
        now = datetime.now()

        # No cached token — try to refresh
        if cached is None:
            if refresh_fn:
                return self._refresh(account_id, refresh_fn)
            return None

        # Check expiry
        if cached.token.expires_at:
            ttl = (cached.token.expires_at - cached.cached_at).total_seconds()
            elapsed = (now - cached.cached_at).total_seconds()

            if ttl > 0 and elapsed >= ttl:
                # Token expired — refresh (blocking)
                if refresh_fn:
                    return self._refresh(account_id, refresh_fn)
                return None

            if ttl > 0 and elapsed >= ttl * self._refresh_threshold and refresh_fn and not cached.is_refreshing:
                # Past threshold — refresh if not already refreshing
                    # Fire async refresh in background
                    cached.is_refreshing = True
                    t = threading.Thread(
                        target=self._refresh,
                        args=(account_id, refresh_fn),
                        daemon=True,
                    )
                    t.start()

        return cached.token

    def _refresh(
        self,
        account_id: str,
        refresh_fn: Callable[[], SessionToken],
    ) -> SessionToken | None:
        """Refresh token with per-account locking."""
        lock = self._get_lock(account_id)
        with lock:
            try:
                new_token = refresh_fn()
                self.set_token(account_id, new_token)
                cached = self._sessions.get(account_id)
                if cached:
                    cached.is_refreshing = False
                    cached.refresh_count += 1
                return new_token
            except Exception as e:
                logger.error("Token refresh failed for %s: %s", account_id, e)
                cached = self._sessions.get(account_id)
                if cached:
                    cached.is_refreshing = False
                return None

    # ------------------------------------------------------------------
    # Health monitoring
    # ------------------------------------------------------------------

    def check_health(self, account_id: str) -> HealthStatus:
        """Check if an account's session is healthy.

        Returns Healthy if a valid (non-expired) token is cached.
        Returns Unhealthy if token is expired or not cached.
        """
        cached = self._sessions.get(account_id)
        now = datetime.now()

        if cached is None:
            return HealthStatus(
                healthy=False,
                status_message="No cached session",
                last_checked=now,
            )

        if cached.token.expires_at and now >= cached.token.expires_at:
            return HealthStatus(
                healthy=False,
                status_message="Token expired",
                last_checked=now,
            )

        if self._is_in_cooldown(account_id):
            return HealthStatus(
                healthy=False,
                status_message="Rate-limited (in cooldown)",
                last_checked=now,
            )

        return HealthStatus(
            healthy=True,
            status_message="Session valid",
            last_checked=now,
        )


__all__ = [
    "CachedSession",
    "SessionManager",
]
