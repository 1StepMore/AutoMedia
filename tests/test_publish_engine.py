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


@pytest.fixture()
def sample_artifact_dir(tmp_path: Any) -> str:
    """Temporary artifact directory for publish tests."""
    return str(tmp_path / "artifact")


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    AdapterRegistry.clear()
    yield


# ---------------------------------------------------------------------------
# Basic happy path
# ---------------------------------------------------------------------------


class TestPublishAll:
    def test_single_ok_adapter(self, sample_artifact_dir: str) -> None:
        AdapterRegistry.register(_OkAdapter)
        engine = PublishEngine()
        results = engine.publish_all(sample_artifact_dir, SAMPLE_PROJECT)
        assert results == {
            "ok_adapter": {"status": "ok", "platform": "ok_adapter"},
        }

    def test_multiple_ok_adapters(self, sample_artifact_dir: str) -> None:
        class _AnotherOk(BasePlatformAdapter):
            @property
            def platform_name(self) -> str:
                return "another_ok"

            def publish(self, artifact_dir: str, project: dict) -> dict:
                return {"status": "ok", "from": "another_ok"}

        AdapterRegistry.register(_OkAdapter)
        AdapterRegistry.register(_AnotherOk)
        engine = PublishEngine()
        results = engine.publish_all(sample_artifact_dir, SAMPLE_PROJECT)
        assert len(results) == 2
        assert results["ok_adapter"]["status"] == "ok"
        assert results["another_ok"]["status"] == "ok"

    def test_no_registered_adapters(self, sample_artifact_dir: str) -> None:
        engine = PublishEngine()
        results = engine.publish_all(sample_artifact_dir, SAMPLE_PROJECT)
        assert results == {}


# ---------------------------------------------------------------------------
# Disabled / validation-skipped adapters
# ---------------------------------------------------------------------------


class TestSkipping:
    def test_disabled_adapter_skipped(self, sample_artifact_dir: str) -> None:
        AdapterRegistry.register(_DisabledAdapter)
        engine = PublishEngine()
        results = engine.publish_all(sample_artifact_dir, SAMPLE_PROJECT)
        assert results == {}  # adapter was never invoked

    def test_validation_failure_returns_skipped(self, sample_artifact_dir: str) -> None:
        AdapterRegistry.register(_FailingValidationAdapter)
        engine = PublishEngine()
        results = engine.publish_all(sample_artifact_dir, SAMPLE_PROJECT)
        assert results == {
            "failing_validation": {"status": "skipped", "reason": "validation failed"},
        }


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    def test_crashing_adapter_reports_error(self, sample_artifact_dir: str) -> None:
        AdapterRegistry.register(_CrashAdapter)
        engine = PublishEngine()
        results = engine.publish_all(sample_artifact_dir, SAMPLE_PROJECT)
        assert results["crash_adapter"]["status"] == "error"
        assert "API unreachable" in results["crash_adapter"]["reason"]


# ---------------------------------------------------------------------------
# Real adapter integration (requires env vars to fully exercise)
# ---------------------------------------------------------------------------


class TestRealAdapters:
    def test_wechat_publisher_disabled_without_env(self, tmp_path: Any) -> None:
        """Without env vars, WechatPublisher.validate() returns False."""
        from automedia.adapters.platforms.wechat_publisher import WechatPublisher  # noqa: PLC0415

        os.environ.pop("WX_APPID", None)
        os.environ.pop("WX_APPSECRET", None)

        dummy_dir = str(tmp_path / "void")
        adapter = WechatPublisher()
        assert adapter.validate(dummy_dir) is False

        # Publish also checks for credentials and returns error when missing
        result = adapter.publish(dummy_dir, {"dummy": True})
        assert result["status"] == "error"
        assert "platform" in result
        assert result["platform"] == "wechat"

    def test_feishu_notifier_enabled_with_env(self, tmp_path: Any) -> None:
        from unittest.mock import MagicMock, patch

        from automedia.adapters.platforms.feishu_notifier import FeishuNotifier  # noqa: PLC0415

        os.environ["FEISHU_WEBHOOK_URL"] = "https://example.com/hook"
        try:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"data": {"message_id": "mock_msg_001"}}

            dummy_dir = str(tmp_path / "void")
            with patch(
                "automedia.adapters.platforms.feishu_notifier._httpx_module.post",
                return_value=mock_resp,
            ) as mock_post:
                adapter = FeishuNotifier()
                assert adapter.enabled is True
                assert adapter.validate(dummy_dir) is True
                result = adapter.publish(dummy_dir, {"dummy": True})

            mock_post.assert_called_once()
            assert result["status"] == "ok"
            assert result["platform"] == "feishu"
            assert result["message_id"] == "mock_msg_001"
        finally:
            os.environ.pop("FEISHU_WEBHOOK_URL", None)


