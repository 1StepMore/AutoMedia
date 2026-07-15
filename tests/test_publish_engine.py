"""Tests for PublishEngine orchestration."""

from __future__ import annotations

import os
from typing import Any

from automedia.adapters.base import AutomationLevel

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

    def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict[str, Any]:
        return {"status": "ok", "platform": self.platform_name}


class _DisabledAdapter(BasePlatformAdapter):
    """Has enabled=False."""

    @property
    def platform_name(self) -> str:
        return "disabled_adapter"

    @property
    def enabled(self) -> bool:
        return False

    def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict[str, Any]:
        msg = "Should never be called"
        raise RuntimeError(msg)


class _FailingValidationAdapter(BasePlatformAdapter):
    """validate() returns False."""

    @property
    def platform_name(self) -> str:
        return "failing_validation"

    def validate(self, artifact_dir: str) -> bool:
        return False

    def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict[str, Any]:
        msg = "Should never be called"
        raise RuntimeError(msg)


class _CrashAdapter(BasePlatformAdapter):
    """publish() raises an exception."""

    @property
    def platform_name(self) -> str:
        return "crash_adapter"

    def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict[str, Any]:
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

            def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict:
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
# Automation level routing
# ---------------------------------------------------------------------------


class _PublishTrackerAdapter(BasePlatformAdapter):
    """Records whether publish() was called — used to verify auto routing."""

    publish_called: bool = False
    last_draft_only: bool = False

    @property
    def platform_name(self) -> str:
        return "tracker_adapter"

    def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict[str, Any]:
        type(self).publish_called = True
        type(self).last_draft_only = kwargs.get("draft_only", False)
        return {"status": "ok", "platform": self.platform_name}


class _DraftTrackerAdapter(BasePlatformAdapter):
    """Returns draft response — used to verify review/draft_only routing."""

    publish_called: bool = False
    last_draft_only: bool = False

    @property
    def platform_name(self) -> str:
        return "draft_adapter"

    def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict[str, Any]:
        type(self).publish_called = True
        is_draft = kwargs.get("draft_only", False)
        type(self).last_draft_only = is_draft
        if is_draft:
            return {
                "status": "draft_created",
                "platform": "draft_adapter",
                "draft_id": "draft_001",
                "draft_url": "https://example.com/draft/001",
            }
        return {"status": "ok", "platform": "draft_adapter"}


class TestAutomationLevels:
    """Verify that automation levels route correctly without calling adapter.publish()."""

    def test_auto_calls_publish(self, sample_artifact_dir: str) -> None:
        _PublishTrackerAdapter.publish_called = False
        AdapterRegistry.register(_PublishTrackerAdapter)
        engine = PublishEngine()
        results = engine.publish_all(
            sample_artifact_dir,
            SAMPLE_PROJECT,
            automation={"tracker_adapter": "auto"},
        )
        assert _PublishTrackerAdapter.publish_called is True
        assert results["tracker_adapter"]["status"] == "ok"

    def test_review_calls_publish_with_draft_only(self, sample_artifact_dir: str) -> None:
        _DraftTrackerAdapter.publish_called = False
        _DraftTrackerAdapter.last_draft_only = False
        AdapterRegistry.register(_DraftTrackerAdapter)
        engine = PublishEngine()
        results = engine.publish_all(
            sample_artifact_dir,
            SAMPLE_PROJECT,
            automation={"draft_adapter": "review"},
        )
        assert _DraftTrackerAdapter.publish_called is True
        assert _DraftTrackerAdapter.last_draft_only is True
        assert results["draft_adapter"] == {
            "status": "draft_created",
            "platform": "draft_adapter",
            "draft_id": "draft_001",
            "draft_url": "https://example.com/draft/001",
        }

    def test_manual_returns_skipped(self, sample_artifact_dir: str) -> None:
        _PublishTrackerAdapter.publish_called = False
        AdapterRegistry.register(_PublishTrackerAdapter)
        engine = PublishEngine()
        results = engine.publish_all(
            sample_artifact_dir,
            SAMPLE_PROJECT,
            automation={"tracker_adapter": "manual"},
        )
        assert _PublishTrackerAdapter.publish_called is False
        assert results["tracker_adapter"] == {
            "status": "skipped",
            "platform": "tracker_adapter",
            "reason": "automation level: manual",
        }

    def test_defaults_used_when_automation_not_provided(
        self, sample_artifact_dir: str
    ) -> None:
        """Without automation param, defaults from AUTOMATION_DEFAULTS apply."""
        from automedia.adapters.base import AUTOMATION_DEFAULTS

        AdapterRegistry.register(_OkAdapter)
        engine = PublishEngine()

        # The ok_adapter platform is not in AUTOMATION_DEFAULTS, so it falls
        # back to "auto" — publish should proceed normally.
        results = engine.publish_all(sample_artifact_dir, SAMPLE_PROJECT)
        assert results["ok_adapter"]["status"] == "ok"

    def test_defaults_applied_for_unknown_platform(
        self, sample_artifact_dir: str
    ) -> None:
        """A platform not in the automation dict falls back to defaults."""
        _PublishTrackerAdapter.publish_called = False
        AdapterRegistry.register(_PublishTrackerAdapter)
        engine = PublishEngine()
        # tracker_adapter is not in the automation dict → defaults → "auto"
        results = engine.publish_all(
            sample_artifact_dir,
            SAMPLE_PROJECT,
            automation={},
        )
        assert _PublishTrackerAdapter.publish_called is True
        assert results["tracker_adapter"]["status"] == "ok"

    def test_defaults_use_builtin_defaults_for_known_platforms(
        self, sample_artifact_dir: str,
    ) -> None:
        """Known platforms like xiaohongshu should default to manual."""
        from automedia.adapters.base import AUTOMATION_DEFAULTS

        class _XHSAdapter(BasePlatformAdapter):
            publish_called = False

            @property
            def platform_name(self) -> str:
                return "xiaohongshu"

            def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict:
                type(self).publish_called = True
                return {"status": "ok"}

        AdapterRegistry.register(_XHSAdapter)
        engine = PublishEngine()

        # No automation passed → AUTOMATION_DEFAULTS → xiaohongshu is manual
        results = engine.publish_all(sample_artifact_dir, SAMPLE_PROJECT)
        assert _XHSAdapter.publish_called is False
        assert results["xiaohongshu"]["status"] == "skipped"
        assert "manual" in results["xiaohongshu"]["reason"]


