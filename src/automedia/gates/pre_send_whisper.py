"""V2 Pre-Send Whisper Gate — full audio transcription verification + MD5.

Checks:
    1. whisper_transcription — full audio transcription completed
    2. transcription_length  — transcription text meets minimum length
    3. md5_integrity         — audio file MD5 matches recorded hash
    4. red_line_7            — Red Line 7: full transcription, not sampling

Red Line 7: Full audio must be transcribed, no partial/sampling allowed.
"""

from __future__ import annotations

import hashlib
from typing import Any

from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result
from automedia.gates.base import BaseGate
from automedia.gates.helpers import apply_mock_overrides

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "whisper_transcription",
    "transcription_length",
    "md5_integrity",
    "red_line_7",
]

_MIN_TRANSCRIPTION_LENGTH: int = 10


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_whisper_transcription(transcription: str) -> CheckResult:
    """Check 1: full audio transcription completed (non-empty)."""
    name = "whisper_transcription"
    if transcription and transcription.strip():
        return {"name": name, "passed": True, "detail": "transcription non-empty"}
    return {"name": name, "passed": False, "detail": "transcription is empty"}


def _check_transcription_length(transcription: str) -> CheckResult:
    """Check 2: transcription text meets minimum length."""
    name = "transcription_length"
    length = len(transcription.strip())
    if length >= _MIN_TRANSCRIPTION_LENGTH:
        return {
            "name": name,
            "passed": True,
            "detail": f"length {length} >= {_MIN_TRANSCRIPTION_LENGTH}",
        }
    return {
        "name": name,
        "passed": False,
        "detail": f"length {length} < {_MIN_TRANSCRIPTION_LENGTH}",
    }


def _check_md5_integrity(audio_path: str, expected_md5: str) -> CheckResult:
    """Check 3: audio file MD5 matches recorded hash."""
    name = "md5_integrity"
    if not expected_md5:
        return {"name": name, "passed": True, "detail": "no expected_md5 provided, skip"}
    try:
        h = hashlib.md5()  # noqa: S324 — integrity checksum
        with open(audio_path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        actual = h.hexdigest()
        if actual == expected_md5:
            return {"name": name, "passed": True, "detail": "MD5 matches"}
        return {
            "name": name,
            "passed": False,
            "detail": f"MD5 mismatch: {actual} != {expected_md5}",
        }
    except FileNotFoundError:
        return {"name": name, "passed": False, "detail": f"audio file not found: {audio_path}"}
    except Exception as exc:
        return {"name": name, "passed": False, "detail": f"MD5 check error: {exc}"}


def _check_red_line_7(transcription: str, full_audio: bool) -> CheckResult:
    """Check 4 (Red Line 7): full transcription, not sampling."""
    name = "red_line_7"
    if full_audio:
        return {
            "name": name,
            "passed": True,
            "detail": "Red Line 7 satisfied: full audio transcribed",
        }
    return {
        "name": name,
        "passed": False,
        "detail": "Red Line 7 violated: only partial/sampled transcription",
    }


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# V2PreSendWhisper gate
# ---------------------------------------------------------------------------


class V2PreSendWhisper(BaseGate):
    """V2 Pre-Send Whisper Gate — full audio transcription + MD5 (Red Line 7).

    ``gate_context`` expected keys:
        - ``transcription``: str — Whisper transcription result
        - ``audio_path``: str — path to audio file for MD5 check
        - ``expected_md5``: str — expected MD5 hash (empty to skip)
        - ``full_audio``: bool — whether full audio was transcribed (Red Line 7)
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error``.
    """

    _gate_name = "V2"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run V2 pre-send whisper checks and return structured result."""
        transcription: str = gate_context.get("transcription", "")
        audio_path: str = gate_context.get("audio_path", "")
        expected_md5: str = gate_context.get("expected_md5", "")
        full_audio: bool = gate_context.get("full_audio", True)
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            ("whisper_transcription", lambda: _check_whisper_transcription(transcription)),
            ("transcription_length", lambda: _check_transcription_length(transcription)),
            ("md5_integrity", lambda: _check_md5_integrity(audio_path, expected_md5)),
            ("red_line_7", lambda: _check_red_line_7(transcription, full_audio)),
        ]

        checks = apply_mock_overrides(check_fns, mock_results)

        return build_gate_result(checks, gate="V2", expected_suffix=".")
