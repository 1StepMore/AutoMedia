"""V5 MP3 vs SRT Gate — Whisper transcription diff vs SRT text ≥80%.

Checks:
    1. whisper_vs_srt_diff — diff ratio between Whisper output and SRT text
    2. srt_not_empty       — SRT file content is non-empty
    3. whisper_not_empty   — Whisper transcription is non-empty

failure_mode = "rewrite" — on failure, pipeline can rewrite/fix and retry.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from automedia.gates._context import GateContext
from automedia.gates._result import build_gate_result
from automedia.gates.base import BaseGate

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "whisper_vs_srt_diff",
    "srt_not_empty",
    "whisper_not_empty",
]

_MIN_DIFF_RATIO: float = 0.80


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_srt_timestamps(srt_text: str) -> str:
    """Strip SRT timestamps and sequence numbers, leaving only dialogue text."""
    # Remove sequence numbers (lines that are just digits)
    lines = re.sub(r"^\d+\s*$", "", srt_text, flags=re.MULTILINE)
    # Remove timestamp lines (00:00:00,000 --> 00:00:01,000)
    lines = re.sub(r"\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}", "", lines)
    # Remove HTML tags
    lines = re.sub(r"<[^>]+>", "", lines)
    # Collapse whitespace
    lines = re.sub(r"\s+", " ", lines).strip()
    return lines


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_whisper_vs_srt_diff(whisper_text: str, srt_text: str) -> dict[str, Any]:
    """Check 1: diff ratio between Whisper output and SRT text ≥80%."""
    name = "whisper_vs_srt_diff"
    if not whisper_text.strip() or not srt_text.strip():
        return {"name": name, "passed": False, "detail": "empty whisper or SRT text"}

    clean_srt = _strip_srt_timestamps(srt_text)
    ratio = SequenceMatcher(None, whisper_text.strip().lower(), clean_srt.lower()).ratio()
    if ratio >= _MIN_DIFF_RATIO:
        return {
            "name": name,
            "passed": True,
            "detail": f"similarity {ratio:.1%} >= {_MIN_DIFF_RATIO:.0%}",
        }
    return {
        "name": name,
        "passed": False,
        "detail": f"similarity {ratio:.1%} < {_MIN_DIFF_RATIO:.0%}",
    }


def _check_srt_not_empty(srt_text: str) -> dict[str, Any]:
    """Check 2: SRT file content is non-empty."""
    name = "srt_not_empty"
    if srt_text.strip():
        return {"name": name, "passed": True, "detail": "SRT text non-empty"}
    return {"name": name, "passed": False, "detail": "SRT text is empty"}


def _check_whisper_not_empty(whisper_text: str) -> dict[str, Any]:
    """Check 3: Whisper transcription is non-empty."""
    name = "whisper_not_empty"
    if whisper_text.strip():
        return {"name": name, "passed": True, "detail": "Whisper text non-empty"}
    return {"name": name, "passed": False, "detail": "Whisper text is empty"}


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# V5Mp3VsSrt gate
# ---------------------------------------------------------------------------


class V5Mp3VsSrt(BaseGate):
    """V5 MP3 vs SRT Gate — Whisper transcription diff vs SRT text ≥80%.

    ``gate_context`` expected keys:
        - ``whisper_text``: str — Whisper transcription output
        - ``srt_text``: str — SRT subtitle file content
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing.

    failure_mode = "rewrite" — on failure, pipeline can rewrite and retry.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error``.
    """

    _gate_name = "V5"
    _failure_mode = "rewrite"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run V5 MP3 vs SRT checks and return structured result."""
        whisper_text: str = gate_context.get("whisper_text", "")
        srt_text: str = gate_context.get("srt_text", "")
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            ("whisper_vs_srt_diff", lambda: _check_whisper_vs_srt_diff(whisper_text, srt_text)),
            ("srt_not_empty", lambda: _check_srt_not_empty(srt_text)),
            ("whisper_not_empty", lambda: _check_whisper_not_empty(whisper_text)),
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

        return build_gate_result(checks, gate="V5", expected_suffix=".")
