"""V6 Subtitle Render Gate — PIL pixel brightness verification (Red Line 5).

Checks:
    1. subtitle_region_brightness — subtitle region pixel brightness above threshold
    2. subtitle_region_contrast   — sufficient contrast in subtitle region
    3. subtitle_visible           — subtitle text is visible (not transparent)
    4. red_line_5                 — Red Line 5: pixel-level subtitle validation

Red Line 5: Subtitle rendering must be validated at the pixel level.
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
    "subtitle_region_brightness",
    "subtitle_region_contrast",
    "subtitle_visible",
    "red_line_5",
]

_MIN_BRIGHTNESS: int = 50
_MIN_CONTRAST: int = 80


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_subtitle_region_brightness(avg_brightness: int) -> CheckResult:
    """Check 1: subtitle region pixel brightness above threshold."""
    name = "subtitle_region_brightness"
    if avg_brightness >= _MIN_BRIGHTNESS:
        return {
            "name": name,
            "passed": True,
            "detail": f"brightness {avg_brightness} >= {_MIN_BRIGHTNESS}",
        }
    return {
        "name": name,
        "passed": False,
        "detail": f"brightness {avg_brightness} < {_MIN_BRIGHTNESS}",
    }


def _check_subtitle_region_contrast(contrast: int) -> CheckResult:
    """Check 2: sufficient contrast in subtitle region."""
    name = "subtitle_region_contrast"
    if contrast >= _MIN_CONTRAST:
        return {"name": name, "passed": True, "detail": f"contrast {contrast} >= {_MIN_CONTRAST}"}
    return {"name": name, "passed": False, "detail": f"contrast {contrast} < {_MIN_CONTRAST}"}


def _check_subtitle_visible(opacity: float) -> CheckResult:
    """Check 3: subtitle text is visible (not transparent)."""
    name = "subtitle_visible"
    if opacity > 0.0:
        return {"name": name, "passed": True, "detail": f"opacity {opacity} > 0"}
    return {"name": name, "passed": False, "detail": f"opacity {opacity} == 0 (invisible)"}


def _check_red_line_5(pixel_valid: bool) -> CheckResult:
    """Check 4 (Red Line 5): pixel-level subtitle validation passed."""
    name = "red_line_5"
    if pixel_valid:
        return {
            "name": name,
            "passed": True,
            "detail": "Red Line 5 satisfied: pixel-level validation passed",
        }
    return {
        "name": name,
        "passed": False,
        "detail": "Red Line 5 violated: pixel-level validation failed",
    }


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# V6SubtitleRender gate
# ---------------------------------------------------------------------------


class V6SubtitleRender(BaseGate):
    """V6 Subtitle Render Gate — PIL pixel brightness verification (Red Line 5).

    ``gate_context`` expected keys:
        - ``avg_brightness``: int — average pixel brightness in subtitle region (0-255)
        - ``contrast``: int — contrast value in subtitle region
        - ``opacity``: float — subtitle text opacity (0.0-1.0)
        - ``pixel_valid``: bool — overall pixel-level validation result (Red Line 5)
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error``.
    """

    _gate_name = "V6"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run V6 subtitle render checks and return structured result."""
        avg_brightness: int = gate_context.get("avg_brightness", 0)
        contrast: int = gate_context.get("contrast", 0)
        opacity: float = gate_context.get("opacity", 0.0)
        pixel_valid: bool = gate_context.get("pixel_valid", False)
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            (
                "subtitle_region_brightness",
                lambda: _check_subtitle_region_brightness(avg_brightness),
            ),
            ("subtitle_region_contrast", lambda: _check_subtitle_region_contrast(contrast)),
            ("subtitle_visible", lambda: _check_subtitle_visible(opacity)),
            ("red_line_5", lambda: _check_red_line_5(pixel_valid)),
        ]

        checks = apply_mock_overrides(check_fns, mock_results)

        return build_gate_result(checks, gate="V6", expected_suffix=".")
