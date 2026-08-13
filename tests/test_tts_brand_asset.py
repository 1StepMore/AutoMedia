"""Tests for V4TTSBrandAsset gate — voice consistency verification."""

from __future__ import annotations

from typing import Any

from automedia.gates.base import BaseGate, _registry
from automedia.gates.tts_brand_asset import _CHECK_NAMES, V4TTSBrandAsset


def _make_context(
    *,
    voice_id: str = "brand-voice-01",
    expected_voice_id: str = "brand-voice-01",
    speaking_rate: float = 1.0,
    segments: list[dict[str, Any]] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "voice_id": voice_id,
        "expected_voice_id": expected_voice_id,
        "speaking_rate": speaking_rate,
        "segments": segments
        if segments is not None
        else [
            {"voice_params": {"pitch": 1.0, "speed": 1.0}},
            {"voice_params": {"pitch": 1.0, "speed": 1.0}},
        ],
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


class TestV4Metadata:
    def test_gate_name(self) -> None:
        assert V4TTSBrandAsset().gate_name == "V4"

    def test_failure_mode(self) -> None:
        assert V4TTSBrandAsset().failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(V4TTSBrandAsset, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "V4" in _registry
        assert _registry.get("V4") is V4TTSBrandAsset


class TestV4MockDriven:
    def test_all_checks_pass(self) -> None:
        result = V4TTSBrandAsset().execute(_make_context(mock_results=_all_pass_mock()))
        assert result["passed"] is True
        assert result["gate"] == "V4"
        assert result["error"] is None
        assert len(result["checks"]) == 3

    def test_voice_id_failure(self) -> None:
        result = V4TTSBrandAsset().execute(
            _make_context(mock_results=_fail_check("voice_id_match"))
        )
        assert result["passed"] is False

    def test_speaking_rate_failure(self) -> None:
        result = V4TTSBrandAsset().execute(_make_context(mock_results=_fail_check("speaking_rate")))
        assert result["passed"] is False

    def test_voice_consistency_failure(self) -> None:
        result = V4TTSBrandAsset().execute(
            _make_context(mock_results=_fail_check("voice_consistency"))
        )
        assert result["passed"] is False

    def test_all_checks_fail(self) -> None:
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        result = V4TTSBrandAsset().execute(_make_context(mock_results=fail_all))
        assert result["passed"] is False


class TestV4RealLogic:
    def test_matching_voice_id_passes(self) -> None:
        result = V4TTSBrandAsset().execute(_make_context(voice_id="v1", expected_voice_id="v1"))
        chk = next(c for c in result["checks"] if c["name"] == "voice_id_match")
        assert chk["passed"] is True

    def test_mismatched_voice_id_fails(self) -> None:
        result = V4TTSBrandAsset().execute(_make_context(voice_id="v1", expected_voice_id="v2"))
        chk = next(c for c in result["checks"] if c["name"] == "voice_id_match")
        assert chk["passed"] is False

    def test_no_expected_voice_id_skips(self) -> None:
        result = V4TTSBrandAsset().execute(_make_context(expected_voice_id=""))
        chk = next(c for c in result["checks"] if c["name"] == "voice_id_match")
        assert chk["passed"] is True

    def test_speaking_rate_in_range(self) -> None:
        result = V4TTSBrandAsset().execute(_make_context(speaking_rate=1.2))
        chk = next(c for c in result["checks"] if c["name"] == "speaking_rate")
        assert chk["passed"] is True

    def test_speaking_rate_too_fast(self) -> None:
        result = V4TTSBrandAsset().execute(_make_context(speaking_rate=3.0))
        chk = next(c for c in result["checks"] if c["name"] == "speaking_rate")
        assert chk["passed"] is False

    def test_speaking_rate_too_slow(self) -> None:
        result = V4TTSBrandAsset().execute(_make_context(speaking_rate=0.1))
        chk = next(c for c in result["checks"] if c["name"] == "speaking_rate")
        assert chk["passed"] is False

    def test_consistent_segments_pass(self) -> None:
        segments = [
            {"voice_params": {"pitch": 1.0}},
            {"voice_params": {"pitch": 1.0}},
            {"voice_params": {"pitch": 1.0}},
        ]
        result = V4TTSBrandAsset().execute(_make_context(segments=segments))
        chk = next(c for c in result["checks"] if c["name"] == "voice_consistency")
        assert chk["passed"] is True

    def test_inconsistent_segments_fail(self) -> None:
        segments = [
            {"voice_params": {"pitch": 1.0}},
            {"voice_params": {"pitch": 2.0}},
        ]
        result = V4TTSBrandAsset().execute(_make_context(segments=segments))
        chk = next(c for c in result["checks"] if c["name"] == "voice_consistency")
        assert chk["passed"] is False


class TestV4ResultStructure:
    def test_result_has_all_required_keys(self) -> None:
        result = V4TTSBrandAsset().execute(_make_context(mock_results=_all_pass_mock()))
        for key in ("passed", "gate", "checks", "error"):
            assert key in result

    def test_missing_context_keys(self) -> None:
        result = V4TTSBrandAsset().execute({})
        assert result["gate"] == "V4"
        assert len(result["checks"]) == 3
