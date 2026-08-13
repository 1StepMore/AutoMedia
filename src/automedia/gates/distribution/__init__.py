"""Distribution gates — platform-specific content rewrite and formatting.

D-gates handle content reformatting, rewriting, and packaging for specific
publishing platforms. Each D-gate reads the base content and produces a
platform-adapted version stored under ``04_distribution/<platform>/`` in
the project directory.
"""

from automedia.gates.distribution.d1_wechat import D1Gate
from automedia.gates.distribution.d2_twitter import D2Gate
from automedia.gates.distribution.d3_zhihu import D3ZhihuRewrite
from automedia.gates.distribution.d4_xiaohongshu import D4Gate
from automedia.gates.distribution.d5_bilibili import D5BilibiliRewrite
from automedia.gates.distribution.d6_youtube import D6YouTubeGate
from automedia.gates.distribution.d7_tiktok import D7Gate

__all__ = [
    "D1Gate",
    "D2Gate",
    "D3ZhihuRewrite",
    "D4Gate",
    "D5BilibiliRewrite",
    "D6YouTubeGate",
    "D7Gate",
]
