"""G1 rewrite budget tests (issue #651).

main ``3e24c55`` (#650) gave G1's judge findings a real targeted rewrite but
with no round limit — the produce-audio run measured 5 rewrite rounds
(≈ 33.8 minutes), burning the whole scenario budget (46 min > timeout 45 min),
so the step died as ``exit_code=None`` (timeout kill) instead of a G1 verdict.

Budget contract (#651), applied ONLY to the targeted LLM rewrite — the
deterministic regex-rewrite path and the ``max_quality_retries`` semantics
are untouched:

1. ``llm.text_generation.max_rewrite_attempts`` (default 2, no user config
   required) hard-caps the rewrite rounds; past the budget the gate goes
   ``non_retryable`` with a ``rewrite budget exhausted`` reason;
2. two consecutive rewrites that barely change the previously applied text
   (difflib ratio > 0.95, whitespace-insensitive) also stop the loop with a
   ``no substantive change`` reason — the #639 char-halving criterion is
   deliberately NOT reused here (rewrite outputs fluctuate / grow);
3. one rewrite call is hard-bounded at 180s (same mechanism as
   ``llm_check_with_fallback``: worker thread + ``future.result(timeout)``)
   and fails closed to ``None``;
4. rounds that performed rewrites carry ``rewrite_attempts`` /
   ``rewrite_total_s`` bookkeeping (+ ``rewrite_rejected_reason`` when the
   rewrite was rejected); no rewrite ⇒ no bookkeeping keys.
"""

from __future__ import annotations

from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

import pytest

import automedia.gates.humanizer as humanizer_module
from automedia.gates.humanizer import G1Humanizer

_LLMKey = "automedia.gates.humanizer.llm_check_with_fallback"
_RewriteKey = "automedia.gates.humanizer._attempt_g1_rewrite"

_CONTENT = "众所周知，人工智能正在改变世界。总的来说，未来值得期待。"


def _judge_fail(monkeypatch: pytest.MonkeyPatch, issues: tuple[str, ...] = ("三段式结构",)) -> None:
    """Drive the gate through the LLM-judge path with a failing verdict."""

    def _fake_llm_check(**_kwargs: Any) -> dict[str, Any]:
        return {"method": "llm", "passed": False, "issues": list(issues)}

    monkeypatch.setattr(_LLMKey, _fake_llm_check)


def _make_ctx() -> dict[str, Any]:
    """A persistent context: the same dict flows through every retry round."""
    return {"content": _CONTENT, "config": {"enable_llm": True}}


# ---------------------------------------------------------------------------
# (1) Round budget: distinct rewrites every round → stop after max attempts
# ---------------------------------------------------------------------------


def test_rewrite_stops_at_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    _judge_fail(monkeypatch)
    counter = {"n": 0}

    def _fake_rewrite(_content: str, _reason: str) -> str:
        counter["n"] += 1
        # Every round produces a substantively different rewrite — only the
        # round budget can stop this loop.
        return f"改写第{counter['n']}版：人工智能正在重塑日常生活的每个角落，未来值得期待。"

    monkeypatch.setattr(_RewriteKey, _fake_rewrite)
    gate = G1Humanizer()
    ctx = _make_ctx()

    r1 = gate.execute(ctx)
    assert r1["passed"] is False
    assert "non_retryable" not in r1

    r2 = gate.execute(ctx)
    assert "non_retryable" not in r2

    r3 = gate.execute(ctx)  # 3rd round (max=2) → budget exhausted
    assert r3["non_retryable"] is True
    assert "budget exhausted" in r3["non_retryable_reason"]
    assert r3["rewrite_attempts"] == 2
    # The exhausted round must not spend another LLM rewrite call.
    assert counter["n"] == 2


# ---------------------------------------------------------------------------
# (2) No-progress stop: two consecutive near-identical rewrites → stop
# ---------------------------------------------------------------------------


def test_rewrite_stops_when_output_barely_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    _judge_fail(monkeypatch)

    # Both rounds return a rewrite nearly identical to their input text
    # (whitespace-insensitive ratio > 0.95, yet not byte-identical).
    monkeypatch.setattr(_RewriteKey, lambda content, reason: content + "微。")

    gate = G1Humanizer()
    ctx = _make_ctx()

    r1 = gate.execute(ctx)
    # The first no-progress round is tolerated and still ships the rewrite.
    assert "non_retryable" not in r1

    # The engine applies each round's modified_content into the context
    # before the retry evaluates it — simulate that apply so round 2
    # compares against the previously APPLIED rewrite, as in production.
    ctx["content"] = r1["modified_content"]

    r2 = gate.execute(ctx)
    assert r2["non_retryable"] is True
    assert "no substantive change" in r2["non_retryable_reason"]


# ---------------------------------------------------------------------------
# (3) Single-call timeout: provider timeout → fail-closed None, no crash
# ---------------------------------------------------------------------------


def test_rewrite_timeout_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def _timeout(_prompt: str, **_kwargs: Any) -> Any:
        raise FutureTimeoutError("simulated rewrite timeout")

    monkeypatch.setattr("automedia.gates.humanizer.llm_complete_structured_safe", _timeout)

    assert humanizer_module._attempt_g1_rewrite(_CONTENT, "reason") is None


# ---------------------------------------------------------------------------
# (4) Bookkeeping: rounds that performed rewrites record attempts + seconds
# ---------------------------------------------------------------------------


def test_bookkeeping_written(monkeypatch: pytest.MonkeyPatch) -> None:
    _judge_fail(monkeypatch)
    counter = {"n": 0}

    def _fake_rewrite(_content: str, _reason: str) -> str:
        counter["n"] += 1
        return f"第{counter['n']}次实质改写：内容与上一轮明显不同。"

    monkeypatch.setattr(_RewriteKey, _fake_rewrite)
    gate = G1Humanizer()
    ctx = _make_ctx()

    r1 = gate.execute(ctx)
    assert r1["rewrite_attempts"] == 1
    assert r1["rewrite_total_s"] > 0
    assert "rewrite_rejected_reason" not in r1

    r2 = gate.execute(ctx)
    assert r2["rewrite_attempts"] == 2
    assert r2["rewrite_total_s"] >= r1["rewrite_total_s"]
    assert r2["rewrite_total_s"] > 0
    assert "rewrite_rejected_reason" not in r2


# ---------------------------------------------------------------------------
# (5) Deterministic path: untouched — retryable, no budget keys, no state
# ---------------------------------------------------------------------------


def test_deterministic_path_unaffected(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_llm_check(**_kwargs: Any) -> dict[str, Any]:
        return {"method": "deterministic", "passed": False, "issues": ["overused adverbs"]}

    monkeypatch.setattr(_LLMKey, _fake_llm_check)
    ctx = _make_ctx()

    result = G1Humanizer().execute(ctx)

    assert result["passed"] is False
    assert result["method"] == "deterministic"
    # The deterministic regex rewrite stays retryable and writes none of the
    # rewrite-budget keys — ``max_quality_retries`` semantics unchanged.
    for key in (
        "non_retryable",
        "rewrite_attempts",
        "rewrite_total_s",
        "rewrite_rejected_reason",
    ):
        assert key not in result
    # The shared apply-state dict was never touched on this path.
    assert "_rewrite_apply_state" not in ctx
