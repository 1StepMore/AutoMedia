"""Tests for G3BrandCTA gate — zero-tolerance brand & CTA compliance."""

from __future__ import annotations

from typing import Any

from automedia.gates._result import build_gate_result
from automedia.gates.base import BaseGate, _registry
from automedia.gates.brand_cta import (
    _CHECK_NAMES,
    G3BrandCTA,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_DEFAULT_BRAND_PROFILE: dict[str, Any] = {
    "brand_name": "壹目贯维",
    "brand_aliases": ["1StepMore", "OneStepMore"],
    "brand_identity": "AI内容生产公司",
    "blocked_words": ["投资情报", "股票推荐", "保证收益"],
}


def _make_context(
    *,
    content: str = (
        "壹目贯维是一家AI内容生产公司，专注于用AI驱动内容创作。"
        "如果你想了解我们的服务，立即咨询获取免费试用。"
    ),
    brand_profile: dict[str, Any] | None = None,
    video_script: str | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a gate_context dict with sensible defaults."""
    ctx: dict[str, Any] = {
        "content": content,
        "brand_profile": brand_profile if brand_profile is not None else _DEFAULT_BRAND_PROFILE,
    }
    if video_script is not None:
        ctx["video_script"] = video_script
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


class TestG3Metadata:
    """G3BrandCTA has correct gate_name, failure_mode, and is registered."""

    def test_gate_name(self) -> None:
        gate = G3BrandCTA()
        assert gate.gate_name == "G3"

    def test_failure_mode_is_stop(self) -> None:
        """零容忍 = pipeline STOP."""
        gate = G3BrandCTA()
        assert gate.failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(G3BrandCTA, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "G3" in _registry
        assert _registry.get("G3") is G3BrandCTA


# =========================================================================
# Mock-driven execute() tests
# =========================================================================


class TestG3MockDriven:
    """execute() respects _mock_results for deterministic testing."""

    def test_all_checks_pass(self) -> None:
        """All 6 mock checks pass → overall passed=True."""
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G3BrandCTA().execute(ctx)

        assert result["passed"] is True
        assert result["gate"] == "G3"
        assert result["error"] is None
        assert len(result["checks"]) == 6

    def test_brand_name_failure_stops_gate(self) -> None:
        """brand_name_present failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("brand_name_present", "not found"))
        result = G3BrandCTA().execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == "G3"
        failed = [c for c in result["checks"] if not c["passed"]]
        assert len(failed) == 1
        assert failed[0]["name"] == "brand_name_present"

    def test_cta_failure_stops_gate(self) -> None:
        """cta_present failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("cta_present", "no CTA"))
        result = G3BrandCTA().execute(ctx)
        assert result["passed"] is False

    def test_brand_identity_failure_stops_gate(self) -> None:
        """brand_identity failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("brand_identity", "wrong identity"))
        result = G3BrandCTA().execute(ctx)
        assert result["passed"] is False

    def test_blocked_words_failure_stops_gate(self) -> None:
        """blocked_words_absent failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("blocked_words_absent", "found blocked"))
        result = G3BrandCTA().execute(ctx)
        assert result["passed"] is False

    def test_cta_sync_failure_stops_gate(self) -> None:
        """cta_direction_sync failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("cta_direction_sync", "mismatch"))
        result = G3BrandCTA().execute(ctx)
        assert result["passed"] is False

    def test_bridge_sentence_failure_stops_gate(self) -> None:
        """bridge_sentence failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("bridge_sentence", "no bridge"))
        result = G3BrandCTA().execute(ctx)
        assert result["passed"] is False

    def test_all_checks_fail(self) -> None:
        """All 6 checks fail → overall passed=False."""
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        ctx = _make_context(mock_results=fail_all)
        result = G3BrandCTA().execute(ctx)
        assert result["passed"] is False
        assert all(not c["passed"] for c in result["checks"])

    def test_mock_detail_propagated(self) -> None:
        """Mock detail strings appear verbatim in result."""
        mock = _all_pass_mock()
        mock["brand_identity"] = {"passed": False, "detail": "custom error 456"}
        ctx = _make_context(mock_results=mock)
        result = G3BrandCTA().execute(ctx)
        bi = next(c for c in result["checks"] if c["name"] == "brand_identity")
        assert bi["detail"] == "custom error 456"


# =========================================================================
# Real-logic tests (no mock)
# =========================================================================


class TestG3RealBrandName:
    """Real brand name detection without mocks."""

    def test_primary_brand_name_found(self) -> None:
        """Primary brand_name appears in content → pass."""
        ctx = _make_context(content="壹目贯维提供AI驱动的内容解决方案。")
        result = G3BrandCTA().execute(ctx)
        bn = next(c for c in result["checks"] if c["name"] == "brand_name_present")
        assert bn["passed"] is True

    def test_alias_brand_name_found(self) -> None:
        """Brand alias appears in content → pass."""
        ctx = _make_context(content="1StepMore is a leading AI content company.")
        result = G3BrandCTA().execute(ctx)
        bn = next(c for c in result["checks"] if c["name"] == "brand_name_present")
        assert bn["passed"] is True

    def test_brand_name_missing_fails(self) -> None:
        """No brand name in content → fail."""
        ctx = _make_context(content="这是一篇通用文章，没有提到任何品牌。")
        result = G3BrandCTA().execute(ctx)
        bn = next(c for c in result["checks"] if c["name"] == "brand_name_present")
        assert bn["passed"] is False

    def test_brand_name_case_insensitive(self) -> None:
        """Brand name matching is case-insensitive."""
        ctx = _make_context(content="1stepmore delivers AI content solutions.")
        result = G3BrandCTA().execute(ctx)
        bn = next(c for c in result["checks"] if c["name"] == "brand_name_present")
        assert bn["passed"] is True


class TestG3RealCTA:
    """Real CTA detection without mocks."""

    def test_cta_found_consult(self) -> None:
        """立即咨询 → CTA present."""
        ctx = _make_context(content="壹目贯维。立即咨询了解更多。")
        result = G3BrandCTA().execute(ctx)
        cta = next(c for c in result["checks"] if c["name"] == "cta_present")
        assert cta["passed"] is True

    def test_cta_found_free_trial(self) -> None:
        """免费试用 → CTA present."""
        ctx = _make_context(content="壹目贯维。免费试用我们的AI平台。")
        result = G3BrandCTA().execute(ctx)
        cta = next(c for c in result["checks"] if c["name"] == "cta_present")
        assert cta["passed"] is True

    def test_cta_missing_fails(self) -> None:
        """No CTA in content → fail."""
        ctx = _make_context(content="壹目贯维是一家AI内容生产公司，提供多种服务。")
        result = G3BrandCTA().execute(ctx)
        cta = next(c for c in result["checks"] if c["name"] == "cta_present")
        assert cta["passed"] is False


class TestG3RealBrandIdentity:
    """Real brand identity check without mocks."""

    def test_identity_ai_content_production(self) -> None:
        """Content contains 'AI内容生产' → pass."""
        ctx = _make_context(content="壹目贯维是AI内容生产领域的先行者。立即咨询。")
        result = G3BrandCTA().execute(ctx)
        bi = next(c for c in result["checks"] if c["name"] == "brand_identity")
        assert bi["passed"] is True

    def test_identity_wrong_in_profile_fails(self) -> None:
        """brand_profile declares wrong identity → fail."""
        profile = {**_DEFAULT_BRAND_PROFILE, "brand_identity": "投资情报分析"}
        ctx = _make_context(
            content="壹目贯维提供投资情报分析服务。立即咨询。",
            brand_profile=profile,
        )
        result = G3BrandCTA().execute(ctx)
        bi = next(c for c in result["checks"] if c["name"] == "brand_identity")
        assert bi["passed"] is False

    def test_identity_missing_in_content_fails(self) -> None:
        """Content has no identity phrase → fail."""
        ctx = _make_context(content="壹目贯维提供各种技术服务。立即咨询。")
        result = G3BrandCTA().execute(ctx)
        bi = next(c for c in result["checks"] if c["name"] == "brand_identity")
        assert bi["passed"] is False


class TestG3RealBlockedWords:
    """Real blocked words check without mocks."""

    def test_no_blocked_words_pass(self) -> None:
        """Content without blocked words → pass."""
        ctx = _make_context(content="壹目贯维是AI内容生产公司。立即咨询。")
        result = G3BrandCTA().execute(ctx)
        bw = next(c for c in result["checks"] if c["name"] == "blocked_words_absent")
        assert bw["passed"] is True

    def test_blocked_word_found_fails(self) -> None:
        """Content contains blocked word → fail."""
        ctx = _make_context(content="壹目贯维提供投资情报服务。立即咨询。")
        result = G3BrandCTA().execute(ctx)
        bw = next(c for c in result["checks"] if c["name"] == "blocked_words_absent")
        assert bw["passed"] is False

    def test_empty_blocked_words_list_passes(self) -> None:
        """Empty blocked_words list → always pass."""
        profile = {**_DEFAULT_BRAND_PROFILE, "blocked_words": []}
        ctx = _make_context(brand_profile=profile)
        result = G3BrandCTA().execute(ctx)
        bw = next(c for c in result["checks"] if c["name"] == "blocked_words_absent")
        assert bw["passed"] is True


class TestG3RealBridgeSentence:
    """Real bridge sentence check without mocks."""

    def test_bridge_before_cta_passes(self) -> None:
        """Transition phrase before CTA → pass."""
        ctx = _make_context(content="壹目贯维是AI内容生产公司。如果您想了解我们的服务，立即咨询。")
        result = G3BrandCTA().execute(ctx)
        bs = next(c for c in result["checks"] if c["name"] == "bridge_sentence")
        assert bs["passed"] is True

    def test_no_bridge_fails(self) -> None:
        """CTA with no preceding context → fail."""
        ctx = _make_context(content="立即咨询。")
        result = G3BrandCTA().execute(ctx)
        bs = next(c for c in result["checks"] if c["name"] == "bridge_sentence")
        assert bs["passed"] is False

    def test_sentence_break_as_bridge(self) -> None:
        """A sentence break before CTA counts as transition."""
        ctx = _make_context(content="壹目贯维是AI内容生产公司。立即咨询。")
        result = G3BrandCTA().execute(ctx)
        bs = next(c for c in result["checks"] if c["name"] == "bridge_sentence")
        assert bs["passed"] is True


class TestG3RealCTASync:
    """Real CTA direction sync check without mocks."""

    def test_no_video_script_skips_sync(self) -> None:
        """No video_script in context → sync check passes."""
        ctx = _make_context(
            content="壹目贯维是AI内容生产公司。立即咨询。",
            video_script=None,
        )
        result = G3BrandCTA().execute(ctx)
        sync = next(c for c in result["checks"] if c["name"] == "cta_direction_sync")
        assert sync["passed"] is True

    def test_video_and_article_sync_passes(self) -> None:
        """Video + article share CTA keywords → pass."""
        ctx = _make_context(
            content="壹目贯维是AI内容生产公司。立即咨询获取详情。",
            video_script="欢迎来到壹目贯维，立即咨询我们的AI解决方案。",
        )
        result = G3BrandCTA().execute(ctx)
        sync = next(c for c in result["checks"] if c["name"] == "cta_direction_sync")
        assert sync["passed"] is True

    def test_video_no_cta_fails_sync(self) -> None:
        """Video script without CTA → sync fails."""
        ctx = _make_context(
            content="壹目贯维是AI内容生产公司。立即咨询。",
            video_script="壹目贯维提供各种AI服务，我们很专业。",
        )
        result = G3BrandCTA().execute(ctx)
        sync = next(c for c in result["checks"] if c["name"] == "cta_direction_sync")
        assert sync["passed"] is False


# =========================================================================
# Result structure
# =========================================================================


class TestG3ResultStructure:
    """Returned dict always has the expected keys and types."""

    def test_result_has_required_keys(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G3BrandCTA().execute(ctx)

        assert "passed" in result
        assert "gate" in result
        assert "checks" in result
        assert "error" in result

    def test_checks_have_correct_structure(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G3BrandCTA().execute(ctx)

        for check in result["checks"]:
            assert "name" in check
            assert "passed" in check
            assert "detail" in check
            assert isinstance(check["passed"], bool)
            assert isinstance(check["detail"], str)

    def test_all_six_checks_present(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G3BrandCTA().execute(ctx)
        check_names = [c["name"] for c in result["checks"]]
        assert check_names == _CHECK_NAMES

    def test_six_checks_total(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G3BrandCTA().execute(ctx)
        assert len(result["checks"]) == 6


# =========================================================================
# Edge cases & zero-tolerance
# =========================================================================


class TestG3EdgeCases:
    """Edge-case handling and zero-tolerance enforcement."""

    def test_missing_context_keys(self) -> None:
        """Empty gate_context doesn't crash — uses defaults."""
        result = G3BrandCTA().execute({})
        assert result["gate"] == "G3"
        assert isinstance(result["checks"], list)
        assert result["passed"] is False  # no brand name, no CTA → fail

    def test_single_failure_stops_pipeline(self) -> None:
        """Zero-tolerance: even one failure → passed=False."""
        mock = _all_pass_mock()
        mock["bridge_sentence"] = {"passed": False, "detail": "missing"}
        ctx = _make_context(mock_results=mock)
        result = G3BrandCTA().execute(ctx)
        assert result["passed"] is False

    def test_build_result_all_pass(self) -> None:
        """build_gate_result returns passed=True when all checks pass."""
        checks = [{"name": n, "passed": True, "detail": "ok"} for n in _CHECK_NAMES]
        result = build_gate_result(checks, gate="G3")
        assert result["passed"] is True
        assert result["gate"] == "G3"
        assert result["error"] is None

    def test_build_result_one_fail(self) -> None:
        """build_gate_result returns passed=False when any check fails."""
        checks = [{"name": n, "passed": True, "detail": "ok"} for n in _CHECK_NAMES]
        checks[2] = {"name": "brand_identity", "passed": False, "detail": "bad"}
        result = build_gate_result(checks, gate="G3")
        assert result["passed"] is False
