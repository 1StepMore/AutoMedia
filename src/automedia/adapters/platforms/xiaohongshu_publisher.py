"""Xiaohongshu (小红书 / RED) publisher adapter — manual publish only.

Limitation
----------
Xiaohongshu does **not** provide a public API for automated content
publishing.  Publishing is **manual-only**: a human must post through
the RED mobile app or web creator portal.

The adapter serves as a placeholder: it validates credentials, documents
the requirement, and returns ``"not_implemented"``.  No automated publish
attempt is made.

This is an **intentional divergence**.  See the F32 section of
``docs/dev/founder-expectations.md`` for the documented rationale.

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
    """Publish content to Xiaohongshu (小红书 / RED) — manual-only.

    .. caution::

       Xiaohongshu has **no public API**.  Publishing is **manual-only**:
       human intervention through the RED mobile app or web creator
       portal is required.  This adapter is a placeholder that validates
       credentials and documents the requirement.
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

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        """Return ``"not_implemented"`` — Xiaohongshu is manual-only.

        This is an intentional divergence: the platform has no public
        API, so the adapter never attempts automated publishing.
        """
        _ = artifact_dir, project, draft_only  # mark parameters as used
        logger.info(
            "Xiaohongshu publish called — returning not_implemented",
            platform="xiaohongshu",
            reason="No public API available for automated publishing",
        )
        return {
            "status": "not_implemented",
            "platform": "xiaohongshu",
            "reason": "Manual publish only — Xiaohongshu has no public API. "
            "A human must post via the RED mobile app or web creator portal.",
        }
