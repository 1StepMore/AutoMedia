"""G1 non-retryable marking tests (issue #640, plan B).

Root cause: when the LLM judge (``method="llm"``) fails G1, its findings are
structural/style-level (三段式结构, 对偶句, 贴纸标题感, 节奏均匀) while the
retry loop only re-runs ``_rewrite_content`` — pure regex word replacement.
``before == after`` in the gate diffs, so every quality-retry round re-fails
and burns ~1 minute of LLM tokens each.

Fix contract:

1. G1 marks ``non_retryable`` when the LLM judge path fails (the
   deterministic fallback stays retryable — regex rewrite is effective
   there);
2. GateEngine stops the quality-retry loop on a ``non_retryable`` verdict
   without consuming the remaining budget, recording ``retries_skipped``;
3. the LLM judge's full findings (``checks[].detail``) are preserved in the
   report — all issues are joined, never truncated to the first one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from structlog.testing import capture_logs

from automedia.gates.humanizer import G1Humanizer
from automedia.pipelines.gate_engine import GateEngine

_LLMMockKey = "automedia.gates.humanizer.llm_check_with_fallback"

_CONTENT = "众所周知，人工智能正在改变世界。总的来说，未来值得期待。"


# ---------------------------------------------------------------------------
# (1) LLM judge failure → non_retryable marked, rewrite still produced
# ---------------------------------------------------------------------------


def test_llm_judge_failure_marks_non_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM judge fails → ``non_retryable=True``; ``modified_content`` kept."""
    seen: dict[str, Any] = {}

    def _fake_llm_check(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"method": "llm", "passed": False, "issues": ["三段式结构"]}

    monkeypatch.setattr(_LLMMockKey, _fake_llm_check)

    result = G1Humanizer().execute({"content": _CONTENT, "config": {"enable_llm": True}})

    assert seen["text"] == _CONTENT
    assert result["passed"] is False
    assert result["method"] == "llm"
    assert result["non_retryable"] is True
    assert "regex rewrite cannot address them" in result["non_retryable_reason"]
    # The regex rewrite output is preserved as a report diagnostic — it may
    # still have fixed filler-word findings even though it cannot fix the
    # structural ones.
    assert result["modified_content"] is not None


# ---------------------------------------------------------------------------
# (2) LLM judge pass → no non_retryable field at all
# ---------------------------------------------------------------------------


def test_llm_judge_pass_is_retryable_neutral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM judge passes → the result carries no ``non_retryable`` key."""

    def _fake_llm_check(**kwargs: Any) -> dict[str, Any]:
        return {"method": "llm", "passed": True, "issues": []}

    monkeypatch.setattr(_LLMMockKey, _fake_llm_check)

    result = G1Humanizer().execute({"content": _CONTENT, "config": {"enable_llm": True}})

    assert result["passed"] is True
    assert "non_retryable" not in result
    assert "non_retryable_reason" not in result


# ---------------------------------------------------------------------------
# (3) Deterministic fallback failure → still retryable
# ---------------------------------------------------------------------------


def test_deterministic_fallback_failure_is_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``method="deterministic"`` failure → NO mark; regex can fix it."""

    def _fake_llm_check(**kwargs: Any) -> dict[str, Any]:
        return {"method": "deterministic", "passed": False, "issues": ["overused adverbs"]}

    monkeypatch.setattr(_LLMMockKey, _fake_llm_check)

    result = G1Humanizer().execute({"content": _CONTENT, "config": {"enable_llm": True}})

    assert result["passed"] is False
    assert result["method"] == "deterministic"
    assert "non_retryable" not in result


# ---------------------------------------------------------------------------
# (4) Engine stops the quality-retry loop on non_retryable
# ---------------------------------------------------------------------------


class _FakeGate:
    """Lightweight gate stub that bypasses BaseGate's auto-registration."""

    def __init__(
        self,
        name: str,
        mode: str,
        execute_fn: Any,
    ) -> None:
        self._name = name
        self._mode = mode
        self._execute_fn = execute_fn

    @property
    def gate_name(self) -> str:
        return self._name

    @property
    def failure_mode(self) -> str:
        return self._mode

    def execute(self, ctx: dict[str, Any]) -> dict[str, Any]:
        return self._execute_fn(ctx)


def test_engine_stops_retrying_when_non_retryable(tmp_path: Path) -> None:
    """Gate always returns ``non_retryable`` → executed exactly once.

    The engine must not spend the remaining quality-retry budget (nor log a
    misleading ``degraded`` candidate chain) when the gate's verdict says the
    findings cannot be fixed by rewrites.  ``retries_skipped`` makes the
    skip visible in the gate report.
    """
    original = "original draft text\n" * 5
    drafts = tmp_path / "01_content" / "drafts"
    drafts.mkdir(parents=True)
    draft_path = drafts / "draft.md"
    draft_path.write_text(original, encoding="utf-8")
    context: dict[str, Any] = {
        "content": original,
        "project_dir": str(tmp_path),
        "output_files": [{"type": "article", "path": str(draft_path)}],
    }

    calls = {"n": 0}

    def _execute(_ctx: dict[str, Any]) -> dict[str, Any]:
        calls["n"] += 1
        return {
            "passed": False,
            "gate": "G1",
            "non_retryable": True,
            "non_retryable_reason": "llm-judge findings are structural/style-level",
        }

    gate = _FakeGate("G1", "retry", _execute)
    engine = GateEngine([gate], max_quality_retries=3, max_regenerations=0)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    with capture_logs() as logs:
        ok, results = engine.run(context)

    assert ok is False
    assert calls["n"] == 1  # initial execution only — zero quality retries
    final = results[-1]
    assert final["passed"] is False
    assert final["retries_skipped"] is True
    assert "gate.non_retryable" in [e["event"] for e in logs]
    non_retryable_logs = [e for e in logs if e["event"] == "gate.non_retryable"]
    assert non_retryable_logs[0]["gate_name"] == "G1"
    assert "structural/style-level" in non_retryable_logs[0]["reason"]
    # Nothing was applied, so no rollback artifacts appear on the result.
    assert "degraded" not in final
    assert context["content"] == original
    assert draft_path.read_text(encoding="utf-8") == original
