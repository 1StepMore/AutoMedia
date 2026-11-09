"""Canonical word lists shared by the detecting and the documenting sides.

G1 flags these words; the failure-mode knowledge base tells an author what to
avoid.  Both must name the same list, or the guidance contradicts the gate
(#442).
"""

from __future__ import annotations

import re

CN_OFFICIALESE_WORDS: tuple[str, ...] = (
    "赋能",
    "抓手",
    "闭环",
    "颗粒度",
    "底层逻辑",
    "生态",
)

CN_OFFICIALESE_PATTERNS: tuple[str, ...] = tuple(
    r"生态(?!系统)" if word == "生态" else re.escape(word) for word in CN_OFFICIALESE_WORDS
)

CN_OFFICIALESE_RE = re.compile("|".join(CN_OFFICIALESE_PATTERNS))
