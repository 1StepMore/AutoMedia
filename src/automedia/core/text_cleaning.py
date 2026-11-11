"""Shared text hygiene for machine-produced copy.

Two boundaries need the same ``#459`` structure-tag stripping:

- the **narration/subtitle boundary** (video track): what TTS may say —
  :mod:`automedia.pipelines.narration`;
- the **draft → publishable-copy boundary** (image track): what may be
  posted as article body / thread posts — ``clean_publishable_copy`` below,
  applied by the content-writer gate for ``text_with_cover`` /
  ``social-thread`` (#464).

The cleaning primitives live here (a leaf module both tracks can import)
and :mod:`automedia.pipelines.narration` re-exports them, so the video
track's behaviour is unchanged while the image track reuses — not
duplicates — the same logic.
"""

from __future__ import annotations

import re

#: Cue keywords that mark a bracket as a production note rather than prose.
#: ``切`` covers both ``[切]`` and the colonised ``[切：画面瞬间变得干净…]``
#: form the writer model emits (#455).
_CUE_KEYWORDS = (
    r"(?:画面|镜头|镜号|机位|构图|音效|配乐|音乐|bgm|字幕|花字|旁白|画外音|"
    r"切|转场|特效|特写|全景|中景|近景|远景|视觉|提示|"
    r"visual|sfx|vfx|cut\s*to|transition|shot)"
)

#: ``[画面：…]`` / ``（镜头：…）`` / ``【音效：…】`` — anything bracketed that
#: opens with a cue keyword.  The body may contain ``/``, ``、`` and colons;
#: only the matching bracket pair terminates it.
_BRACKETED_CUE_RE = re.compile(
    r"[\[【（(]\s*" + _CUE_KEYWORDS + r"[^\[\]【】（）()]{0,300}?[\]】）)]",
    re.IGNORECASE,
)

#: A cue whose closing bracket never arrives (truncated draft, or the closer
#: landed on the next line).  Runs to end of line only.
_DANGLING_CUE_RE = re.compile(
    r"[\[【（(]\s*" + _CUE_KEYWORDS + r"[^\[\]【】（）()\n]*$",
    re.IGNORECASE | re.MULTILINE,
)

_HSPACE_RUN_RE = re.compile(r"[ \t]{2,}")

#: Paired markdown emphasis markers (``**粗体**`` / ``__粗体__`` / ``*斜体*`` /
#: ``_斜体_``).  The narrator reads the markers themselves out loud ("星号星号",
#: issue #444), so only the emphasised words may survive.  Single underscores
#: inside a word (``a_b_c``) are not emphasis and stay untouched.
_EMPHASIS_PAIR_RES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\*\*(.+?)\*\*", re.DOTALL), r"\1"),
    (re.compile(r"__(.+?)__", re.DOTALL), r"\1"),
    (re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", re.DOTALL), r"\1"),
    (re.compile(r"(?<!\w)_(?!_)(.+?)(?<!_)_(?!\w)", re.DOTALL), r"\1"),
)

#: Stray runs left behind by unpaired markers (``**`` / ``__``).  Never prose,
#: always read aloud — drop them.
_STRAY_EMPHASIS_RE = re.compile(r"\*{2,}|_{2,}")

#: Emoji pictographs are not spoken words (#496).  The service TTS reads 👇 as
#: a description of the glyph ("反手十指向下指"), the audio carries that reading
#: and the ASR transcript records it as if the script had said it.  The
#: pictographic planes (``\U0001F000-\U0001FAFF``) cover 👇/👉/🔥/flags; the two
#: symbol blocks add ✅ ⭐ ✔; the keycap alternative takes its base digit
#: (``1️⃣``); the trailing classes drop the variation selectors, ZWJ and keycap
#: marks a sequence leaves behind.  CJK text and punctuation are outside every
#: class and survive untouched.
_EMOJI_RE = re.compile(
    "(?:[0-9#*]\ufe0f?\u20e3)"
    "|[\U0001f000-\U0001faff\u2600-\u27bf\u2b00-\u2bff\ufe00-\ufe0f\u200d\u20e3]"
)

