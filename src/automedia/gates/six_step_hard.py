"""V7 6-Step Hard Gate — file integrity / MD5 / Whisper full-check.

Checks (6 hard constraints):
    1. file_exists      — all required output files exist
    2. file_size_valid  — files are non-empty and within size limits
    3. md5_verified     — MD5 checksums match recorded values
    4. whisper_full     — Whisper ran on full audio (not sampled)
    5. format_valid     — output format matches expected codec/container
    6. duration_valid   — output duration within expected range
"""

from __future__ import annotations

import os
from typing import Any

from structlog import get_logger

from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result
from automedia.gates.base import BaseGate
from automedia.gates.helpers import apply_mock_overrides

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "file_exists",
    "file_size_valid",
    "md5_verified",
    "whisper_full",
    "format_valid",
    "duration_valid",
]


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_file_exists(required_files: list[str]) -> CheckResult:
    """Check 1: all required output files exist."""
    name = "file_exists"
    if not required_files:
        return {"name": name, "passed": True, "detail": "no required files to check"}
    missing = [f for f in required_files if not os.path.isfile(f)]
    if missing:
        return {"name": name, "passed": False, "detail": f"missing files: {missing}"}
    return {"name": name, "passed": True, "detail": f"all {len(required_files)} files exist"}


def _check_file_size_valid(file_sizes: dict[str, int]) -> CheckResult:
    """Check 2: files are non-empty and within size limits."""
    name = "file_size_valid"
    if not file_sizes:
        return {"name": name, "passed": True, "detail": "no file sizes to check"}
    issues: list[str] = []
    for path, size in file_sizes.items():
        if size <= 0:
            issues.append(f"{path}: empty ({size} bytes)")
        elif size > 2 * 1024 * 1024 * 1024:  # 2GB limit
            issues.append(f"{path}: too large ({size} bytes)")
    if issues:
        return {"name": name, "passed": False, "detail": "; ".join(issues[:3])}
    return {"name": name, "passed": True, "detail": f"all {len(file_sizes)} files have valid sizes"}


def _check_md5_verified(md5_records: dict[str, dict[str, str]]) -> CheckResult:
    """Check 3: MD5 checksums match recorded values.

    md5_records: {file_path: {"expected": str, "actual": str}}
    """
    name = "md5_verified"
    if not md5_records:
        return {"name": name, "passed": True, "detail": "no MD5 records to verify"}
    mismatches: list[str] = []
    for path, rec in md5_records.items():
        expected = rec.get("expected", "")
        actual = rec.get("actual", "")
        if expected and actual and expected != actual:
            mismatches.append(f"{os.path.basename(path)}: {actual} != {expected}")
    if mismatches:
        return {"name": name, "passed": False, "detail": f"MD5 mismatches: {mismatches[:3]}"}
    return {"name": name, "passed": True, "detail": f"all {len(md5_records)} MD5s verified"}


def _check_whisper_full(whisper_full_audio: bool) -> CheckResult:
    """Check 4: Whisper ran on full audio (not sampled)."""
    name = "whisper_full"
    if whisper_full_audio:
        return {"name": name, "passed": True, "detail": "Whisper ran on full audio"}
    return {"name": name, "passed": False, "detail": "Whisper did NOT run on full audio"}


def _check_format_valid(actual_format: str, expected_format: str) -> CheckResult:
    """Check 5: output format matches expected codec/container."""
    name = "format_valid"
    if not expected_format:
        return {"name": name, "passed": True, "detail": "no expected format to check"}
    if actual_format.lower() == expected_format.lower():
        return {"name": name, "passed": True, "detail": f"format matches: {actual_format}"}
    return {
        "name": name,
        "passed": False,
        "detail": f"format mismatch: {actual_format!r} != {expected_format!r}",
    }


def _check_duration_valid(
    actual_duration: float,
    expected_min: float,
    expected_max: float,
) -> CheckResult:
    """Check 6: output duration within expected range."""
    name = "duration_valid"
    if expected_min == 0.0 and expected_max == 0.0:
        return {"name": name, "passed": True, "detail": "no duration range to check"}
    if expected_min <= actual_duration <= expected_max:
        return {
            "name": name,
            "passed": True,
            "detail": (
                f"duration {actual_duration:.1f}s in [{expected_min:.1f}, {expected_max:.1f}]"
            ),
        }
    return {
        "name": name,
        "passed": False,
        "detail": (
            f"duration {actual_duration:.1f}s outside [{expected_min:.1f}, {expected_max:.1f}]"
        ),
    }


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# V7SixStepHard gate
# ---------------------------------------------------------------------------


class V7SixStepHard(BaseGate):
    """V7 6-Step Hard Gate — file integrity / MD5 / Whisper full-check.

    ``gate_context`` expected keys:
        - ``required_files``: list[str] — paths that must exist
        - ``file_sizes``: dict[str, int] — {path: size_in_bytes}
        - ``md5_records``: dict[str, dict] — {path: {"expected": str, "actual": str}}
        - ``whisper_full_audio``: bool — whether Whisper ran on full audio
        - ``actual_format``: str — actual output format
        - ``expected_format``: str — expected output format
        - ``actual_duration``: float — actual output duration in seconds
        - ``expected_duration_min``: float — minimum expected duration
        - ``expected_duration_max``: float — maximum expected duration
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error``.
    """

    _gate_name = "V7"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run V7 6-step hard checks and return structured result."""
        if not gate_context.get("hyperframes_available", True):
            return {"passed": True, "gate": "V7", "status": "skipped", "reason": "HyperFrames not installed — video QA skipped"}

        required_files: list[str] = gate_context.get("required_files", [])
        file_sizes: dict[str, int] = gate_context.get("file_sizes", {})
        md5_records: dict[str, dict[str, str]] = gate_context.get("md5_records", {})
        whisper_full_audio: bool = gate_context.get("whisper_full_audio", True)
        actual_format: str = gate_context.get("actual_format", "")
        expected_format: str = gate_context.get("expected_format", "")
        actual_duration: float = gate_context.get("actual_duration", 0.0)
        expected_duration_min: float = gate_context.get("expected_duration_min", 0.0)
        expected_duration_max: float = gate_context.get("expected_duration_max", 0.0)
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            ("file_exists", lambda: _check_file_exists(required_files)),
            ("file_size_valid", lambda: _check_file_size_valid(file_sizes)),
            ("md5_verified", lambda: _check_md5_verified(md5_records)),
            ("whisper_full", lambda: _check_whisper_full(whisper_full_audio)),
            ("format_valid", lambda: _check_format_valid(actual_format, expected_format)),
            (
                "duration_valid",
                lambda: _check_duration_valid(
                    actual_duration, expected_duration_min, expected_duration_max
                ),
            ),
        ]

        checks = apply_mock_overrides(check_fns, mock_results)

        return build_gate_result(checks, gate="V7", expected_suffix=".")