class TestAutomationLevelsWithAccountIds:
    """Automation routing in the account-aware publishing path."""

    def test_manual_skips_account(self, sample_artifact_dir: str, monkeypatch: Any) -> None:
        class _WechatStub(BasePlatformAdapter):
            publish_called = False

            @property
            def platform_name(self) -> str:
                return "wechat"

            def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict[str, Any]:
                type(self).publish_called = True
                return {"status": "ok", "account_id": self._account_id}

        AdapterRegistry.register(_WechatStub)

        class _MockRegistry:
            def get(self, account_id: str) -> dict[str, Any] | None:
                if account_id == "acc_wechat_001":
                    return {"account_id": "acc_wechat_001", "platform": "wechat"}
                return None

        monkeypatch.setattr(
            "automedia.accounts.registry.AccountRegistry",
            _MockRegistry,
        )

        engine = PublishEngine()
        results = engine.publish_all(
            sample_artifact_dir,
            SAMPLE_PROJECT,
            account_ids=["acc_wechat_001"],
            automation={"wechat": "manual"},
        )

        assert _WechatStub.publish_called is False
        assert results["acc_wechat_001"]["status"] == "skipped"
        assert "manual" in results["acc_wechat_001"]["reason"]

    def test_review_account_calls_publish_with_draft_only(
        self, sample_artifact_dir: str, monkeypatch: Any,
    ) -> None:
        class _WechatStub(BasePlatformAdapter):
            publish_called = False
            last_draft_only = False

            @property
            def platform_name(self) -> str:
                return "wechat"

            def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict[str, Any]:
                type(self).publish_called = True
                type(self).last_draft_only = kwargs.get("draft_only", False)
                if kwargs.get("draft_only"):
                    return {
                        "status": "draft_created",
                        "platform": "wechat",
                        "draft_id": "draft_001",
                        "draft_url": "https://example.com/draft",
                    }
                return {"status": "ok", "account_id": self._account_id}

        AdapterRegistry.register(_WechatStub)

        class _MockRegistry:
            def get(self, account_id: str) -> dict[str, Any] | None:
                if account_id == "acc_wechat_001":
                    return {"account_id": "acc_wechat_001", "platform": "wechat"}
                return None

        monkeypatch.setattr(
            "automedia.accounts.registry.AccountRegistry",
            _MockRegistry,
        )

        engine = PublishEngine()
        results = engine.publish_all(
            sample_artifact_dir,
            SAMPLE_PROJECT,
            account_ids=["acc_wechat_001"],
            automation={"wechat": "review"},
        )

        assert _WechatStub.publish_called is True
        assert _WechatStub.last_draft_only is True
        assert results["acc_wechat_001"]["status"] == "draft_created"
        assert results["acc_wechat_001"]["draft_url"] == "https://example.com/draft"

    def test_auto_publishes_account(self, sample_artifact_dir: str, monkeypatch: Any) -> None:
        class _WechatStub(BasePlatformAdapter):
            publish_called = False

            @property
            def platform_name(self) -> str:
                return "wechat"

            def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict[str, Any]:
                type(self).publish_called = True
                return {"status": "ok", "account_id": self._account_id}

        AdapterRegistry.register(_WechatStub)

        class _MockRegistry:
            def get(self, account_id: str) -> dict[str, Any] | None:
                if account_id == "acc_wechat_001":
                    return {"account_id": "acc_wechat_001", "platform": "wechat"}
                return None

        monkeypatch.setattr(
            "automedia.accounts.registry.AccountRegistry",
            _MockRegistry,
        )

        engine = PublishEngine()
        results = engine.publish_all(
            sample_artifact_dir,
            SAMPLE_PROJECT,
            account_ids=["acc_wechat_001"],
            automation={"wechat": "auto"},
        )

        assert _WechatStub.publish_called is True
        assert results["acc_wechat_001"]["status"] == "ok"


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

            def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict[str, Any]:
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

            def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Error classification unit tests
