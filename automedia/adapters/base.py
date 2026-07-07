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
