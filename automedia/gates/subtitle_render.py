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

from automedia.gates.base import BaseGate


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


def _check_subtitle_region_brightness(avg_brightness: int) -> dict[str, Any]:
    """Check 1: subtitle region pixel brightness above threshold."""
    name = "subtitle_region_brightness"
    if avg_brightness >= _MIN_BRIGHTNESS:
        return {"name": name, "passed": True, "detail": f"brightness {avg_brightness} >= {_MIN_BRIGHTNESS}"}
    return {"name": name, "passed": False, "detail": f"brightness {avg_brightness} < {_MIN_BRIGHTNESS}"}


def _check_subtitle_region_contrast(contrast: int) -> dict[str, Any]:
    """Check 2: sufficient contrast in subtitle region."""
    name = "subtitle_region_contrast"
    if contrast >= _MIN_CONTRAST:
        return {"name": name, "passed": True, "detail": f"contrast {contrast} >= {_MIN_CONTRAST}"}
    return {"name": name, "passed": False, "detail": f"contrast {contrast} < {_MIN_CONTRAST}"}


def _check_subtitle_visible(opacity: float) -> dict[str, Any]:
    """Check 3: subtitle text is visible (not transparent)."""
    name = "subtitle_visible"
    if opacity > 0.0:
        return {"name": name, "passed": True, "detail": f"opacity {opacity} > 0"}
    return {"name": name, "passed": False, "detail": f"opacity {opacity} == 0 (invisible)"}


def _check_red_line_5(pixel_valid: bool) -> dict[str, Any]:
    """Check 4 (Red Line 5): pixel-level subtitle validation passed."""
    name = "red_line_5"
    if pixel_valid:
        return {"name": name, "passed": True, "detail": "Red Line 5 satisfied: pixel-level validation passed"}
    return {"name": name, "passed": False, "detail": "Red Line 5 violated: pixel-level validation failed"}


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------


def _derive_expected(check_name: str) -> str:
    """Convert a snake_case check name to a human-readable expected statement."""
    return check_name.replace("_", " ").capitalize() + "."


def _build_result(
    checks: list[dict[str, Any]],
    *,
    error: str | None = None,
) -> dict[str, Any]:
    """Assemble the final gate result dict from individual *checks*."""
    all_passed = all(c["passed"] for c in checks)
    first_fail = next((c for c in checks if not c["passed"]), None)
    target = first_fail if first_fail is not None else checks[0]
    expected_vs_actual = {
        "check": target["name"],
        "expected": _derive_expected(target["name"]),
        "actual": target.get("detail", ""),
        "context": {},
    }
    return {
        "passed": all_passed,
        "gate": "V6",
        "checks": checks,
        "error": error,
        "expected_vs_actual": expected_vs_actual,
    }


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

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        """Run V6 subtitle render checks and return structured result."""
        avg_brightness: int = gate_context.get("avg_brightness", 0)
        contrast: int = gate_context.get("contrast", 0)
        opacity: float = gate_context.get("opacity", 0.0)
        pixel_valid: bool = gate_context.get("pixel_valid", False)
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            ("subtitle_region_brightness", lambda: _check_subtitle_region_brightness(avg_brightness)),
            ("subtitle_region_contrast", lambda: _check_subtitle_region_contrast(contrast)),
            ("subtitle_visible", lambda: _check_subtitle_visible(opacity)),
            ("red_line_5", lambda: _check_red_line_5(pixel_valid)),
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
