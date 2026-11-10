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

# CTA trigger phrases (Chinese + English)
_CTA_PATTERNS: list[str] = [
    r"立即(?:咨询|体验|试用|预约|注册|下载|了解|行动|联系|关注)",
    r"免费(?:咨询|试用|体验|领取|下载|注册)",
    r"(?:扫码|点击|访问).*(?:了解更多|预约|注册|体验|咨询)",
    r"联系我们",
    r"(?:了解更多|查看完整|获取更多).*(?:详情|信息|资料)",
    r"(?:join|sign\s*up|get\s*started|learn\s*more|contact\s*us|try\s*(?:it|now|free))",
    r"(?:call|email|reach)\s*(?:us|me|out)",
    r"(?:subscribe|follow)\s*(?:us|me|now)?",
    r"👇",
    r"🔗",
    r"(?:链接|入口|通道|通道).*(?:在|如下|如下)",
]
_CTA_RE = re.compile(
    r"(?:" + "|".join(_CTA_PATTERNS) + r")",
    re.IGNORECASE,
)

#: Chinese colloquial CTAs (#388).  The list above is written for formal
#: copy — 「立即咨询」「扫码了解」— while short-video scripts end with
#: 「评论区扣个1」「点个关注不迷路」, which matched nothing.  G3 is
#: ``failure_mode=stop``, so one miss kills the run before any V gate executes;
#: the vocabulary has to cover how Chinese creators actually ask.
#:
#: Deliberately narrower than "any occurrence of 关注": a beat that merely says
#: 「关注行业动态」is not asking the viewer to do anything, and a CTA check that
#: passes on it teaches the writer nothing.
_CJK_CTA_PATTERNS: list[str] = [
    # Follow / subscribe
    r"点(?:个|一下|一波)?关注",
    r"关注(?:我|我们|一下|一波)",
    r"关注不迷路",
    r"记得关注",
    r"求关注",
    # Comment / interact
    r"评论区",
    r"留言",
    r"扣个?\s*\d+",
    r"评论(?:区)?(?:见|聊|告诉我)",
    # Save / share / like
    r"收藏(?:一下|起来|本文)?",
    r"转发(?:给|一下)?",
    r"点赞",
    r"双击",
    r"三连",
    # Private channel / next episode
    r"私信(?:我|我们)?",
    r"下期见",
    r"我们下期见",
]

_CJK_CTA_RE = re.compile("|".join(_CJK_CTA_PATTERNS))

#: Window size (characters) used to approximate the "正文首段" when the
#: content carries no blank-line paragraph separation.  Matches the 200-char
#: context window already used by :func:`_check_bridge_sentence`.
_BRAND_IDENTITY_WINDOW_CHARS: int = 200

#: Character window for **script-format** content (short-video, social thread).
#: A video script opens with ``### 黄金开头`` — a 3-second hook that must not
#: carry the brand positioning line — so the identity naturally lands in the
#: *second* block ("我是壹目贯维，一家AI内容生产服务商").  Judging only the first
#: block failed every real brand running ``short-video`` (#379).  300 characters
#: covers the hook plus the opening voice-over without letting a brand hide its
#: identity at the end of the script.
_BRAND_IDENTITY_SCRIPT_WINDOW_CHARS: int = 300

_EXPECTED_MAP: dict[str, str] = {
    "brand_name_present": "Brand name appears in content",
    "cta_present": "Call-to-action is present in content",
    # A declared identity must land in the first paragraph; an undeclared
    # profile skips this check entirely (see G3BrandCTA.execute).
    "brand_identity": (
        "Declared brand identity appears in the first paragraph "
        "(skipped when the brand declares no identity)"
    ),
    "blocked_words_absent": "No blocked/forbidden words appear in content",
    "cta_direction_sync": "Video and article CTA directions are synchronized",
    "bridge_sentence": "Bridge/transition sentence appears before CTA",
}


