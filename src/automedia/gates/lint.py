"""V0 Lint Gate — HyperFrames lint check (0 errors required).

Checks:
    1. lint_errors    — lint result must report 0 errors
    2. lint_warnings  — lint warnings count is within tolerance
    3. syntax_valid   — source syntax is valid
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
    "lint_errors",
    "lint_warnings",
    "syntax_valid",
]

_MAX_WARNINGS: int = 10

_EXPECTED_MAP: dict[str, str] = {
    "lint_errors": "0 lint errors",
    "lint_warnings": f"Lint warnings within {_MAX_WARNINGS}",
    "syntax_valid": "Source syntax is valid",
}


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_lint_errors(lint_result: dict[str, Any]) -> dict[str, Any]:
    """Check 1: lint result must report 0 errors."""
    name = "lint_errors"
    errors: int = lint_result.get("errors", 0)
    if errors == 0:
        return {"name": name, "passed": True, "detail": "0 lint errors"}
    return {"name": name, "passed": False, "detail": f"{errors} lint error(s) found"}


def _check_lint_warnings(lint_result: dict[str, Any]) -> dict[str, Any]:
    """Check 2: lint warnings count is within tolerance."""
    name = "lint_warnings"
    warnings: int = lint_result.get("warnings", 0)
    if warnings <= _MAX_WARNINGS:
        return {"name": name, "passed": True, "detail": f"{warnings} warnings <= {_MAX_WARNINGS}"}
    return {"name": name, "passed": False, "detail": f"{warnings} warnings exceed {_MAX_WARNINGS}"}


def _check_syntax_valid(lint_result: dict[str, Any]) -> dict[str, Any]:
    """Check 3: source syntax is valid."""
    name = "syntax_valid"
    syntax_ok: bool = lint_result.get("syntax_ok", True)
    if syntax_ok:
        return {"name": name, "passed": True, "detail": "syntax valid"}
    return {"name": name, "passed": False, "detail": "syntax errors detected"}


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# V0Lint gate
# ---------------------------------------------------------------------------


class V0Lint(BaseGate):
    """V0 Lint Gate — verify HyperFrames lint reports 0 errors.

    ``gate_context`` expected keys:
        - ``lint_result``: dict with keys ``errors``, ``warnings``, ``syntax_ok``
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing without running real lint.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error``.
    """

    _gate_name = "V0"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run V0 lint checks and return structured result."""
        lint_result: dict[str, Any] = gate_context.get("lint_result", {})
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            ("lint_errors", lambda: _check_lint_errors(lint_result)),
            ("lint_warnings", lambda: _check_lint_warnings(lint_result)),
            ("syntax_valid", lambda: _check_syntax_valid(lint_result)),
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

        return build_gate_result(checks, gate="V0", expected_map=_EXPECTED_MAP)
