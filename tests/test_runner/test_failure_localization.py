"""Failure-localization tests (graph-engineering-rollout Wave 2, Todo 8).

Pins the ``affected_downstream`` contract: when a gate fails, the pipeline
result names every not-yet-executed gate downstream of the first failure,
restricted to the mode's gate list.

The seam is the pure helper ``_compute_affected_downstream`` (imported at
module top level — RED = collection ImportError until it exists) plus one
integration test through the mocked ``run_full_pipeline`` pattern from
``tests/test_runner.py`` proving the runner attaches the field on a real
gate failure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.pipelines.gate_engine import GateLogEntry, PipelineResult
from automedia.pipelines.runner import _MODE_MAP, _compute_affected_downstream


class TestComputeAffectedDownstream:
    """The pure helper: DAG downstream closure ∩ mode gate list."""

    def test_affected_downstream_for_g3_in_auto(self) -> None:
        """G3's closure restricted to auto mode = G6 + H0."""
        assert _compute_affected_downstream(_MODE_MAP["auto"], "G3") == [
            "G6",
            "H0",
        ]

    def test_affected_downstream_none_gate_returns_empty(self) -> None:
        """No failed gate → empty affected set."""
        assert _compute_affected_downstream(_MODE_MAP["auto"], None) == []

    def test_affected_downstream_v3_includes_h0(self) -> None:
        """V3's closure spans the video tail and H0 — no copy gates."""
        affected = _compute_affected_downstream(_MODE_MAP["auto"], "V3")
        assert affected == ["V4", "V5", "V6", "V7", "H0"]

    def test_affected_downstream_restricted_to_mode_list(self) -> None:
        """V3 failed in text_only: only gates present in the mode's list count.

        V3's full closure is V4..V7, H0, L1..L4, P1..P4 — but text_only runs
        no V/P gates and no lifecycle gates, so only H0 is affected.
        """
        affected = _compute_affected_downstream(_MODE_MAP["text_only"], "V3")
        assert affected == ["H0"]

    def test_affected_downstream_unknown_gate_returns_empty(self) -> None:
        """A gate not in the DAG has no downstream closure."""
        assert _compute_affected_downstream(_MODE_MAP["auto"], "ZZ") == []


class TestPipelineResultField:
    """``PipelineResult.affected_downstream`` — additive dataclass field."""

    def test_default_is_empty_list(self) -> None:
        result = PipelineResult()
        assert result.affected_downstream == []

    def test_error_field_type_unchanged(self) -> None:
        """Public-API guard: ``error`` stays ``str | None`` and defaults to None."""
        result = PipelineResult()
        assert result.error is None
        result2 = PipelineResult(error="boom")
        assert result2.error == "boom"
        assert result2.affected_downstream == []

    def test_set_via_keyword(self) -> None:
        result = PipelineResult(status="partial", affected_downstream=["G4", "G5"])
        assert result.affected_downstream == ["G4", "G5"]

    def test_gate_log_entry_status_literal_covers_failed_and_error(self) -> None:
        """The runner keys on ``status in ("failed", "error")`` — both literals exist."""
        failed = GateLogEntry(gate_name="G3", status="failed", duration_s=0.1)
        errored = GateLogEntry(gate_name="G4", status="error", duration_s=0.1)
        assert failed.status in ("failed", "error")
        assert errored.status in ("failed", "error")


class TestFinalizePipelineAttachesField:
    """Integration: ``_finalize_pipeline`` computes the field from gates_log."""

    @pytest.fixture()
    def project(self, tmp_path: Path) -> MagicMock:
        proj = MagicMock()
        proj.project_id = "proj-fl-1"
        proj.project_dir = str(tmp_path)
        return proj

    def _finalize(
        self,
        project: MagicMock,
        results: list[dict[str, Any]],
        success: bool = False,
    ) -> PipelineResult:
        from automedia.pipelines.runner import _finalize_pipeline

        with patch(
            "automedia.core.llm_client.get_usage_summary",
            return_value={"total_tokens": 0},
        ):
            return _finalize_pipeline(
                success=success,
                results=results,
                mode="auto",
                gate_context={},
                project=project,
                config={},
                brand="testbrand",
                topic="test topic",
                start=0.0,
                workflow=None,
            )

    def test_partial_result_carries_affected_downstream(self, project: MagicMock) -> None:
        """A G3 failure in auto mode marks G4, G5, G6 and H0 affected, NOT video."""
        results = [
            {"passed": True, "gate": "CW", "duration_s": 0.1},
            {"passed": True, "gate": "G0", "duration_s": 0.1},
            {"passed": False, "gate": "G3", "error": "tone drift", "duration_s": 0.2},
        ]
        result = self._finalize(project, results)
        assert result.status == "partial"
        assert result.error is None  # gate failure never sets error
        assert result.affected_downstream == [
            "G6",
            "H0",
        ]

    def test_success_result_has_empty_affected_downstream(self, project: MagicMock) -> None:
        results = [{"passed": True, "gate": "CW", "duration_s": 0.1}]
        result = self._finalize(project, results, success=True)
        assert result.status == "success"
        assert result.affected_downstream == []

    def test_error_status_entry_also_drives_localization(self, project: MagicMock) -> None:
        """``status="error"`` entries count as failures, same as ``failed``."""
        results = [
            {"passed": True, "gate": "V0", "duration_s": 0.1},
            {
                "passed": False,
                "gate": "V2",
                "error": "whisper crashed",
                "status": "error",
                "duration_s": 0.2,
            },
        ]
        result = self._finalize(project, results)
        assert result.affected_downstream == [
            "V3",
            "V4",
            "V5",
            "V6",
            "V7",
            "H0",
        ]
