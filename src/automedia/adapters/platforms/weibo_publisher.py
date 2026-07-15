"""Weibo (微博) publisher adapter — manual publish only.

Limitation
----------
Weibo's Open Platform REST API supports text and image posting via
OAuth2, but does **not** provide a video upload/publish REST endpoint
for server-side use.  Video publishing requires the mobile SDK or
browser automation.  Full content automation is **manual-only**.

This is an **intentional divergence**.  See the F34 section of
``docs/dev/founder-expectations.md`` for the documented rationale.
"""

from __future__ import annotations

from typing import Any

import structlog

from automedia.adapters.base import BasePlatformAdapter, PublishResult
from automedia.core.credential_loader import load_credential_or_env

logger = structlog.get_logger(__name__)


class WeiboPublisher(BasePlatformAdapter):
    """Publish content to Weibo (微博) — manual-only."""

    @property
    def platform_name(self) -> str:
        return "weibo"

    @property
    def enabled(self) -> bool:
        return bool(load_credential_or_env("WEIBO_COOKIE", "weibo_cookie"))

    def validate(self, artifact_dir: str) -> bool:
        cookie = load_credential_or_env("WEIBO_COOKIE", "weibo_cookie")
        if not cookie:
            logger.warning(
                "Weibo publisher disabled — credentials not set",
                platform="weibo",
            )
            return False
        logger.info("Weibo publisher validated", platform="weibo")
        return True

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        _ = artifact_dir, project, draft_only
        logger.info(
            "Weibo publish called — returning not_implemented",
            platform="weibo",
            reason="Weibo has no video publish REST API for server-side use",
        )
        return {
            "status": "not_implemented",
            "platform": "weibo",
            "reason": "Manual publish only — Weibo's API does not support automated video publishing. "
            "A human must post via the Weibo web or mobile interface.",
        }
