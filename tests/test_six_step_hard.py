"""Tests for V7SixStepHard gate — 6-step hard constraint."""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest

from automedia.gates.six_step_hard import V7SixStepHard, _build_result, _CHECK_NAMES
from automedia.gates.base import BaseGate, _registry


def _make_context(
    *,
    required_files: list[str] | None = None,
    file_sizes: dict[str, int] | None = None,
    md5_records: dict[str, dict[str, str]] | None = None,
    whisper_full_audio: bool = True,
    actual_format: str = "mp3",
    expected_format: str = "mp3",
    actual_duration: float = 60.0,
    expected_duration_min: float = 30.0,
    expected_duration_max: float = 120.0,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "required_files": required_files if required_files is not None else [],
        "file_sizes": file_sizes if file_sizes is not None else {},
        "md5_records": md5_records if md5_records is not None else {},
        "whisper_full_audio": whisper_full_audio,
        "actual_format": actual_format,
        "expected_format": expected_format,
        "actual_duration": actual_duration,
        "expected_duration_min": expected_duration_min,
        "expected_duration_max": expected_duration_max,
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


class TestV7Metadata:
    def test_gate_name(self) -> None:
        assert V7SixStepHard().gate_name == "V7"

    def test_failure_mode(self) -> None:
        assert V7SixStepHard().failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(V7SixStepHard, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "V7" in _registry
        assert _registry.get("V7") is V7SixStepHard


class TestV7MockDriven:
    def test_all_checks_pass(self) -> None:
        result = V7SixStepHard().execute(_make_context(mock_results=_all_pass_mock()))
        assert result["passed"] is True
        assert result["gate"] == "V7"
        assert result["error"] is None
        assert len(result["checks"]) == 6

    def test_file_exists_failure(self) -> None:
        result = V7SixStepHard().execute(_make_context(mock_results=_fail_check("file_exists")))
        assert result["passed"] is False

    def test_file_size_failure(self) -> None:
        result = V7SixStepHard().execute(_make_context(mock_results=_fail_check("file_size_valid")))
        assert result["passed"] is False

    def test_md5_failure(self) -> None:
        result = V7SixStepHard().execute(_make_context(mock_results=_fail_check("md5_verified")))
        assert result["passed"] is False

    def test_whisper_full_failure(self) -> None:
        result = V7SixStepHard().execute(_make_context(mock_results=_fail_check("whisper_full")))
        assert result["passed"] is False

    def test_format_failure(self) -> None:
        result = V7SixStepHard().execute(_make_context(mock_results=_fail_check("format_valid")))
        assert result["passed"] is False

    def test_duration_failure(self) -> None:
        result = V7SixStepHard().execute(_make_context(mock_results=_fail_check("duration_valid")))
        assert result["passed"] is False

    def test_all_checks_fail(self) -> None:
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        result = V7SixStepHard().execute(_make_context(mock_results=fail_all))
        assert result["passed"] is False


class TestV7RealLogic:
    def test_existing_files_pass(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            result = V7SixStepHard().execute(_make_context(required_files=[path]))
            chk = next(c for c in result["checks"] if c["name"] == "file_exists")
            assert chk["passed"] is True
        finally:
            os.unlink(path)

    def test_missing_files_fail(self) -> None:
        result = V7SixStepHard().execute(_make_context(required_files=["/nonexistent/file.mp3"]))
        chk = next(c for c in result["checks"] if c["name"] == "file_exists")
        assert chk["passed"] is False

    def test_valid_file_sizes_pass(self) -> None:
        result = V7SixStepHard().execute(_make_context(file_sizes={"/tmp/a.mp3": 1024}))
        chk = next(c for c in result["checks"] if c["name"] == "file_size_valid")
        assert chk["passed"] is True

    def test_empty_file_size_fails(self) -> None:
        result = V7SixStepHard().execute(_make_context(file_sizes={"/tmp/a.mp3": 0}))
        chk = next(c for c in result["checks"] if c["name"] == "file_size_valid")
        assert chk["passed"] is False

    def test_md5_match_passes(self) -> None:
        result = V7SixStepHard().execute(_make_context(md5_records={
            "/tmp/a.mp3": {"expected": "abc123", "actual": "abc123"},
        }))
        chk = next(c for c in result["checks"] if c["name"] == "md5_verified")
        assert chk["passed"] is True

    def test_md5_mismatch_fails(self) -> None:
        result = V7SixStepHard().execute(_make_context(md5_records={
            "/tmp/a.mp3": {"expected": "abc123", "actual": "def456"},
        }))
        chk = next(c for c in result["checks"] if c["name"] == "md5_verified")
        assert chk["passed"] is False

    def test_whisper_full_passes(self) -> None:
        result = V7SixStepHard().execute(_make_context(whisper_full_audio=True))
        chk = next(c for c in result["checks"] if c["name"] == "whisper_full")
        assert chk["passed"] is True

    def test_whisper_not_full_fails(self) -> None:
        result = V7SixStepHard().execute(_make_context(whisper_full_audio=False))
        chk = next(c for c in result["checks"] if c["name"] == "whisper_full")
        assert chk["passed"] is False

    def test_format_match_passes(self) -> None:
        result = V7SixStepHard().execute(_make_context(actual_format="mp3", expected_format="mp3"))
        chk = next(c for c in result["checks"] if c["name"] == "format_valid")
        assert chk["passed"] is True

    def test_format_mismatch_fails(self) -> None:
        result = V7SixStepHard().execute(_make_context(actual_format="wav", expected_format="mp3"))
        chk = next(c for c in result["checks"] if c["name"] == "format_valid")
        assert chk["passed"] is False

    def test_duration_in_range_passes(self) -> None:
        result = V7SixStepHard().execute(_make_context(actual_duration=60.0, expected_duration_min=30.0, expected_duration_max=120.0))
        chk = next(c for c in result["checks"] if c["name"] == "duration_valid")
        assert chk["passed"] is True

    def test_duration_out_of_range_fails(self) -> None:
        result = V7SixStepHard().execute(_make_context(actual_duration=200.0, expected_duration_min=30.0, expected_duration_max=120.0))
        chk = next(c for c in result["checks"] if c["name"] == "duration_valid")
        assert chk["passed"] is False


class TestV7ResultStructure:
    def test_result_has_all_required_keys(self) -> None:
        result = V7SixStepHard().execute(_make_context(mock_results=_all_pass_mock()))
        for key in ("passed", "gate", "checks", "error"):
            assert key in result

    def test_checks_have_correct_structure(self) -> None:
        result = V7SixStepHard().execute(_make_context(mock_results=_all_pass_mock()))
        for check in result["checks"]:
            assert isinstance(check["passed"], bool)
            assert isinstance(check["detail"], str)

    def test_all_six_checks_present(self) -> None:
        result = V7SixStepHard().execute(_make_context(mock_results=_all_pass_mock()))
        assert [c["name"] for c in result["checks"]] == _CHECK_NAMES

    def test_missing_context_keys(self) -> None:
        result = V7SixStepHard().execute({})
        assert result["gate"] == "V7"
        assert len(result["checks"]) == 6
