"""G5 HTML Hard Gate — structural HTML integrity checks.

Checks:
    1. tag_integrity    — basic HTML tags are properly opened/closed
    2. no_markdown      — HTML contains no Markdown artifacts
    3. tag_count        — tags list ≥ 5
"""

from __future__ import annotations

import re
from typing import Any

from automedia.gates.base import BaseGate


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "tag_integrity",
    "no_markdown",
    "tag_count",
]

# Markdown artifacts that should NOT appear in rendered HTML
_MARKDOWN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^#{1,6}\s", re.MULTILINE),
    re.compile(r"\*\*[^*]+\*\*"),
    re.compile(r"(?m)^[-*]\s"),
    re.compile(r"(?m)^\d+\.\s"),
    re.compile(r"!\[.*?\]\(.*?\)"),
    re.compile(r"\[.*?\]\(.*?\)"),
    re.compile(r"`[^`]+`"),
    re.compile(r"```"),
    re.compile(r"~~.*?~~"),
]

# Tags that are expected to appear paired in well-formed HTML
_PAIRED_TAGS: list[str] = [
    "html", "head", "body", "div", "p", "span", "h1", "h2", "h3",
    "h4", "h5", "h6", "ul", "ol", "li", "table", "tr", "td", "th",
    "a", "strong", "em", "b", "i", "u", "section", "article",
    "header", "footer", "nav", "main", "aside", "blockquote",
    "form", "label", "select", "option", "textarea",
]

# Tags that are self-closing (void elements)
_VOID_TAGS: set[str] = {
    "br", "hr", "img", "input", "meta", "link", "area", "base",
    "col", "embed", "source", "track", "wbr",
}

# Regex to extract tag names (opening and closing)
_OPEN_TAG_RE = re.compile(r"<(\w+)[^>]*>", re.DOTALL)
_CLOSE_TAG_RE = re.compile(r"</(\w+)>", re.DOTALL)


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_tag_integrity(content: str) -> dict[str, Any]:
    """Check 1: Basic HTML tag structure is well-formed.

    For every paired tag that appears, count open vs close tags.
    Reports mismatches for tags where counts differ.
    """
    name = "tag_integrity"
    if not content.strip():
        return {"name": name, "passed": True, "detail": "empty content"}

    open_tags = _OPEN_TAG_RE.findall(content)
    close_tags = _CLOSE_TAG_RE.findall(content)

    # Count occurrences of each tag
    open_counts: dict[str, int] = {}
    for t in open_tags:
        t_lower = t.lower()
        if t_lower not in _VOID_TAGS:
            open_counts[t_lower] = open_counts.get(t_lower, 0) + 1

    close_counts: dict[str, int] = {}
    for t in close_tags:
        t_lower = t.lower()
        close_counts[t_lower] = close_counts.get(t_lower, 0) + 1

    mismatches: list[str] = []
    all_tag_names = set(open_counts) | set(close_counts)
    for tag in sorted(all_tag_names):
        open_n = open_counts.get(tag, 0)
        close_n = close_counts.get(tag, 0)
        if open_n != close_n:
            mismatches.append(f"<{tag}>: {open_n} open vs {close_n} close")

    if mismatches:
        return {
            "name": name,
            "passed": False,
            "detail": f"tag mismatch(es): {'; '.join(mismatches[:5])}",
        }
    return {"name": name, "passed": True, "detail": "all paired tags match"}


def _check_no_markdown(content: str) -> dict[str, Any]:
    """Check 2: HTML content contains no Markdown artifacts."""
    name = "no_markdown"
    if not content.strip():
        return {"name": name, "passed": True, "detail": "empty content"}

    found_artifacts: list[str] = []
    for pattern in _MARKDOWN_PATTERNS:
        matches = pattern.findall(content)
        if matches:
            found_artifacts.append(f"matches for {pattern.pattern}")
            break

    if found_artifacts:
        return {
            "name": name,
            "passed": False,
            "detail": f"Markdown artifact(s) detected: {'; '.join(found_artifacts[:3])}",
        }
    return {"name": name, "passed": True, "detail": "no Markdown artifacts detected"}


def _check_tag_count(tags: list[str]) -> dict[str, Any]:
    """Check 3: tags count ≥ 5."""
    name = "tag_count"
    count = len(tags)
    if count >= 5:
        return {"name": name, "passed": True, "detail": f"{count} tags ≥ 5"}
    return {"name": name, "passed": False, "detail": f"{count} tags < 5"}


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------


def _derive_expected(check_name: str) -> str:
    """Convert a snake_case check name to a human-readable expected statement."""
    return check_name.replace("_", " ").capitalize() + "."


def _build_result(
    checks: list[dict[str, Any]],
    *,
    error: str | None = None,
) -> dict[str, Any]:
    """Assemble the final gate result dict from individual *checks*."""
    all_passed = all(c["passed"] for c in checks)
    first_fail = next((c for c in checks if not c["passed"]), None)
    target = first_fail if first_fail is not None else checks[0]
    expected_vs_actual = {
        "check": target["name"],
        "expected": _derive_expected(target["name"]),
        "actual": target.get("detail", ""),
        "context": {},
    }
    return {
        "passed": all_passed,
        "gate": "G5",
        "checks": checks,
        "error": error,
        "expected_vs_actual": expected_vs_actual,
    }


# ---------------------------------------------------------------------------
# G5HtmlHard gate
# ---------------------------------------------------------------------------


class G5HtmlHard(BaseGate):
    """G5 HTML Hard Gate — structural HTML integrity checks.

    ``gate_context`` expected keys:
        - ``content``: str — HTML string to validate
        - ``tags``: list[str] — article tags
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing without running real detection.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error``.
    """

    _gate_name = "G5"
    _failure_mode = "stop"

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        """Run HTML-hard checks and return structured result."""
        content: str = gate_context.get("content", "")
        tags: list[str] = gate_context.get("tags", [])
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            ("tag_integrity", lambda: _check_tag_integrity(content)),
            ("no_markdown", lambda: _check_no_markdown(content)),
            ("tag_count", lambda: _check_tag_count(tags)),
        ]

        checks: list[dict[str, Any]] = []
        for name, fn in check_fns:
            if mock_results is not None and name in mock_results:
                mock = mock_results[name]
                checks.append({
                    "name": name,
                    "passed": bool(mock["passed"]),
                    "detail": str(mock.get("detail", "")),
                })
            else:
                checks.append(fn())

        return _build_result(checks)
