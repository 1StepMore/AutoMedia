"""AutoMedia platform adapters."""

from automedia.adapters.base import BasePlatformAdapter
from automedia.adapters.platforms.feishu_notifier import FeishuNotifier  # noqa: E402

# ---------------------------------------------------------------------------
# Auto-register built-in platform adapters
# ---------------------------------------------------------------------------
from automedia.adapters.platforms.wechat_publisher import WechatPublisher  # noqa: E402
from automedia.adapters.platforms.xiaohongshu_publisher import XiaohongshuPublisher  # noqa: E402
from automedia.adapters.platforms.zhihu_publisher import ZhihuPublisher  # noqa: E402
from automedia.adapters.publish_engine import PublishEngine
from automedia.adapters.registry import AdapterRegistry

AdapterRegistry.register(WechatPublisher)
AdapterRegistry.register(FeishuNotifier)
AdapterRegistry.register(XiaohongshuPublisher)
AdapterRegistry.register(ZhihuPublisher)

__all__ = [
    "BasePlatformAdapter",
    "AdapterRegistry",
    "PublishEngine",
    "WechatPublisher",
    "FeishuNotifier",
    "XiaohongshuPublisher",
    "ZhihuPublisher",
]
