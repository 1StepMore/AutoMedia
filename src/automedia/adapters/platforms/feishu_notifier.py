"""Feishu (Lark) notification stub."""

from __future__ import annotations

import os
from typing import Any

from automedia.adapters.base import BasePlatformAdapter


class FeishuNotifier(BasePlatformAdapter):
    """Send notification to Feishu group / webhook (stub)."""

    @property
    def platform_name(self) -> str:
        return "feishu"

    @property
    def enabled(self) -> bool:
        """Only enabled when FEISHU_WEBHOOK_URL is set."""
        return bool(os.environ.get("FEISHU_WEBHOOK_URL"))

    def validate(self, artifact_dir: str) -> bool:
        """Stub validation — always passes for now."""
        return True

    def publish(self, artifact_dir: str, project: dict[str, Any]) -> dict[str, Any]:
        """Stub: return a simulated success result."""
        _ = artifact_dir, project
        return {"status": "ok", "platform": "feishu", "message_id": "stub_001"}
