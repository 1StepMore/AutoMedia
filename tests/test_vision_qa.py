"""Tests for V1VisionQA gate — per-entry vision QA (Red Line 6)."""

from __future__ import annotations

from typing import Any

from automedia.gates.base import BaseGate, _registry
from automedia.gates.vision_qa import _CHECK_NAMES, V1VisionQA


def _good_entry(idx: int = 0, base_dir: str = "/tmp") -> dict[str, Any]:
    return {
        "mid_frame_path": f"{base_dir}/mid_{idx}.png",
        "end_silence_frame_path": f"{base_dir}/end_{idx}.png",
        "qa_passed": True,
        "checked": True,
    }


def _make_context(
    *,
    entries: list[dict[str, Any]] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "entries": entries if entries is not None else [_good_entry(0), _good_entry(1)],
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


class TestV1Metadata:
    def test_gate_name(self) -> None:
        assert V1VisionQA().gate_name == "V1"

    def test_failure_mode(self) -> None:
        assert V1VisionQA().failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(V1VisionQA, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "V1" in _registry
        assert _registry.get("V1") is V1VisionQA


class TestV1MockDriven:
    def test_all_checks_pass(self) -> None:
        result = V1VisionQA().execute(_make_context(mock_results=_all_pass_mock()))
        assert result["passed"] is True
        assert result["gate"] == "V1"
        assert result["error"] is None
        assert len(result["checks"]) == 4

    def test_mid_frame_failure(self) -> None:
        result = V1VisionQA().execute(_make_context(mock_results=_fail_check("mid_frame_valid")))
        assert result["passed"] is False

    def test_end_silence_failure(self) -> None:
        result = V1VisionQA().execute(_make_context(mock_results=_fail_check("end_silence_valid")))
        assert result["passed"] is False

    def test_all_entries_failed(self) -> None:
        result = V1VisionQA().execute(_make_context(mock_results=_fail_check("all_entries_passed")))
        assert result["passed"] is False

    def test_red_line_6_failure(self) -> None:
        result = V1VisionQA().execute(
            _make_context(mock_results=_fail_check("red_line_6", "sampling detected"))
        )
        assert result["passed"] is False

    def test_all_checks_fail(self) -> None:
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        result = V1VisionQA().execute(_make_context(mock_results=fail_all))
        assert result["passed"] is False


class TestV1RealLogic:
    def test_good_entries_all_pass(self, tmp_path: Any) -> None:
        entries = [_good_entry(i, str(tmp_path)) for i in range(3)]
        result = V1VisionQA().execute(_make_context(entries=entries))
        assert result["passed"] is True

    def test_missing_mid_frame_fails(self, tmp_path: Any) -> None:
        entry = _good_entry(0, str(tmp_path))
        entry["mid_frame_path"] = ""
        result = V1VisionQA().execute(_make_context(entries=[entry]))
        chk = next(c for c in result["checks"] if c["name"] == "mid_frame_valid")
        assert chk["passed"] is False

    def test_missing_end_silence_fails(self, tmp_path: Any) -> None:
        entry = _good_entry(0, str(tmp_path))
        entry["end_silence_frame_path"] = ""
        result = V1VisionQA().execute(_make_context(entries=[entry]))
        chk = next(c for c in result["checks"] if c["name"] == "end_silence_valid")
        assert chk["passed"] is False

    def test_entry_qa_failed(self, tmp_path: Any) -> None:
        entry = _good_entry(0, str(tmp_path))
        entry["qa_passed"] = False
        result = V1VisionQA().execute(_make_context(entries=[entry]))
        chk = next(c for c in result["checks"] if c["name"] == "all_entries_passed")
        assert chk["passed"] is False

    def test_red_line_6_unchecked_entry_fails(self, tmp_path: Any) -> None:
        entry = _good_entry(0, str(tmp_path))
        entry["checked"] = False
        result = V1VisionQA().execute(_make_context(entries=[entry]))
        chk = next(c for c in result["checks"] if c["name"] == "red_line_6")
        assert chk["passed"] is False

    def test_empty_entries_fails_all(self) -> None:
        result = V1VisionQA().execute(_make_context(entries=[]))
        assert result["passed"] is False


class TestV1ResultStructure:
    def test_result_has_all_required_keys(self) -> None:
        result = V1VisionQA().execute(_make_context(mock_results=_all_pass_mock()))
        for key in ("passed", "gate", "checks", "error"):
            assert key in result

    def test_checks_have_correct_structure(self) -> None:
        result = V1VisionQA().execute(_make_context(mock_results=_all_pass_mock()))
        for check in result["checks"]:
            assert isinstance(check["passed"], bool)
            assert isinstance(check["detail"], str)

    def test_missing_context_keys(self) -> None:
        result = V1VisionQA().execute({})
        assert result["gate"] == "V1"
        assert len(result["checks"]) == 4
