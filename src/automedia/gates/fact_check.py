"""G0 Fact-Check Gate — 5-step verification pipeline.

Steps:
    1. 来源追溯 (Source Trace) — content references source_url
    2. 数字验证 (Number Verification) — numbers match source_data
    3. 时间线 (Timeline) — event timeline is logically consistent
    4. 引文 (Quotes) — quotes match original text
    5. 实体 (Entities) — key entity names are correct

When ``gate_context["_mock_results"]`` is present, each check's result is
driven from that dict instead of calling the LLM provider — making the gate
fully deterministic for unit testing.

When ``gate_context["config"]["enable_llm"]`` is ``True`` (default), the gate
attempts LLM-based evaluation via :func:`llm_check_with_fallback` before
falling back to the deterministic substring-matching logic.
"""

from __future__ import annotations

import logging
from typing import Any

from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result
from automedia.gates.base import BaseGate
from automedia.gates.llm_helpers import LLMCheckResult, llm_check_with_fallback

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CHECK_NAMES: list[str] = [
    "source_trace",
    "number_verification",
    "timeline",
    "quotes",
    "entities",
]


_EXPECTED_MAP: dict[str, str] = {
    "source_trace": "Content references the source URL domain",
    "number_verification": "All key numbers match the source data",
    "timeline": "Event dates are chronologically consistent",
    "quotes": "Quotes match the original source text",
    "entities": "Key entity names match the source data",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_deterministic_checks(
    content: str,
    source_url: str,
    source_data: dict[str, Any],
    ) -> list[CheckResult]:
    """Run all 5 deterministic checks and return the check dicts."""
    return [
        _check_source_trace(content, source_url, source_data),
        _check_number_verification(content, source_data),
        _check_timeline(content, source_data),
        _check_quotes(content, source_data),
        _check_entities(content, source_data),
    ]


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_source_trace(
    content: str, source_url: str, source_data: dict[str, Any]
) -> CheckResult:
    """Step 1: Verify that *content* references the *source_url* domain."""
    name = "source_trace"
    if not source_url:
        return {"name": name, "passed": True, "detail": "no source_url to verify"}

    # Extract domain from source_url for matching
    from urllib.parse import urlparse

    parsed = urlparse(source_url)
    domain = parsed.netloc.lower()

    # Simple heuristic: domain or a notable fragment should appear in content
    content_lower = content.lower()
    if domain in content_lower or domain.replace("www.", "") in content_lower:
        return {
            "name": name,
            "passed": True,
            "detail": f"source domain '{domain}' found in content",
        }

    # Fallback: check if source_data contains any reference text
    reference_text = source_data.get("reference_text", "")
    if reference_text and reference_text.lower() in content_lower:
        return {"name": name, "passed": True, "detail": "reference text found in content"}

    return {
        "name": name,
        "passed": False,
        "detail": f"source domain '{domain}' not found in content",
    }


def _check_number_verification(content: str, source_data: dict[str, Any]) -> CheckResult:
    """Step 2: Verify that numbers in *content* match *source_data.key_numbers*."""
    name = "number_verification"
    key_numbers: dict[str, str] = source_data.get("key_numbers", {})

    if not key_numbers:
        return {"name": name, "passed": True, "detail": "no key_numbers to verify"}

    mismatches: list[str] = []
    for label, expected_value in key_numbers.items():
        expected_str = str(expected_value)
        # Check if the expected number appears in content
        if expected_str not in content:
            mismatches.append(f"expected '{label}'={expected_str} not found in content")

    if mismatches:
        return {"name": name, "passed": False, "detail": "; ".join(mismatches)}
    return {"name": name, "passed": True, "detail": f"all {len(key_numbers)} key_numbers verified"}


def _check_timeline(content: str, source_data: dict[str, Any]) -> CheckResult:
    """Step 3: Verify that event dates in *content* are chronologically consistent."""
    name = "timeline"
    published_date: str = source_data.get("published_date", "")

    if not published_date:
        return {"name": name, "passed": True, "detail": "no published_date to check against"}

    import re
    from datetime import datetime

    # Try to parse the published_date
    try:
        pub_dt = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return {
            "name": name,
            "passed": True,
            "detail": f"cannot parse published_date: {published_date}",
        }

    # Look for ISO-like dates in content
    date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
    content_dates = date_pattern.findall(content)

    future_dates: list[str] = []
    for d_str in content_dates:
        try:
            d = datetime.fromisoformat(d_str)
            if d > pub_dt:
                future_dates.append(d_str)
        except ValueError:
            continue

    if future_dates:
        return {
            "name": name,
            "passed": False,
            "detail": f"dates after publication found: {future_dates}",
        }
    return {"name": name, "passed": True, "detail": "timeline consistent"}


def _check_quotes(content: str, source_data: dict[str, Any]) -> CheckResult:
    """Step 4: Verify that quotes in *content* match *source_data.quotes*."""
    name = "quotes"
    source_quotes: list[str] = source_data.get("quotes", [])

    if not source_quotes:
        return {"name": name, "passed": True, "detail": "no source quotes to verify"}

    content_lower = content.lower()
    missing: list[str] = []
    for quote in source_quotes:
        if quote.lower() not in content_lower:
            missing.append(quote[:60])

    if missing:
        return {
            "name": name,
            "passed": False,
            "detail": f"{len(missing)} quote(s) not found in content",
        }
    return {"name": name, "passed": True, "detail": f"all {len(source_quotes)} quotes verified"}


def _check_entities(content: str, source_data: dict[str, Any]) -> CheckResult:
    """Step 5: Verify that key entity names in *content* match *source_data.entities*."""
    name = "entities"
    source_entities: list[str] = source_data.get("entities", [])

    if not source_entities:
        return {"name": name, "passed": True, "detail": "no source entities to verify"}

    content_lower = content.lower()
    missing: list[str] = []
    for entity in source_entities:
        if entity.lower() not in content_lower:
            missing.append(entity)

    if missing:
        return {"name": name, "passed": False, "detail": f"entities not found: {missing}"}
    return {"name": name, "passed": True, "detail": f"all {len(source_entities)} entities verified"}


# ---------------------------------------------------------------------------
# G0FactCheck gate
# ---------------------------------------------------------------------------


class G0FactCheck(BaseGate):
    """G0 Fact-Check Gate — 5-step verification of content against source data.

    ``gate_context`` expected keys:
        - ``topic``: str — topic of the content
        - ``content``: str — generated content to fact-check
        - ``source_data``: dict with keys:
            - ``url``: str
            - ``published_date``: str (ISO format)
            - ``key_numbers``: dict[str, str]
            - ``entities``: list[str]
            - ``quotes``: list[str]
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing without an LLM.
    """

    _gate_name = "G0"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run 5-step fact-check and return structured result."""
        content: str = gate_context.get("content", "")
        source_data: dict[str, Any] = gate_context.get("source_data", {})
        source_url: str = source_data.get("url", "")
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        config: dict[str, Any] = gate_context.get("config", {})
        enable_llm: bool = config.get("enable_llm", True) if isinstance(config, dict) else True

        if mock_results is not None:
            checks: list[CheckResult] = []
            for name in _CHECK_NAMES:
                if name in mock_results:
                    mock = mock_results[name]
                    checks.append(
                        {
                            "name": name,
                            "passed": bool(mock["passed"]),
                            "detail": str(mock.get("detail", "")),
                        }
                    )
                else:
                    checks.append({"name": name, "passed": True, "detail": ""})

            return build_gate_result(
                checks,
                gate="G0",
                expected_map=_EXPECTED_MAP,
                confidence=round(
                    sum(1 for c in checks if c["passed"]) / len(checks) if checks else 0.0,
                    4,
                ),
            )

        if enable_llm:
            # Mutable container captures per-step checks from deterministic fallback closure
            captured_checks: list[CheckResult] = []

            def _deterministic_fn(_text: str) -> LLMCheckResult:
                det_checks = _run_deterministic_checks(content, source_url, source_data)
                captured_checks.extend(det_checks)
                return {
                    "passed": all(c["passed"] for c in det_checks),
                    "issues": [c["detail"] for c in det_checks if not c["passed"]],
                }

            llm_result = llm_check_with_fallback(
                text=content,
                check_type="fact_check",
                prompt_template_name="fact_check_g0",
                deterministic_fn=_deterministic_fn,
                source_data=source_data,
            )

            method = llm_result.get("method", "deterministic")

            if method == "deterministic" and captured_checks:
                checks = captured_checks
            else:
                passed = llm_result["passed"]
                issues = llm_result.get("issues", [])
                detail = (
                    "; ".join(issues) if issues
                    else ("verified by LLM" if passed else "fact-check failed")
                )
                checks = [
                    {"name": name, "passed": passed, "detail": detail}
                    for name in _CHECK_NAMES
                ]

            confidence = llm_result.get("confidence")
            if confidence is None:
                confidence = round(
                    sum(1 for c in checks if c["passed"]) / len(checks) if checks else 0.0,
                    4,
                )

            logger.info("G0 fact-check method=%s passed=%s", method, llm_result["passed"])

            return build_gate_result(
                checks,
                gate="G0",
                expected_map=_EXPECTED_MAP,
                confidence=confidence,
                method=method,
            )

        checks = _run_deterministic_checks(content, source_url, source_data)
        return build_gate_result(
            checks,
            gate="G0",
            expected_map=_EXPECTED_MAP,
            confidence=round(
                sum(1 for c in checks if c["passed"]) / len(checks) if checks else 0.0,
                4,
            ),
            method="deterministic",
        )
