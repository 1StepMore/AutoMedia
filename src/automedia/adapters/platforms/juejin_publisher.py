"""Juejin (掘金) publisher adapter — manual publish only.

Limitation
----------
Juejin does not provide a public API for automated content publishing.
Publishing is **manual-only**: a human must post through the Juejin
web editor or mobile app.

This is an **intentional divergence**.  See the F34 section of
``docs/dev/founder-expectations.md`` for the documented rationale.
"""

from __future__ import annotations

from typing import Any

import structlog

from automedia.adapters.base import BasePlatformAdapter, PublishResult
from automedia.core.credential_loader import load_credential_or_env

logger = structlog.get_logger(__name__)


class JuejinPublisher(BasePlatformAdapter):
    """Publish content to Juejin (掘金) — manual-only."""

    @property
    def platform_name(self) -> str:
        return "juejin"

    @property
    def enabled(self) -> bool:
        return bool(load_credential_or_env("JUJIN_COOKIE", "juejin_cookie"))

    def validate(self, artifact_dir: str) -> bool:
        cookie = load_credential_or_env("JUJIN_COOKIE", "juejin_cookie")
        if not cookie:
            logger.warning(
                "Juejin publisher disabled — credentials not set",
                platform="juejin",
            )
            return False
        logger.info("Juejin publisher validated", platform="juejin")
        return True

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        _ = artifact_dir, project, draft_only
        logger.info(
            "Juejin publish called — returning not_implemented",
            platform="juejin",
            reason="No public API available for automated publishing",
        )
        return {
            "status": "not_implemented",
            "platform": "juejin",
            "reason": "Manual publish only — Juejin has no public API. "
            "A human must post via the Juejin web editor or mobile app.",
        }
