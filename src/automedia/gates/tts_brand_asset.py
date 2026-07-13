"""V4 TTS Brand Asset Gate — voice consistency verification.

Checks:
    1. voice_id_match     — TTS voice ID matches brand asset
    2. speaking_rate      — speaking rate within acceptable range
    3. voice_consistency  — voice parameters consistent across segments
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
    "voice_id_match",
    "speaking_rate",
    "voice_consistency",
]

_MIN_RATE: float = 0.5
_MAX_RATE: float = 2.0


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_voice_id_match(actual_voice_id: str, expected_voice_id: str) -> CheckResult:
    """Check 1: TTS voice ID matches brand asset."""
    name = "voice_id_match"
    if not expected_voice_id:
        return {"name": name, "passed": True, "detail": "no expected_voice_id provided, skip"}
    if actual_voice_id == expected_voice_id:
        return {"name": name, "passed": True, "detail": f"voice_id matches: {actual_voice_id}"}
    return {
        "name": name,
        "passed": False,
        "detail": f"voice_id mismatch: {actual_voice_id!r} != {expected_voice_id!r}",
    }


def _check_speaking_rate(speaking_rate: float) -> CheckResult:
    """Check 2: speaking rate within acceptable range."""
    name = "speaking_rate"
    if speaking_rate == 0.0:
        return {"name": name, "passed": True, "detail": "no speaking_rate provided, skip"}
    if _MIN_RATE <= speaking_rate <= _MAX_RATE:
        return {
            "name": name,
            "passed": True,
            "detail": f"rate {speaking_rate} in [{_MIN_RATE}, {_MAX_RATE}]",
        }
    return {
        "name": name,
        "passed": False,
        "detail": f"rate {speaking_rate} outside [{_MIN_RATE}, {_MAX_RATE}]",
    }


def _check_voice_consistency(segments: list[dict[str, Any]]) -> CheckResult:
    """Check 3: voice parameters consistent across segments."""
    name = "voice_consistency"
    if not segments:
        return {"name": name, "passed": True, "detail": "no segments to verify"}
    reference = segments[0].get("voice_params", {})
    if not reference:
        return {"name": name, "passed": True, "detail": "no voice_params in segments"}
    mismatches: list[int] = []
    for i, seg in enumerate(segments[1:], start=1):
        params = seg.get("voice_params", {})
        if params != reference:
            mismatches.append(i)
    if mismatches:
        return {
            "name": name,
            "passed": False,
            "detail": f"segments {mismatches} have inconsistent voice_params",
        }
    return {"name": name, "passed": True, "detail": f"all {len(segments)} segments consistent"}


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# V4TTSBrandAsset gate
# ---------------------------------------------------------------------------


class V4TTSBrandAsset(BaseGate):
    """V4 TTS Brand Asset Gate — voice consistency verification.

    ``gate_context`` expected keys:
        - ``voice_id``: str — actual TTS voice ID used
        - ``expected_voice_id``: str — brand asset expected voice ID
        - ``speaking_rate``: float — actual speaking rate
        - ``segments``: list of dicts, each with ``voice_params``: dict
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error``.
    """

    _gate_name = "V4"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run V4 TTS brand asset checks and return structured result."""
        voice_id: str = gate_context.get("voice_id", "")
        expected_voice_id: str = gate_context.get("expected_voice_id", "")
        speaking_rate: float = gate_context.get("speaking_rate", 0.0)
        segments: list[dict[str, Any]] = gate_context.get("segments", [])
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            ("voice_id_match", lambda: _check_voice_id_match(voice_id, expected_voice_id)),
            ("speaking_rate", lambda: _check_speaking_rate(speaking_rate)),
            ("voice_consistency", lambda: _check_voice_consistency(segments)),
        ]

        checks = apply_mock_overrides(check_fns, mock_results)

        return build_gate_result(checks, gate="V4", expected_suffix=".")
