"""Shared helper utilities for gate implementations.

Provides reusable boilerplate to reduce duplication across gate
``execute()`` methods — particularly the mock-override pattern
used by most gates for deterministic test results.
"""

from __future__ import annotations

from typing import Any, Callable

from automedia.gates._result import CheckResult


def apply_mock_overrides(
    check_fns: list[tuple[str, Callable[[], CheckResult]]],
    mock_results: dict[str, dict[str, Any]] | None,
) -> list[CheckResult]:
    """Build a list of check result dicts, overriding with mock values
    when the gate is running under test.

    Each callable in *check_fns* is a ``(name, fn)`` pair where ``fn``
    is a zero-argument callable that returns ``{"name": str, "passed": bool,
    "detail": str}``.

    When *mock_results* is provided and contains a key matching the check
    name, the mock value is used verbatim instead of calling *fn* — making
    the gate fully deterministic for unit testing.

    Args:
        check_fns: Sequence of ``(check_name, callable)`` pairs.
        mock_results: Optional dict of ``{check_name: {"passed": bool,
            "detail": str}}`` from ``gate_context["_mock_results"]``.

    Returns:
        List of check result dicts compatible with ``build_gate_result()``.
    """
    checks: list[CheckResult] = []
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
    return checks
