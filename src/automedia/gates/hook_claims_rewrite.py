"""Deterministic hedge pass for G0 hook-claim tokens (AutoMedia#598).

The G0 rewrite is an LLM round-trip; when the model leaves a banned
outcome-promise token in the hook area, the gate re-detects the same token on
retry and can never converge. This module closes that loop the same way #594
(G1 officialese) and #597 (G2 long sentences) did: a deterministic replacement
over the closed token list, applied only to the sentences the criteria already
flagged.

Contract:

- Only the hit sentences (:attr:`HookClaimHit.text`) are rewritten — body text
  outside the flagged hook segments is returned byte-identical.
- Longer tokens win (``轻松搞定`` before ``轻松``).
- A token with no entry in :data:`HEDGE_MAP` is left alone; the gate then keeps
  failing honestly instead of faking a pass.
- ``HOOK_CLAIMS_BANNED_TOKENS`` and the criteria are untouched.
"""

from __future__ import annotations

import re

from automedia.prompts.hook_claims import hook_area_violations

# Rewrite-time hedge table (#598). Keys mirror the banned tokens where a
# natural hedge exists; a token without an entry stays red by design.
HEDGE_MAP: dict[str, str] = {
    "轻松搞定": "不那么费劲地处理",
    "轻松": "不那么费劲",
    "搞定": "处理完",
    "学会": "掌握",
    "包会": "能上手",
    "速成": "快速入门",
    "保证": "通常",
    "决定": "影响",
    "必然": "多半",
    "一定": "往往",
    "满分": "高分",
    "精通": "熟练",
    "逆袭": "出现转机",
    "躺赢": "占先机",
    "必看": "值得一看",
    "必学": "值得一学",
    "错过就完了": "容易错过",
    "改变命运": "带来变化",
    "化繁为简": "把复杂变简单",
    "不再难": "没那么难",
    "从此不再": "之后较少",
    "再也不": "很少再",
    "告别": "减少对它的依赖",
    "摆脱": "减少对它的依赖",
    "零基础也能": "零基础也可以",
    "一招": "一个方法",
    "教你": "讲给你",
}

# Longer keys first so ``轻松搞定`` is not half-replaced into
# ``不那么费劲搞定``.  Sorted once at import time.
_HEDGE_ORDER: tuple[str, ...] = tuple(sorted(HEDGE_MAP, key=len, reverse=True))


def _hedge_sentence(sentence: str) -> str:
    """Apply :data:`HEDGE_MAP` to one sentence, longest token first."""
    hedged = sentence
    for token in _HEDGE_ORDER:
        if token in hedged:
            hedged = hedged.replace(token, HEDGE_MAP[token])
    return hedged


# ``HookClaimHit.text`` is the whitespace-normalised segment (source lines
# joined with a single space), capped at 160 chars.  The originals keep their
# own line breaks, so the hit text is matched whitespace-insensitively and the
# span is widened to the segment boundary when the hit text was truncated.
_WHITESPACE_RE = re.compile(r"\s+")
_BLOCK_END_RE = re.compile(r"\n[ \t]*\n|\n(?=[ \t]*#)")

_HIT_TEXT_CAP = 160


def _sentence_pattern(sentence: str) -> re.Pattern[str]:
    parts = [re.escape(part) for part in _WHITESPACE_RE.split(sentence)]
    return re.compile(r"\s+".join(parts))


def _locate(text: str, sentence: str, cursor: int) -> tuple[int, int] | None:
    """Find the span of *sentence* in *text*, whitespace-insensitively."""
    pattern = _sentence_pattern(sentence)
    match = pattern.search(text, cursor) or pattern.search(text)
    if match is None:
        return None
    start, end = match.span()
    if len(sentence) >= _HIT_TEXT_CAP:
        # Truncated hit text — widen to the whole segment so the tokens that
        # live past the cap are hedged too.
        block_end = _BLOCK_END_RE.search(text, end)
        end = block_end.start() if block_end else len(text)
    return start, end


def hedge_hook_claims(content: str) -> str:
    """Hedge the flagged hook sentences of *content*; leave everything else.

    Hit sentences are taken from :func:`hook_area_violations` and written back
    in first-occurrence order, so a sentence repeated in the original is
    hedged once per reported hit.  Any text outside the flagged segments — the
    body — is returned byte-identical.
    """
    if not content:
        return content
    text = content
    cursor = 0
    for hit in hook_area_violations(content):
        span = _locate(text, hit.text, cursor)
        if span is None:
            # Truncated hit text (over 160 chars) or already rewritten —
            # nothing safe to splice; leaving it keeps the gate honest.
            continue
        start, end = span
        hedged = _hedge_sentence(text[start:end])
        if hedged == text[start:end]:
            continue
        text = text[:start] + hedged + text[end:]
        cursor = start + len(hedged)
    return text
