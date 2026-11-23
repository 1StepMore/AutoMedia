"""G1 targeted rewrite from the LLM judge (issue #640, plan A).

Plan B (#642) marked G1 ``non_retryable`` when the LLM judge failed, because
``_rewrite_content`` is regex-only and cannot fix structural findings — every
retry converged to ``before == after``.  Plan A closes the loop: on a judge
failure the gate requests one structured rewrite targeting the judge's exact
findings.  When a usable rewrite comes back the result stays retryable and
carries it as ``modified_content``; when it does not (fail-closed), the #642
behavior is preserved.  ``passed``/``checks`` always keep the judge's verdict
— a rewrite must never turn a red verdict green.
"""

from __future__ import annotations

from typing import Any

import pytest

import automedia.gates.humanizer as humanizer_module
from automedia.gates.humanizer import G1Humanizer, G1RewriteResult

_LLMMockKey = "automedia.gates.humanizer.llm_check_with_fallback"
_RewriteMockKey = "automedia.gates.humanizer._attempt_g1_rewrite"

_CONTENT = "众所周知，人工智能正在改变世界。总的来说，未来值得期待。"
_REWRITTEN = "人工智能正在改变世界，这一点已经渗透进日常生活的每个角落。未来，值得期待。"


def _judge_fail(monkeypatch: pytest.MonkeyPatch, issues: list[str]) -> None:
    """Drive the gate through the LLM-judge path with a failing verdict."""

    def _fake_llm_check(**_kwargs: Any) -> dict[str, Any]:
        return {"method": "llm", "passed": False, "issues": issues}

    monkeypatch.setattr(_LLMMockKey, _fake_llm_check)


# ---------------------------------------------------------------------------
# (1) Judge fail + usable rewrite → retryable, modified_content = rewrite
# ---------------------------------------------------------------------------


def test_judge_fail_with_rewrite_is_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def _fake_rewrite(content: str, reason: str) -> str | None:
        seen["content"] = content
        seen["reason"] = reason
        return _REWRITTEN

    _judge_fail(monkeypatch, ["三段式结构", "节奏均匀"])
    monkeypatch.setattr(_RewriteMockKey, _fake_rewrite)

    result = G1Humanizer().execute({"content": _CONTENT, "config": {"enable_llm": True}})

    assert result["passed"] is False
    assert result["method"] == "llm"
    assert result["modified_content"] == _REWRITTEN
    assert "non_retryable" not in result
    assert "non_retryable_reason" not in result
    # The rewrite request carries the original content and the judge's findings.
    assert seen["content"] == _CONTENT
    assert "三段式结构" in seen["reason"]


# ---------------------------------------------------------------------------
# (2) Judge fail + no rewrite → #642 non_retryable behavior preserved
# ---------------------------------------------------------------------------


def test_judge_fail_without_rewrite_stays_non_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _judge_fail(monkeypatch, ["三段式结构"])
    monkeypatch.setattr(_RewriteMockKey, lambda content, reason: None)

    result = G1Humanizer().execute({"content": _CONTENT, "config": {"enable_llm": True}})

    assert result["passed"] is False
    assert result["non_retryable"] is True
    assert "regex rewrite cannot address them" in result["non_retryable_reason"]
    assert result["modified_content"] != _REWRITTEN  # regex diagnostic output, not plan-A


# ---------------------------------------------------------------------------
# (3) Rewrite seam raises → fail-closed, no crash, no half-product
# ---------------------------------------------------------------------------


def test_rewrite_exception_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    content = "plain test content without AI patterns."

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("rewrite provider failed (simulated)")

    monkeypatch.setattr("automedia.gates.humanizer.load_prompt", _boom)
    assert humanizer_module._attempt_g1_rewrite(content, "reason") is None

    monkeypatch.setattr("automedia.gates.humanizer.llm_complete_structured_safe", _boom)
    assert humanizer_module._attempt_g1_rewrite(content, "reason") is None


# ---------------------------------------------------------------------------
# (4) Rewrite identical to the original (whitespace-insensitive) → rejected
# ---------------------------------------------------------------------------


def test_rewrite_identical_to_original_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    content = "第一句内容。第二句内容。\n"
    # Same text modulo whitespace — exactly the before == after idle retry.
    same = "第一句内容。  第二句内容。\n\n"

    monkeypatch.setattr(
        "automedia.gates.humanizer.llm_complete_structured_safe",
        lambda _prompt, **_kwargs: G1RewriteResult(rewritten_content=same),
    )

    assert humanizer_module._attempt_g1_rewrite(content, "reason") is None


# ---------------------------------------------------------------------------
# (5) Rewrite never flips the verdict — passed stays False
# ---------------------------------------------------------------------------


def test_passed_semantics_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    _judge_fail(monkeypatch, ["贴纸标题感"])
    monkeypatch.setattr(_RewriteMockKey, lambda content, reason: _REWRITTEN)

    result = G1Humanizer().execute({"content": _CONTENT, "config": {"enable_llm": True}})

    assert result["passed"] is False
    failing = [c for c in result["checks"] if not c["passed"]]
    assert failing  # judge findings preserved verbatim
    assert all("贴纸标题感" in c["detail"] for c in failing)
