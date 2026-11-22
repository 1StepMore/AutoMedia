"""Quality-retry convergence tests for GateEngine (issue #637).

Real-run evidence: a failing G1 retried 10 rounds with completion_tokens
halving each round, and the final draft was whichever round happened to be
last (``_latest_draft`` picks by mtime).  These tests pin the three fixes:

1. every applied rewrite is recorded as a candidate in ``apply_state``;
2. two consecutive >50% shrinkings stop the retry loop early
   (``retry_non_converging`` / ``retry_shrinking``);
3. when all retries fail the no-partial-write contract holds: context and
   disk draft roll back to the pre-apply original, the chain is marked
   ``degraded``, and the candidates survive only as diagnostics (result
   metadata plus candidate bodies inside the gate-diff records) — never as
   final content.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from automedia.pipelines.gate_engine import GateEngine


class _FakeGate:
    """Lightweight gate stub that bypasses BaseGate's auto-registration."""

    def __init__(
        self,
        name: str,
        mode: str,
        execute_fn: Callable[[dict[str, Any]], dict[str, Any]],
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


def _rewrite_gate(
    rewrites: list[str],
    passes_on_call: int | None = None,
) -> tuple[_FakeGate, dict[str, int]]:
    """Gate emitting the next rewrite per execution (G1 style).

    Emits ``rewrites[n]`` as ``modified_content`` on execution *n* while the
    list lasts.  When *passes_on_call* is set, that execution (0-based)
    returns ``passed=True`` and emits no rewrite.
    """
    state = {"n": 0}

    def _execute(ctx: dict[str, Any]) -> dict[str, Any]:
        n = state["n"]
        state["n"] += 1
        if passes_on_call is not None and n == passes_on_call:
            return {"passed": True, "gate": "G1"}
        result: dict[str, Any] = {"passed": False, "gate": "G1"}
        if n < len(rewrites):
            result["modified_content"] = rewrites[n]
        return result

    return _FakeGate("G1", "retry", _execute), state


def _make_context(tmp_path: Path, original: str) -> tuple[dict[str, Any], Path]:
    """Context + CW-registered article draft pre-filled with *original*."""
    drafts = tmp_path / "01_content" / "drafts"
    drafts.mkdir(parents=True)
    draft_path = drafts / "draft.md"
    draft_path.write_text(original, encoding="utf-8")
    context: dict[str, Any] = {
        "content": original,
        "project_dir": str(tmp_path),
        "output_files": [{"type": "article", "path": str(draft_path)}],
    }
    return context, draft_path


def _read_diff_records(diffs_dir: Path) -> list[dict[str, Any]]:
    """Load every JSON diff record from a ``.automedia/gate_diffs`` dir."""
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(diffs_dir.glob("*.json"))]


# ---------------------------------------------------------------------------
# (1) All retries fail → rollback (no partial write), candidates as diagnostics
# ---------------------------------------------------------------------------


def test_all_retries_failed_rolls_back_and_records_candidates(tmp_path: Path) -> None:
    """3243/1675/969-char candidates, all fail → original restored + recorded.

    Mirrors the observed produce-audio cost log where completion tokens
    halved every round.  The failed chain's rewrites must never survive as
    final content (downstream consumers treat the draft as quality-checked
    output), so context and disk draft return to the pre-apply original and
    the candidates survive only as diagnostics: result metadata (no bodies)
    plus candidate bodies inside the gate-diff records.
    """
    original = "original draft text\n" * 5
    context, draft_path = _make_context(tmp_path, original)
    r1, r2, r3 = "a" * 3243, "b" * 1675, "c" * 969
    gate, state = _rewrite_gate([r1, r2, r3])
    engine = GateEngine([gate], max_quality_retries=3, max_regenerations=0)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    ok, results = engine.run(context)

    assert ok is False
    assert state["n"] == 4  # initial execution + all 3 quality retries
    final = results[-1]
    assert final["passed"] is False
    # No partial write: neither candidate lands in the content flow.
    assert context["content"] == original
    assert draft_path.read_text(encoding="utf-8") == original
    # Diagnostics only — metadata on the result, no candidate bodies here.
    assert final["degraded"] is True
    assert final["degraded_reason"] == "all retries failed; candidate list recorded for diagnosis"
    assert final["retry_candidates"] == [
        {"attempt": 1, "chars": 3243},
        {"attempt": 2, "chars": 1675},
        {"attempt": 3, "chars": 969},
    ]
    # Candidate bodies live in the gate-diff records, not the draft.
    records = _read_diff_records(tmp_path / ".automedia" / "gate_diffs")
    bodies = [c["content"] for rec in records for c in rec.get("candidates") or []]
    assert r1 in bodies
    assert r2 in bodies
    assert r3 in bodies


