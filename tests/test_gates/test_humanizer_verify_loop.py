"""Tests for the G1 humanize→verify closed loop (issue #62, Wave-B B4).

The verify loop is OFF by default: with no config toggle, the gate result
must be byte-identical to the pre-B4 behavior — no ``detector_score`` /
``verify_iterations`` keys, and the detector is never invoked.  When
enabled via ``gate_context["config"]["gates"]["humanizer"]["verify_loop"]``
(``enabled=True``, ``max_iterations`` >= 1, default 3), the deterministic
AI-taste detector verifies the final output and the result exposes
``detector_score`` (final ai_score) and ``verify_iterations``.

All fixtures are synthetic strings (the CN officialese text scores 5/9 on
the real humanizer patterns — see tests/test_detectors/).
"""

from __future__ import annotations

from typing import Any

import pytest

from automedia.gates.humanizer import G1Humanizer

# ---------------------------------------------------------------------------
# Synthetic fixture strings (no production data)
# ---------------------------------------------------------------------------

_CLEAN_EN = "A quick brown fox jumps over the lazy dog. The sky is blue today."

# CN officialese — real matches for _CN_ACADEMIC_RE (赋能/闭环/底层逻辑/生态),
# _HOLLOW_INTRO_RES (值得注意的是), _CN_FILLER_RE (综上所述),
# _TEMPLATE_CONCLUSION_RES (综上所述) and _ABSOLUTE_RE (所有人都/毫无疑问):
# fails 5 of 9 humanizer checks (ai_score 0.556 > 0.5).
_CN_OFFICIALESE = (
    "综上所述，与此同时，我们必须推进产业赋能与闭环管理。"
    "值得注意的是，所有人都需要认识到，贯彻新发展理念势在必行。"
    "毫无疑问，我们必须落实底层逻辑，加强生态建设。"
)

_VERIFY_LOOP_ENV = "AUTOMEDIA_HUMANIZER_VERIFY_LOOP"


