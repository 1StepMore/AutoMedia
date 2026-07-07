"""WeChat Official Account publisher stub."""

from __future__ import annotations

import os
from typing import Any

from automedia.adapters.base import BasePlatformAdapter


class WechatPublisher(BasePlatformAdapter):
    """Publish article to WeChat Official Account (stub)."""

    @property
    def platform_name(self) -> str:
        return "wechat"

    def validate(self, artifact_dir: str) -> bool:
        """Check that WX_APPID and WX_APPSECRET are set."""
        return bool(os.environ.get("WX_APPID")) and bool(
            os.environ.get("WX_APPSECRET")
        )

    def publish(
        self, artifact_dir: str, project: dict[str, Any]
    ) -> dict[str, Any]:
        """Stub: return a simulated success result."""
        _ = artifact_dir, project  # mark as used
        return {"status": "ok", "platform": "wechat", "article_id": "stub_001"}
