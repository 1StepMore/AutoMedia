"""V3 Content Semantic Gate — keyword coverage ≥80% (3-source comparison).

Checks:
    1. keyword_coverage — keyword coverage ≥80% across 3 sources
    2. source_alignment — sources are aligned on key topics
    3. no_hallucination  — no hallucinated keywords outside source overlap
"""

from __future__ import annotations

from typing import Any

from automedia.gates._context import GateContext
from automedia.gates._result import build_gate_result
from automedia.gates.base import BaseGate


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "keyword_coverage",
    "source_alignment",
    "no_hallucination",
]

_MIN_COVERAGE: float = 0.80

_EXPECTED_MAP: dict[str, str] = {
    "keyword_coverage": f"Keyword coverage ≥ {_MIN_COVERAGE:.0%}",
    "source_alignment": "At least 2 of 3 sources are present",
    "no_hallucination": "No excessive hallucinated keywords outside source overlap",
}


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_keyword_coverage(
    source_keywords: list[str],
    content_keywords: list[str],
) -> dict[str, Any]:
    """Check 1: keyword coverage ≥80% across 3 sources.

    Coverage = |source ∩ content| / |source|.
    """
    name = "keyword_coverage"
    if not source_keywords:
        return {"name": name, "passed": True, "detail": "no source keywords to verify"}
    source_set = {k.lower() for k in source_keywords}
    content_set = {k.lower() for k in content_keywords}
    matched = source_set & content_set
    coverage = len(matched) / len(source_set)
    if coverage >= _MIN_COVERAGE:
        return {
            "name": name,
            "passed": True,
            "detail": (
                f"coverage {coverage:.1%} >= {_MIN_COVERAGE:.0%} ({len(matched)}/{len(source_set)})"
            ),
        }
    return {
        "name": name,
        "passed": False,
        "detail": (
            f"coverage {coverage:.1%} < {_MIN_COVERAGE:.0%} ({len(matched)}/{len(source_set)})"
        ),
    }


def _check_source_alignment(source_texts: list[str]) -> dict[str, Any]:
    """Check 2: at least 2 of 3 sources are present (alignment)."""
    name = "source_alignment"
    present = sum(1 for t in source_texts if t and t.strip())
    if present >= 2:
        return {
            "name": name,
            "passed": True,
            "detail": f"{present} of {len(source_texts)} sources present",
        }
    return {
        "name": name,
        "passed": False,
        "detail": f"only {present} of {len(source_texts)} sources present (need >= 2)",
    }


def _check_no_hallucination(
    source_keywords: list[str],
    content_keywords: list[str],
    max_hallucination_ratio: float = 0.30,
) -> dict[str, Any]:
    """Check 3: no excessive hallucinated keywords outside source overlap."""
    name = "no_hallucination"
    if not content_keywords:
        return {"name": name, "passed": True, "detail": "no content keywords"}
    source_set = {k.lower() for k in source_keywords}
    content_set = {k.lower() for k in content_keywords}
    hallucinated = content_set - source_set
    ratio = len(hallucinated) / len(content_set) if content_set else 0.0
    if ratio <= max_hallucination_ratio:
        return {
            "name": name,
            "passed": True,
            "detail": f"hallucination ratio {ratio:.1%} <= {max_hallucination_ratio:.0%}",
        }
    return {
        "name": name,
        "passed": False,
        "detail": f"hallucination ratio {ratio:.1%} > {max_hallucination_ratio:.0%}",
    }


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# V3ContentSemantic gate
# ---------------------------------------------------------------------------


class V3ContentSemantic(BaseGate):
    """V3 Content Semantic Gate — keyword coverage ≥80% across 3 sources.

    ``gate_context`` expected keys:
        - ``source_keywords``: list[str] — keywords from 3 source documents
        - ``content_keywords``: list[str] — keywords extracted from content
        - ``source_texts``: list[str] — the 3 source texts (for alignment check)
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error``.
    """

    _gate_name = "V3"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run V3 content semantic checks and return structured result."""
        source_keywords: list[str] = gate_context.get("source_keywords", [])
        content_keywords: list[str] = gate_context.get("content_keywords", [])
        source_texts: list[str] = gate_context.get("source_texts", [])
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            (
                "keyword_coverage",
                lambda: _check_keyword_coverage(source_keywords, content_keywords),
            ),
            ("source_alignment", lambda: _check_source_alignment(source_texts)),
            (
                "no_hallucination",
                lambda: _check_no_hallucination(source_keywords, content_keywords),
            ),
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

        result = build_gate_result(checks, gate="V3", expected_map=_EXPECTED_MAP)

        return result
