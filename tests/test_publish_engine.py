"""Tests for PublishEngine orchestration."""

from __future__ import annotations

import os
from typing import Any

import pytest

from automedia.adapters.base import BasePlatformAdapter
from automedia.adapters.publish_engine import PublishEngine
from automedia.adapters.registry import AdapterRegistry

# ---------------------------------------------------------------------------
# Stub adapters for testing
# ---------------------------------------------------------------------------


class _OkAdapter(BasePlatformAdapter):
    """Always succeeds."""

    @property
    def platform_name(self) -> str:
        return "ok_adapter"

    def publish(self, artifact_dir: str, project: dict) -> dict[str, Any]:
        return {"status": "ok", "platform": self.platform_name}


class _DisabledAdapter(BasePlatformAdapter):
    """Has enabled=False."""

    @property
    def platform_name(self) -> str:
        return "disabled_adapter"

    @property
    def enabled(self) -> bool:
        return False

    def publish(self, artifact_dir: str, project: dict) -> dict[str, Any]:
        msg = "Should never be called"
        raise RuntimeError(msg)


class _FailingValidationAdapter(BasePlatformAdapter):
    """validate() returns False."""

    @property
    def platform_name(self) -> str:
        return "failing_validation"

    def validate(self, artifact_dir: str) -> bool:
        return False

    def publish(self, artifact_dir: str, project: dict) -> dict[str, Any]:
        msg = "Should never be called"
        raise RuntimeError(msg)


class _CrashAdapter(BasePlatformAdapter):
    """publish() raises an exception."""

    @property
    def platform_name(self) -> str:
        return "crash_adapter"

    def publish(self, artifact_dir: str, project: dict) -> dict[str, Any]:
        raise ConnectionError("API unreachable")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PROJECT = {
    "topic": "test",
    "config": {"platforms": ["ok_adapter", "disabled_adapter"]},
}
SAMPLE_ARTIFACT_DIR = "/tmp/automedia_test_artifact"


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    AdapterRegistry.clear()
    yield


# ---------------------------------------------------------------------------
# Basic happy path
# ---------------------------------------------------------------------------


class TestPublishAll:
    def test_single_ok_adapter(self) -> None:
        AdapterRegistry.register(_OkAdapter)
        engine = PublishEngine()
        results = engine.publish_all(SAMPLE_ARTIFACT_DIR, SAMPLE_PROJECT)
        assert results == {
            "ok_adapter": {"status": "ok", "platform": "ok_adapter"},
        }

    def test_multiple_ok_adapters(self) -> None:
        class _AnotherOk(BasePlatformAdapter):
            @property
            def platform_name(self) -> str:
                return "another_ok"

            def publish(self, artifact_dir: str, project: dict) -> dict:
                return {"status": "ok", "from": "another_ok"}

        AdapterRegistry.register(_OkAdapter)
        AdapterRegistry.register(_AnotherOk)
        engine = PublishEngine()
        results = engine.publish_all(SAMPLE_ARTIFACT_DIR, SAMPLE_PROJECT)
        assert len(results) == 2
        assert results["ok_adapter"]["status"] == "ok"
        assert results["another_ok"]["status"] == "ok"

    def test_no_registered_adapters(self) -> None:
        engine = PublishEngine()
        results = engine.publish_all(SAMPLE_ARTIFACT_DIR, SAMPLE_PROJECT)
        assert results == {}


# ---------------------------------------------------------------------------
# Disabled / validation-skipped adapters
# ---------------------------------------------------------------------------


class TestSkipping:
    def test_disabled_adapter_skipped(self) -> None:
        AdapterRegistry.register(_DisabledAdapter)
        engine = PublishEngine()
        results = engine.publish_all(SAMPLE_ARTIFACT_DIR, SAMPLE_PROJECT)
        assert results == {}  # adapter was never invoked

    def test_validation_failure_returns_skipped(self) -> None:
        AdapterRegistry.register(_FailingValidationAdapter)
        engine = PublishEngine()
        results = engine.publish_all(SAMPLE_ARTIFACT_DIR, SAMPLE_PROJECT)
        assert results == {
            "failing_validation": {"status": "skipped", "reason": "validation failed"},
        }


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    def test_crashing_adapter_reports_error(self) -> None:
        AdapterRegistry.register(_CrashAdapter)
        engine = PublishEngine()
        results = engine.publish_all(SAMPLE_ARTIFACT_DIR, SAMPLE_PROJECT)
        assert results["crash_adapter"]["status"] == "error"
        assert "API unreachable" in results["crash_adapter"]["reason"]


# ---------------------------------------------------------------------------
# Real adapter integration (requires env vars to fully exercise)
# ---------------------------------------------------------------------------


class TestRealAdapters:
    def test_wechat_publisher_disabled_without_env(self) -> None:
        """Without env vars, WechatPublisher.validate() returns False."""
        from automedia.adapters.platforms.wechat_publisher import WechatPublisher  # noqa: PLC0415

        os.environ.pop("WX_APPID", None)
        os.environ.pop("WX_APPSECRET", None)

        adapter = WechatPublisher()
        assert adapter.validate("/tmp/void") is False

        # The stub publish does not require validation to call
        result = adapter.publish("/tmp/void", {"dummy": True})
        assert result["status"] == "ok"

    def test_feishu_notifier_enabled_with_env(self) -> None:
        from automedia.adapters.platforms.feishu_notifier import FeishuNotifier  # noqa: PLC0415

        os.environ["FEISHU_WEBHOOK_URL"] = "https://example.com/hook"
        try:
            adapter = FeishuNotifier()
            assert adapter.enabled is True
            assert adapter.validate("/tmp/void") is True
            result = adapter.publish("/tmp/void", {"dummy": True})
            assert result["status"] == "ok"
            assert result["platform"] == "feishu"
        finally:
            os.environ.pop("FEISHU_WEBHOOK_URL", None)