# ---------------------------------------------------------------------------


class TestClassifyPublishError:
    """Unit tests for :func:`classify_publish_error`."""

    def test_credential_expired_from_reason(self) -> None:
        from automedia.adapters.publish_engine import classify_publish_error

        assert classify_publish_error(reason="token expired") == "credential_expired"
        assert classify_publish_error(reason="401 Unauthorized") == "credential_expired"
        assert classify_publish_error(reason="403 Forbidden") == "credential_expired"
        assert classify_publish_error(reason="invalid credential") == "credential_expired"
        assert classify_publish_error(reason="access_token is invalid") == "credential_expired"
        assert classify_publish_error(reason="cookie expired") == "credential_expired"
        assert classify_publish_error(reason="invalid cookie") == "credential_expired"
        assert classify_publish_error(reason="unauthorized") == "credential_expired"
        assert classify_publish_error(reason="auth failed") == "credential_expired"

    def test_rate_limited_from_reason(self) -> None:
        from automedia.adapters.publish_engine import classify_publish_error

        assert classify_publish_error(reason="429 Too Many Requests") == "rate_limited"
        assert classify_publish_error(reason="rate limit exceeded") == "rate_limited"
        assert classify_publish_error(reason="too many requests") == "rate_limited"

    def test_network_error_from_exception_type(self) -> None:
        from automedia.adapters.publish_engine import classify_publish_error

        assert classify_publish_error(exception=TimeoutError("connection")) == "network_error"
        assert classify_publish_error(exception=ConnectionError("refused")) == "network_error"

    def test_network_error_from_exception_name(self) -> None:
        from automedia.adapters.publish_engine import classify_publish_error

        class ConnectTimeout(Exception):
            ...

        class RemoteProtocolError(Exception):
            ...

        assert classify_publish_error(exception=ConnectTimeout("timeout")) == "network_error"
        assert (
            classify_publish_error(exception=RemoteProtocolError("reset"))
            == "network_error"
        )

    def test_network_error_from_reason(self) -> None:
        from automedia.adapters.publish_engine import classify_publish_error

        assert classify_publish_error(reason="Connection refused") == "network_error"
        assert classify_publish_error(reason="timeout occurred") == "network_error"
        assert classify_publish_error(reason="DNS resolution failed") == "network_error"
        assert classify_publish_error(reason="unreachable host") == "network_error"

    def test_content_rejected_from_reason(self) -> None:
        from automedia.adapters.publish_engine import classify_publish_error

        assert classify_publish_error(reason="content rejected") == "content_rejected"
        assert classify_publish_error(reason="blocked by platform") == "content_rejected"

    def test_unknown_fallback(self) -> None:
        from automedia.adapters.publish_engine import classify_publish_error

        assert classify_publish_error(reason="some random error") == "unknown"
        assert classify_publish_error(exception=ValueError("weird")) == "unknown"
        assert classify_publish_error() == "unknown"

    def test_case_insensitive_matching(self) -> None:
        from automedia.adapters.publish_engine import classify_publish_error

        assert classify_publish_error(reason="TOKEN EXPIRED") == "credential_expired"
        assert classify_publish_error(reason="429") == "rate_limited"
        assert classify_publish_error(reason="CONNECTION RESET") == "network_error"

    def test_http_status_error_by_status_code(self) -> None:
        from automedia.adapters.publish_engine import classify_publish_error

        class _FakeResponse:
            status_code = 429

        class HTTPStatusError(Exception):
            def __init__(self) -> None:
                super().__init__("429 Too Many Requests")
                self.response = _FakeResponse()

        assert (
            classify_publish_error(exception=HTTPStatusError())
            == "rate_limited"
        )


