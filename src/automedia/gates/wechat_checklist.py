"""G4 WeChat Checklist Gate — 7-step compliance check for WeChat articles.

Steps:
    1. title_length    — title ≤ 9 characters
    2. digest_length   — digest ≤ 20 characters
    3. no_markdown     — HTML contains no Markdown artifacts (#, **, -, etc.)
    4. cover_exists    — cover image is provided
    5. tag_count       — tags ≥ 5
    6. body_image_count — body images between 3 and 6
    7. sensitive_words — content contains no blocked terms
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
    "title_length",
    "digest_length",
    "no_markdown",
    "cover_exists",
    "tag_count",
    "body_image_count",
    "sensitive_words",
]

# Markdown artifacts that should NOT appear in rendered HTML
_MARKDOWN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^#{1,6}\s", re.MULTILINE),  # headings: # ## ###
    re.compile(r"\*\*[^*]+\*\*"),  # bold: **text**
    re.compile(r"(?m)^[-*]\s"),  # unordered list: - item / * item
    re.compile(r"(?m)^\d+\.\s"),  # ordered list: 1. item
    re.compile(r"!\[.*?\]\(.*?\)"),  # markdown image: ![alt](url)
    re.compile(r"\[.*?\]\(.*?\)"),  # markdown link: [text](url)
    re.compile(r"`[^`]+`"),  # inline code: `code`
    re.compile(r"```"),  # code fence: ```
    re.compile(r"~~.*?~~"),  # strikethrough: ~~text~~
]

# Common sensitive / blocked terms (simplified list for testing)
_SENSITIVE_WORDS: list[str] = [
    "赌博",
    "色情",
    "暴力",
    "毒品",
    "诈骗",
    "赌博网站",
    "代刷",
    "恶意营销",
]

_SENSITIVE_RE = re.compile(
    r"(?:" + "|".join(re.escape(w) for w in _SENSITIVE_WORDS) + r")",
)

# HTML img tag pattern
_IMG_RE = re.compile(r"<img\s[^>]*src\s*=\s*\"[^\"]*\"[^>]*/?>", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_title_length(title: str) -> CheckResult:
    """Step 1: title ≤ 9 characters."""
    name = "title_length"
    length = len(title)
    if length <= 9:
        return {"name": name, "passed": True, "detail": f"title length {length} ≤ 9"}
    return {"name": name, "passed": False, "detail": f"title length {length} > 9"}


def _check_digest_length(digest: str) -> CheckResult:
    """Step 2: digest ≤ 20 characters."""
    name = "digest_length"
    length = len(digest)
    if length <= 20:
        return {"name": name, "passed": True, "detail": f"digest length {length} ≤ 20"}
    return {"name": name, "passed": False, "detail": f"digest length {length} > 20"}


def _check_no_markdown(content: str) -> CheckResult:
    """Step 3: HTML content contains no Markdown artifacts."""
    name = "no_markdown"
    if not content.strip():
        return {"name": name, "passed": True, "detail": "empty content"}

    found_artifacts: list[str] = []
    for pattern in _MARKDOWN_PATTERNS:
        matches = pattern.findall(content)
        if matches:
            found_artifacts.append(f"matches for {pattern.pattern}")
            break  # one per pattern is enough

    if found_artifacts:
        return {
            "name": name,
            "passed": False,
            "detail": f"Markdown artifact(s) detected: {'; '.join(found_artifacts[:3])}",
        }
    return {"name": name, "passed": True, "detail": "no Markdown artifacts detected"}


def _check_cover_exists(cover_image: str) -> CheckResult:
    """Step 4: cover image is provided."""
    name = "cover_exists"
    if cover_image:
        return {"name": name, "passed": True, "detail": "cover image provided"}
    return {"name": name, "passed": False, "detail": "no cover image"}


def _check_tag_count(tags: list[str]) -> CheckResult:
    """Step 5: tags count ≥ 5."""
    name = "tag_count"
    count = len(tags)
    if count >= 5:
        return {"name": name, "passed": True, "detail": f"{count} tags ≥ 5"}
    return {"name": name, "passed": False, "detail": f"{count} tags < 5"}


def _check_body_image_count(body_images: list[str]) -> CheckResult:
    """Step 6: body image count between 3 and 6."""
    name = "body_image_count"
    count = len(body_images)
    if 3 <= count <= 6:
        return {"name": name, "passed": True, "detail": f"{count} body images in [3, 6]"}
    return {"name": name, "passed": False, "detail": f"{count} body images outside range [3, 6]"}


def _check_sensitive_words(content: str) -> CheckResult:
    """Step 7: content contains no sensitive/blocked words."""
    name = "sensitive_words"
    if not content.strip():
        return {"name": name, "passed": True, "detail": "empty content"}

    matches = _SENSITIVE_RE.findall(content)
    if matches:
        found = sorted(set(m.lower() for m in matches))
        return {
            "name": name,
            "passed": False,
            "detail": f"sensitive term(s) found: {', '.join(found[:5])}",
        }
    return {"name": name, "passed": True, "detail": "no sensitive words detected"}


def _extract_body_images(content: str) -> list[str]:
    """Extract img src URLs from HTML content."""
    return _IMG_RE.findall(content)


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# G4WechatChecklist gate
# ---------------------------------------------------------------------------


class G4WechatChecklist(BaseGate):
    """G4 WeChat Checklist Gate — 7-step compliance check for WeChat articles.

    ``gate_context`` expected keys:
        - ``content``: str — HTML string of the article body
        - ``title``: str — article title
        - ``digest``: str — article digest / description
        - ``cover_image``: str — URL or path to cover image (truthy = provided)
        - ``tags``: list[str] — article tags
        - ``body_images`` (optional): list[str] — image URLs in body.
          If not provided, extracted from ``content`` via regex.
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing without running real detection.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error``.
    """

    _gate_name = "G4"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run 7-step WeChat checklist and return structured result."""
        content: str = gate_context.get("content", "")
        title: str = gate_context.get("title", "")
        digest: str = gate_context.get("digest", "")
        cover_image: str = gate_context.get("cover_image", "")
        tags: list[str] = gate_context.get("tags", [])
        body_images: list[str] = gate_context.get("body_images", _extract_body_images(content))
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            ("title_length", lambda: _check_title_length(title)),
            ("digest_length", lambda: _check_digest_length(digest)),
            ("no_markdown", lambda: _check_no_markdown(content)),
            ("cover_exists", lambda: _check_cover_exists(cover_image)),
            ("tag_count", lambda: _check_tag_count(tags)),
            ("body_image_count", lambda: _check_body_image_count(body_images)),
            ("sensitive_words", lambda: _check_sensitive_words(content)),
        ]

        checks = apply_mock_overrides(check_fns, mock_results)

        return build_gate_result(checks, gate="G4")