# ---------------------------------------------------------------------------
# (2) Two consecutive >50% shrinkings → stop early, mark non-converging
# ---------------------------------------------------------------------------


def test_marks_non_converging_when_two_consecutive_halvings(tmp_path: Path) -> None:
    """2000 → 900 → 400 chars: the loop stops before the 3rd retry attempt.

    ``max_quality_retries=5`` proves the stop is the convergence detection,
    not budget exhaustion: only 3 executions happen (initial + 2 retries).
    """
    original = "original draft text\n" * 5
    context, draft_path = _make_context(tmp_path, original)
    r1, r2, r3 = "a" * 2000, "b" * 900, "c" * 400
    gate, state = _rewrite_gate([r1, r2, r3])
    engine = GateEngine([gate], max_quality_retries=5, max_regenerations=0)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    ok, results = engine.run(context)

    assert ok is False
    # Stopped before the 3rd retry attempt: initial + 2 retries only
    # (without the detection it would run 6 executions).
    assert state["n"] == 3
    final = results[-1]
    assert final["retry_non_converging"] is True
    assert final["retry_shrinking"] == [2000, 900, 400]
    # No partial write: the non-converging chain is rolled back too —
    # the original content is restored despite candidates existing.
    assert context["content"] == original
    assert draft_path.read_text(encoding="utf-8") == original
    assert final["degraded"] is True


# ---------------------------------------------------------------------------
# (3) A passing retry wins even over a longer failed candidate
# ---------------------------------------------------------------------------


def test_passing_retry_wins_over_longer_failed_candidate(tmp_path: Path) -> None:
    """Round 1 fails (5000 chars), round 2 passes (1200 chars) → round 2."""
    original = "original draft text\n" * 5
    context, draft_path = _make_context(tmp_path, original)
    r1 = "a" * 5000
    gate, state = _rewrite_gate([r1], passes_on_call=1)
    engine = GateEngine([gate], max_quality_retries=3, max_regenerations=0)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    ok, results = engine.run(context)

    assert ok is True
    assert state["n"] == 2  # initial fail + one passing retry
    final = results[-1]
    assert final["passed"] is True
    assert final.get("degraded") is not True
    assert "degraded_reason" not in final
    # The passing retry evaluated and kept its (shorter) rewrite — the
    # longer failed candidate must NOT be promoted over a passing round.
    assert context["content"] == r1
    assert draft_path.read_text(encoding="utf-8") == r1


# ---------------------------------------------------------------------------
# (4) No candidates at all → pre-existing rollback behavior unchanged
# ---------------------------------------------------------------------------


def test_rolls_back_when_no_candidates(tmp_path: Path) -> None:
    """Gate never emits modified_content → original content preserved."""
    original = "original draft text\n" * 5
    context, draft_path = _make_context(tmp_path, original)
    gate, state = _rewrite_gate([])
    engine = GateEngine([gate], max_quality_retries=2, max_regenerations=0)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    ok, results = engine.run(context)

    assert ok is False
    assert state["n"] == 3  # initial execution + 2 quality retries
    final = results[-1]
    assert final["passed"] is False
    assert "degraded" not in final
    assert "degraded_reason" not in final
    # Original content restored — identical to the pre-#637 behavior.
    assert context["content"] == original
    assert draft_path.read_text(encoding="utf-8") == original
