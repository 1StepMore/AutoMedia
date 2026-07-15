"""Bilibili (哔哩哔哩) publisher adapter — manual publish only.

Limitation
----------
Bilibili's Open Platform API requires enterprise registration and
HMAC-SHA256 request signing.  Automated publishing without enterprise
qualification is not supported.  Publishing is **manual-only**.

This is an **intentional divergence**.  See the F34 section of
``docs/dev/founder-expectations.md`` for the documented rationale.
"""

from __future__ import annotations

from typing import Any

import structlog

from automedia.adapters.base import BasePlatformAdapter, PublishResult
from automedia.core.credential_loader import load_credential_or_env

logger = structlog.get_logger(__name__)


class BilibiliPublisher(BasePlatformAdapter):
    """Publish content to Bilibili (哔哩哔哩) — manual-only."""

    @property
    def platform_name(self) -> str:
        return "bilibili"

    @property
    def enabled(self) -> bool:
        return bool(load_credential_or_env("BILIBILI_COOKIE", "bilibili_cookie"))

    def validate(self, artifact_dir: str) -> bool:
        cookie = load_credential_or_env("BILIBILI_COOKIE", "bilibili_cookie")
        if not cookie:
            logger.warning(
                "Bilibili publisher disabled — credentials not set",
                platform="bilibili",
            )
            return False
        logger.info("Bilibili publisher validated", platform="bilibili")
        return True

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        _ = artifact_dir, project, draft_only
        logger.info(
            "Bilibili publish called — returning not_implemented",
            platform="bilibili",
            reason="Bilibili requires enterprise registration for API access",
        )
        return {
            "status": "not_implemented",
            "platform": "bilibili",
            "reason": "Manual publish only — Bilibili requires enterprise registration for API access. "
            "A human must post via the Bilibili web uploader.",
        }
