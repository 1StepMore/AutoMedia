"""Pre-gate Topic Selection Gate — intercepts disallowed topic categories.

Intercepts topics matching forbidden categories before they enter the
pipeline:
    - 公益科普 (charity / public science education)
    - 政府工具 (government tools / policy)
    - 投资 (investment)
    - 金融 (finance / financial products)
    - 娱乐 (entertainment / celebrity gossip)
"""

from __future__ import annotations

import re
from typing import Any

from automedia.gates._context import GateContext
from automedia.gates._result import build_gate_result
from automedia.gates.base import BaseGate
from automedia.gates.llm_helpers import run_deep_check

# ---------------------------------------------------------------------------
# Forbidden keyword patterns (Chinese + English)
# ---------------------------------------------------------------------------

_FORBIDDEN_PATTERNS: list[dict[str, Any]] = [
    {
        "check": "topic_not_charity",
        "patterns": [
            r"公益",
            r"科普",
            r"慈善",
            r"charity",
            r"public\s*science",
            r"donation",
            r"fundraising",
            r"募捐",
        ],
    },
    {
        "check": "topic_not_gov_tool",
        "patterns": [
            r"政府",
            r"政策",
            r"政务",
            r"government",
            r"policy",
            r"administration",
            r"bureau",
            r"ministry",
        ],
    },
    {
        "check": "topic_not_investment",
        "patterns": [
            r"投资",
            r"invest",
            r"investment",
            r"venture",
            r"capital",
            r"equity",
            r"portfolio",
        ],
    },
    {
        "check": "topic_not_finance",
        "patterns": [
            r"金融",
            r"finance",
            r"financial",
            r"股票",
            r"stock",
            r"基金",
            r"fund",
            r"理财",
            r"wealth",
            r"banking",
        ],
    },
    {
        "check": "topic_not_entertainment",
        "patterns": [
            r"娱乐",
            r"entertainment",
            r"celebrity",
            r"gossip",
            r"明星",
            r"艺人",
            r"actor",
            r"actress",
            r"网红",
            r"演唱会",
            r"concert",
            r"concert tour",
            r"体育",
            r"sports",
            r"比赛",
            r"match",
            r"tournament",
            r"球赛",
            r"足球",
            r"soccer",
            r"basketball",
            r"NBA",
        ],
    },
]

_CHECK_NAMES: list[str] = [entry["check"] for entry in _FORBIDDEN_PATTERNS] + [
    "topic_length_valid",
]

_EXPECTED_MAP: dict[str, str] = {
    "topic_not_charity": "Topic does not match charity/public-science category",
    "topic_not_gov_tool": "Topic does not match government tools category",
    "topic_not_investment": "Topic does not match investment category",
    "topic_not_finance": "Topic does not match finance category",
    "topic_not_entertainment": "Topic does not match entertainment category",
    "topic_length_valid": "Topic length is between 5 and 500 characters",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



def _check_topic_not_category(
    topic: str,
    check_name: str,
    patterns: list[str],
    category_label: str,
) -> dict[str, Any]:
    """Check that *topic* does not match any of the forbidden *patterns*."""
    if not isinstance(topic, str):
        return {
            "name": check_name,
            "passed": True,
            "detail": "topic is not a string, skipping category check",
        }
    topic_lower = topic.lower()
    for pattern in patterns:
        if re.search(pattern, topic_lower):
            return {
                "name": check_name,
                "passed": False,
                "detail": (
                    f"topic matches forbidden category '{category_label}' (matched: /{pattern}/)"
                ),
            }
    return {
        "name": check_name,
        "passed": True,
        "detail": f"no forbidden '{category_label}' patterns detected",
    }


def _check_topic_length_valid(topic: str) -> dict[str, Any]:
    """Check that the topic string has a reasonable length."""
    name = "topic_length_valid"
    if not isinstance(topic, str):
        return {"name": name, "passed": False, "detail": "topic is not a string"}
    if len(topic.strip()) == 0:
        return {"name": name, "passed": False, "detail": "topic is empty"}
    stripped = topic.strip()
    if len(stripped) < 5:
        return {
            "name": name,
            "passed": False,
            "detail": f"topic too short ({len(stripped)} chars, min 5)",
        }
    if len(stripped) > 500:
        return {
            "name": name,
            "passed": False,
            "detail": f"topic too long ({len(stripped)} chars, max 500)",
        }
    return {
        "name": name,
        "passed": True,
        "detail": f"topic length ({len(stripped)} chars) is valid",
    }


# ---------------------------------------------------------------------------
# TopicSelectionGate
# ---------------------------------------------------------------------------


class TopicSelectionGate(BaseGate):
    """Pre-gate Topic Selection Gate — intercepts disallowed topic categories.

    ``gate_context`` expected keys:
        - ``topic``: str — the topic string to evaluate
        - ``topic_category`` (optional): str — explicit category override
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` for deterministic testing.
    """

    _gate_name = "pre-gate"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run topic quality checks and return structured result."""
        topic: str = gate_context.get("topic", "")
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = []

        # Add a check for each forbidden category
        for entry in _FORBIDDEN_PATTERNS:
            check_name = entry["check"]
            patterns = entry["patterns"]
            # Extract a human-readable label from the check name
            label = check_name.replace("topic_not_", "").replace("_", " ")
            check_fns.append(
                (
                    check_name,
                    lambda _p=patterns, _n=check_name, _l=label: _check_topic_not_category(
                        topic, _n, _p, _l
                    ),
                )
            )

        # Add length check
        check_fns.append(("topic_length_valid", lambda: _check_topic_length_valid(topic)))

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

        result = build_gate_result(checks, gate="pre-gate", expected_map=_EXPECTED_MAP)

        # Optional LLM deep-check — advisory only, never blocks the gate
        config = gate_context.get("config", {})
        if config.get("enable_llm_deep_check", False):
            try:
                llm_result = run_deep_check(topic, "topic appropriateness and quality")
                if not llm_result.get("passed", True):
                    result.setdefault("issues", []).extend(llm_result.get("issues", []))
                    result["llm_deep_check"] = llm_result.get("method", "unknown")
            except Exception:
                pass  # LLM check is optional, don't fail the gate

        return result
