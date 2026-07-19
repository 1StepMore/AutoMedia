"""Kuaishou (快手) publisher adapter — manual publish only.

Limitation
----------
Kuaishou does not provide a publicly accessible API for automated
content publishing.  Publishing is **manual-only**.

This is an **intentional divergence**.  See the F34 section of
``docs/dev/founder-expectations.md`` for the documented rationale.
"""

from __future__ import annotations

from typing import Any

import structlog

from automedia.adapters.base import BasePlatformAdapter, PublishResult
from automedia.core.credential_loader import load_credential_or_env

logger = structlog.get_logger(__name__)


class KuaishouPublisher(BasePlatformAdapter):
    """Publish content to Kuaishou (快手) — manual-only."""

    is_stub = True

    @property
    def platform_name(self) -> str:
        return "kuaishou"

    @property
    def enabled(self) -> bool:
        return bool(load_credential_or_env("KUAISHOU_COOKIE", "kuaishou_cookie"))

    def validate(self, artifact_dir: str) -> bool:
        cookie = load_credential_or_env("KUAISHOU_COOKIE", "kuaishou_cookie")
        if not cookie:
            logger.warning(
                "Kuaishou publisher disabled — credentials not set",
                platform="kuaishou",
            )
            return False
        logger.info("Kuaishou publisher validated", platform="kuaishou")
        return True

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        _ = artifact_dir, project, draft_only
        logger.info(
            "Kuaishou publish called — returning not_implemented",
            platform="kuaishou",
            reason="No public API available for automated publishing",
        )
        return {
            "status": "not_implemented",
            "platform": "kuaishou",
            "reason": "Manual publish only — Kuaishou has no public API. "
            "A human must post via the Kuaishou app.",
        }
