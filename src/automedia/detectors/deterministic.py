"""DeterministicTasteDetector — the built-in, env-free AI-taste detector.

The built-in detector requires no environment configuration and is always
available.  It REUSES the G1 humanizer's 9-category regex detection
strictly by import — every check function comes from
``automedia.gates.humanizer``, so bugfixes and new patterns (including the
#73 Chinese AI-taste additions) propagate here automatically.  The
patterns are never duplicated in this module.

Scoring contract (matches the approved plan):

    ai_score = (# failing checks) / (# checks run)
    passed   = ai_score <= 0.5    — above 0.5 the text reads as AI-written

The check count is always derived from the actual check list run (via the
humanizer's own ``_CHECK_NAMES`` inventory), never hardcoded.
"""

from __future__ import annotations

from collections.abc import Callable

from automedia.detectors.base import BaseDetector, DetectorResult
from automedia.gates._result import CheckResult
from automedia.gates.humanizer import (
    _CHECK_NAMES,
    _check_absolute_assertions,
    _check_filler_connectors,
    _check_hollow_intros,
    _check_long_conjunctions,
    _check_overacademic_vocabulary,
    _check_overused_adverbs,
    _check_repetitive_structures,
    _check_template_conclusions,
    _check_vague_subjects,
)

# Reuse contract: the _check_* functions are private to
# automedia.gates.humanizer; importing them from a sibling module is the
# established norm in this codebase (tests/test_humanizer.py does the same).
# If the humanizer gains a new check, add the function here AND the name to
# _CHECK_NAMES there — the detector derives its total from _CHECK_NAMES, so
# a drift between the two lists fails loudly (KeyError) instead of silently
# scoring with a stale inventory.
_CHECK_FUNCTIONS: dict[str, Callable[[str], CheckResult]] = {
    "overused_adverbs": _check_overused_adverbs,
    "hollow_intros": _check_hollow_intros,
    "vague_subjects": _check_vague_subjects,
    "filler_connectors": _check_filler_connectors,
    "long_conjunctions": _check_long_conjunctions,
    "template_conclusions": _check_template_conclusions,
    "overacademic_vocabulary": _check_overacademic_vocabulary,
    "absolute_assertions": _check_absolute_assertions,
    "repetitive_structures": _check_repetitive_structures,
}


def _run_all_checks(content: str) -> list[CheckResult]:
    """Run every humanizer check against *content*.

    The check set is derived from the humanizer's own ``_CHECK_NAMES``
    ordering so the detector's total always matches the humanizer's current
    inventory — the count is never hardcoded here.
    """
    return [_CHECK_FUNCTIONS[name](content) for name in _CHECK_NAMES]


class DeterministicTasteDetector(BaseDetector):
    """Score text with the G1 humanizer's 9 regex categories.

    ``_env_required`` is empty, so this detector is always available: no
    environment configuration, no external calls, purely deterministic.
    """

    _detector_name = "deterministic_taste"
    _env_required = ""

    def detect(self, text: str) -> DetectorResult:
        """Run the 9 humanizer checks and aggregate them into an ai_score.

        Args:
            text: The text to inspect.  Empty or whitespace-only input is
                handled gracefully (ai_score 0.0, passed True, detail
                "empty input").

        Returns:
            A :class:`DetectorResult` whose ``ai_score`` is the failing
            fraction of the humanizer checks (0.0 = no AI-taste markers,
            1.0 = every check failed) and whose ``passed`` is True only
            when ``ai_score <= 0.5``.
        """
        if not text or not text.strip():
            return {
                "name": self.detector_name,
                "ai_score": 0.0,
                "passed": True,
                "detail": "empty input",
                "method": "deterministic",
                "checks": [],
            }

        checks = _run_all_checks(text)
        total = len(checks)
        failing = [c for c in checks if not c["passed"]]
        ai_score = len(failing) / total if total else 0.0
        passed = ai_score <= 0.5

        if not failing:
            detail = f"all {total} checks passed — no AI-taste markers detected"
        else:
            summary = "; ".join(f"{c['name']} ({c['detail']})" for c in failing)
            detail = f"{len(failing)} of {total} checks failed: {summary}"

        return {
            "name": self.detector_name,
            "ai_score": ai_score,
            "passed": passed,
            "detail": detail,
            "method": "deterministic",
            "checks": list(checks),
        }
