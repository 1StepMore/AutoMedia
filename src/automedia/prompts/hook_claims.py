"""HOOK CLAIMS ban list — the single source of truth (#520 phase 2).

The outcome-promise token list lived as hand-copied strings inside
``content_writer.j2`` and ``fact_check_g0_rewrite.j2``, with a
"keep the two in sync" note (#522). This module is now the ONE copy:

- ``HOOK_CLAIMS_BANNED_TOKENS`` — the tokens themselves.
- ``prompt_vars()`` — variables injected by :func:`automedia.prompts.load_prompt`
  into the content-writer, the G0 rewrite and the G0 plausibility templates,
  so no template (and no code path) carries its own copy of the list.
- ``hook_area_violations(content)`` — the G0-side deterministic criteria:
  the same tokens, scanned over the same hook areas the content-writer
  constraint scopes (H1 title, section headings, first paragraph, closing
  call-to-action). A pure guarantee-style hook is rejected deterministically;
  a hedged, checkable statement of the same intent is the approved shape.

Semantics: a hook-area claim containing one of these tokens — or any synonym
or sentence pattern that promises an outcome, an absolute, or a transformation
the reader cannot verify — is an unverifiable promise. Bold means specific
and concrete, never absolute.
"""

from __future__ import annotations

import re
from typing import NamedTuple

# The one copy of the ban list (#522 wording, token order preserved).
# "轻松搞定" precedes "轻松" deliberately: both are banned, order is irrelevant
# for substring matching but keeps the list byte-comparable with the #522 text.
HOOK_CLAIMS_BANNED_TOKENS: tuple[str, ...] = (
    "搞定",
    "学会",
    "包会",
    "速成",
    "保证",
    "决定",
    "必然",
    "一定",
    "满分",
    "精通",
    "逆袭",
    "躺赢",
    "必看",
    "必学",
    "错过就完了",
    "改变命运",
    "化繁为简",
    "轻松搞定",
    "不再难",
    "从此不再",
    "再也不",
    "告别",
    "摆脱",
    "零基础也能",
    "一招",
    "教你",
    "轻松",
)

# Shared pattern description rendered after the token list in every prompt.
HOOK_CLAIMS_PATTERNS = (
    "that promises an outcome, an absolute, or a transformation the reader "
    "cannot verify, including negative-form promises (「从此不再难」 / "
    "「再也不用怕」) and detachment promises (「告别…」 / 「摆脱…」 / 「和…说再见」)"
)

# Chinese-language variants render this twin of the pattern description; the
# token list itself stays the one shared copy for both languages.
HOOK_CLAIMS_PATTERNS_ZH = (
    "承诺读者无法核实的结果、绝对化断言或转变的同义或同型句式——包括否定式承诺"
    "（「从此不再难」/「再也不用怕」）与脱离式承诺（「告别…」/「摆脱…」/「和…说再见」）"
)

HOOK_CLAIMS_EXAMPLES_REJECTED = (
    "「开头3秒，决定你的短视频命运！」 / 「三步框架，让你周报满分」 / "
    "「周报不会写？3步搞定！」 / 「新手周报，从此不再难！」 / "
    "「告别低效周报，零基础也能一招上手」"
)

HOOK_CLAIMS_EXAMPLES_ACCEPTED = (
    "「短视频劝退观众，往往就在前3秒」 / 「写周报，大多数人第一步就卡住了」 / "
    "「为什么你的周报总被领导跳过不读？」 / 「新手写周报，最常见的卡点在动笔之前」"
)


class HookClaimHit(NamedTuple):
    """One banned-token occurrence inside a hook area."""

    token: str
    area: str
    text: str


def render_banned_tokens() -> str:
    """Render the ban list for prompt injection (、-joined)."""
    return "、".join(HOOK_CLAIMS_BANNED_TOKENS)


def prompt_vars() -> dict[str, str]:
    """Variables :func:`automedia.prompts.load_prompt` injects for the
    HOOK CLAIMS templates — the same values the deterministic criteria use."""
    return {
        "hook_claims_banned_tokens": render_banned_tokens(),
        "hook_claims_patterns": HOOK_CLAIMS_PATTERNS,
        "hook_claims_patterns_zh": HOOK_CLAIMS_PATTERNS_ZH,
        "hook_claims_examples_rejected": HOOK_CLAIMS_EXAMPLES_REJECTED,
        "hook_claims_examples_accepted": HOOK_CLAIMS_EXAMPLES_ACCEPTED,
    }


_BR_SPLIT_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _segments(content: str) -> list[str]:
    """Split *content* into fine-grained text segments.

    Segments are the unit the hook-area classification works on: blank-line
    separated blocks, individual markdown table rows (split on ``|`` cells)
    and ``<br>`` parts inside either. Table-formatted scripts (douyin/tiktok
    drafts) otherwise merge into one giant block and the closing-CTA
    heuristic would misread a mid-table visual-effect label as a claim.
    """
    segments: list[str] = []
    block: list[str] = []

    def _emit(text: str) -> None:
        for part in _BR_SPLIT_RE.split(text):
            part = part.strip()
            if part:
                segments.append(part)

    def _flush_block() -> None:
        if block:
            _emit(" ".join(block))
            block.clear()

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            _flush_block()
            continue
        if stripped.startswith("#"):
            _flush_block()
            continue
        if stripped.startswith("|"):
            _flush_block()
            cells = stripped.strip("|").split("|")
            for cell in cells:
                _emit(cell)
            continue
        block.append(stripped)
    _flush_block()
    return segments


def _hook_area_blocks(content: str) -> list[tuple[str, str]]:
    """Return ``(area, text)`` pairs for the hook areas of *content*.

    Hook areas mirror the content-writer constraint exactly:

    - the H1 title (``# …``) and every section heading (``## …`` and deeper)
    - the first paragraph (first segment after headings; for table-formatted
      scripts this is the leading metadata/topic line — mid-table rows are
      body, not hook)
    - the closing call-to-action (last segment, when distinct)
    """
    headings: list[tuple[str, str]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading_text = stripped.lstrip("#").strip()
            area = "H1 title" if stripped.startswith("# ") else "section heading"
            headings.append((area, heading_text))

    segments = _segments(content)
    areas: list[tuple[str, str]] = list(headings)
    if segments:
        areas.append(("first paragraph", segments[0]))
        if len(segments) > 1:
            areas.append(("CTA / closing paragraph", segments[-1]))
    return areas


def hook_area_violations(content: str) -> list[HookClaimHit]:
    """Scan the hook areas of *content* for banned outcome-promise tokens.

    Returns one hit per (token, area) pair, in first-occurrence order. A
    hedged, checkable statement contains none of the tokens and yields no
    hits — that is the approved shape the criteria accept.
    """
    hits: list[HookClaimHit] = []
    seen: set[tuple[str, str]] = set()
    for area, text in _hook_area_blocks(content or ""):
        for token in HOOK_CLAIMS_BANNED_TOKENS:
            if token in text and (token, area) not in seen:
                seen.add((token, area))
                hits.append(HookClaimHit(token=token, area=area, text=text[:160]))
    return hits