# Bridge / transition sentence patterns before CTA
_BRIDGE_PATTERNS: list[str] = [
    r"(?:如果|若您|如果您|如您).*(?:感兴趣|想|需要|希望|愿意)",
    r"(?:想要|想).*(?:了解|体验|尝试|获取|获得)",
    r"(?:别犹豫|别错过|不要错过|现在就|马上)",
    r"(?:有兴趣|有需要|准备好)",
    r"(?:ready|interested|want)\s+to\b",
    r"(?:don'?t\s+(?:hesitate|wait|miss))",
    r"(?:if\s+you\s+(?:want|need|are\s+interested))",
]
_BRIDGE_RE = re.compile(
    r"(?:" + "|".join(_BRIDGE_PATTERNS) + r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_brand_name_present(
    content: str,
    brand_profile: dict[str, Any],
) -> CheckResult:
    """Check 1: 主品牌名或别名是否在内容中出现。"""
    name = "brand_name_present"
    brand_name: str = brand_profile.get("brand_name", "")
    aliases: list[str] = brand_profile.get("aliases", [])

    # Build list of all names to search for
    all_names: list[str] = []
    if brand_name:
        all_names.append(brand_name)
    all_names.extend(aliases)

    if not all_names:
        return {
            "name": name,
            "passed": False,
            "detail": "no brand_name or aliases defined in brand_profile",
        }

    content_lower = content.lower()
    found: list[str] = []
    found.extend(n for n in all_names if n.lower() in content_lower)

    if found:
        return {
            "name": name,
            "passed": True,
            "detail": f"brand name found: {', '.join(found)}",
        }
    return {
        "name": name,
        "passed": False,
        "detail": f"none of the brand names found: {', '.join(all_names)}",
    }


def _cta_matches(content: str) -> list[str]:
    """Return every CTA hit, using the CJK vocabulary for Chinese copy (#388)."""
    matches = _CTA_RE.findall(content)
    if is_cjk_dominant(content):
        matches += _CJK_CTA_RE.findall(content)
    return matches


def _first_cta_start(content: str) -> int | None:
    """Position of the earliest CTA in *content*, or ``None`` when absent."""
    starts: list[int] = []
    match = _CTA_RE.search(content)
    if match:
        starts.append(match.start())
    if is_cjk_dominant(content):
        cjk_match = _CJK_CTA_RE.search(content)
        if cjk_match:
            starts.append(cjk_match.start())
    return min(starts) if starts else None


def _check_cta_present(content: str) -> CheckResult:
    """Check 2: CTA（行动号召）是否存在。

    按语言分流（#388）：英文/书面句式走 :data:`_CTA_RE`，CJK 内容额外走
    :data:`_CJK_CTA_RE`。把中文塞进英文正则会让词表既难读又互相干扰，
    而漏判的代价很高——G3 是 ``stop``，一次漏判整轮就结束，V 轨没有机会执行。
    """
    name = "cta_present"
    matches = _cta_matches(content)
    if matches:
        found = sorted({m.strip() for m in matches})
        return {
            "name": name,
            "passed": True,
            "detail": f"CTA found: {', '.join(found[:5])}",
        }
    return {
        "name": name,
        "passed": False,
        "detail": "no call-to-action detected in content",
    }


def _normalize_identity(text: str) -> str:
    """归一化身份文本：折叠内部空白、去首尾空白、大小写不敏感。"""
    return re.sub(r"\s+", " ", text).strip().lower()


def _split_paragraphs(content: str) -> list[str]:
    """按空行切分正文段落（Markdown / 纯文本通用）。"""
    return [block.strip() for block in re.split(r"\n\s*\n", content.strip()) if block.strip()]


#: ``gate_context["content_format"]`` values that denote a spoken script rather
#: than an article.  Scripts open with a hook, so the identity window widens.
_SCRIPT_FORMATS: frozenset[str] = frozenset({"short_video", "social_thread"})


def _is_script_format(gate_context: GateContext | dict[str, Any]) -> bool:
    """True when the content is a spoken script (short-video / social thread)."""
    return str(gate_context.get("content_format", "") or "") in _SCRIPT_FORMATS


def _first_identity_window(content: str, *, script_format: bool = False) -> tuple[str, str]:
    """返回判定品牌身份所用的「正文首段」文本及其人类可读的窗口描述。

    中文说明：优先取正文的第一段——跳过开头的纯 Markdown 标题块（H1 标题
    不承载定位句）。若正文没有任何段落切分（整篇只有一个文本块），退化为
    **前 N 个字符**的窗口，``N = :data:`_BRAND_IDENTITY_WINDOW_CHARS```。
    返回的窗口描述用于失败信息，方便排障时知道「在哪个窗口找的」。

    脚本格式（``script_format=True``，短视频 / 社媒串）改用前
    :data:`_BRAND_IDENTITY_SCRIPT_WINDOW_CHARS` 个字符的窗口：这类稿子的第一段
    必须是有钩子的开头（前 3 秒），品牌定位句按写作规范落在第二段，用「首段」
    判定会把所有真实品牌判死（#379）。
    """
    if script_format:
        window = content.strip()[:_BRAND_IDENTITY_SCRIPT_WINDOW_CHARS]
        return (
            window,
            f"first {_BRAND_IDENTITY_SCRIPT_WINDOW_CHARS} characters (script format)",
        )
    paragraphs = _split_paragraphs(content)
    if len(paragraphs) > 1:
        for index, block in enumerate(paragraphs):
            lines = [ln for ln in block.splitlines() if ln.strip()]
            if lines and all(ln.lstrip().startswith("#") for ln in lines):
                continue
            return block, f"first body paragraph (paragraph {index + 1})"
    window = content.strip()[:_BRAND_IDENTITY_WINDOW_CHARS]
    return window, f"first {_BRAND_IDENTITY_WINDOW_CHARS} characters (no paragraph break)"


def _locate_identity(content: str, expected: str) -> str:
    """定位声明身份在正文中的首次出现位置（供失败信息使用）。

    先按段落定位（返回 ``paragraph N``），段落级找不到时再退回整篇字符
    偏移（返回 ``character N``），始终找不到则返回 ``not found anywhere``。
    """
    needle = _normalize_identity(expected)
    for index, block in enumerate(_split_paragraphs(content)):
        if needle in _normalize_identity(block):
            return f"paragraph {index + 1}"
    pos = content.lower().find(expected.lower())
    if pos < 0:
        pos = _normalize_identity(content).find(needle)
    if pos >= 0:
        return f"character {pos}"
    return "not found anywhere"


#: ``brand_identity`` 在品牌档案里常以 ``{识别点: 描述}`` 的 dict 形态出现
#: （#460：yimuguanwei 档案即 dict，G3 曾直接 ``.strip()`` 崩溃，堵死三条
#: 图文轨）。取值时只认这些**常见身份键**的值拼成判定文本；一个可判定键
#: 都没有 → 记 ``skipped`` 并写明缺哪些键，绝不拿非身份键的值硬造
#: identity 文本。
_BRAND_IDENTITY_DICT_KEYS: tuple[str, ...] = (
    "识别点",
    "识别",
    "描述",
    "价值观",
    "定位",
    "身份",
    "slogan",
    "identity",
    "description",
    "values",
    "positioning",
)


def _coerce_identity_text(value: Any) -> tuple[str, list[str], str]:  # noqa: ANN401 — brand_identity arrives as an arbitrary YAML value from brand profiles (#460)
    """把档案声明的 ``brand_identity`` 归一成可判定的文本，一律不抛异常。

    兼容四种输入（#460 执行契约）：

    - ``str``：strip 后原样返回，单一判定片段（行为与 #460 之前完全一致）；
    - ``dict``：品牌档案常见 ``{识别点: 描述}`` 形态——按
      :data:`_BRAND_IDENTITY_DICT_KEYS` 里的常见键取各键的值（固定键序，
      保证判定可复现），每个值是一个**判定片段**；一个可判定键都没有 →
      返回空文本 + ``missing`` 说明（期望哪些键、实际有哪些键），
      调用方据此记 ``skipped``——绝不拿非身份键的值硬造 identity 文本；
    - ``list``：逐项递归（str 取本身，dict 走 dict 规则），每项一个片段；
    - ``None``：视为未声明，返回空文本；其余标量（数字等）安全转 str。

    Returns:
        ``(identity_text, fragments, missing_detail)``。``identity_text``
        是各片段用「；」拼接的展示文本；``fragments`` 是逐片段判定用的
        列表（判据：**每个**片段都要落在身份窗口内——str 形态单片段时
        与历史判据逐字等价，dict/list 多片段时取最严格读法）。
        ``identity_text`` 为空时 ``missing_detail`` 解释缺什么；
        未声明（``None``）时三者皆空。
    """
    if value is None:
        return "", [], ""
    if isinstance(value, str):
        text = value.strip()
        return text, ([text] if text else []), ""
    if isinstance(value, dict):
        parts: list[str] = []
        for key in _BRAND_IDENTITY_DICT_KEYS:
            val = value.get(key)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
        if parts:
            return "；".join(parts), parts, ""
        got = ", ".join(str(k) for k in value) or "<empty dict>"
        return (
            "",
            [],
            (
                "dict has no recognizable identity key "
                f"(expected one of {'/'.join(_BRAND_IDENTITY_DICT_KEYS)}); "
                f"got keys: {got}"
            ),
        )
    if isinstance(value, list):
        list_parts: list[str] = []
        for item in value:
            _, item_parts, _ = _coerce_identity_text(item)
            list_parts.extend(item_parts)
        if list_parts:
            return "；".join(list_parts), list_parts, ""
        return "", [], "list is empty or carries no determinable identity text"
    # 其余标量（数字等）：安全转文本，不抛异常。
    text = str(value).strip()
    return text, ([text] if text else []), ""


def _check_brand_identity(
    content: str,
    brand_profile: dict[str, Any],
    *,
    script_format: bool = False,
) -> CheckResult:
    """Check 3: 品牌身份是否出现在正文首段。

    判据（#202，方案 ②；#460 扩展非 str 形态）：品牌档案声明了
    ``brand_identity`` 时，归一化后的**每个声明片段**（str 形态即声明值
    本身；dict/list 形态按 :func:`_coerce_identity_text` 拆片段）必须出现
    在**正文首段**（无段落切分时取前 :data:`_BRAND_IDENTITY_WINDOW_CHARS`
    个字符的窗口），全部出现即 pass。「全文只出现一次」由写作端 Prompt
    保证，判据不因重复而判失败。档案**未声明** ``brand_identity``（或
    dict/list 取不到可判定内容）时该子检查不适用 → 返回 skip
    （``passed=True`` + ``status="skipped"``），不再用凭空默认短语判失败。

    中文说明：本检查只回答一个问题——**档案声明的身份是否落在正文首段**。
    它不回答「这个身份是否被允许」：那属于 per-brand 的约束，归属
    ``blocked_words``（见 :func:`_check_blocked_words`，#157）。
    """
    name = "brand_identity"

    declared_value: Any = brand_profile.get("brand_identity", "")
    expected, fragments, missing_detail = _coerce_identity_text(declared_value)

    # 未声明身份 ⇒ 不适用：skip 并记账，绝不判失败（#202）。dict/list 形态
    # 取不到可判定内容时同样 skip，并写明缺哪个字段（#460）。
    if not expected or not fragments:
        detail = "skipped (no declared identity)"
        if missing_detail:
            detail = f"skipped (brand_identity {missing_detail})"
        return {
            "name": name,
            "passed": True,
            "status": "skipped",
            "detail": detail,
        }

    window, window_desc = _first_identity_window(content, script_format=script_format)
    normalized_window = _normalize_identity(window)
    missing_fragments = [
        fragment for fragment in fragments if _normalize_identity(fragment) not in normalized_window
    ]
    if not missing_fragments:
        return {
            "name": name,
            "passed": True,
            "detail": f"declared brand identity '{expected}' found in {window_desc}",
        }

    # str 单片段：保持 #460 之前的失败文案逐字不变；dict/list 多片段：
    # 额外点名哪些片段缺失（判据 = 每个片段都要落进身份窗口）。
    location = _locate_identity(content, missing_fragments[0])
    detail = (
        f"declared brand identity '{expected}' not found in the {window_desc}; "
        f"first occurrence in content: {location}"
    )
    if len(fragments) > 1:
        detail += f"; missing fragment(s): {', '.join(missing_fragments)}"
    return {
        "name": name,
        "passed": False,
        "detail": detail,
    }


def _check_blocked_words(
    content: str,
    brand_profile: dict[str, Any],
) -> CheckResult:
    """Check 4: 禁止词是否出现。"""
    name = "blocked_words_absent"
    blocked_words: list[str] = brand_profile.get("blocked_words", [])

    if not blocked_words:
        return {
            "name": name,
            "passed": True,
            "detail": "no blocked_words defined",
        }

    content_lower = content.lower()
    found: list[str] = []
    found.extend(word for word in blocked_words if word.lower() in content_lower)

    if found:
        return {
            "name": name,
            "passed": False,
            "detail": f"blocked words found: {', '.join(found)}",
        }
    return {
        "name": name,
        "passed": True,
        "detail": f"all {len(blocked_words)} blocked word(s) absent",
    }


def _check_cta_direction_sync(
    content: str,
    video_script: str | None,
    brand_profile: dict[str, Any],
) -> CheckResult:
    """Check 5: 视频 + 文章 CTA 方向是否同步。

    If no video_script is provided, the check passes (nothing to sync).
    Otherwise, verify both contain CTA and share at least one common
    CTA-related keyword.
    """
    name = "cta_direction_sync"

    if not video_script:
        return {
            "name": name,
            "passed": True,
            "detail": "no video_script provided, skipping sync check",
        }

    # Both must have CTA
    article_has_cta = bool(_CTA_RE.search(content))
    video_has_cta = bool(_CTA_RE.search(video_script))

    if not article_has_cta:
        return {
            "name": name,
            "passed": False,
            "detail": "article has no CTA, cannot sync with video",
        }
    if not video_has_cta:
        return {
            "name": name,
            "passed": False,
            "detail": "video script has no CTA, cannot sync with article",
        }

    # Extract CTA-related keywords from both — look for action verbs
    action_keywords = [
        "咨询",
        "体验",
        "试用",
        "预约",
        "注册",
        "下载",
        "了解",
        "联系",
        "关注",
        "领取",
        "获取",
    ]
    article_actions = [kw for kw in action_keywords if kw in content]
    video_actions = [kw for kw in action_keywords if kw in video_script]

    common = set(article_actions) & set(video_actions)
    if common:
        return {
            "name": name,
            "passed": True,
            "detail": f"CTA direction synced, shared keywords: {', '.join(sorted(common))}",
        }

    return {
        "name": name,
        "passed": False,
        "detail": (
            f"CTA direction mismatch: article actions={article_actions}, "
            f"video actions={video_actions}"
        ),
    }


def _check_bridge_sentence(
    content: str,
) -> CheckResult:
    """Check 6: CTA 前是否存在过渡句 (bridge sentence)。

    Strategy: find the CTA region, then check the preceding text
    for bridge/transition patterns.
    """
    name = "bridge_sentence"

    # Find first CTA match position (language-aware, #388 — a Chinese CTA the
    # previous regex could not see made this check report "no CTA found").
    cta_start = _first_cta_start(content)
    if cta_start is None:
        return {
            "name": name,
            "passed": False,
            "detail": "no CTA found, cannot check bridge sentence",
        }

    # Look at the text before the CTA (up to 200 chars)
    preceding_start = max(0, cta_start - 200)
    preceding_text = content[preceding_start:cta_start]

    # Check for bridge patterns
    if _BRIDGE_RE.search(preceding_text):
        return {
            "name": name,
            "passed": True,
            "detail": "bridge/transition sentence found before CTA",
        }

    # Fallback: check if there's a sentence break (。！!？?) before the CTA
    # indicating at least some preceding context
    if re.search(r"[。！!？?\n]", preceding_text):
        return {
            "name": name,
            "passed": True,
            "detail": "sentence break found before CTA (contextual transition)",
        }

    return {
        "name": name,
        "passed": False,
        "detail": "no transition/bridge sentence found before CTA",
    }


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# G3BrandCTA gate
# ---------------------------------------------------------------------------


class G3BrandCTA(BaseGate):
    """G3 Brand CTA Gate — zero-tolerance brand & CTA compliance.

    Red Line 4 强制工序最后一道.  **任何一项检查失败 → pipeline STOP.**

    ``gate_context`` expected keys:
        - ``content``: str — article/content to check
        - ``brand_profile``: dict with keys:
            - ``brand_name``: str — primary brand name
            - ``aliases``: list[str] — alternative brand names
            - ``brand_identity``: str | dict | list | None — declared brand
              identity; dict/list brand-profile forms are joined into judgment
              text via :func:`_coerce_identity_text` and never raise (#460)
            - ``blocked_words``: list[str] — forbidden words
        - ``video_script`` (optional): str — for CTA direction sync check
        - ``content_format`` (optional): str — ``"short_video"`` /
          ``"social_thread"`` mark spoken scripts, whose identity window is
          character-based instead of "first paragraph" (#379)
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error``.
    """

    _gate_name = "G3"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run 6-point brand & CTA compliance check and return structured result."""
        content: str = gate_context.get("content", "")
        if content.lstrip().startswith(CONTENT_PLACEHOLDER_PREFIX):
            return {
                "passed": True,
                "gate": "G3",
                "checks": [],
                "status": "skipped",
                "reason": "no article content in this mode (runner placeholder)",
            }
        brand_profile: dict[str, Any] | None = gate_context.get("brand_profile", {})
        video_script: str | None = gate_context.get("video_script")
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        if brand_profile is None:
            return {
                "passed": True,
                "gate": "G3",
                "checks": [],
                "error": None,
            }

        check_fns: list[tuple[str, Any]] = [
            ("brand_name_present", lambda: _check_brand_name_present(content, brand_profile)),
            ("cta_present", lambda: _check_cta_present(content)),
            (
                "brand_identity",
                lambda: _check_brand_identity(
                    content,
                    brand_profile,
                    script_format=_is_script_format(gate_context),
                ),
            ),
            ("blocked_words_absent", lambda: _check_blocked_words(content, brand_profile)),
            (
                "cta_direction_sync",
                lambda: _check_cta_direction_sync(content, video_script, brand_profile),
            ),
            ("bridge_sentence", lambda: _check_bridge_sentence(content)),
        ]

        checks = apply_mock_overrides(check_fns, mock_results)

        # expected 文案跟随档案声明值动态拼接；未声明时保持默认描述。
        expected_map = dict(_EXPECTED_MAP)
        declared_expected = _coerce_identity_text(brand_profile.get("brand_identity"))[0]
        if declared_expected:
            expected_map["brand_identity"] = (
                f"Brand identity '{declared_expected}' appears in the first paragraph"
            )

        result = build_gate_result(checks, gate="G3", expected_map=expected_map)

        return result