def _make_context(
    *,
    content: str,
    verify_loop: bool = False,
    max_iterations: int = 3,
    extra_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a gate_context dict on the deterministic path (enable_llm=False).

    *verify_loop* controls whether the ``gates.humanizer.verify_loop``
    config block is present.  *extra_config* merges additional top-level
    config keys on top of the defaults.
    """
    config: dict[str, Any] = {"enable_llm": False}
    if verify_loop:
        config["gates"] = {
            "humanizer": {"verify_loop": {"enabled": True, "max_iterations": max_iterations}}
        }
    if extra_config is not None:
        config.update(extra_config)
    return {"content": content, "config": config}


# =========================================================================
# Toggle OFF — baseline behavior must be byte-identical
# =========================================================================


class TestVerifyLoopOff:
    """With the toggle off the result shape is unchanged and the detector
    is never invoked."""

    def test_off_result_has_no_detector_keys(self) -> None:
        """Toggle OFF → result has exactly the baseline keys (no detector_*)."""
        ctx = _make_context(content=_CN_OFFICIALESE, verify_loop=False)
        result = G1Humanizer().execute(ctx)
        assert set(result) == {
            "passed",
            "gate",
            "checks",
            "error",
            "expected_vs_actual",
            "modified_content",
        }
        assert "detector_score" not in result
        assert "verify_iterations" not in result

    def test_off_still_rewrites_ai_marked_content(self) -> None:
        """Toggle OFF → the baseline rewrite still happens for failing content."""
        ctx = _make_context(content=_CN_OFFICIALESE, verify_loop=False)
        result = G1Humanizer().execute(ctx)
        assert result["passed"] is False
        assert result["gate"] == "G1"
        assert result["modified_content"] is not None

    def test_off_clean_content_still_passes(self) -> None:
        """Toggle OFF → clean content still passes with no modified_content."""
        ctx = _make_context(content=_CLEAN_EN, verify_loop=False)
        result = G1Humanizer().execute(ctx)
        assert result["passed"] is True
        assert result["modified_content"] is None

    def test_detector_never_invoked_when_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OFF → the deterministic detector is never called (no loop cost)."""

        def _boom(_text: str) -> dict[str, Any]:
            raise AssertionError("detector must not be invoked when the toggle is off")

        monkeypatch.setattr(
            "automedia.detectors.deterministic.DeterministicTasteDetector.detect", _boom
        )
        ctx = _make_context(content=_CN_OFFICIALESE, verify_loop=False)
        result = G1Humanizer().execute(ctx)
        assert result["passed"] is False


# =========================================================================
# Toggle ON — closed loop behaviour
# =========================================================================


class TestVerifyLoopOn:
    """With the toggle on, detector_score + verify_iterations are exposed."""

    def test_on_clean_english_verifies_and_passes(self) -> None:
        """Toggle ON + clean English → at least one verification, score <= 0.5."""
        ctx = _make_context(content=_CLEAN_EN, verify_loop=True)
        result = G1Humanizer().execute(ctx)
        assert result["passed"] is True
        assert result["verify_iterations"] >= 1
        assert result["detector_score"] <= 0.5
        assert isinstance(result["detector_score"], float)
        assert isinstance(result["verify_iterations"], int)

    def test_on_cn_officialese_reports_honest_score(self) -> None:
        """Toggle ON + CN officialese → detector_score present and honest."""
        ctx = _make_context(content=_CN_OFFICIALESE, verify_loop=True)
        result = G1Humanizer().execute(ctx)
        assert "detector_score" in result
        assert "verify_iterations" in result
        assert result["verify_iterations"] >= 1
        assert result["verify_iterations"] <= 3  # default budget respected
        assert result["modified_content"] is not None

    def test_on_cn_officialese_converges(self) -> None:
        """Toggle ON + CN officialese → the rewrite converges on the first pass.

        The rewritten output (0.222 on the real humanizer patterns) no
        longer reads AI-written: the loop stops with detector_score <= 0.5
        after a single verification.
        """
        ctx = _make_context(content=_CN_OFFICIALESE, verify_loop=True)
        result = G1Humanizer().execute(ctx)
        assert result["detector_score"] <= 0.5
        assert result["verify_iterations"] == 1
        assert result["passed"] is False  # gate verdict still reflects the check failures

    def test_detector_score_matches_final_output(self) -> None:
        """detector_score equals the detector's score on the FINAL output."""
        from automedia.detectors import DeterministicTasteDetector

        ctx = _make_context(content=_CN_OFFICIALESE, verify_loop=True, max_iterations=2)
        result = G1Humanizer().execute(ctx)
        final = result["modified_content"]
        assert final is not None
        assert result["detector_score"] == DeterministicTasteDetector().detect(final)["ai_score"]

    def test_empty_content_with_loop_enabled(self) -> None:
        """Empty content + toggle ON → honest 0.0 score, one verification."""
        ctx = _make_context(content="", verify_loop=True)
        result = G1Humanizer().execute(ctx)
        assert result["passed"] is True
        assert result["detector_score"] == 0.0
        assert result["verify_iterations"] == 1
        assert result["modified_content"] is None


# =========================================================================
# Iteration budget & termination guarantees
# =========================================================================


class TestVerifyLoopBudget:
    """The loop is bounded: budget cap, no-progress stop, no hangs."""

    def test_non_converging_rewrite_stops_at_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A rewrite that keeps changing but never converges stops at the budget."""
        monkeypatch.setattr(
            "automedia.gates.humanizer._rewrite_content",
            lambda text: f"{text} 此外，",
        )
        ctx = _make_context(content=_CN_OFFICIALESE, verify_loop=True, max_iterations=3)
        result = G1Humanizer().execute(ctx)
        assert result["verify_iterations"] == 3
        assert result["detector_score"] > 0.5
        assert result["passed"] is False

    def test_identical_rewrite_stops_early(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An identity rewrite (no progress) stops after one verification."""
        monkeypatch.setattr("automedia.gates.humanizer._rewrite_content", lambda text: text)
        ctx = _make_context(content=_CN_OFFICIALESE, verify_loop=True, max_iterations=3)
        result = G1Humanizer().execute(ctx)
        assert result["verify_iterations"] == 1
        assert result["detector_score"] > 0.5
        assert result["passed"] is False

    def test_budget_one_quick_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """budget=1 → exactly one detector pass, then stop (non-converging rewrite)."""
        monkeypatch.setattr(
            "automedia.gates.humanizer._rewrite_content",
            lambda text: f"{text} 此外，",
        )
        ctx = _make_context(content=_CN_OFFICIALESE, verify_loop=True, max_iterations=1)
        result = G1Humanizer().execute(ctx)
        assert result["verify_iterations"] == 1
        assert result["detector_score"] > 0.5

    def test_max_iterations_below_one_coerced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """max_iterations=0 is coerced to a minimum of 1 (never zero passes)."""
        monkeypatch.setattr(
            "automedia.gates.humanizer._rewrite_content",
            lambda text: f"{text} 此外，",
        )
        ctx = _make_context(content=_CN_OFFICIALESE, verify_loop=True, max_iterations=0)
        result = G1Humanizer().execute(ctx)
        assert result["verify_iterations"] == 1
        assert result["detector_score"] > 0.5

    def test_env_backstop_enables_loop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AUTOMEDIA_HUMANIZER_VERIFY_LOOP=1 enables the loop without config."""
        monkeypatch.setenv(_VERIFY_LOOP_ENV, "1")
        ctx = _make_context(content=_CLEAN_EN, verify_loop=False)  # no config block
        result = G1Humanizer().execute(ctx)
        assert "detector_score" in result
        assert "verify_iterations" in result
        assert result["detector_score"] <= 0.5

    def test_env_flag_zero_keeps_loop_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AUTOMEDIA_HUMANIZER_VERIFY_LOOP=0 does not enable the loop."""
        monkeypatch.setenv(_VERIFY_LOOP_ENV, "0")
        ctx = _make_context(content=_CN_OFFICIALESE, verify_loop=False)
        result = G1Humanizer().execute(ctx)
        assert "detector_score" not in result
        assert "verify_iterations" not in result