# ---------------------------------------------------------------------------
# build_error_result unit tests
# ---------------------------------------------------------------------------


class TestBuildErrorResult:
    """Unit tests for :func:`build_error_result`."""

    def test_rate_limited_structure(self) -> None:
        from automedia.adapters.publish_engine import build_error_result

        result = build_error_result("wechat", "rate_limited", "429 Too Many")
        assert result["status"] == "error"
        assert result["platform"] == "wechat"
        assert result["error_code"] == "rate_limited"
        assert result["error_message"] == "429 Too Many"
        assert result["reason"] == "429 Too Many"
        assert result["retryable"] is True
        assert result["action"] == "retry"
        assert result["max_retries"] == 3

    def test_credential_expired_structure(self) -> None:
        from automedia.adapters.publish_engine import build_error_result

        result = build_error_result("wechat", "credential_expired", "token expired")
        assert result["status"] == "error"
        assert result["error_code"] == "credential_expired"
        assert result["retryable"] is True
        assert result["action"] == "refresh_credential"
        assert "max_retries" not in result

    def test_network_error_structure(self) -> None:
        from automedia.adapters.publish_engine import build_error_result

        result = build_error_result("zhihu", "network_error", "connection refused")
        assert result["status"] == "error"
        assert result["error_code"] == "network_error"
        assert result["retryable"] is True
        assert result["action"] == "retry"
        assert result["max_retries"] == 2

    def test_content_rejected_structure(self) -> None:
        from automedia.adapters.publish_engine import build_error_result

        result = build_error_result("zhihu", "content_rejected", "blocked")
        assert result["retryable"] is False
        assert result["action"] == "fix_content"

    def test_unknown_structure(self) -> None:
        from automedia.adapters.publish_engine import build_error_result

        result = build_error_result("feishu", "unknown", "something broke")
        assert result["retryable"] is False
        assert result["action"] == "investigate"

    def test_with_exception(self) -> None:
        from automedia.adapters.publish_engine import build_error_result

        exc = ConnectionError("API unreachable")
        result = build_error_result("wechat", "network_error", str(exc), exception=exc)
        assert result["exception"] == "ConnectionError"
        assert result["reason"] == "API unreachable"


# ---------------------------------------------------------------------------
# Retry logic tests
# ---------------------------------------------------------------------------


class _RetryCounterAdapter(BasePlatformAdapter):
    """Adapter that fails N times with a given error pattern, then succeeds.

    Attributes
    ----------
    call_count:
        Number of times ``publish()`` has been called (shared across
        instances via the class attribute).
    """

    call_count: int = 0
    fail_for: int = 3
    error_reason: str = "429 Too Many Requests"
    raise_exception: bool = True

    @property
    def platform_name(self) -> str:
        return "retry_counter"

    def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict[str, Any]:
        type(self).call_count += 1
        if type(self).call_count <= type(self).fail_for:
            if type(self).raise_exception:
                raise Exception(type(self).error_reason)
            return {
                "status": "error",
                "platform": self.platform_name,
                "reason": type(self).error_reason,
            }
        return {"status": "ok", "platform": self.platform_name}


