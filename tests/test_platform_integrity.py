"""Tests for L3PlatformIntegrity gate — platform material completeness."""

from __future__ import annotations

from typing import Any

import pytest

from automedia.gates.platform_integrity import L3PlatformIntegrity, _CHECK_NAMES
from automedia.gates.base import BaseGate, _registry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_context(
    *,
    platforms: list[str] | None = None,
    expected_platforms: list[str] | None = None,
    content_platform_map: dict[str, Any] | None = None,
    unified_content: str = "Unified content for all platforms.",
    media_files: list[str] | None = None,
    file_paths: list[str] | None = None,
    platform_variants: dict[str, str] | None = None,
    formats: list[str] | None = None,
    required_formats: list[str] | None = None,
    archive_metadata: dict[str, Any] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a gate_context dict with sensible defaults."""
    ctx: dict[str, Any] = {
        "platforms": platforms if platforms is not None else ["wechat", "weibo"],
        "expected_platforms": expected_platforms if expected_platforms is not None else ["wechat", "weibo"],
        "content_platform_map": content_platform_map if content_platform_map is not None else {},
        "unified_content": unified_content,
        "media_files": media_files if media_files is not None else ["video.mp4", "image.jpg"],
        "file_paths": file_paths if file_paths is not None else ["video.mp4", "image.jpg"],
        "platform_variants": platform_variants if platform_variants is not None else {},
        "formats": formats if formats is not None else ["mp4", "txt", "json"],
        "required_formats": required_formats if required_formats is not None else ["mp4", "txt", "json"],
        "archive_metadata": archive_metadata
        if archive_metadata is not None
        else {
            "title": "Test Archive",
            "platform": "wechat",
            "created_at": "2026-07-07T10:00:00",
        },
    }
    if mock_results is not None:
        ctx["_mock_results"] = mock_results
    return ctx


def _all_pass_mock() -> dict[str, dict[str, Any]]:
    """Return mock results where every check passes."""
    return {name: {"passed": True, "detail": "ok"} for name in _CHECK_NAMES}


def _fail_check(name: str, detail: str = "failed") -> dict[str, dict[str, Any]]:
    """Return mock results where *name* fails and the rest pass."""
    results = _all_pass_mock()
    results[name] = {"passed": False, "detail": detail}
    return results


# =========================================================================
# Gate metadata & registration
# =========================================================================


class TestL3Metadata:
    """L3PlatformIntegrity has correct gate_name, failure_mode, and is registered."""

    def test_gate_name(self) -> None:
        gate = L3PlatformIntegrity()
        assert gate.gate_name == "L3"

    def test_failure_mode(self) -> None:
        gate = L3PlatformIntegrity()
        assert gate.failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(L3PlatformIntegrity, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "L3" in _registry
        assert _registry.get("L3") is L3PlatformIntegrity


# =========================================================================
# Mock-driven execute() tests
# =========================================================================


class TestL3MockDriven:
    """execute() respects _mock_results for deterministic testing."""

    def test_all_checks_pass(self) -> None:
        """All 6 mock checks pass → overall passed=True."""
        ctx = _make_context(mock_results=_all_pass_mock())
        result = L3PlatformIntegrity().execute(ctx)

        assert result["passed"] is True
        assert result["gate"] == "L3"
        assert result["error"] is None
        assert len(result["checks"]) == 6

    def test_single_check_failure(self) -> None:
        """One check fails → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("all_platforms_present", "missing platforms"))
        result = L3PlatformIntegrity().execute(ctx)

        assert result["passed"] is False
        failed = [c for c in result["checks"] if not c["passed"]]
        assert len(failed) == 1
        assert failed[0]["name"] == "all_platforms_present"

    def test_all_checks_fail(self) -> None:
        """All 6 checks fail → overall passed=False."""
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        ctx = _make_context(mock_results=fail_all)
        result = L3PlatformIntegrity().execute(ctx)

        assert result["passed"] is False
        assert all(not c["passed"] for c in result["checks"])


# =========================================================================
# Real-logic tests
# =========================================================================


