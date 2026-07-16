"""Shared gate result builder.

Provides :func:`build_gate_result` — the single implementation of the
``_build_result`` helper that was previously duplicated across all gate
modules.
"""

from __future__ import annotations

from typing import Any, TypedDict

from structlog import get_logger

log = get_logger(__name__)


class CheckResult(TypedDict):
    """Individual check dict produced by a gate check function.

    Every gate check returns at minimum ``name``, ``passed``, and ``detail``.
    Additional keys (e.g. ``method``, ``confidence``) may be present when
    the check was performed by an LLM.
    """

    name: str
    passed: bool
    detail: str


class ExpectedVsActual(TypedDict):
    """Expected-vs-actual comparison for the first failing check."""

    check: str
    expected: str
    actual: str
    context: dict[str, Any]


class GateResult(TypedDict, total=False):
    """Structured result produced by a gate execution.

    ``passed``, ``gate``, ``checks``, ``error``, and
    ``expected_vs_actual`` are always present when the gate runs
    successfully.  ``duration_s`` is injected by ``GateEngine`` after
    execution.  Extra keys such as ``output_path``, ``modified_content``,
    or ``retry_count`` are gate-specific.
    """

    passed: bool
    gate: str
    checks: list[CheckResult]
    error: str | None
    expected_vs_actual: ExpectedVsActual
    duration_s: float
    output_path: str
    retry_count: int
    modified_content: str
    method: str
    confidence: float


def _derive_expected(
    check_name: str,
    *,
    expected_map: dict[str, str] | None = None,
    suffix: str = "",
) -> str:
    """Convert a snake-case *check_name* to a human-readable expected statement.

    If *expected_map* is provided and contains *check_name*, the mapped value
    is returned.  Otherwise the check name is title-cased with underscores
    replaced by spaces, and *suffix* is appended.
    """
    if expected_map is not None and check_name in expected_map:
        return expected_map[check_name]
    return check_name.replace("_", " ").capitalize() + suffix


def _derive_suggestion(check_name: str, threshold: str) -> str:
    """Derive a remediation suggestion from the check name and expected threshold."""
    check_label = check_name.replace("_", " ")
    threshold_lower = threshold.lower()

    if threshold_lower.startswith(("no ", "not ")):
        return f"Remove or avoid {check_label} to satisfy: {threshold}"
    if "must" in threshold_lower or "should" in threshold_lower:
        return f"Ensure {check_label} to satisfy: {threshold}"
    if "between" in threshold_lower or "within" in threshold_lower or threshold_lower.startswith("all "):
        return f"Verify {check_label} meets: {threshold}"

    return f"Address {check_label} to match expected: {threshold}"


def _enrich_failing_checks(
    checks: list[CheckResult],
    *,
    expected_map: dict[str, str] | None = None,
    expected_suffix: str = "",
) -> None:
    """Add structured error fields to all failing check dicts in-place.

    Each failing check (``passed=False``) receives ``check_name``,
    ``actual_value``, ``threshold``, ``detail``, and ``suggestion`` keys
    for a standardized error schema.
    """
    for check in checks:
        if not check["passed"]:
            check_name = check["name"]
            threshold = _derive_expected(check_name, expected_map=expected_map, suffix=expected_suffix)
            check["check_name"] = check_name
            check["actual_value"] = check.get("detail", "")
            check["threshold"] = threshold
            check["suggestion"] = _derive_suggestion(check_name, threshold)


def build_gate_result(
    checks: list[CheckResult],
    *,
    gate: str,
    error: str | None = None,
    expected_map: dict[str, str] | None = None,
    expected_suffix: str = "",
    **extra: Any,  # noqa: ANN401 — pass-through to result dict; gate-specific keys vary
) -> dict[str, Any]:
    """Assemble the final gate result dict from individual *checks*.

    Parameters
    ----------
    checks:
        List of individual check dicts (each must have ``name``, ``passed``,
        and ``detail`` keys).
    gate:
        Gate identifier string (e.g. ``"G0"``, ``"V1"``, ``"pre-gate"``).
    error:
        Optional error message.
    expected_map:
        Optional mapping of check names to human-readable expected statements.
        When provided, lookups are tried here before falling back to the
        default title-case derivation.
    expected_suffix:
        Optional suffix appended to the derived expected statement (e.g.
        ``"."``).  Only affects the fallback derivation, not explicit map
        entries.
    **extra:
        Additional key-value pairs merged into the result dict (e.g.
        ``modified_content``, ``confidence``).
    """
    all_passed = all(c["passed"] for c in checks)

    # Build expected_vs_actual from first failing check, or first check if all pass
    target = next(
        (c for c in checks if not c["passed"]),
        checks[0] if checks else None,
    )
    expected_vs_actual: ExpectedVsActual | dict[str, Any] = {}
    if target:
        expected_vs_actual = {
            "check": target["name"],
            "expected": _derive_expected(
                target["name"],
                expected_map=expected_map,
                suffix=expected_suffix,
            ),
            "actual": target.get("detail", ""),
            "context": {},
        }

    # Enrich failing checks with structured error fields
    _enrich_failing_checks(checks, expected_map=expected_map, expected_suffix=expected_suffix)

    result: dict[str, Any] = {
        "passed": all_passed,
        "gate": gate,
        "checks": checks,
        "error": error,
        "expected_vs_actual": expected_vs_actual,
    }
    result.update(extra)
    return result