class TestPublishWithRetry:
    """Tests for :func:`_publish_with_retry`."""

    def setup_method(self) -> None:
        _RetryCounterAdapter.call_count = 0

    # ------------------------------------------------------------------
    # rate_limited: max 3 retries
    # ------------------------------------------------------------------

    def test_rate_limited_retries_and_succeeds(self, monkeypatch: Any) -> None:
        """rate_limited error is retried up to 3 times; success on retry."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RetryCounterAdapter.fail_for = 2
        _RetryCounterAdapter.error_reason = "429 Too Many Requests"
        _RetryCounterAdapter.raise_exception = True
        self.setup_method()

        result = _publish_with_retry(
            _RetryCounterAdapter(), "/tmp", {"topic": "test"}, "retry_counter",
        )
        assert result["status"] == "ok"
        assert _RetryCounterAdapter.call_count == 3

    def test_rate_limited_exhausts_retries(self, monkeypatch: Any) -> None:
        """rate_limited fails all 3 retries → structured error returned."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RetryCounterAdapter.fail_for = 99
        _RetryCounterAdapter.error_reason = "429 Too Many Requests"
        _RetryCounterAdapter.raise_exception = True
        self.setup_method()

        result = _publish_with_retry(
            _RetryCounterAdapter(), "/tmp", {"topic": "test"}, "retry_counter",
        )
        assert result["status"] == "error"
        assert result["error_code"] == "rate_limited"
        assert result["retryable"] is True
        assert result["max_retries"] == 3
        assert _RetryCounterAdapter.call_count == 4

    # ------------------------------------------------------------------
    # network_error: max 2 retries
    # ------------------------------------------------------------------

    def test_network_error_retries_and_succeeds(self, monkeypatch: Any) -> None:
        """network_error is retried up to 2 times; success on retry."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RetryCounterAdapter.fail_for = 1
        _RetryCounterAdapter.error_reason = "Connection refused"
        _RetryCounterAdapter.raise_exception = True
        self.setup_method()

        result = _publish_with_retry(
            _RetryCounterAdapter(), "/tmp", {"topic": "test"}, "retry_counter",
        )
        assert result["status"] == "ok"
        assert _RetryCounterAdapter.call_count == 2

    def test_network_error_exhausts_retries(self, monkeypatch: Any) -> None:
        """network_error fails all 2 retries → structured error."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RetryCounterAdapter.fail_for = 99
        _RetryCounterAdapter.error_reason = "ConnectTimeout"
        _RetryCounterAdapter.raise_exception = True
        self.setup_method()

        result = _publish_with_retry(
            _RetryCounterAdapter(), "/tmp", {"topic": "test"}, "retry_counter",
        )
        assert result["status"] == "error"
        assert result["error_code"] == "network_error"
        assert result["retryable"] is True
        assert result["max_retries"] == 2
        assert _RetryCounterAdapter.call_count == 3

    # ------------------------------------------------------------------
    # credential_expired: NOT auto-retried
    # ------------------------------------------------------------------

    def test_credential_expired_not_retried(self, monkeypatch: Any) -> None:
        """credential_expired returns immediately, no retry, retryable=True."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RetryCounterAdapter.fail_for = 99
        _RetryCounterAdapter.error_reason = "token expired"
        _RetryCounterAdapter.raise_exception = True
        self.setup_method()

        result = _publish_with_retry(
            _RetryCounterAdapter(), "/tmp", {"topic": "test"}, "retry_counter",
        )
        assert result["status"] == "error"
        assert result["error_code"] == "credential_expired"
        assert result["retryable"] is True
        assert result["action"] == "refresh_credential"
        assert "max_retries" not in result
        assert _RetryCounterAdapter.call_count == 1

    # ------------------------------------------------------------------
    # Returned error result (not exception) — retry still works
    # ------------------------------------------------------------------

    def test_retry_returned_error_not_exception(self, monkeypatch: Any) -> None:
        """Retry also works when adapter returns status=error instead of raising."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RetryCounterAdapter.fail_for = 2
        _RetryCounterAdapter.error_reason = "429 Too Many Requests"
        _RetryCounterAdapter.raise_exception = False
        self.setup_method()

        result = _publish_with_retry(
            _RetryCounterAdapter(), "/tmp", {"topic": "test"}, "retry_counter",
        )
        assert result["status"] == "ok"
        assert _RetryCounterAdapter.call_count == 3

    # ------------------------------------------------------------------
    # content_rejected: never retried
    # ------------------------------------------------------------------

    def test_content_rejected_not_retried(self, monkeypatch: Any) -> None:
        """content_rejected is never retried."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RetryCounterAdapter.fail_for = 99
        _RetryCounterAdapter.error_reason = "content rejected: sensitive content"
        _RetryCounterAdapter.raise_exception = False
        self.setup_method()

        result = _publish_with_retry(
            _RetryCounterAdapter(), "/tmp", {"topic": "test"}, "retry_counter",
        )
        assert result["status"] == "error"
        assert result["error_code"] == "content_rejected"
        assert result["retryable"] is False
        assert _RetryCounterAdapter.call_count == 1

    # ------------------------------------------------------------------
    # unknown error: never retried
    # ------------------------------------------------------------------

    def test_unknown_not_retried(self, monkeypatch: Any) -> None:
        """Unknown errors are never retried."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RetryCounterAdapter.fail_for = 99
        _RetryCounterAdapter.error_reason = "something completely unexpected"
        _RetryCounterAdapter.raise_exception = True
        self.setup_method()

        result = _publish_with_retry(
            _RetryCounterAdapter(), "/tmp", {"topic": "test"}, "retry_counter",
        )
        assert result["status"] == "error"
        assert result["error_code"] == "unknown"
        assert result["retryable"] is False
        assert _RetryCounterAdapter.call_count == 1


