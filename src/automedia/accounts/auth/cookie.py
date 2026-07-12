"""Cookie-based authentication for platforms without OAuth."""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


class CookieAuth:
    """Cookie-based authentication.

    Validates cookies by calling a platform-specific health check
    function, and provides a fallback for manual cookie refresh.
    """

    @staticmethod
    def validate_cookie(
        cookie_str: str,
        health_check_fn: Callable[[str], bool] | None = None,
    ) -> bool:
        """Check if a cookie string appears valid.

        When *health_check_fn* is provided, calls it with the cookie
        to verify it's still valid against the platform.

        When no health check is available, performs basic format validation:

        * Non-empty
        * Contains ``=`` (key=value pairs)
        """
        if not cookie_str or not cookie_str.strip():
            return False

        if health_check_fn:
            try:
                return health_check_fn(cookie_str)
            except Exception:
                logger.warning("Cookie health check failed", exc_info=True)
                return False

        # Basic format check: should contain at least one key=value pair
        return "=" in cookie_str
