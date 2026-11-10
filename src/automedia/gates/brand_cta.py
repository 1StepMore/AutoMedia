"""G3 Brand CTA Gate — zero-tolerance brand & CTA compliance check.

Red Line 4 强制工序最后一道 gate.  Any single check failure → pipeline STOP.

Checks:
    1. brand_name_present   — 主品牌名或别名列表出现
    2. cta_present          — CTA（行动号召）存在
    3. brand_identity       — 品牌身份出现在正文首段（未声明身份时 skip，不判失败）
    4. blocked_words_absent — 禁止词未出现
    5. cta_direction_sync   — 视频 + 文章 CTA 方向同步（可选）
    6. bridge_sentence      — CTA 前存在过渡句

When ``gate_context["_mock_results"]`` is present, each check's result is
driven from that dict instead of running real detection — making the gate
fully deterministic for unit testing.
"""

from __future__ import annotations

import re
from typing import Any

from structlog import get_logger

from automedia.gates._context import CONTENT_PLACEHOLDER_PREFIX, GateContext
from automedia.gates._result import CheckResult, build_gate_result
from automedia.gates.base import BaseGate
from automedia.gates.helpers import apply_mock_overrides, is_cjk_dominant

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "brand_name_present",
    "cta_present",
    "brand_identity",
    "blocked_words_absent",
    "cta_direction_sync",
    "bridge_sentence",
]

# ... (full file content truncated in this demo for length; in real the full content is used)
# The actual implementation has the normalize logic at the _check_brand_identity function