# ---------------------------------------------------------------------------
# Partial failure — one platform fails, others succeed (legacy path)
# ---------------------------------------------------------------------------


class TestPartialFailure:
    """One platform failing does not block others (legacy path)."""

    def test_partial_failure_legacy_path(self, sample_artifact_dir: str) -> None:
        """One adapter raises, another succeeds — both results are reported."""

        class _FailAdapter(BasePlatformAdapter):
            @property
            def platform_name(self) -> str:
                return "fail_adapter"

            def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict[str, Any]:
                raise ConnectionError("API unreachable")

        AdapterRegistry.register(_OkAdapter)
        AdapterRegistry.register(_FailAdapter)
        engine = PublishEngine()
        results = engine.publish_all(sample_artifact_dir, SAMPLE_PROJECT)

        assert results["ok_adapter"]["status"] == "ok"
        assert results["fail_adapter"]["status"] == "error"
        assert "API unreachable" in results["fail_adapter"]["reason"]

    def test_partial_failure_error_and_skip(self, sample_artifact_dir: str) -> None:
        """One adapter errors, another is skipped — both reported correctly."""

        class _FailAdapter(BasePlatformAdapter):
            @property
            def platform_name(self) -> str:
                return "fail_adapter"

            def publish(self, artifact_dir: str, project: dict, **kwargs: Any) -> dict[str, Any]:
                raise ConnectionError("timeout")

        AdapterRegistry.register(_FailingValidationAdapter)
        AdapterRegistry.register(_FailAdapter)
        engine = PublishEngine()
        results = engine.publish_all(sample_artifact_dir, SAMPLE_PROJECT)

        assert results["failing_validation"]["status"] == "skipped"
        assert results["fail_adapter"]["status"] == "error"


# ---------------------------------------------------------------------------
# Credential refresh integration tests
# ---------------------------------------------------------------------------


class _RefreshableAdapter(BasePlatformAdapter):
    """Fails N times with ``credential_expired``, then succeeds.

    Used to test the ``refresh_fn`` integration in ``_publish_with_retry``.
    """

    call_count: int = 0
    fail_for: int = 1
    error_reason: str = "token expired"
    raise_exception: bool = False

    @property
    def platform_name(self) -> str:
        return "refresh_test"

    def publish(
        self, artifact_dir: str, project: dict, **kwargs: Any,
    ) -> dict[str, Any]:
        type(self).call_count += 1
        if type(self).call_count <= type(self).fail_for:
            if type(self).raise_exception:
                raise Exception(type(self).error_reason)
            return {
                "status": "error",
                "platform": self.platform_name,
                "reason": type(self).error_reason,
            }
        return {"status": "ok", "platform": self.platform_name}


