"""Tests for V2PreSendWhisper gate — full audio transcription + MD5 (Red Line 7)."""

from __future__ import annotations

import hashlib
import os
import tempfile
from typing import Any

from automedia.gates.base import BaseGate, _registry
from automedia.gates.pre_send_whisper import _CHECK_NAMES, V2PreSendWhisper


def _make_context(
    *,
    transcription: str = "Hello world, this is a test transcription.",
    audio_path: str = "",
    expected_md5: str = "",
    full_audio: bool = True,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "transcription": transcription,
        "audio_path": audio_path,
        "expected_md5": expected_md5,
        "full_audio": full_audio,
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


class TestV2Metadata:
    def test_gate_name(self) -> None:
        assert V2PreSendWhisper().gate_name == "V2"

    def test_failure_mode(self) -> None:
        assert V2PreSendWhisper().failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(V2PreSendWhisper, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "V2" in _registry
        assert _registry.get("V2") is V2PreSendWhisper


class TestV2MockDriven:
    def test_all_checks_pass(self) -> None:
        result = V2PreSendWhisper().execute(_make_context(mock_results=_all_pass_mock()))
        assert result["passed"] is True
        assert result["gate"] == "V2"
        assert result["error"] is None
        assert len(result["checks"]) == 4

    def test_whisper_transcription_failure(self) -> None:
        result = V2PreSendWhisper().execute(
            _make_context(mock_results=_fail_check("whisper_transcription"))
        )
        assert result["passed"] is False

    def test_transcription_length_failure(self) -> None:
        result = V2PreSendWhisper().execute(
            _make_context(mock_results=_fail_check("transcription_length"))
        )
        assert result["passed"] is False

    def test_md5_integrity_failure(self) -> None:
        result = V2PreSendWhisper().execute(
            _make_context(mock_results=_fail_check("md5_integrity"))
        )
        assert result["passed"] is False

    def test_red_line_7_failure(self) -> None:
        result = V2PreSendWhisper().execute(
            _make_context(mock_results=_fail_check("red_line_7", "partial only"))
        )
        assert result["passed"] is False

    def test_all_checks_fail(self) -> None:
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        result = V2PreSendWhisper().execute(_make_context(mock_results=fail_all))
        assert result["passed"] is False


class TestV2RealLogic:
    def test_valid_transcription_passes(self) -> None:
        result = V2PreSendWhisper().execute(
            _make_context(transcription="This is a valid transcription.")
        )
        assert result["passed"] is True

    def test_empty_transcription_fails(self) -> None:
        result = V2PreSendWhisper().execute(_make_context(transcription=""))
        chk = next(c for c in result["checks"] if c["name"] == "whisper_transcription")
        assert chk["passed"] is False

    def test_short_transcription_fails_length(self) -> None:
        result = V2PreSendWhisper().execute(_make_context(transcription="hi"))
        chk = next(c for c in result["checks"] if c["name"] == "transcription_length")
        assert chk["passed"] is False

    def test_full_audio_flag_passes_red_line_7(self) -> None:
        result = V2PreSendWhisper().execute(_make_context(full_audio=True))
        chk = next(c for c in result["checks"] if c["name"] == "red_line_7")
        assert chk["passed"] is True

    def test_partial_audio_fails_red_line_7(self) -> None:
        result = V2PreSendWhisper().execute(_make_context(full_audio=False))
        chk = next(c for c in result["checks"] if c["name"] == "red_line_7")
        assert chk["passed"] is False

    def test_md5_match_passes(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(b"test audio content")
            path = f.name
        try:
            expected = hashlib.md5(b"test audio content").hexdigest()
            result = V2PreSendWhisper().execute(
                _make_context(audio_path=path, expected_md5=expected)
            )
            chk = next(c for c in result["checks"] if c["name"] == "md5_integrity")
            assert chk["passed"] is True
        finally:
            os.unlink(path)

    def test_md5_mismatch_fails(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(b"test audio content")
            path = f.name
        try:
            result = V2PreSendWhisper().execute(
                _make_context(audio_path=path, expected_md5="bad_md5")
            )
            chk = next(c for c in result["checks"] if c["name"] == "md5_integrity")
            assert chk["passed"] is False
        finally:
            os.unlink(path)

    def test_missing_audio_file_fails_md5(self) -> None:
        result = V2PreSendWhisper().execute(
            _make_context(audio_path="/nonexistent.mp3", expected_md5="abc")
        )
        chk = next(c for c in result["checks"] if c["name"] == "md5_integrity")
        assert chk["passed"] is False


class TestV2ResultStructure:
    def test_result_has_all_required_keys(self) -> None:
        result = V2PreSendWhisper().execute(_make_context(mock_results=_all_pass_mock()))
        for key in ("passed", "gate", "checks", "error"):
            assert key in result

    def test_missing_context_keys(self) -> None:
        result = V2PreSendWhisper().execute({})
        assert result["gate"] == "V2"
        assert len(result["checks"]) == 4
