"""API Key authentication for simple platforms."""

from __future__ import annotations

from structlog import get_logger

log = get_logger(__name__)


class ApiKeyAuth:
    """API Key based authentication handler."""

    @staticmethod
    def validate_key(api_key: str) -> bool:
        """Basic API key format validation.

        Checks:

        * Non-empty
        * Minimum length (8 chars)
        """
        if not api_key or not api_key.strip():
            return False
        return len(api_key.strip()) >= 8
