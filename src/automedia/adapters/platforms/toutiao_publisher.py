"""Toutiao (头条) publisher adapter — manual publish only.

Limitation
----------
Toutiao (by ByteDance) does not provide a publicly accessible API for
automated content publishing.  Publishing is **manual-only**.

This is an **intentional divergence**.  See the F34 section of
``docs/dev/founder-expectations.md`` for the documented rationale.
"""

from __future__ import annotations

from typing import Any

import structlog

from automedia.adapters.base import BasePlatformAdapter, PublishResult
from automedia.core.credential_loader import load_credential_or_env

logger = structlog.get_logger(__name__)


class ToutiaoPublisher(BasePlatformAdapter):
    """Publish content to Toutiao (头条) — manual-only."""

    is_stub = True

    @property
    def platform_name(self) -> str:
        return "toutiao"

    @property
    def enabled(self) -> bool:
        return bool(load_credential_or_env("TOUTIAO_COOKIE", "toutiao_cookie"))

    def validate(self, artifact_dir: str) -> bool:
        cookie = load_credential_or_env("TOUTIAO_COOKIE", "toutiao_cookie")
        if not cookie:
            logger.warning(
                "Toutiao publisher disabled — credentials not set",
                platform="toutiao",
            )
            return False
        logger.info("Toutiao publisher validated", platform="toutiao")
        return True

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        _ = artifact_dir, project, draft_only
        logger.info(
            "Toutiao publish called — returning not_implemented",
            platform="toutiao",
            reason="No public API available for automated publishing",
        )
        return {
            "status": "not_implemented",
            "platform": "toutiao",
            "reason": "Manual publish only — Toutiao has no public API. "
            "A human must post via the Toutiao web or mobile interface.",
        }
