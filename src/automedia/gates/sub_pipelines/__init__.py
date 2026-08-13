"""Sub-pipeline gates — multi-stage repurpose pipelines for content formats.

P-series gates handle content repurposing into specific output formats.
Each P-gate runs a sequenced sub-pipeline (e.g. rewrite → review → humanize)
using platform-adapted prompts, and writes the result to
``04_repurpose/<format>/`` in the project directory.
"""

from automedia.gates.sub_pipelines.p1_wechat import P1WechatGate
from automedia.gates.sub_pipelines.p2_twitter import P2TwitterGate
from automedia.gates.sub_pipelines.p3_newsletter import P3NewsletterGate
from automedia.gates.sub_pipelines.p4_bilibili import P4BilibiliRepurpose

__all__ = [
    "P1WechatGate",
    "P2TwitterGate",
    "P3NewsletterGate",
    "P4BilibiliRepurpose",
]
