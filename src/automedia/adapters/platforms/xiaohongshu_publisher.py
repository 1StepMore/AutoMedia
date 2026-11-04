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

import os
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

    is_stub = True

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
        """Publish via browser automation or return ``"not_implemented"``.

        Two modes, selected by ``platforms.xiaohongshu.publish_mode``
        (``.automedia/config.yaml``):

        - ``manual`` (default): the historical behaviour — Xiaohongshu has no
          public API, so the adapter returns ``not_implemented`` and a human
          posts via the creator portal.
        - ``browser`` (#353): drive the creator publish page with Playwright
          using the captured login session, fill title/body/images, and STOP
          before the publish confirmation (``ready_for_confirmation``) — the
          human reviews the screenshot and clicks publish. Never automated.
        """
        mode_cfg = ((project.get("config") or {}).get("platforms") or {}).get("xiaohongshu") or {}
        publish_mode = str(mode_cfg.get("publish_mode", "manual"))
        if publish_mode != "browser":
            _ = artifact_dir, draft_only  # mark parameters as used
            logger.info(
                "Xiaohongshu publish called — returning not_implemented",
                platform="xiaohongshu",
                reason="No public API available for automated publishing",
            )
            return {
                "status": "not_implemented",
                "platform": "xiaohongshu",
                "reason": "Manual publish only — Xiaohongshu has no public API. "
                "A human must post via the RED mobile app or web creator portal. "
                "Browser automation is available via "
                "platforms.xiaohongshu.publish_mode: browser.",
            }

        from automedia.adapters.platforms.xiaohongshu_browser import (
            prepare_xiaohongshu_note,
        )

        drafts_dir = os.path.join(artifact_dir, "drafts")
        title = str(project.get("title") or project.get("topic") or "AutoMedia")
        body = ""
        if os.path.isdir(drafts_dir):
            for name in sorted(os.listdir(drafts_dir)):
                if name.endswith((".html", ".md", ".txt")):
                    with open(os.path.join(drafts_dir, name), encoding="utf-8") as fh:
                        body = fh.read()
                    break
        if not body:
            body = str(project.get("content") or title)

        # media: cover/carousel images produced by the pipeline
        images: list[str] = []
        for key in ("cover_image", "fallback_frame"):
            p = str(project.get(key) or "")
            if p and os.path.isfile(p):
                images.append(p)
        images.extend(
            str(p) for p in (project.get("carousel_images") or []) if os.path.isfile(str(p))
        )
        images = images[:18]  # XHS note limit (18 images)

        screenshot = os.path.join(artifact_dir, "05_review", "xhs-ready-for-confirmation.png")
        result = prepare_xiaohongshu_note(
            title[:20],  # XHS title limit
            body,
            images,
            screenshot,
            account_id=mode_cfg.get("account_id") or None,
        )
        logger.info(
            "Xiaohongshu browser publish finished",
            platform="xiaohongshu",
            status=result.get("status"),
        )
        return result
