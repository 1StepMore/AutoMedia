"""Tests for V6SubtitleRender gate — PIL pixel brightness (Red Line 5)."""

from __future__ import annotations

from typing import Any

import pytest

from automedia.gates.subtitle_render import V6SubtitleRender, _build_result, _CHECK_NAMES
from automedia.gates.base import BaseGate, _registry


def _make_context(
    *,
    avg_brightness: int = 200,
    contrast: int = 150,
    opacity: float = 1.0,
    pixel_valid: bool = True,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "avg_brightness": avg_brightness,
        "contrast": contrast,
        "opacity": opacity,
        "pixel_valid": pixel_valid,
    }
    if mock_results is not None:
        ctx["_mock_results"] = mock_results
    return ctx


def _all_pass_mock() -> dict[str, dict[str, Any]]:
    return {name: {"passed": True, "detail": "ok"} for name in _CHECK_NAMES}


def _fail_check(name: str, detail: str = "failed") -> dict[str, dict[str, Any]]:
    results = _all_pass_mock()
    results[name] = {"passed": False, "detail": detail}
    return results


class TestV6Metadata:
    def test_gate_name(self) -> None:
        assert V6SubtitleRender().gate_name == "V6"

    def test_failure_mode(self) -> None:
        assert V6SubtitleRender().failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(V6SubtitleRender, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "V6" in _registry
        assert _registry.get("V6") is V6SubtitleRender


class TestV6MockDriven:
    def test_all_checks_pass(self) -> None:
        result = V6SubtitleRender().execute(_make_context(mock_results=_all_pass_mock()))
        assert result["passed"] is True
        assert result["gate"] == "V6"
        assert result["error"] is None
        assert len(result["checks"]) == 4

    def test_brightness_failure(self) -> None:
        result = V6SubtitleRender().execute(_make_context(mock_results=_fail_check("subtitle_region_brightness")))
        assert result["passed"] is False

    def test_contrast_failure(self) -> None:
        result = V6SubtitleRender().execute(_make_context(mock_results=_fail_check("subtitle_region_contrast")))
        assert result["passed"] is False

    def test_visible_failure(self) -> None:
        result = V6SubtitleRender().execute(_make_context(mock_results=_fail_check("subtitle_visible")))
        assert result["passed"] is False

    def test_red_line_5_failure(self) -> None:
        result = V6SubtitleRender().execute(_make_context(mock_results=_fail_check("red_line_5", "pixel check failed")))
        assert result["passed"] is False

    def test_all_checks_fail(self) -> None:
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        result = V6SubtitleRender().execute(_make_context(mock_results=fail_all))
        assert result["passed"] is False


class TestV6RealLogic:
    def test_high_brightness_passes(self) -> None:
        result = V6SubtitleRender().execute(_make_context(avg_brightness=200))
        chk = next(c for c in result["checks"] if c["name"] == "subtitle_region_brightness")
        assert chk["passed"] is True

    def test_low_brightness_fails(self) -> None:
        result = V6SubtitleRender().execute(_make_context(avg_brightness=10))
        chk = next(c for c in result["checks"] if c["name"] == "subtitle_region_brightness")
        assert chk["passed"] is False

    def test_high_contrast_passes(self) -> None:
        result = V6SubtitleRender().execute(_make_context(contrast=150))
        chk = next(c for c in result["checks"] if c["name"] == "subtitle_region_contrast")
        assert chk["passed"] is True

    def test_low_contrast_fails(self) -> None:
        result = V6SubtitleRender().execute(_make_context(contrast=20))
        chk = next(c for c in result["checks"] if c["name"] == "subtitle_region_contrast")
        assert chk["passed"] is False

    def test_visible_subtitle_passes(self) -> None:
        result = V6SubtitleRender().execute(_make_context(opacity=1.0))
        chk = next(c for c in result["checks"] if c["name"] == "subtitle_visible")
        assert chk["passed"] is True

    def test_invisible_subtitle_fails(self) -> None:
        result = V6SubtitleRender().execute(_make_context(opacity=0.0))
        chk = next(c for c in result["checks"] if c["name"] == "subtitle_visible")
        assert chk["passed"] is False

    def test_red_line_5_pixel_valid_passes(self) -> None:
        result = V6SubtitleRender().execute(_make_context(pixel_valid=True))
        chk = next(c for c in result["checks"] if c["name"] == "red_line_5")
        assert chk["passed"] is True

    def test_red_line_5_pixel_invalid_fails(self) -> None:
        result = V6SubtitleRender().execute(_make_context(pixel_valid=False))
        chk = next(c for c in result["checks"] if c["name"] == "red_line_5")
        assert chk["passed"] is False


class TestV6ResultStructure:
    def test_result_has_all_required_keys(self) -> None:
        result = V6SubtitleRender().execute(_make_context(mock_results=_all_pass_mock()))
        for key in ("passed", "gate", "checks", "error"):
            assert key in result

    def test_missing_context_keys(self) -> None:
        result = V6SubtitleRender().execute({})
        assert result["gate"] == "V6"
        assert len(result["checks"]) == 4
