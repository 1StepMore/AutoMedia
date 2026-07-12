"""
.. deprecated::
   Use :class:`automedia.adapters.platforms.xiaohongshu_publisher.XiaohongshuPublisher`
   instead of this stub.  This module is kept for backward compatibility
   and will be removed in a future release.

Xiaohongshu adapter — stub for publishing to 小红书 (RED).
"""

from __future__ import annotations

from typing import Any


class XiaohongshuAdapter:
    """Stub adapter for publishing content to Xiaohongshu (小红书 / RED).

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
        """Stub: publish *content* to Xiaohongshu.

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
            "platform": "xiaohongshu",
        }
