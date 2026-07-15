"""Xiaohongshu (小红书 / RED) publisher adapter.

Limitation
----------
Xiaohongshu does **not** provide a public API for automated content
publishing.  The adapter therefore documents the requirement and returns
a ``"not_implemented"`` status — manual posting via the RED mobile
app or web creator portal is required.

Credentials are resolved via :func:`load_credential_or_env` with
backward-compatible support for the legacy ``XHS_COOKIE`` environment
variable and the standard ``AUTOMEDIA_XIAOHONGSHU_COOKIE`` credential.
"""

from __future__ import annotations

from typing import Any

import structlog

from automedia.adapters.base import BasePlatformAdapter, PublishResult
from automedia.core.credential_loader import load_credential_or_env

logger = structlog.get_logger(__name__)


class XiaohongshuPublisher(BasePlatformAdapter):
    """Publish content to Xiaohongshu (小红书 / RED).

    .. caution::

       Xiaohongshu has **no public API**.  Publishing requires manual
       intervention through the RED mobile app or web creator portal.
       This adapter serves as a placeholder and dependency tracker.
    """

    @property
    def platform_name(self) -> str:
        return "xiaohongshu"

    @property
    def enabled(self) -> bool:
        """Only enabled when Xiaohongshu credentials are available."""
        return bool(load_credential_or_env("XHS_COOKIE", "xiaohongshu_cookie"))

    def validate(self, artifact_dir: str) -> bool:
        """Check that Xiaohongshu credentials are non-empty."""
        cookie = load_credential_or_env("XHS_COOKIE", "xiaohongshu_cookie")
        if not cookie:
            logger.warning(
                "Xiaohongshu publisher disabled — credentials not set",
                platform="xiaohongshu",
            )
            return False
        logger.info(
            "Xiaohongshu publisher validated",
            platform="xiaohongshu",
        )
        return True

    def publish(self, artifact_dir: str, project: dict[str, Any]) -> PublishResult:
        """Report that automated publishing is unavailable for Xiaohongshu.

        Returns a ``"not_implemented"`` status explaining that RED
        has no public API for automated posting.
        """
        _ = artifact_dir, project  # mark parameters as used
        logger.info(
            "Xiaohongshu publish called — returning not_implemented",
            platform="xiaohongshu",
            reason="No public API available for automated publishing",
        )
        return {
            "status": "not_implemented",
            "platform": "xiaohongshu",
            "reason": "Xiaohongshu has no public API for automated publishing. "
            "Manual posting required.",
        }
