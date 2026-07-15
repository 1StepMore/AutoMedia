"""Feishu (Lark) webhook notifier — sends interactive card messages.

Credentials are resolved via :func:`load_credential_or_env` with
backward-compatible support for the legacy ``FEISHU_WEBHOOK_URL``
environment variable and the standard ``AUTOMEDIA_FEISHU_WEBHOOK_URL``
credential.
"""

from __future__ import annotations

from typing import Any

from structlog import get_logger

from automedia.adapters.base import BasePlatformAdapter, PublishResult
from automedia.core.credential_loader import load_credential_or_env

log = get_logger(__name__)

# httpx is an optional dependency; fall back gracefully when unavailable
_httpx_module: Any = None
_has_httpx = False
try:
    import httpx as _httpx_module  # type: ignore[assignment]

    _has_httpx = True
except ImportError:  # pragma: no cover
    from automedia.core._import_helpers import warn_missing_optional

    warn_missing_optional("httpx", feature="Feishu notifications disabled")


class FeishuNotifier(BasePlatformAdapter):
    """Send an interactive card notification to a Feishu group via webhook."""

    @property
    def platform_name(self) -> str:
        return "feishu"

    @property
    def enabled(self) -> bool:
        """Only enabled when Feishu webhook URL is set."""
        return bool(
            load_credential_or_env("FEISHU_WEBHOOK_URL", "feishu_webhook_url")
        )

    def validate(self, artifact_dir: str) -> bool:
        """Check that Feishu webhook URL is set."""
        _ = artifact_dir
        return bool(
            load_credential_or_env("FEISHU_WEBHOOK_URL", "feishu_webhook_url")
        )

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------
    def publish(self, artifact_dir: str, project: dict[str, Any]) -> PublishResult:
        """POST an interactive card to the configured Feishu webhook.

        Returns
        -------
        dict
            ``{"status": "ok", "platform": "feishu", "message_id": …}``
            on success, or ``{"status": "error", "platform": "feishu",
            "reason": …}`` on failure.
        """
        _ = artifact_dir

        # --- pre-flight: webhook URL -------------------------------------------
        webhook_url = load_credential_or_env("FEISHU_WEBHOOK_URL", "feishu_webhook_url")
        if not webhook_url:
            log.warning("feishu_notifier.missing_webhook_url")
            return {
                "status": "error",
                "platform": "feishu",
                "reason": "FEISHU_WEBHOOK_URL is not set",
            }

        # --- pre-flight: httpx --------------------------------------------------
        if not _has_httpx:
            log.error("feishu_notifier.httpx_not_available")
            return {
                "status": "error",
                "platform": "feishu",
                "reason": "httpx is not available",
            }

        # --- build card payload -------------------------------------------------
        topic = project.get("topic", "unknown")
        brand = project.get("brand", "unknown")
        status = project.get("status", "unknown")

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": "AutoMedia Publish Notification",
                    },
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": (
                                f"**Topic:** {topic}\n"
                                f"**Brand:** {brand}\n"
                                f"**Status:** {status}"
                            ),
                        },
                    },
                ],
            },
        }

        # --- POST ---------------------------------------------------------------
        try:
            resp = _httpx_module.post(
                webhook_url,
                json=payload,
                timeout=30.0,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except Exception as exc:
            log.error("feishu_notifier.http_error", error=str(exc))
            return {
                "status": "error",
                "platform": "feishu",
                "reason": str(exc),
            }

        message_id = data.get("data", {}).get("message_id", "unknown")
        log.info(
            "feishu_notifier.sent",
            message_id=message_id,
            topic=topic,
            brand=brand,
        )
        return {
            "status": "ok",
            "platform": "feishu",
            "message_id": message_id,
        }
