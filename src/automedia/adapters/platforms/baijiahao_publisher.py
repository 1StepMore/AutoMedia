"""Baijiahao (百家号) publisher adapter — manual publish only.

Limitation
----------
Baijiahao (Baidu's content platform) does not provide a publicly
accessible API for automated content publishing.  Publishing is
**manual-only**.

This is an **intentional divergence**.  See the F34 section of
``docs/dev/founder-expectations.md`` for the documented rationale.
"""

from __future__ import annotations

from typing import Any

import structlog

from automedia.adapters.base import BasePlatformAdapter, PublishResult
from automedia.core.credential_loader import load_credential_or_env

logger = structlog.get_logger(__name__)


class BaijiahaoPublisher(BasePlatformAdapter):
    """Publish content to Baijiahao (百家号) — manual-only."""

    @property
    def platform_name(self) -> str:
        return "baijiahao"

    @property
    def enabled(self) -> bool:
        return bool(load_credential_or_env("BAIJIAHAO_COOKIE", "baijiahao_cookie"))

    def validate(self, artifact_dir: str) -> bool:
        cookie = load_credential_or_env("BAIJIAHAO_COOKIE", "baijiahao_cookie")
        if not cookie:
            logger.warning(
                "Baijiahao publisher disabled — credentials not set",
                platform="baijiahao",
            )
            return False
        logger.info("Baijiahao publisher validated", platform="baijiahao")
        return True

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        _ = artifact_dir, project, draft_only
        logger.info(
            "Baijiahao publish called — returning not_implemented",
            platform="baijiahao",
            reason="No public API available for automated publishing",
        )
        return {
            "status": "not_implemented",
            "platform": "baijiahao",
            "reason": "Manual publish only — Baijiahao has no public API. "
            "A human must post via the Baijiahao web platform.",
        }
