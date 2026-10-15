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

from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result
from automedia.gates.base import BaseGate
from automedia.gates.helpers import apply_mock_overrides

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

#: Window size (characters) used to approximate the "正文首段" when the
#: content carries no blank-line paragraph separation.  Matches the 200-char
#: context window already used by :func:`_check_bridge_sentence`.
_BRAND_IDENTITY_WINDOW_CHARS: int = 200

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


def _check_cta_present(content: str) -> CheckResult:
    """Check 2: CTA（行动号召）是否存在。"""
    name = "cta_present"
    matches = _CTA_RE.findall(content)
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


def _first_identity_window(content: str) -> tuple[str, str]:
    """返回判定品牌身份所用的「正文首段」文本及其人类可读的窗口描述。

    中文说明：优先取正文的第一段——跳过开头的纯 Markdown 标题块（H1 标题
    不承载定位句）。若正文没有任何段落切分（整篇只有一个文本块），退化为
    **前 N 个字符**的窗口，``N = :data:`_BRAND_IDENTITY_WINDOW_CHARS```。
    返回的窗口描述用于失败信息，方便排障时知道「在哪个窗口找的」。
    """
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


def _check_brand_identity(
    content: str,
    brand_profile: dict[str, Any],
) -> CheckResult:
    """Check 3: 品牌身份是否出现在正文首段。

    判据（#202，方案 ②）：品牌档案声明了 ``brand_identity`` 时，归一化后的
    声明值必须出现在**正文首段**（无段落切分时取前
    :data:`_BRAND_IDENTITY_WINDOW_CHARS` 个字符的窗口），出现次数 ≥1 即
    pass。「全文只出现一次」由写作端 Prompt 保证，判据不因重复而判失败。
    档案**未声明** ``brand_identity`` 时该子检查不适用 → 返回 skip
    （``passed=True`` + ``status="skipped"``），不再用凭空默认短语判失败。

    中文说明：本检查只回答一个问题——**档案声明的身份是否落在正文首段**。
    它不回答「这个身份是否被允许」：那属于 per-brand 的约束，归属
    ``blocked_words``（见 :func:`_check_blocked_words`，#157）。
    """
    name = "brand_identity"

    declared_identity: str = brand_profile.get("brand_identity", "")
    expected = declared_identity.strip()

    # 未声明身份 ⇒ 不适用：skip 并记账，绝不判失败（#202）。
    if not expected:
        return {
            "name": name,
            "passed": True,
            "status": "skipped",
            "detail": "skipped (no declared identity)",
        }

    window, window_desc = _first_identity_window(content)
    if _normalize_identity(expected) in _normalize_identity(window):
        return {
            "name": name,
            "passed": True,
            "detail": f"declared brand identity '{expected}' found in {window_desc}",
        }

    location = _locate_identity(content, expected)
    return {
        "name": name,
        "passed": False,
        "detail": (
            f"declared brand identity '{expected}' not found in the {window_desc}; "
            f"first occurrence in content: {location}"
        ),
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

    # Find first CTA match position
    cta_match = _CTA_RE.search(content)
    if not cta_match:
        return {
            "name": name,
            "passed": False,
            "detail": "no CTA found, cannot check bridge sentence",
        }

    # Look at the text before the CTA (up to 200 chars)
    cta_start = cta_match.start()
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
            - ``brand_identity``: str — declared brand identity
            - ``blocked_words``: list[str] — forbidden words
        - ``video_script`` (optional): str — for CTA direction sync check
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
            ("brand_identity", lambda: _check_brand_identity(content, brand_profile)),
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
        declared_expected = (brand_profile.get("brand_identity") or "").strip()
        if declared_expected:
            expected_map["brand_identity"] = (
                f"Brand identity '{declared_expected}' appears in the first paragraph"
            )

        result = build_gate_result(checks, gate="G3", expected_map=expected_map)

        return result
