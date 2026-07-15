"""AutoMedia platform adapters."""

from automedia.adapters.base import AutomationLevel, AUTOMATION_DEFAULTS, BasePlatformAdapter
from automedia.adapters.platforms.feishu_notifier import FeishuNotifier  # noqa: E402

# ---------------------------------------------------------------------------
# Auto-register built-in platform adapters
# ---------------------------------------------------------------------------
from automedia.adapters.platforms.wechat_publisher import WechatPublisher  # noqa: E402
from automedia.adapters.platforms.xiaohongshu_publisher import XiaohongshuPublisher  # noqa: E402
from automedia.adapters.platforms.instagram_publisher import InstagramPublisher  # noqa: E402
from automedia.adapters.platforms.twitter_publisher import TwitterPublisher  # noqa: E402
from automedia.adapters.platforms.youtube_publisher import YouTubePublisher  # noqa: E402
from automedia.adapters.platforms.zhihu_publisher import ZhihuPublisher  # noqa: E402
from automedia.adapters.platforms.reddit_publisher import RedditPublisher  # noqa: E402
from automedia.adapters.platforms.linkedin_publisher import LinkedInPublisher  # noqa: E402
from automedia.adapters.platforms.facebook_publisher import FacebookPublisher  # noqa: E402
from automedia.adapters.platforms.tiktok_publisher import TikTokPublisher  # noqa: E402
from automedia.adapters.platforms.medium_publisher import MediumPublisher  # noqa: E402
from automedia.adapters.platforms.wordpress_publisher import WordPressPublisher  # noqa: E402
from automedia.adapters.platforms.douyin_publisher import DouyinPublisher  # noqa: E402
from automedia.adapters.platforms.bilibili_publisher import BilibiliPublisher  # noqa: E402
from automedia.adapters.platforms.weibo_publisher import WeiboPublisher  # noqa: E402
from automedia.adapters.platforms.toutiao_publisher import ToutiaoPublisher  # noqa: E402
from automedia.adapters.platforms.baijiahao_publisher import BaijiahaoPublisher  # noqa: E402
from automedia.adapters.platforms.kuaishou_publisher import KuaishouPublisher  # noqa: E402
from automedia.adapters.platforms.juejin_publisher import JuejinPublisher  # noqa: E402
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
AdapterRegistry.register(TwitterPublisher)
AdapterRegistry.register(YouTubePublisher)
AdapterRegistry.register(ZhihuPublisher)
AdapterRegistry.register(RedditPublisher)
AdapterRegistry.register(LinkedInPublisher)
AdapterRegistry.register(FacebookPublisher)
AdapterRegistry.register(TikTokPublisher)
AdapterRegistry.register(MediumPublisher)
AdapterRegistry.register(InstagramPublisher)
AdapterRegistry.register(WordPressPublisher)
AdapterRegistry.register(DouyinPublisher)
AdapterRegistry.register(BilibiliPublisher)
AdapterRegistry.register(WeiboPublisher)
AdapterRegistry.register(ToutiaoPublisher)
AdapterRegistry.register(BaijiahaoPublisher)
AdapterRegistry.register(KuaishouPublisher)
AdapterRegistry.register(JuejinPublisher)

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
