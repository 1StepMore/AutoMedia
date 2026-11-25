"""Pre-gate Topic Selection Gate — intercepts disallowed topic categories.

Intercepts topics matching forbidden categories before they enter the
pipeline:
    - 公益科普 (charity / public science education)
    - 政府工具 (government tools / policy)
    - 投资 (investment)
    - 金融 (finance / financial products)
    - 娱乐 (entertainment / celebrity gossip)
    - 体育 (sports)

Since B26/C4 the verdict is an **LLM classification** (``topic_category``
check): the six keyword groups above are a *fallback only*, because a regex
over topic wording is wrong in both directions — it misses "帮 NGO 做内容营销"
(no forbidden word, same subject matter) and misfires on "公益科普的正确做法"
(the studio refused the *topic*, not the critique of how it is produced).

Verdict rules:
    - LLM judge available ⇒ ``topic_category`` decides, the regex groups are
      reported as one advisory check (never decisive).
    - LLM unavailable ⇒ the legacy regex checks decide, plus one advisory
      check saying the judge was skipped. Degradation is visible in the
      report instead of being silent.
    - ``_mock_results`` keeps driving the legacy path unchanged (tests).
"""

from __future__ import annotations

import re
from typing import Any

from structlog import get_logger

from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result
from automedia.gates.base import BaseGate
from automedia.gates.helpers import apply_mock_overrides
from automedia.gates.llm_helpers import LLMCheckResult, llm_check_with_fallback

log = get_logger(__name__)

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

#: Check name emitted by the LLM-judge path (B26/C4).
_LLM_CHECK_NAME: str = "topic_category"

#: Advisory check that keeps the regex verdict visible without letting it decide.
_ADVISORY_CHECK_NAME: str = "topic_category_regex_advisory"

#: Prompt template used for the classification.
_JUDGE_PROMPT: str = "topic_category_judge"

#: Reason recorded when the LLM judge cannot produce a usable verdict.
_JUDGE_UNAVAILABLE_REASON: str = (
    "skipped: no LLM judge available — deterministic regex fallback decided"
)

_EXPECTED_MAP: dict[str, str] = {
    "topic_not_charity": "Topic does not match charity/public-science category",
    "topic_not_gov_tool": "Topic does not match government tools category",
    "topic_not_investment": "Topic does not match investment category",
    "topic_not_finance": "Topic does not match finance category",
    "topic_not_entertainment": "Topic does not match entertainment category",
    "topic_length_valid": "Topic length is between 5 and 500 characters",
}

_EXPECTED_MAP[_LLM_CHECK_NAME] = "The topic's subject matter is not a refused category"
_EXPECTED_MAP[_ADVISORY_CHECK_NAME] = "Advisory only — never decides the verdict"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_topic_not_category(
    topic: str,
    check_name: str,
    patterns: list[str],
    category_label: str,
) -> CheckResult:
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


def _check_topic_length_valid(topic: str) -> CheckResult:
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
# LLM classification (B26/C4)
# ---------------------------------------------------------------------------


def _judge_with_retry(topic: str) -> LLMCheckResult:
    """Run the topic judge, retrying once on a failed attempt.

    Measured 2026-11-25: 5 live samples at ``timeout=30`` produced one
    fallback (transient).  A second attempt costs nothing when the first
    succeeds, and keeps the regex fallback for what is actually down.
    """

    def _unavailable(_text: str) -> LLMCheckResult:
        return {"passed": False, "issues": ["llm unavailable"]}

    judged: LLMCheckResult = {}
    for _attempt in range(2):
        judged = llm_check_with_fallback(
            text=topic,
            check_type="topic_category",
            prompt_template_name=_JUDGE_PROMPT,
            deterministic_fn=_unavailable,
        )
        if judged.get("method") == "llm":
            return judged
    return judged


def _llm_topic_category(topic: str) -> dict[str, Any] | None:
    """Ask the LLM which refused category (if any) the topic belongs to.

    Returns ``{"forbidden": bool, "category": str, "reason": str}`` on a usable
    verdict, ``None`` when no verdict exists (missing topic, LLM failure,
    unexpected shape).  ``None`` is deliberately not a pass: the caller falls
    back to the deterministic regex path and says so in the report.
    """
    if not topic.strip():
        return None

    try:
        judged = _judge_with_retry(topic)
    except Exception:
        log.warning("pre-gate topic judge failed", exc_info=True)
        return None

    # ``method != "llm"`` means the deterministic fallback ran: no verdict.
    if judged.get("method") != "llm":
        return None

    structured = judged.get("structured_issues") or []
    category = "none"
    reason = ""
    if structured and isinstance(structured[0], dict):
        category = str(structured[0].get("category") or "none").strip() or "none"
        reason = str(structured[0].get("reason") or "").strip()

    llm_passed = bool(judged.get("passed", True))
    if category in ("", "none"):
        if llm_passed:
            return {"forbidden": False, "category": "none", "reason": reason}
        # The judge refused the topic but named no category — still a refusal.
        category = "other_refused"
    return {
        "forbidden": True,
        "category": category,
        "reason": reason or "; ".join(judged.get("issues") or []),
    }


def _check_topic_category_llm(verdict: dict[str, Any]) -> CheckResult:
    """Check 1 (LLM path): the topic's subject matter is not a refused category."""
    if verdict["forbidden"]:
        detail = f"refused category '{verdict['category']}'"
        if verdict["reason"]:
            detail = f"{detail} — {verdict['reason']}"
        return {"name": _LLM_CHECK_NAME, "passed": False, "detail": detail}
    detail = "allowed by the judge"
    if verdict["reason"]:
        detail = f"{detail} — {verdict['reason']}"
    return {"name": _LLM_CHECK_NAME, "passed": True, "detail": detail}


def _check_regex_advisory(topic: str) -> CheckResult:
    """Check 3 (LLM path): keep the regex verdict visible, never decisive.

    ``passed`` is always ``True``: B26/C4 demoted the keyword groups because
    they cannot tell "content about charity" from "comms work for a charity".
    """
    matched: list[str] = []
    for entry in _FORBIDDEN_PATTERNS:
        label = entry["check"].replace("topic_not_", "").replace("_", " ")
        for pattern in entry["patterns"]:
            if re.search(pattern, topic.lower()):
                matched.append(f"{label} (/{pattern}/)")
                break
    detail = "advisory only — no keyword group matched"
    if matched:
        detail = "advisory only — keyword groups matched: " + "; ".join(matched)
    return {"name": _ADVISORY_CHECK_NAME, "passed": True, "detail": detail}


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

        # Legacy deterministic path — kept for `_mock_results` consumers and used
        # as the fallback when no LLM judge exists.
        if mock_results is not None:
            return build_gate_result(
                apply_mock_overrides(check_fns, mock_results),
                gate="pre-gate",
                expected_map=_EXPECTED_MAP,
            )

        verdict = _llm_topic_category(topic)
        if verdict is None:
            checks = [fn() for _, fn in check_fns]
            checks.append(
                {
                    "name": _LLM_CHECK_NAME,
                    "passed": True,
                    "detail": _JUDGE_UNAVAILABLE_REASON,
                }
            )
            return build_gate_result(checks, gate="pre-gate", expected_map=_EXPECTED_MAP)

        checks = [
            _check_topic_category_llm(verdict),
            _check_topic_length_valid(topic),
            _check_regex_advisory(topic),
        ]
        return build_gate_result(checks, gate="pre-gate", expected_map=_EXPECTED_MAP)