class TestL3RealLogic:
    """Real logic execution for platform integrity checks."""

    def test_all_platforms_present_passes(self) -> None:
        """All expected platforms present passes."""
        ctx = _make_context(
            platforms=["wechat", "weibo", "douyin"],
            expected_platforms=["wechat", "weibo"],
        )
        result = L3PlatformIntegrity().execute(ctx)
        ap = next(c for c in result["checks"] if c["name"] == "all_platforms_present")
        assert ap["passed"] is True

    def test_missing_platform_fails(self) -> None:
        """Missing expected platform fails."""
        ctx = _make_context(
            platforms=["wechat"],
            expected_platforms=["wechat", "weibo", "douyin"],
        )
        result = L3PlatformIntegrity().execute(ctx)
        ap = next(c for c in result["checks"] if c["name"] == "all_platforms_present")
        assert ap["passed"] is False
        assert "missing" in ap["detail"]

    def test_platform_splitting_detected(self) -> None:
        """Content split across platforms fails no_platform_splitting."""
        ctx = _make_context(
            content_platform_map={"wechat": "content_a", "weibo": "content_b"},
        )
        result = L3PlatformIntegrity().execute(ctx)
        ns = next(c for c in result["checks"] if c["name"] == "no_platform_splitting")
        assert ns["passed"] is False
        assert "split" in ns["detail"]

    def test_missing_unified_content_fails(self) -> None:
        """Missing unified content fails no_platform_splitting."""
        ctx = _make_context(
            content_platform_map={},
            unified_content="",
        )
        result = L3PlatformIntegrity().execute(ctx)
        ns = next(c for c in result["checks"] if c["name"] == "no_platform_splitting")
        assert ns["passed"] is False

    def test_material_integrity_all_present(self) -> None:
        """All referenced media files present passes."""
        ctx = _make_context(
            media_files=["a.mp4", "b.jpg"],
            file_paths=["a.mp4", "b.jpg", "c.txt"],
        )
        result = L3PlatformIntegrity().execute(ctx)
        mi = next(c for c in result["checks"] if c["name"] == "material_integrity")
        assert mi["passed"] is True

    def test_missing_media_file_fails(self) -> None:
        """Referenced media file missing from archive fails."""
        ctx = _make_context(
            media_files=["a.mp4", "missing.mov"],
            file_paths=["a.mp4"],
        )
        result = L3PlatformIntegrity().execute(ctx)
        mi = next(c for c in result["checks"] if c["name"] == "material_integrity")
        assert mi["passed"] is False
        assert "missing" in mi["detail"]

    def test_format_completeness_missing_format_fails(self) -> None:
        """Required format missing fails."""
        ctx = _make_context(
            formats=["mp4", "txt"],
            required_formats=["mp4", "txt", "json"],
        )
        result = L3PlatformIntegrity().execute(ctx)
        fc = next(c for c in result["checks"] if c["name"] == "format_completeness")
        assert fc["passed"] is False
        assert "json" in fc["detail"]

    def test_metadata_integrity_platform_mismatch_fails(self) -> None:
        """Archive metadata platform not in platforms list fails."""
        ctx = _make_context(
            platforms=["weibo", "douyin"],
            archive_metadata={
                "title": "Test",
                "platform": "wechat",
                "created_at": "2026-07-07T10:00:00",
            },
        )
        result = L3PlatformIntegrity().execute(ctx)
        mi = next(c for c in result["checks"] if c["name"] == "metadata_integrity")
        assert mi["passed"] is False


# =========================================================================
# Result structure
# =========================================================================


class TestL3ResultStructure:
    """Returned dict always has the expected keys and types."""

    def test_result_has_all_required_keys(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = L3PlatformIntegrity().execute(ctx)

        assert "passed" in result
        assert "gate" in result
        assert "checks" in result
        assert "error" in result

    def test_checks_have_correct_structure(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = L3PlatformIntegrity().execute(ctx)

        for check in result["checks"]:
            assert "name" in check
            assert "passed" in check
            assert "detail" in check
            assert isinstance(check["passed"], bool)
            assert isinstance(check["detail"], str)

    def test_all_six_checks_present(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = L3PlatformIntegrity().execute(ctx)

        check_names = [c["name"] for c in result["checks"]]
        assert check_names == _CHECK_NAMES


# =========================================================================
# Edge cases
# =========================================================================


class TestL3EdgeCases:
    """Edge-case handling."""

    def test_empty_context_does_not_crash(self) -> None:
        """Empty gate_context doesn't crash."""
        result = L3PlatformIntegrity().execute({})
        assert result["gate"] == "L3"
        assert isinstance(result["checks"], list)

    def test_no_expected_platforms_skips_check(self) -> None:
        """No expected_platforms specified → check skips."""
        ctx = _make_context(expected_platforms=[])
        result = L3PlatformIntegrity().execute(ctx)
        ap = next(c for c in result["checks"] if c["name"] == "all_platforms_present")
        assert ap["passed"] is True

    def test_empty_media_files_passes(self) -> None:
        """Empty media_files list passes material_integrity."""
        ctx = _make_context(media_files=[])
        result = L3PlatformIntegrity().execute(ctx)
        mi = next(c for c in result["checks"] if c["name"] == "material_integrity")
        assert mi["passed"] is True

    def test_no_formats_specified_fails(self) -> None:
        """No formats specified fails format_completeness."""
        ctx = _make_context(formats=[])
        result = L3PlatformIntegrity().execute(ctx)
        fc = next(c for c in result["checks"] if c["name"] == "format_completeness")
        assert fc["passed"] is False

    def test_mock_detail_propagated(self) -> None:
        """Mock detail strings appear verbatim."""
        mock = _all_pass_mock()
        mock["material_integrity"] = {"passed": False, "detail": "custom integrity error"}
        ctx = _make_context(mock_results=mock)
        result = L3PlatformIntegrity().execute(ctx)
        mi = next(c for c in result["checks"] if c["name"] == "material_integrity")
        assert mi["detail"] == "custom integrity error"
