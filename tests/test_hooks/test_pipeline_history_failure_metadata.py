"""``gate:completed`` must carry the failure reason and failed check names (#442)."""

from __future__ import annotations

import json
from pathlib import Path

from automedia.hooks.pipeline_history import PipelineHistoryHook, _read_history


def _completed_meta(project_dir: Path) -> dict[str, object]:
    rows = _read_history(str(project_dir))
    assert rows[-1]["action"] == "G1:completed"
    return json.loads(str(rows[-1]["metadata_json"]))


def test_failure_details_are_recorded(tmp_path: Path) -> None:
    PipelineHistoryHook().after_gate(
        "G1",
        {"project_dir": str(tmp_path), "project_id": "p1"},
        {
            "passed": False,
            "error": None,
            "checks": [
                {"name": "tone", "passed": True, "detail": ""},
                {"name": "overacademic_vocabulary", "passed": False, "detail": "found 1"},
            ],
            "failure_reason": "found 1",
        },
    )

    meta = _completed_meta(tmp_path)
    assert meta["failure_reason"] == "found 1"
    assert meta["failed_checks"] == ["overacademic_vocabulary"]


def test_error_is_the_fallback_reason(tmp_path: Path) -> None:
    PipelineHistoryHook().after_gate(
        "G1",
        {"project_dir": str(tmp_path), "project_id": "p1"},
        {"passed": False, "error": "rewrite failed"},
    )

    meta = _completed_meta(tmp_path)
    assert meta["failure_reason"] == "rewrite failed"
    assert "failed_checks" not in meta
