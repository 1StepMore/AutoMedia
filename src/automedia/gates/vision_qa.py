"""V1 Vision QA Gate — per-entry visual quality assurance.

Checks:
    1. mid_frame_valid     — mid-frame image exists and is readable
    2. end_silence_valid   — end-silence frame image exists and is readable
    3. all_entries_passed  — all entries passed their individual QA
    4. red_line_6          — full coverage (not sampling), every entry checked

Red Line 6: Every entry must be individually QA'd (no sampling).
"""

from __future__ import annotations

from typing import Any

from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result
from automedia.gates.base import BaseGate
from automedia.gates.helpers import apply_mock_overrides

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "mid_frame_valid",
    "end_silence_valid",
    "all_entries_passed",
    "red_line_6",
]


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_mid_frame_valid(entries: list[dict[str, Any]]) -> CheckResult:
    """Check 1: every entry has a valid mid_frame_path."""
    name = "mid_frame_valid"
    if not entries:
        return {"name": name, "passed": False, "detail": "no entries provided"}
    missing = [i for i, e in enumerate(entries) if not e.get("mid_frame_path")]
    if missing:
        return {
            "name": name,
            "passed": False,
            "detail": f"entries {missing} missing mid_frame_path",
        }
    return {
        "name": name,
        "passed": True,
        "detail": f"all {len(entries)} entries have mid_frame_path",
    }


def _check_end_silence_frame_valid(entries: list[dict[str, Any]]) -> CheckResult:
    """Check 2: every entry has a valid end_silence_frame_path."""
    name = "end_silence_valid"
    if not entries:
        return {"name": name, "passed": False, "detail": "no entries provided"}
    missing = [i for i, e in enumerate(entries) if not e.get("end_silence_frame_path")]
    if missing:
        return {
            "name": name,
            "passed": False,
            "detail": f"entries {missing} missing end_silence_frame_path",
        }
    return {
        "name": name,
        "passed": True,
        "detail": f"all {len(entries)} entries have end_silence_frame_path",
    }


def _check_all_entries_passed(entries: list[dict[str, Any]]) -> CheckResult:
    """Check 3: every entry has qa_passed=True."""
    name = "all_entries_passed"
    if not entries:
        return {"name": name, "passed": False, "detail": "no entries provided"}
    failed = [i for i, e in enumerate(entries) if not e.get("qa_passed", False)]
    if failed:
        return {"name": name, "passed": False, "detail": f"entries {failed} failed vision QA"}
    return {"name": name, "passed": True, "detail": f"all {len(entries)} entries passed vision QA"}


def _check_red_line_6(entries: list[dict[str, Any]]) -> CheckResult:
    """Check 4 (Red Line 6): full coverage — every entry must be checked, no sampling."""
    name = "red_line_6"
    if not entries:
        return {
            "name": name,
            "passed": False,
            "detail": "no entries to verify (Red Line 6: full coverage required)",
        }
    unchecked = [i for i, e in enumerate(entries) if not e.get("checked", False)]
    if unchecked:
        return {
            "name": name,
            "passed": False,
            "detail": f"entries {unchecked} not checked — Red Line 6 requires full coverage",
        }
    return {
        "name": name,
        "passed": True,
        "detail": f"Red Line 6 satisfied: all {len(entries)} entries checked (full coverage)",
    }


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# V1VisionQA gate
# ---------------------------------------------------------------------------


class V1VisionQA(BaseGate):
    """V1 Vision QA Gate — per-entry visual quality assurance (Red Line 6).

    ``gate_context`` expected keys:
        - ``entries``: list of dicts, each with:
            - ``mid_frame_path``: str
            - ``end_silence_frame_path``: str
            - ``qa_passed``: bool (result of vision QA)
            - ``checked``: bool (whether entry was checked at all)
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error``.
    """

    _gate_name = "V1"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run V1 vision QA checks and return structured result."""
        entries: list[dict[str, Any]] = gate_context.get("entries", [])
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            ("mid_frame_valid", lambda: _check_mid_frame_valid(entries)),
            ("end_silence_valid", lambda: _check_end_silence_frame_valid(entries)),
            ("all_entries_passed", lambda: _check_all_entries_passed(entries)),
            ("red_line_6", lambda: _check_red_line_6(entries)),
        ]

        checks = apply_mock_overrides(check_fns, mock_results)

        return build_gate_result(checks, gate="V1", expected_suffix=".")
