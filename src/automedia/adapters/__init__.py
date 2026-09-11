"""AutoMedia platform adapters."""

import contextlib

from automedia.adapters.base import AUTOMATION_DEFAULTS, AutomationLevel, BasePlatformAdapter
from automedia.adapters.platforms.baijiahao_publisher import BaijiahaoPublisher
from automedia.adapters.platforms.bilibili_publisher import BilibiliPublisher
from automedia.adapters.platforms.douyin_publisher import DouyinPublisher
from automedia.adapters.platforms.facebook_publisher import FacebookPublisher
from automedia.adapters.platforms.feishu_notifier import FeishuNotifier
from automedia.adapters.platforms.instagram_publisher import InstagramPublisher
from automedia.adapters.platforms.juejin_publisher import JuejinPublisher
from automedia.adapters.platforms.kuaishou_publisher import KuaishouPublisher
from automedia.adapters.platforms.linkedin_publisher import LinkedInPublisher
from automedia.adapters.platforms.medium_publisher import MediumPublisher
from automedia.adapters.platforms.reddit_publisher import RedditPublisher
from automedia.adapters.platforms.tiktok_publisher import TikTokPublisher
from automedia.adapters.platforms.toutiao_publisher import ToutiaoPublisher
from automedia.adapters.platforms.twitter_publisher import TwitterPublisher

# ---------------------------------------------------------------------------
# Auto-register built-in platform adapters
# ---------------------------------------------------------------------------
from automedia.adapters.platforms.wechat_publisher import WechatPublisher
from automedia.adapters.platforms.weibo_publisher import WeiboPublisher
from automedia.adapters.platforms.wordpress_publisher import WordPressPublisher
from automedia.adapters.platforms.xiaohongshu_publisher import XiaohongshuPublisher
from automedia.adapters.platforms.youtube_publisher import YouTubePublisher
from automedia.adapters.platforms.zhihu_publisher import ZhihuPublisher
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

__all__ = [  # noqa: RUF022 - entries grouped by category; order intentional
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