# ---------------------------------------------------------------------------
# PRD-4: account-aware publishing
# ---------------------------------------------------------------------------


class TestPublishAllWithAccountIds:
    """Tests for the ``account_ids`` parameter on :meth:`PublishEngine.publish_all`."""

    def test_publish_legacy_no_account_ids(
        self, sample_artifact_dir: str
    ) -> None:
        """Legacy behaviour (account_ids=None) is unchanged."""
        AdapterRegistry.register(_OkAdapter)
        engine = PublishEngine()
        results = engine.publish_all(sample_artifact_dir, SAMPLE_PROJECT)
        assert results == {
            "ok_adapter": {"status": "ok", "platform": "ok_adapter"},
        }

    def test_publish_with_account_ids(
        self, sample_artifact_dir: str, monkeypatch: Any
    ) -> None:
        """Publish to specific accounts via AccountRegistry lookup."""

        class _WechatStub(BasePlatformAdapter):
            @property
            def platform_name(self) -> str:
                return "wechat"

            def publish(self, artifact_dir: str, project: dict) -> dict[str, Any]:
                return {"status": "ok", "account_id": self._account_id}

        AdapterRegistry.register(_WechatStub)

        # Mock AccountRegistry so it returns metadata without touching disk
        class _MockRegistry:
            def get(self, account_id: str) -> dict[str, Any] | None:
                if account_id == "acc_wechat_001":
                    return {"account_id": "acc_wechat_001", "platform": "wechat"}
                if account_id == "acc_wechat_002":
                    return {"account_id": "acc_wechat_002", "platform": "wechat"}
                return None

        monkeypatch.setattr(
            "automedia.accounts.registry.AccountRegistry",
            _MockRegistry,
        )

        engine = PublishEngine()
        results = engine.publish_all(
            sample_artifact_dir,
            SAMPLE_PROJECT,
            account_ids=["acc_wechat_001", "acc_wechat_002"],
        )

        assert len(results) == 2
        assert results["acc_wechat_001"]["status"] == "ok"
        assert results["acc_wechat_001"]["account_id"] == "acc_wechat_001"
        assert results["acc_wechat_002"]["status"] == "ok"
        assert results["acc_wechat_002"]["account_id"] == "acc_wechat_002"

    def test_publish_with_nonexistent_account(
        self, sample_artifact_dir: str, monkeypatch: Any
    ) -> None:
        """Unknown account_id produces an error entry without crashing."""

        class _MockRegistry:
            def get(self, account_id: str) -> dict[str, Any] | None:
                return None  # always not found

        monkeypatch.setattr(
            "automedia.accounts.registry.AccountRegistry",
            _MockRegistry,
        )

        engine = PublishEngine()
        results = engine.publish_all(
            sample_artifact_dir,
            SAMPLE_PROJECT,
            account_ids=["acc_nonexistent_999"],
        )

        assert results["acc_nonexistent_999"]["status"] == "error"
        assert "not found" in results["acc_nonexistent_999"]["reason"]

    def test_publish_partial_failure(
        self, sample_artifact_dir: str, monkeypatch: Any
    ) -> None:
        """One account failing should not block other accounts."""

        class _ConditionalWechat(BasePlatformAdapter):
            @property
            def platform_name(self) -> str:
                return "wechat"

            def publish(self, artifact_dir: str, project: dict) -> dict[str, Any]:
                if self._account_id == "acc_crash":
                    raise ConnectionError("token expired")
                return {"status": "ok"}

        AdapterRegistry.register(_ConditionalWechat)

        class _MockRegistry:
            def get(self, account_id: str) -> dict[str, Any] | None:
                mapping = {
                    "acc_ok": {"account_id": "acc_ok", "platform": "wechat"},
                    "acc_crash": {"account_id": "acc_crash", "platform": "wechat"},
                }
                return mapping.get(account_id)

        monkeypatch.setattr(
            "automedia.accounts.registry.AccountRegistry",
            _MockRegistry,
        )

        engine = PublishEngine()
        results = engine.publish_all(
            sample_artifact_dir,
            SAMPLE_PROJECT,
            account_ids=["acc_ok", "acc_crash"],
        )

        assert results["acc_ok"]["status"] == "ok"
        assert results["acc_crash"]["status"] == "error"
        assert "token expired" in results["acc_crash"]["reason"]
