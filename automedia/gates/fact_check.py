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
"""

from __future__ import annotations

from typing import Any

from automedia.gates.base import BaseGate


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


def _derive_expected(check_name: str) -> str:
    """Convert a check name to a human-readable expected statement."""
    return _EXPECTED_MAP.get(check_name, check_name.replace("_", " ").capitalize())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_result(
    checks: list[dict[str, Any]],
    *,
    error: str | None = None,
) -> dict[str, Any]:
    """Assemble the final gate result dict from individual *checks*."""
    all_passed = all(c["passed"] for c in checks)
    # Confidence: 1.0 when all pass, otherwise ratio of passed checks
    passed_count = sum(1 for c in checks if c["passed"])
    confidence = passed_count / len(checks) if checks else 0.0

    # Build expected_vs_actual from first failing check, or first check if all pass
    target = next((c for c in checks if not c["passed"]), checks[0] if checks else None)
    expected_vs_actual: dict[str, Any] = {}
    if target:
        expected_vs_actual = {
            "check": target["name"],
            "expected": _derive_expected(target["name"]),
            "actual": target.get("detail", ""),
            "context": {},
        }

    return {
        "passed": all_passed,
        "gate": "G0",
        "checks": checks,
        "error": error,
        "confidence": round(confidence, 4),
        "expected_vs_actual": expected_vs_actual,
    }


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------

def _check_source_trace(
    content: str, source_url: str, source_data: dict[str, Any]
) -> dict[str, Any]:
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
        return {"name": name, "passed": True, "detail": f"source domain '{domain}' found in content"}

    # Fallback: check if source_data contains any reference text
    reference_text = source_data.get("reference_text", "")
    if reference_text and reference_text.lower() in content_lower:
        return {"name": name, "passed": True, "detail": "reference text found in content"}

    return {
        "name": name,
        "passed": False,
        "detail": f"source domain '{domain}' not found in content",
    }


def _check_number_verification(
    content: str, source_data: dict[str, Any]
) -> dict[str, Any]:
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


def _check_timeline(
    content: str, source_data: dict[str, Any]
) -> dict[str, Any]:
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
        return {"name": name, "passed": True, "detail": f"cannot parse published_date: {published_date}"}

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


def _check_quotes(
    content: str, source_data: dict[str, Any]
) -> dict[str, Any]:
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
        return {"name": name, "passed": False, "detail": f"{len(missing)} quote(s) not found in content"}
    return {"name": name, "passed": True, "detail": f"all {len(source_quotes)} quotes verified"}


def _check_entities(
    content: str, source_data: dict[str, Any]
) -> dict[str, Any]:
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

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        """Run 5-step fact-check and return structured result."""
        topic: str = gate_context.get("topic", "")
        content: str = gate_context.get("content", "")
        source_data: dict[str, Any] = gate_context.get("source_data", {})
        source_url: str = source_data.get("url", "")
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        # Determine each check result — use mock if available, otherwise run check
        check_fns: list[tuple[str, Any]] = [
            ("source_trace", lambda: _check_source_trace(content, source_url, source_data)),
            ("number_verification", lambda: _check_number_verification(content, source_data)),
            ("timeline", lambda: _check_timeline(content, source_data)),
            ("quotes", lambda: _check_quotes(content, source_data)),
            ("entities", lambda: _check_entities(content, source_data)),
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