#: Labels that head a script-structure row (``主题：`` / ``品牌：…`` /
#: ``镜头2``) — they describe the script to a human editor, never the words a
#: narrator says (#455).
_STRUCTURE_LABEL = r"(?:主题|品牌|时长|风格|平台|bgm|音效|字幕|画面|运镜|机位|场景|转场|镜头\s*\d+)"

#: A row or ``｜``-separated segment that opens with a structure label.
_STRUCTURE_SEGMENT_RE = re.compile(rf"^{_STRUCTURE_LABEL}\s*[:：｜|]", re.IGNORECASE)

#: ``镜头1｜0:03-0:09`` — a shot header with its timecode (#455).
_SHOT_HEADER_RE = re.compile(
    r"镜头\s*\d+\s*(?:[｜|:：]\s*)?\d{1,2}:\d{2}\s*[-–—~至]\s*\d{1,2}:\d{2}\s*"
)

#: ``口播：`` / ``口播文案：`` mark the spoken part of the script; the label
#: itself is never spoken (#455).
_SPOKEN_PREFIX_RE = re.compile(r"口播(?:文案)?\s*[:：]\s*")

#: ``0:03-0:09`` / ``（0:00-0:03）`` — production timing.  Never narration:
#: a TTS-ready script writes durations in words, so a colon timecode span is
#: scaffolding wherever it sits (parenthesised section headers included).
_TIMECODE_SPAN_RE = re.compile(r"[（(]?\s*\d{1,2}:\d{2}\s*[-–—~至]\s*\d{1,2}:\d{2}\s*[）)]?")

#: Short uncolonised production tags — ``[切]`` / ``[转场]`` / ``[停顿]``.
#: Deliberately an allowlist: ordinary bracketed prose must survive (#455).
_SHORT_CUE_TAG_RE = re.compile(
    r"\[(?:切|转场|切换|停顿|暂停|淡入|淡出|黑场|闪回|叠化|白闪|黑闪|分屏)\]"
)

#: Segments inside a metadata row are separated by full-width or ASCII bars.
_SEGMENT_SPLIT_RE = re.compile(r"\s*[｜|]\s*")

#: 小节标题词集中清单（#461，owner 裁定「剥」）：分镜脚本的小节标题行
#: （``**黄金开头（0:00-0:03）**`` 等）在时间码被 #455 剥掉后剩下的标题词
#: 本体仍是独立一行，TTS 会把「黄金开头」「正文」「高潮反转」念出来。
#: **这是唯一权威清单——不要把词散落进正则**；新词加在这里。
#: 「反转」来自 #461 的夜跑 ASR 证据（标题行实为 ``高潮/反转``）。
_SECTION_HEADING_WORDS: tuple[str, ...] = (
    "黄金开头",
    "正文",
    "高潮",
    "反转",
    "引导互动",
    "结尾",
    "开场",
    "收尾",
)

#: 一行里允许连接标题词的分隔符（``高潮/反转``、``开场 · 正文``）。
_SECTION_HEADING_SEP_RE = re.compile(r"[\s/、·・\-－—_|｜]+")

#: 行首「标题词：」标签前缀（``高潮：节奏先乱`` → 剥标签保正文）。
_SECTION_HEADING_PREFIX_RE = re.compile(
    r"^(?:" + "|".join(_SECTION_HEADING_WORDS) + r")\s*[:：]\s*"
)


def _is_section_heading_line(line: str) -> bool:
    """整行都是小节标题词（允许分隔符连接）→ True（#461）。

    ``黄金开头`` / ``高潮/反转`` / ``开场 · 正文`` 是标题行；而
    ``这段高潮在于节奏`` 的剩余段不是标题词 → False，正文不误剥。
    """
    segments = [seg for seg in _SECTION_HEADING_SEP_RE.split(line.strip()) if seg]
    return bool(segments) and all(seg in _SECTION_HEADING_WORDS for seg in segments)


# ---------------------------------------------------------------------------
# Publishable-copy boundary (#464)
# ---------------------------------------------------------------------------

#: ``## Post 1: 标题`` / ``### 第2篇：标题`` — a heading marker followed by an
#: optional thread-post label.  The ``#`` markers and the ``Post N:`` /
#: ``第N篇`` label are script structure ("for the editor"); the title text
#: after them is content and is kept (#464).
_PUBLISH_HEADING_RE = re.compile(r"^\s*#{1,6}\s*")

