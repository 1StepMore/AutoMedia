"""A failed gate must say why (#442).

``build_gate_result`` leaves ``error`` as ``None`` for quality failures; the
reason lives in the failing check's ``detail``.
"""

from __future__ import annotations

from automedia.pipelines.gate_engine import _failure_reason


class TestFailureReason:
    def test_error_wins_over_checks(self) -> None:
        result = {
            "error": "boom",
            "checks": [{"name": "x", "passed": False, "detail": "bad x"}],
        }
        assert _failure_reason(result) == "boom"

    def test_falls_back_to_first_failing_check_detail(self) -> None:
        result = {
            "error": None,
            "checks": [
                {"name": "ok", "passed": True, "detail": ""},
                {
                    "name": "overacademic_vocabulary",
                    "passed": False,
                    "detail": "found 1 over-academic word(s): 闭环",
                },
            ],
        }
        assert _failure_reason(result) == "found 1 over-academic word(s): 闭环"

    def test_suggestion_is_the_last_resort(self) -> None:
        result = {"checks": [{"name": "x", "passed": False, "suggestion": "remove x"}]}
        assert _failure_reason(result) == "remove x"

    def test_none_when_nothing_failed(self) -> None:
        passed = {
            "passed": True,
            "error": None,
            "checks": [{"name": "x", "passed": True, "detail": ""}],
        }
        assert _failure_reason(passed) is None
        assert _failure_reason({}) is None
