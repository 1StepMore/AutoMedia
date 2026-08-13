"""AutoMedia platform adapters."""

import contextlib

from automedia.adapters.base import AUTOMATION_DEFAULTS, AutomationLevel, BasePlatformAdapter
from automedia.adapters.platforms.baijiahao_publisher import BaijiahaoPublisher  # noqa: E402
from automedia.adapters.platforms.bilibili_publisher import BilibiliPublisher  # noqa: E402
from automedia.adapters.platforms.douyin_publisher import DouyinPublisher  # noqa: E402
from automedia.adapters.platforms.facebook_publisher import FacebookPublisher  # noqa: E402
from automedia.adapters.platforms.feishu_notifier import FeishuNotifier  # noqa: E402
from automedia.adapters.platforms.instagram_publisher import InstagramPublisher  # noqa: E402
from automedia.adapters.platforms.juejin_publisher import JuejinPublisher  # noqa: E402
from automedia.adapters.platforms.kuaishou_publisher import KuaishouPublisher  # noqa: E402
from automedia.adapters.platforms.linkedin_publisher import LinkedInPublisher  # noqa: E402
from automedia.adapters.platforms.medium_publisher import MediumPublisher  # noqa: E402
from automedia.adapters.platforms.reddit_publisher import RedditPublisher  # noqa: E402
from automedia.adapters.platforms.tiktok_publisher import TikTokPublisher  # noqa: E402
from automedia.adapters.platforms.toutiao_publisher import ToutiaoPublisher  # noqa: E402
from automedia.adapters.platforms.twitter_publisher import TwitterPublisher  # noqa: E402

# ---------------------------------------------------------------------------
# Auto-register built-in platform adapters
# ---------------------------------------------------------------------------
from automedia.adapters.platforms.wechat_publisher import WechatPublisher  # noqa: E402
from automedia.adapters.platforms.weibo_publisher import WeiboPublisher  # noqa: E402
from automedia.adapters.platforms.wordpress_publisher import WordPressPublisher  # noqa: E402
from automedia.adapters.platforms.xiaohongshu_publisher import XiaohongshuPublisher  # noqa: E402
from automedia.adapters.platforms.youtube_publisher import YouTubePublisher  # noqa: E402
from automedia.adapters.platforms.zhihu_publisher import ZhihuPublisher  # noqa: E402
from automedia.adapters.publish_engine import (
    CONTENT_REJECTED,
    CREDENTIAL_EXPIRED,
    NETWORK_ERROR,
    RATE_LIMITED,
    UNKNOWN,
    PublishEngine,
    build_error_result,
    classify_publish_error,
)
from automedia.adapters.registry import AdapterRegistry

_BUILTIN_ADAPTERS: tuple[type[BasePlatformAdapter], ...] = (
    WechatPublisher,
    FeishuNotifier,
    XiaohongshuPublisher,
    TwitterPublisher,
    YouTubePublisher,
    ZhihuPublisher,
    RedditPublisher,
    LinkedInPublisher,
    FacebookPublisher,
    TikTokPublisher,
    MediumPublisher,
    InstagramPublisher,
    WordPressPublisher,
    DouyinPublisher,
    BilibiliPublisher,
    WeiboPublisher,
    ToutiaoPublisher,
    BaijiahaoPublisher,
    KuaishouPublisher,
    JuejinPublisher,
)


def ensure_registered() -> None:
    """Idempotently register all built-in adapters.

    Registration normally happens once at module import, but tests that call
    ``AdapterRegistry.clear()`` empty the singleton; re-importing this module
    does not re-run module-level code.  Call this before validating platform
    names so the registry always contains the built-in set.
    """
    for adapter_cls in _BUILTIN_ADAPTERS:
        with contextlib.suppress(KeyError):
            AdapterRegistry.register(adapter_cls)  # already registered


ensure_registered()

__all__ = [
    "AutomationLevel",
    "AUTOMATION_DEFAULTS",
    "BasePlatformAdapter",
    "AdapterRegistry",
    "PublishEngine",
    "WechatPublisher",
    "FeishuNotifier",
    "XiaohongshuPublisher",
    "TwitterPublisher",
    "YouTubePublisher",
    "ZhihuPublisher",
    "RedditPublisher",
    "TikTokPublisher",
    "LinkedInPublisher",
    "FacebookPublisher",
    "MediumPublisher",
    "InstagramPublisher",
    "WordPressPublisher",
    "DouyinPublisher",
    "BilibiliPublisher",
    "WeiboPublisher",
    "ToutiaoPublisher",
    "BaijiahaoPublisher",
    "KuaishouPublisher",
    "JuejinPublisher",
    # Error codes
    "CREDENTIAL_EXPIRED",
    "RATE_LIMITED",
    "NETWORK_ERROR",
    "CONTENT_REJECTED",
    "UNKNOWN",
    "classify_publish_error",
    "build_error_result",
]