#: The thread-post label itself: ``Post 1:`` / ``post 12：`` / ``第3篇：`` /
#: ``篇2``.  Numbering for a human editor; readers see the posts in order.
_PUBLISH_POST_LABEL_RE = re.compile(
    r"^(?:post\s*\d+|第\s*\d+\s*篇|\d+\s*篇)\s*[:：]\s*", re.IGNORECASE
)

#: ``[文字贴纸：别盲目追求数量]`` / ``【文字贴纸：正确姿势】`` — the sticker
#: text is the card overlay copy, which for the *post text* is the post's
#: punchline; the marker is scaffolding, the content is kept (#464 卡住条款).
_PUBLISH_STICKER_TAG_RE = re.compile(r"[\[【]\s*文字贴纸\s*[:：]\s*([^\]】]*)[\]】]")

#: ``旁白：`` / ``旁白:`` / ``**旁白**：`` — the voice-over label heads the
#: post body; the label is structure, the words after it are the post (#464).
_PUBLISH_NARRATION_PREFIX_RE = re.compile(
    r"^(?:\*{0,2})(?:旁白|口播|画外音)(?:文案)?(?:\*{0,2})\s*[:：]\s*"
)


def strip_emphasis_markers(text: str) -> str:
    """Unwrap markdown emphasis so only the spoken words remain (#444).

    ``**主题**：先跑通流程`` becomes ``主题：先跑通流程``.  Paired markers are
    unwrapped first; whatever run of ``**``/``__`` survives is an unpaired
    marker, which is still unreadable aloud and is removed.  A single
    underscore inside a word (``a_b_c``) is not emphasis and is preserved.
    """
    cleaned = text or ""
    for pattern, replacement in _EMPHASIS_PAIR_RES:
        cleaned = pattern.sub(replacement, cleaned)
    return _STRAY_EMPHASIS_RE.sub("", cleaned)


