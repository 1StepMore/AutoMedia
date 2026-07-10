"""Zhihu draft adapter — stub for saving drafts to Zhihu (知乎)."""

from __future__ import annotations

from typing import Any


class ZhihuDraftAdapter:
    """Stub adapter for publishing drafts to Zhihu (知乎).

    Parameters
    ----------
    config:
        Platform configuration dict.  The adapter is enabled when
        ``config.get("enabled")`` is truthy.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Enabling
    # ------------------------------------------------------------------

    def enabled(self) -> bool:
        """Return whether this adapter is enabled by configuration."""
        return bool(self._config.get("enabled", False))

    # ------------------------------------------------------------------
    # Core contract
    # ------------------------------------------------------------------

    def publish(self, content: dict[str, Any]) -> dict[str, Any]:
        """Stub: publish *content* as a Zhihu draft.

        Parameters
        ----------
        content:
            Dict with keys such as ``"title"``, ``"body"``,
            ``"images"``, *etc.*

        Returns
        -------
        dict
            A result dict with at least ``"status"``.
        """
        _ = content  # mark as used
        return {
            "status": "not_implemented",
            "platform": "zhihu_draft",
        }