class TestCredentialRefresh:
    """Integration tests for credential refresh in ``_publish_with_retry``."""

    def setup_method(self) -> None:
        _RefreshableAdapter.call_count = 0

    # ------------------------------------------------------------------
    # Successful refresh → retry → success
    # ------------------------------------------------------------------

    def test_credential_expired_refresh_success_via_exception(
        self, monkeypatch: Any,
    ) -> None:
        """credential_expired → refresh succeeds → retry → success (exception path)."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RefreshableAdapter.fail_for = 1
        _RefreshableAdapter.error_reason = "token expired"
        _RefreshableAdapter.raise_exception = True
        self.setup_method()

        refresh_called: bool = False

        def mock_refresh() -> bool:
            nonlocal refresh_called
            refresh_called = True
            return True

        result = _publish_with_retry(
            _RefreshableAdapter(), "/tmp", {"topic": "test"},
            "refresh_test", refresh_fn=mock_refresh,
        )

        assert result["status"] == "ok"
        assert _RefreshableAdapter.call_count == 2
        assert refresh_called is True

    def test_credential_expired_refresh_success_via_returned_error(
        self, monkeypatch: Any,
    ) -> None:
        """credential_expired → refresh succeeds → retry → success (result path)."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RefreshableAdapter.fail_for = 1
        _RefreshableAdapter.error_reason = "token expired"
        _RefreshableAdapter.raise_exception = False
        self.setup_method()

        refresh_called: bool = False

        def mock_refresh() -> bool:
            nonlocal refresh_called
            refresh_called = True
            return True

        result = _publish_with_retry(
            _RefreshableAdapter(), "/tmp", {"topic": "test"},
            "refresh_test", refresh_fn=mock_refresh,
        )

        assert result["status"] == "ok"
        assert _RefreshableAdapter.call_count == 2
        assert refresh_called is True

    # ------------------------------------------------------------------
    # Failed refresh → credential_refresh_failed
    # ------------------------------------------------------------------

    def test_credential_expired_refresh_fails_via_exception(
        self, monkeypatch: Any,
    ) -> None:
        """credential_expired → refresh fails → credential_refresh_failed (exception)."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RefreshableAdapter.fail_for = 99
        _RefreshableAdapter.error_reason = "token expired"
        _RefreshableAdapter.raise_exception = True
        self.setup_method()

        refresh_called: bool = False

        def mock_refresh() -> bool:
            nonlocal refresh_called
            refresh_called = True
            return False

        result = _publish_with_retry(
            _RefreshableAdapter(), "/tmp", {"topic": "test"},
            "refresh_test", refresh_fn=mock_refresh,
        )

        assert result["status"] == "error"
        assert result["error_code"] == "credential_refresh_failed"
        assert result["action"] == "reconnect_account"
        assert result["retryable"] is False
        assert "Credential refresh failed" in result["reason"]
        assert _RefreshableAdapter.call_count == 1
        assert refresh_called is True

    def test_credential_expired_refresh_fails_via_returned_error(
        self, monkeypatch: Any,
    ) -> None:
        """credential_expired → refresh fails → credential_refresh_failed (result)."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RefreshableAdapter.fail_for = 99
        _RefreshableAdapter.error_reason = "token expired"
        _RefreshableAdapter.raise_exception = False
        self.setup_method()

        refresh_called: bool = False

        def mock_refresh() -> bool:
            nonlocal refresh_called
            refresh_called = True
            return False

        result = _publish_with_retry(
            _RefreshableAdapter(), "/tmp", {"topic": "test"},
            "refresh_test", refresh_fn=mock_refresh,
        )

        assert result["status"] == "error"
        assert result["error_code"] == "credential_refresh_failed"
        assert result["action"] == "reconnect_account"
        assert result["retryable"] is False
        assert "Credential refresh failed" in result["reason"]
        assert _RefreshableAdapter.call_count == 1
        assert refresh_called is True

    # ------------------------------------------------------------------
    # Refresh_once guarantee (no infinite loops)
    # ------------------------------------------------------------------

    def test_credential_expired_refresh_only_once(
        self, monkeypatch: Any,
    ) -> None:
        """Max 1 refresh per publish — second credential_expired is not retried."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RefreshableAdapter.fail_for = 99
        _RefreshableAdapter.error_reason = "token expired"
        _RefreshableAdapter.raise_exception = False
        self.setup_method()

        refresh_count: int = 0

        def mock_refresh() -> bool:
            nonlocal refresh_count
            refresh_count += 1
            return True

        result = _publish_with_retry(
            _RefreshableAdapter(), "/tmp", {"topic": "test"},
            "refresh_test", refresh_fn=mock_refresh,
        )

        assert result["error_code"] == "credential_refresh_failed"
        assert refresh_count == 1

    # ------------------------------------------------------------------
    # Refresh can fail with exception
    # ------------------------------------------------------------------

    def test_credential_expired_refresh_raises_exception(
        self, monkeypatch: Any,
    ) -> None:
        """refresh_fn raising an exception is caught and treated as failure."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RefreshableAdapter.fail_for = 99
        _RefreshableAdapter.error_reason = "token expired"
        _RefreshableAdapter.raise_exception = True
        self.setup_method()

        def mock_refresh() -> bool:
            raise RuntimeError("API unreachable during refresh")

        result = _publish_with_retry(
            _RefreshableAdapter(), "/tmp", {"topic": "test"},
            "refresh_test", refresh_fn=mock_refresh,
        )

        assert result["status"] == "error"
        assert result["error_code"] == "credential_refresh_failed"
        assert "Credential refresh failed" in result["reason"]
        assert _RefreshableAdapter.call_count == 1

    # ------------------------------------------------------------------
    # Non-credential errors don't trigger refresh
    # ------------------------------------------------------------------

    def test_rate_limited_does_not_trigger_refresh(self, monkeypatch: Any) -> None:
        """rate_limited errors should not trigger credential refresh."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RefreshableAdapter.fail_for = 99
        _RefreshableAdapter.error_reason = "429 Too Many Requests"
        _RefreshableAdapter.raise_exception = True
        self.setup_method()

        refresh_called: bool = False

        def mock_refresh() -> bool:
            nonlocal refresh_called
            refresh_called = True
            return True

        result = _publish_with_retry(
            _RefreshableAdapter(), "/tmp", {"topic": "test"},
            "refresh_test", refresh_fn=mock_refresh,
        )

        assert result["error_code"] == "rate_limited"
        assert refresh_called is False

    def test_network_error_does_not_trigger_refresh(self, monkeypatch: Any) -> None:
        """network_error should not trigger credential refresh."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RefreshableAdapter.fail_for = 99
        _RefreshableAdapter.error_reason = "Connection refused"
        _RefreshableAdapter.raise_exception = True
        self.setup_method()

        refresh_called: bool = False

        def mock_refresh() -> bool:
            nonlocal refresh_called
            refresh_called = True
            return True

        result = _publish_with_retry(
            _RefreshableAdapter(), "/tmp", {"topic": "test"},
            "refresh_test", refresh_fn=mock_refresh,
        )

        assert result["error_code"] == "network_error"
        assert refresh_called is False

    def test_content_rejected_does_not_trigger_refresh(self, monkeypatch: Any) -> None:
        """content_rejected should not trigger credential refresh."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RefreshableAdapter.fail_for = 99
        _RefreshableAdapter.error_reason = "content rejected: spam"
        _RefreshableAdapter.raise_exception = False
        self.setup_method()

        refresh_called: bool = False

        def mock_refresh() -> bool:
            nonlocal refresh_called
            refresh_called = True
            return True

        result = _publish_with_retry(
            _RefreshableAdapter(), "/tmp", {"topic": "test"},
            "refresh_test", refresh_fn=mock_refresh,
        )

        assert result["error_code"] == "content_rejected"
        assert refresh_called is False

    def test_unknown_error_does_not_trigger_refresh(self, monkeypatch: Any) -> None:
        """Unknown errors should not trigger credential refresh."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RefreshableAdapter.fail_for = 99
        _RefreshableAdapter.error_reason = "something unexpected"
        _RefreshableAdapter.raise_exception = True
        self.setup_method()

        refresh_called: bool = False

        def mock_refresh() -> bool:
            nonlocal refresh_called
            refresh_called = True
            return True

        result = _publish_with_retry(
            _RefreshableAdapter(), "/tmp", {"topic": "test"},
            "refresh_test", refresh_fn=mock_refresh,
        )

        assert result["error_code"] == "unknown"
        assert refresh_called is False

    # ------------------------------------------------------------------
    # No refresh_fn — original behavior preserved
    # ------------------------------------------------------------------

    def test_credential_expired_no_refresh_fn_preserves_behavior(
        self, monkeypatch: Any,
    ) -> None:
        """Without refresh_fn, credential_expired returns immediately (backward compat)."""
        from automedia.adapters.publish_engine import _publish_with_retry

        monkeypatch.setattr("time.sleep", lambda _: None)

        _RefreshableAdapter.fail_for = 99
        _RefreshableAdapter.error_reason = "token expired"
        _RefreshableAdapter.raise_exception = True
        self.setup_method()

        result = _publish_with_retry(
            _RefreshableAdapter(), "/tmp", {"topic": "test"},
            "refresh_test",
        )

        assert result["status"] == "error"
        assert result["error_code"] == "credential_expired"
        assert result["retryable"] is True
        assert result["action"] == "refresh_credential"
        assert "max_retries" not in result
        assert _RefreshableAdapter.call_count == 1


# ---------------------------------------------------------------------------
# credential_refresh_failed error code structure
# ---------------------------------------------------------------------------


class TestCredentialRefreshFailedStructure:
    """Verify ``build_error_result`` output for ``credential_refresh_failed``."""

    def test_credential_refresh_failed_structure(self) -> None:
        from automedia.adapters.publish_engine import build_error_result

        result = build_error_result(
            "wechat", "credential_refresh_failed",
            "Credential refresh failed for wechat: token expired",
        )
        assert result["status"] == "error"
        assert result["error_code"] == "credential_refresh_failed"
        assert result["retryable"] is False
        assert result["action"] == "reconnect_account"
        assert "max_retries" not in result
