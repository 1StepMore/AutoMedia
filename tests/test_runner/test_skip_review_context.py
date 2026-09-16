"""``skip_review`` reaches ``gate_context`` so H0 can auto-pass.

The runner owns the bridge: the public ``skip_review`` parameter must land in
``gate_context["skip_review"]`` (True when opted in, False otherwise) for
``H0HumanReviewGate`` to read it.  These tests capture the live context a gate
receives during a mocked ``run_full_pipeline`` run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from automedia.gates._context import GateContext
from automedia.gates.base import BaseGate
from automedia.gates.h0_human_review import H0HumanReviewGate
from automedia.pipelines.runner import run_full_pipeline


class _CaptureSkipReviewGate(BaseGate):
    """Gate that records ``gate_context["skip_review"]``."""

    _gate_name = "H96"
    _failure_mode = "stop"

    def __init__(self, captured: dict[str, Any]) -> None:
        self._captured = captured

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        self._captured["skip_review"] = gate_context.get("skip_review")
        return {"passed": True, "gate": self.gate_name}


def _run_with_capture(
    tmp_path: Path,
    *,
    skip_review: bool,
) -> tuple[str, dict[str, Any]]:
    captured: dict[str, Any] = {}
    with (
        patch("automedia.core.config_loader.load_config", return_value={}),
        patch("automedia.core.project.Project") as mock_project,
        patch("automedia.pipelines.runner._build_gates_from_names") as mock_build,
        patch("automedia.pipelines.runner._record_gate_md5s"),
    ):
        mock_proj = MagicMock()
        mock_proj.project_id = "skip-review-ctx"
        mock_proj.project_dir = str(tmp_path / "skip-review-ctx")
        mock_project.init.return_value = mock_proj
        mock_build.return_value = [_CaptureSkipReviewGate(captured)]

        result = run_full_pipeline("t", "b", mode="auto", skip_review=skip_review)
    return result.status, captured


class TestSkipReviewGateContext:
    """The flag is materialised in gate_context; default preserved."""

    def test_skip_review_true_in_gate_context(self, tmp_path: Path) -> None:
        status, captured = _run_with_capture(tmp_path, skip_review=True)
        assert status == "success"
        assert captured["skip_review"] is True

    def test_skip_review_defaults_false_in_gate_context(self, tmp_path: Path) -> None:
        status, captured = _run_with_capture(tmp_path, skip_review=False)
        assert status == "success"
        assert captured["skip_review"] is False


class TestH0WithSkipReview:
    """H0 auto-passes on a skip-review context."""

    def test_h0_returns_skipped(self) -> None:
        gate = H0HumanReviewGate()
        result = gate.execute({"skip_review": True, "topic": "test"})
        assert result["passed"] is True
        assert result["gate"] == "H0"
        assert result["status"] == "skipped"

    def test_h0_awaits_without_skip_review(self) -> None:
        gate = H0HumanReviewGate()
        result = gate.execute({"topic": "test"})
        assert result["status"] == "awaiting_hitl"
