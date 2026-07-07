"""Tests for V5Mp3VsSrt gate — Whisper diff vs SRT ≥80%."""

from __future__ import annotations

from typing import Any

import pytest

from automedia.gates.mp3_vs_srt import V5Mp3VsSrt, _build_result, _CHECK_NAMES, _strip_srt_timestamps
from automedia.gates.base import BaseGate, _registry


_SRT_SAMPLE = """\
1
00:00:01,000 --> 00:00:03,000
Hello world this is a test

2
00:00:03,500 --> 00:00:05,000
Of subtitle rendering
"""

_WHISPER_SAMPLE = "Hello world this is a test of subtitle rendering"


def _make_context(
    *,
    whisper_text: str = _WHISPER_SAMPLE,
    srt_text: str = _SRT_SAMPLE,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "whisper_text": whisper_text,
        "srt_text": srt_text,
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


class TestV5Metadata:
    def test_gate_name(self) -> None:
        assert V5Mp3VsSrt().gate_name == "V5"

    def test_failure_mode_is_rewrite(self) -> None:
        assert V5Mp3VsSrt().failure_mode == "rewrite"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(V5Mp3VsSrt, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "V5" in _registry
        assert _registry.get("V5") is V5Mp3VsSrt


class TestV5MockDriven:
    def test_all_checks_pass(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context(mock_results=_all_pass_mock()))
        assert result["passed"] is True
        assert result["gate"] == "V5"
        assert result["error"] is None
        assert len(result["checks"]) == 3

    def test_diff_failure(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context(mock_results=_fail_check("whisper_vs_srt_diff")))
        assert result["passed"] is False

    def test_srt_empty_failure(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context(mock_results=_fail_check("srt_not_empty")))
        assert result["passed"] is False

    def test_whisper_empty_failure(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context(mock_results=_fail_check("whisper_not_empty")))
        assert result["passed"] is False

    def test_all_checks_fail(self) -> None:
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        result = V5Mp3VsSrt().execute(_make_context(mock_results=fail_all))
        assert result["passed"] is False


class TestV5RealLogic:
    def test_identical_text_high_similarity(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context(
            whisper_text="hello world test",
            srt_text="1\n00:00:01,000 --> 00:00:02,000\nhello world test\n",
        ))
        chk = next(c for c in result["checks"] if c["name"] == "whisper_vs_srt_diff")
        assert chk["passed"] is True

    def test_different_text_low_similarity(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context(
            whisper_text="completely different text about cats",
            srt_text="1\n00:00:01,000 --> 00:00:02,000\nhello world test\n",
        ))
        chk = next(c for c in result["checks"] if c["name"] == "whisper_vs_srt_diff")
        assert chk["passed"] is False

    def test_empty_srt_fails(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context(srt_text=""))
        chk = next(c for c in result["checks"] if c["name"] == "srt_not_empty")
        assert chk["passed"] is False

    def test_empty_whisper_fails(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context(whisper_text=""))
        chk = next(c for c in result["checks"] if c["name"] == "whisper_not_empty")
        assert chk["passed"] is False

    def test_strip_srt_timestamps(self) -> None:
        cleaned = _strip_srt_timestamps(_SRT_SAMPLE)
        assert "00:00:01" not in cleaned
        assert "1" not in cleaned.strip() or "Hello" in cleaned
        assert "Hello" in cleaned

    def test_failure_mode_is_rewrite_not_stop(self) -> None:
        assert V5Mp3VsSrt().failure_mode == "rewrite"


class TestV5ResultStructure:
    def test_result_has_all_required_keys(self) -> None:
        result = V5Mp3VsSrt().execute(_make_context(mock_results=_all_pass_mock()))
        for key in ("passed", "gate", "checks", "error"):
            assert key in result

    def test_missing_context_keys(self) -> None:
        result = V5Mp3VsSrt().execute({})
        assert result["gate"] == "V5"
        assert len(result["checks"]) == 3
