"""AutoMedia platform adapters."""

from automedia.adapters.base import AutomationLevel, AUTOMATION_DEFAULTS, BasePlatformAdapter
from automedia.adapters.platforms.feishu_notifier import FeishuNotifier  # noqa: E402

# ---------------------------------------------------------------------------
# Auto-register built-in platform adapters
# ---------------------------------------------------------------------------
from automedia.adapters.platforms.wechat_publisher import WechatPublisher  # noqa: E402
from automedia.adapters.platforms.xiaohongshu_publisher import XiaohongshuPublisher  # noqa: E402
from automedia.adapters.platforms.zhihu_publisher import ZhihuPublisher  # noqa: E402
from automedia.adapters.publish_engine import (
    CREDENTIAL_EXPIRED,
    NETWORK_ERROR,
    RATE_LIMITED,
    CONTENT_REJECTED,
    UNKNOWN,
    PublishEngine,
    build_error_result,
    classify_publish_error,
)
from automedia.adapters.registry import AdapterRegistry

AdapterRegistry.register(WechatPublisher)
AdapterRegistry.register(FeishuNotifier)
AdapterRegistry.register(XiaohongshuPublisher)
AdapterRegistry.register(ZhihuPublisher)

__all__ = [
    "AutomationLevel",
    "AUTOMATION_DEFAULTS",
    "BasePlatformAdapter",
    "AdapterRegistry",
    "PublishEngine",
    "WechatPublisher",
    "FeishuNotifier",
    "XiaohongshuPublisher",
    "ZhihuPublisher",
    # Error codes
    "CREDENTIAL_EXPIRED",
    "RATE_LIMITED",
    "NETWORK_ERROR",
    "CONTENT_REJECTED",
    "UNKNOWN",
    "classify_publish_error",
    "build_error_result",
]
