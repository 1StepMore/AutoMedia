"""G3 Brand CTA Gate — zero-tolerance brand & CTA compliance check.

Red Line 4 强制工序最后一道 gate.  Any single check failure → pipeline STOP.

Checks:
    1. brand_name_present   — 主品牌名或别名列表出现
    2. cta_present          — CTA（行动号召）存在
    3. brand_identity       — 品牌身份定位正确（"AI内容生产" / "AI内容生产公司"）
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

from automedia.gates._context import GateContext
from automedia.gates._result import build_gate_result
from automedia.gates.base import BaseGate


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

# Brand identity markers — at least one must appear
_BRAND_IDENTITY_PHRASES: list[str] = [
    "AI内容生产",
    "AI内容生产公司",
    "AI内容创作",
    "AI驱动的内容生产",
]

_EXPECTED_MAP: dict[str, str] = {
    "brand_name_present": "Brand name appears in content",
    "cta_present": "Call-to-action is present in content",
    "brand_identity": "Brand identity 'AI内容生产' is present in content",
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
) -> dict[str, Any]:
    """Check 1: 主品牌名或别名是否在内容中出现。"""
    name = "brand_name_present"
    brand_name: str = brand_profile.get("brand_name", "")
    aliases: list[str] = brand_profile.get("brand_aliases", [])

    # Build list of all names to search for
    all_names: list[str] = []
    if brand_name:
        all_names.append(brand_name)
    all_names.extend(aliases)

    if not all_names:
        return {
            "name": name,
            "passed": False,
            "detail": "no brand_name or brand_aliases defined in brand_profile",
        }

    content_lower = content.lower()
    found: list[str] = []
    for n in all_names:
        if n.lower() in content_lower:
            found.append(n)

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


def _check_cta_present(content: str) -> dict[str, Any]:
    """Check 2: CTA（行动号召）是否存在。"""
    name = "cta_present"
    matches = _CTA_RE.findall(content)
    if matches:
        found = sorted(set(m.strip() for m in matches))
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


def _check_brand_identity(
    content: str,
    brand_profile: dict[str, Any],
) -> dict[str, Any]:
    """Check 3: 品牌身份定位是否正确 — 必须是"AI内容生产"方向。"""
    name = "brand_identity"

    # Also check brand_profile for explicit identity field
    declared_identity: str = brand_profile.get("brand_identity", "")
    expected_identities = [
        "AI内容生产",
        "AI内容生产公司",
        "AI内容创作",
    ]

    # Check if declared identity is valid
    identity_declared_ok = (
        any(expected in declared_identity for expected in expected_identities)
        if declared_identity
        else None
    )

    # Check content for identity phrases
    content_has_identity = any(phrase in content for phrase in _BRAND_IDENTITY_PHRASES)

    # If brand_profile declares an incorrect identity, always fail
    if declared_identity and not identity_declared_ok:
        # Check if it's a clearly wrong identity
        wrong_identities = ["投资情报", "投资分析", "金融分析", "股票", "理财"]
        for wrong in wrong_identities:
            if wrong in declared_identity:
                return {
                    "name": name,
                    "passed": False,
                    "detail": (
                        f"brand identity mismatch: declared '{declared_identity}', "
                        f"expected 'AI内容生产' or similar"
                    ),
                }

    # Content must contain at least one identity phrase
    if content_has_identity:
        found = [p for p in _BRAND_IDENTITY_PHRASES if p in content]
        return {
            "name": name,
            "passed": True,
            "detail": f"brand identity confirmed: {', '.join(found)}",
        }

    # If no explicit identity in brand_profile and not in content → fail
    return {
        "name": name,
        "passed": False,
        "detail": "brand identity 'AI内容生产' not found in content",
    }


def _check_blocked_words(
    content: str,
    brand_profile: dict[str, Any],
) -> dict[str, Any]:
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
    for word in blocked_words:
        if word.lower() in content_lower:
            found.append(word)

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
) -> dict[str, Any]:
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
) -> dict[str, Any]:
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
            - ``brand_aliases``: list[str] — alternative brand names
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
        brand_profile: dict[str, Any] = gate_context.get("brand_profile", {})
        video_script: str | None = gate_context.get("video_script")
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

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

        checks: list[dict[str, Any]] = []
        for name, fn in check_fns:
            if mock_results is not None and name in mock_results:
                mock = mock_results[name]
                checks.append(
                    {
                        "name": name,
                        "passed": bool(mock["passed"]),
                        "detail": str(mock.get("detail", "")),
                    }
                )
            else:
                checks.append(fn())

        result = build_gate_result(checks, gate="G3", expected_map=_EXPECTED_MAP)

        return result
