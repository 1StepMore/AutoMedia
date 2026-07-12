"""Base platform adapter — abstract interface for all publish targets."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BasePlatformAdapter(ABC):
    """Subclass this to implement a concrete platform publisher/notifier.

    Each adapter must define:
    - ``platform_name`` — a unique, human-readable identifier
    - ``publish()`` — the actual publishing logic
    - ``validate()`` — pre-flight checks (env vars, files, credentials)
    """

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self, account_id: str | None = None) -> None:
        """Initialize the adapter with an optional PRD-4 account ID.

        Parameters
        ----------
        account_id:
            Optional account identifier for account-aware publishing.
        """
        self._account_id: str | None = account_id

    # ------------------------------------------------------------------
    # Read-only metadata
    # ------------------------------------------------------------------
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform identifier (e.g. ``"wechat"``)."""
        ...

    # ------------------------------------------------------------------
    # Enabling
    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        """Whether this adapter is enabled by configuration.

        The default implementation checks the project config dict passed
        to ``publish()``; subclasses may override with a static check.
        """
        return True

    # ------------------------------------------------------------------
    # Core contract
    # ------------------------------------------------------------------
    @abstractmethod
    def publish(self, artifact_dir: str, project: dict[str, Any]) -> dict[str, Any]:
        """Publish an artifact directory to this platform.

        Parameters
        ----------
        artifact_dir:
            Path to the rendered artifact directory.
        project:
            Full project dict (topic, metadata, config, …).

        Returns
        -------
        dict
            A result dict that **must** include at least ``"status"``
            (``"ok"`` or ``"error"``).  Additional keys are platform-
            specific.
        """
        ...

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self, artifact_dir: str) -> bool:
        """Check that pre-conditions are satisfied.

        Override in subclasses to verify environment variables,
        credential files, network reachability, *etc.*
        """
        return True

    # ------------------------------------------------------------------
    # PRD-4: Session & health management (concrete defaults)
    # ------------------------------------------------------------------

    def authenticate(self, account_id: str | None = None) -> dict[str, Any]:
        """Authenticate with the platform.

        PRD-4: Override this to use SessionManager for token-based auth.
        Default returns ``"not_implemented"`` for backward compatibility.

        Parameters
        ----------
        account_id:
            Optional account identifier to authenticate as.

        Returns
        -------
        dict
            Result dict with at least ``"status"``.
        """
        return {"status": "not_implemented", "reason": "auth not implemented"}

    def refresh_session(self, account_id: str) -> dict[str, Any]:
        """Refresh the platform session.

        PRD-4: Override this to implement token refresh via SessionManager.
        Default returns ``"not_implemented"`` for backward compatibility.

        Parameters
        ----------
        account_id:
            The account whose session to refresh.

        Returns
        -------
        dict
            Result dict with at least ``"status"``.
        """
        return {"status": "not_implemented", "reason": "session refresh not implemented"}

    def check_health(self, account_id: str | None = None) -> dict[str, Any]:
        """Check if the platform session is healthy.

        PRD-4: Override this to verify credentials are still valid.
        Default returns ``"not_implemented"`` for backward compatibility.

        Parameters
        ----------
        account_id:
            Optional account to health-check.

        Returns
        -------
        dict
            Result dict with ``"status"``, ``"healthy"``, and ``"reason"``.
        """
        return {
            "status": "not_implemented",
            "healthy": False,
            "reason": "health check not implemented",
        }

    def get_analytics(self, account_id: str, period: str = "7d") -> dict[str, Any]:
        """Get platform analytics for an account.

        PRD-4: Override this to return follower count, engagement rate, etc.
        Default returns ``"not_implemented"`` for backward compatibility.

        Parameters
        ----------
        account_id:
            The account to fetch analytics for.
        period:
            Analysis period (e.g. ``"7d"``, ``"30d"``).

        Returns
        -------
        dict
            Result dict with at least ``"status"``.
        """
        return {"status": "not_implemented", "reason": "analytics not implemented"}
