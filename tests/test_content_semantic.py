"""Tests for V3ContentSemantic gate — keyword coverage ≥80%."""

from __future__ import annotations

from typing import Any

from automedia.gates.base import BaseGate, _registry
from automedia.gates.content_semantic import _CHECK_NAMES, V3ContentSemantic


def _make_context(
    *,
    source_keywords: list[str] | None = None,
    content_keywords: list[str] | None = None,
    source_texts: list[str] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "source_keywords": source_keywords
        if source_keywords is not None
        else ["ai", "ml", "data", "model", "train"],
        "content_keywords": content_keywords
        if content_keywords is not None
        else ["ai", "ml", "data", "model", "train", "extra"],
        "source_texts": source_texts if source_texts is not None else ["text1", "text2", "text3"],
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


class TestV3Metadata:
    def test_gate_name(self) -> None:
        assert V3ContentSemantic().gate_name == "V3"

    def test_failure_mode(self) -> None:
        assert V3ContentSemantic().failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(V3ContentSemantic, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "V3" in _registry
        assert _registry.get("V3") is V3ContentSemantic


class TestV3MockDriven:
    def test_all_checks_pass(self) -> None:
        result = V3ContentSemantic().execute(_make_context(mock_results=_all_pass_mock()))
        assert result["passed"] is True
        assert result["gate"] == "V3"
        assert result["error"] is None
        assert len(result["checks"]) == 3

    def test_keyword_coverage_failure(self) -> None:
        result = V3ContentSemantic().execute(
            _make_context(mock_results=_fail_check("keyword_coverage", "low coverage"))
        )
        assert result["passed"] is False

    def test_source_alignment_failure(self) -> None:
        result = V3ContentSemantic().execute(
            _make_context(mock_results=_fail_check("source_alignment"))
        )
        assert result["passed"] is False

    def test_no_hallucination_failure(self) -> None:
        result = V3ContentSemantic().execute(
            _make_context(mock_results=_fail_check("no_hallucination"))
        )
        assert result["passed"] is False

    def test_all_checks_fail(self) -> None:
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        result = V3ContentSemantic().execute(_make_context(mock_results=fail_all))
        assert result["passed"] is False


class TestV3RealLogic:
    def test_full_coverage_passes(self) -> None:
        result = V3ContentSemantic().execute(
            _make_context(
                source_keywords=["ai", "ml", "data"],
                content_keywords=["ai", "ml", "data"],
            )
        )
        chk = next(c for c in result["checks"] if c["name"] == "keyword_coverage")
        assert chk["passed"] is True

    def test_low_coverage_fails(self) -> None:
        result = V3ContentSemantic().execute(
            _make_context(
                source_keywords=["ai", "ml", "data", "model", "train"],
                content_keywords=["ai"],
            )
        )
        chk = next(c for c in result["checks"] if c["name"] == "keyword_coverage")
        assert chk["passed"] is False

    def test_empty_source_keywords_passes(self) -> None:
        result = V3ContentSemantic().execute(_make_context(source_keywords=[]))
        chk = next(c for c in result["checks"] if c["name"] == "keyword_coverage")
        assert chk["passed"] is True

    def test_source_alignment_passes_with_two_sources(self) -> None:
        result = V3ContentSemantic().execute(_make_context(source_texts=["s1", "s2", ""]))
        chk = next(c for c in result["checks"] if c["name"] == "source_alignment")
        assert chk["passed"] is True

    def test_source_alignment_fails_with_one_source(self) -> None:
        result = V3ContentSemantic().execute(_make_context(source_texts=["s1", "", ""]))
        chk = next(c for c in result["checks"] if c["name"] == "source_alignment")
        assert chk["passed"] is False

    def test_no_hallucination_passes_when_content_subset_of_source(self) -> None:
        result = V3ContentSemantic().execute(
            _make_context(
                source_keywords=["ai", "ml", "data"],
                content_keywords=["ai", "ml"],
            )
        )
        chk = next(c for c in result["checks"] if c["name"] == "no_hallucination")
        assert chk["passed"] is True


class TestV3ResultStructure:
    def test_result_has_all_required_keys(self) -> None:
        result = V3ContentSemantic().execute(_make_context(mock_results=_all_pass_mock()))
        for key in ("passed", "gate", "checks", "error"):
            assert key in result

    def test_missing_context_keys(self) -> None:
        result = V3ContentSemantic().execute({})
        assert result["gate"] == "V3"
        assert len(result["checks"]) == 3
