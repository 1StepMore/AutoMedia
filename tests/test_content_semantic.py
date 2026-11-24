"""Tests for V3ContentSemantic gate — LLM claim-support judgement (#661).

All LLM interaction is stubbed: these tests never touch the network.
"""

from __future__ import annotations

from typing import Any

import pytest

from automedia.gates import content_semantic as cs
from automedia.gates.base import BaseGate, _registry
from automedia.gates.content_semantic import (
    _CHECK_NAMES,
    _LLM_CHECK_NAMES,
    V3ContentSemantic,
)


def _make_context(
    *,
    source_keywords: list[str] | None = None,
    content_keywords: list[str] | None = None,
    source_texts: list[str] | None = None,
    content: str = "成稿正文",
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
        "content": content,
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


def _supported_claims(count: int = 3) -> list[dict[str, Any]]:
    return [{"claim": f"主张{i}", "supported": True, "evidence": "源材料"} for i in range(count)]


def _judge_result(claims: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "claims": claims,
        "unsupported_claims": [c["claim"] for c in claims if not c["supported"]],
    }


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

    def test_llm_check_names_are_fixed(self) -> None:
        assert _LLM_CHECK_NAMES == [
            "claims_supported",
            "source_alignment",
            "keyword_coverage_mechanical",
        ]


class TestV3LLMJudge:
    """Four behaviours required by #661 — judge always monkeypatched."""

    def test_all_claims_supported_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            cs, "_llm_semantic_judge", lambda source, content: _judge_result(_supported_claims())
        )

        result = V3ContentSemantic().execute(_make_context())

        assert result["passed"] is True
        assert result["gate"] == "V3"
        names = [c["name"] for c in result["checks"]]
        assert names == _LLM_CHECK_NAMES
        mechanical = next(c for c in result["checks"] if c["name"] == "keyword_coverage_mechanical")
        assert mechanical["passed"] is True
        assert "advisory" in mechanical["detail"]

    def test_one_unsupported_claim_fails_and_names_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        claims = _supported_claims()
        claims.append(
            {"claim": "已有 5 万家企业采用", "supported": False, "evidence": "源材料没有该数字"}
        )
        monkeypatch.setattr(
            cs, "_llm_semantic_judge", lambda source, content: _judge_result(claims)
        )

        result = V3ContentSemantic().execute(_make_context())

        assert result["passed"] is False
        check = next(c for c in result["checks"] if c["name"] == "claims_supported")
        assert check["passed"] is False
        assert "已有 5 万家企业采用" in check["detail"]
        assert "1 条无据" in check["detail"]

    def test_llm_unavailable_skips_not_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cs, "_llm_semantic_judge", lambda source, content: None)

        result = V3ContentSemantic().execute(_make_context())

        assert result["status"] == "skipped"
        assert result["passed"] is True  # repo skip semantics
        assert "LLM semantic judge" in result["reason"]
        assert "checks" not in result

    def test_mechanical_coverage_cannot_fail_the_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            cs, "_llm_semantic_judge", lambda source, content: _judge_result(_supported_claims())
        )

        result = V3ContentSemantic().execute(
            _make_context(
                source_keywords=["ai", "ml", "data", "model", "train"],
                content_keywords=["ai"],
            )
        )

        mechanical = next(c for c in result["checks"] if c["name"] == "keyword_coverage_mechanical")
        assert mechanical["passed"] is True
        assert "20.0%" in mechanical["detail"]
        assert result["passed"] is True

    def test_source_alignment_still_decides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            cs, "_llm_semantic_judge", lambda source, content: _judge_result(_supported_claims())
        )

        result = V3ContentSemantic().execute(_make_context(source_texts=["s1", "", ""]))

        check = next(c for c in result["checks"] if c["name"] == "source_alignment")
        assert check["passed"] is False
        assert result["passed"] is False

    def test_too_few_claims_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            cs, "_llm_semantic_judge", lambda source, content: _judge_result(_supported_claims(2))
        )

        result = V3ContentSemantic().execute(_make_context())

        check = next(c for c in result["checks"] if c["name"] == "claims_supported")
        assert check["passed"] is False


class TestV3JudgeInternals:
    """The judge must fail closed when there is no usable verdict."""

    def test_empty_content_returns_none(self) -> None:
        assert cs._llm_semantic_judge(["源材料"], "   ") is None

    def test_empty_source_returns_none(self) -> None:
        assert cs._llm_semantic_judge(["", "  "], "成稿") is None

    def test_deterministic_fallback_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            cs,
            "llm_check_with_fallback",
            lambda **kwargs: {"passed": False, "issues": [], "method": "deterministic"},
        )

        assert cs._llm_semantic_judge(["源材料"], "成稿") is None

    def test_exception_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("provider down")

        monkeypatch.setattr(cs, "llm_check_with_fallback", _boom)

        assert cs._llm_semantic_judge(["源材料"], "成稿") is None

    def test_malformed_claims_return_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            cs,
            "llm_check_with_fallback",
            lambda **kwargs: {
                "passed": True,
                "issues": [],
                "method": "llm",
                "structured_issues": [{"claim": "缺少 supported 字段"}],
            },
        )

        assert cs._llm_semantic_judge(["源材料"], "成稿") is None

    def test_structured_claims_are_mapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            cs,
            "llm_check_with_fallback",
            lambda **kwargs: {
                "passed": False,
                "issues": ["无据主张"],
                "method": "llm",
                "structured_issues": [
                    {"claim": "有据主张", "supported": True, "evidence": "源材料"},
                    {"claim": "无据主张", "supported": False, "evidence": "源材料没有"},
                    {"claim": "另一条", "supported": True, "evidence": "源材料"},
                ],
            },
        )

        judge = cs._llm_semantic_judge(["源材料"], "成稿")

        assert judge is not None
        assert len(judge["claims"]) == 3
        assert judge["unsupported_claims"] == ["无据主张"]


class TestV3MockDriven:
    """Regression: the ``_mock_results`` path keeps its exact old behaviour."""

    def test_all_checks_pass(self) -> None:
        result = V3ContentSemantic().execute(_make_context(mock_results=_all_pass_mock()))
        assert result["passed"] is True
        assert result["gate"] == "V3"
        assert result["error"] is None
        assert len(result["checks"]) == 3
        assert [c["name"] for c in result["checks"]] == _CHECK_NAMES

    def test_mock_path_does_not_call_the_judge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(source: list[str], content: str) -> dict[str, Any]:
            raise AssertionError("mock path must not call the LLM judge")

        monkeypatch.setattr(cs, "_llm_semantic_judge", _boom)

        result = V3ContentSemantic().execute(_make_context(mock_results=_all_pass_mock()))

        assert result["passed"] is True

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


class TestV3ResultStructure:
    def test_result_has_all_required_keys(self) -> None:
        result = V3ContentSemantic().execute(_make_context(mock_results=_all_pass_mock()))
        for key in ("passed", "gate", "checks", "error"):
            assert key in result

    def test_missing_context_keys(self) -> None:
        """Absent inputs mean no keywords were extracted → the gate reports skipped.

        中文说明：健康度整改（P0-1）之后，缺失输入必须显式记为 ``skipped``，
        而不是对从未产出的内容给出一个关于空值的 verdict。
        """
        result = V3ContentSemantic().execute({})
        assert result["gate"] == "V3"
        assert result["status"] == "skipped"
        assert result["passed"] is True
        assert "checks" not in result
        assert "source_keywords" in result["reason"]