def strip_stage_directions(text: str) -> str:
    """Remove bracketed production cues, keeping the prose around them."""
    if not text:
        return ""
    cleaned = _BRACKETED_CUE_RE.sub("", text)
    cleaned = _DANGLING_CUE_RE.sub("", cleaned)
    lines = [_HSPACE_RUN_RE.sub(" ", line).strip() for line in cleaned.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def strip_structure_labels(text: str) -> str:
    """Drop script structure — metadata rows, shot headers, spoken prefixes.

    ``strip_narration_markup`` feeds TTS and the SRT, so labels such as
    ``主题：`` / ``镜头1｜0:03-0:09`` / ``口播：`` / ``[切]`` would be read
    aloud (#455).  Rows and ``｜``-segments that open with a structure label
    are removed; a shot header or ``口播：`` prefix on a spoken line is peeled
    off and the prose kept.  Bracketed tags outside the production vocabulary
    are left alone.
    """
    kept_lines: list[str] = []
    for line in (text or "").splitlines():
        line = _SHORT_CUE_TAG_RE.sub("", line)
        line = _SHOT_HEADER_RE.sub("", line)
        line = _TIMECODE_SPAN_RE.sub("", line)
        line = _SPOKEN_PREFIX_RE.sub("", line)
        segments = [seg for seg in _SEGMENT_SPLIT_RE.split(line) if seg]
        structured = "".join(
            seg for seg in segments if not _STRUCTURE_SEGMENT_RE.match(seg.strip())
        ).strip()
        if structured:
            # #461：时间码剥掉后剩下的整行标题词是伪标题，丢弃；行首
            # 「标题词：」是标签形式，剥标签保正文。正文里的正常同名词
            # （如「这段高潮在于节奏」）两条规则都不命中，原样保留。
            if _is_section_heading_line(structured):
                continue
            structured = _SECTION_HEADING_PREFIX_RE.sub("", structured).strip()
            if not structured:
                continue
            kept_lines.append(structured)
    return "\n".join(kept_lines).strip()


def strip_emoji(text: str) -> str:
    """Remove emoji pictographs; keep every word and punctuation mark (#496).

    中文说明：TTS 会把 emoji 念成对图形的描述（👇 被念成「反手十指向下
    指」），ASR 再把这句话写进 narration.json，观众于是听到一句没人写过
    的话。emoji 不是口播内容，在旁白边界直接删除；CJK 与中英文标点不在
    删除范围内，照常保留。
    """
    if not text:
        return ""
    return _EMOJI_RE.sub("", text)


def strip_narration_markup(text: str) -> str:
    """Drop markdown structure and production cues from narrated text.

    Headings are section labels, not sentences; bullet markers are scaffolding;
    bracketed cues are notes for whoever edits the video; script structure rows
    and shot headers are notes for the editor (#455).  Only the words a person
    would actually say survive.
    """
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Horizontal rules and empty bullet scaffolding carry no words.
        if not line.strip("-*_ "):
            continue
        line = re.sub(r"^(?:[-*>]\s*)+", "", line).strip()
        if line:
            lines.append(line)
    cleaned = strip_emphasis_markers("\n".join(lines))
    # Cues are stripped before structure rows so ``[画面：…]主题：…`` is still
    # recognised as a metadata row (#455).
    cleaned = strip_stage_directions(cleaned)
    cleaned = strip_structure_labels(cleaned)
    return _HSPACE_RUN_RE.sub(" ", strip_emoji(cleaned)).strip()


def clean_publishable_copy(text: str) -> str:
    """Clean a draft into publishable image-track copy (#464).

    The content writer emits a *storyboard script*; ``text_with_cover`` and
    ``social-thread`` had no equivalent of the video track's narration
    cleaning, so ``##`` headings, ``[画面：…]`` cues, ``旁白：`` prefixes and
    ``[切]`` tags landed verbatim in the post (#464).  At the draft →
    publishable-copy boundary the structure is stripped and the content kept:

    - ``## Post 1: 标题`` → the title line (``#`` markers and the ``Post N:``
      thread label are editor structure; title text and post order survive);
    - ``[画面：…]`` / ``[音效：…]`` / ``[切]`` / ``[转场：…]`` → dropped
      (production cues, no reader-facing content);
    - ``[文字贴纸：xxx]`` → unwrapped to ``xxx`` — the sticker text is the
      card copy and reads as the post's punchline (kept per #464 卡住条款);
    - ``旁白：`` / ``口播：`` prefixes → peeled off, the words kept;
    - ``**粗体**`` emphasis → unwrapped so no literal ``**`` is posted.

    Section-heading *words* that survive as plain lines (``黄金开头`` etc.)
    are #461's scope and are deliberately not touched here.
    """
    if not text:
        return ""
    # Sticker tags are unwrapped *before* cue stripping so their content
    # survives the production-cue pass.
    cleaned = _PUBLISH_STICKER_TAG_RE.sub(r"\1", text)
    # Cue stripping is single-pass; a nested cue (``[画面：[切] 绿幕背景]``,
    # present in the #445 night-run draft) exposes an outer bracket only
    # after the inner one is removed.  Iterate to a fixpoint (bounded).
    for _ in range(3):
        stripped = strip_stage_directions(cleaned)
        if stripped == cleaned:
            break
        cleaned = stripped
    cleaned = strip_emphasis_markers(cleaned)

    kept_lines: list[str] = []
    for raw in cleaned.splitlines():
        line = raw.strip()
        if not line:
            kept_lines.append("")
            continue
        if line.strip("-*_ "):
            # ``- `` / ``> `` bullets are scaffolding; ``##`` heading markers
            # and a thread-post label are editor structure — peel them.
            line = re.sub(r"^(?:[-*>]\s*)+", "", line).strip()
            line = _PUBLISH_HEADING_RE.sub("", line)
            line = _PUBLISH_POST_LABEL_RE.sub("", line)
        line = _PUBLISH_NARRATION_PREFIX_RE.sub("", line).strip()
        kept_lines.append(line)

    out = "\n".join(kept_lines)
    # Collapse runs of blank lines left by dropped cue-only lines.
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


__all__ = [
    "clean_publishable_copy",
    "strip_emoji",
    "strip_emphasis_markers",
    "strip_narration_markup",
    "strip_stage_directions",
    "strip_structure_labels",
]
