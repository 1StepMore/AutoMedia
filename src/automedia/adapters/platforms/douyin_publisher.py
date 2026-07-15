"""Douyin (抖音) publisher adapter — manual publish only.

Limitation
----------
Douyin does **not** provide a public API for automated content
publishing without government/media entity qualification.
Publishing is **manual-only**: a human must post through
the Douyin app or web creator portal.

This is an **intentional divergence**.  See the F34 section of
``docs/dev/founder-expectations.md`` for the documented rationale.
"""

from __future__ import annotations

from typing import Any

import structlog

from automedia.adapters.base import BasePlatformAdapter, PublishResult
from automedia.core.credential_loader import load_credential_or_env

logger = structlog.get_logger(__name__)


class DouyinPublisher(BasePlatformAdapter):
    """Publish content to Douyin (抖音) — manual-only."""

    @property
    def platform_name(self) -> str:
        return "douyin"

    @property
    def enabled(self) -> bool:
        return bool(load_credential_or_env("DOUYIN_COOKIE", "douyin_cookie"))

    def validate(self, artifact_dir: str) -> bool:
        cookie = load_credential_or_env("DOUYIN_COOKIE", "douyin_cookie")
        if not cookie:
            logger.warning(
                "Douyin publisher disabled — credentials not set",
                platform="douyin",
            )
            return False
        logger.info("Douyin publisher validated", platform="douyin")
        return True

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        _ = artifact_dir, project, draft_only
        logger.info(
            "Douyin publish called — returning not_implemented",
            platform="douyin",
            reason="No public API available for automated publishing without government/media qualification",
        )
        return {
            "status": "not_implemented",
            "platform": "douyin",
            "reason": "Manual publish only — Douyin has no publicly accessible API for automated publishing. "
            "A human must post via the Douyin app or web creator portal.",
        }
