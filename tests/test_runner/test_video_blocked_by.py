"""Job-level ``blocked_by`` must surface a missing video (#476).

A run that owed a video but produced none used to end ``awaiting_review``
with the failure visible only in gate-report notes — the UI presented a
clean review-parked run with no mp4 behind it.  ``PipelineResult.blocked_by``
carries ``video_render_failed: <reason>`` on the result object itself, in
both the parked and the partial shapes.
"""

from __future__ import annotations

from typing import Any

import pytest

from automedia.pipelines.runner import _finalize_pipeline, _video_render_failure_note


def _gate_context(**extra: Any) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "content": "本平台是菲律宾外卖平台，覆盖全境。立即咨询。",
        "brand_profile": {
            "brand_name": "壹目贯维",
            "aliases": [],
            "brand_identity": "菲律宾外卖平台",
            "blocked_words": [],
        },
        "mode": "short-video",
    }
    ctx.update(extra)
    return ctx


class _FakeProject:
    project_id = "proj-476"
    project_dir = ""


def _fake_result(passed: bool) -> dict[str, Any]:
    """Raw gate-result dict shaped like GateEngine output."""
    return {"gate": "H0", "passed": passed, "checks": [], "error": None}


@pytest.fixture()
def _mute_io(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Keep finalize from touching disk or md5 trackers."""
    monkeypatch.setattr("automedia.pipelines.runner._produce_media_assets", lambda ctx: None)
    monkeypatch.setattr("automedia.pipelines.runner._record_gate_md5s", lambda *a, **k: None)
    monkeypatch.setattr("automedia.pipelines.runner._write_run_gate_report", lambda *a, **k: None)


def _run_finalize(gate_context: dict[str, Any], *, awaiting_review: bool) -> Any:
    results = [_fake_result(passed=True)]
    return _finalize_pipeline(
        True,
        results,
        "short-video",
        gate_context,
        _FakeProject(),  # type: ignore[arg-type]
        {},
        "yimuguanwei",
        "topic",
        start=0.0,
        workflow=None,
        awaiting_review=awaiting_review,
        owes_video=True,
    )


class TestBlockedByVideoRenderFailed:
    def test_parked_run_reports_blocker(self, _mute_io) -> None:
        """awaiting_review + owed-but-missing video → blocked_by names it (#476)."""
        ctx = _gate_context(
            _media_stage_notes=[
                {
                    "event": "video_render_failed",
                    "error": "Engine 'ffmpeg' not found for modality 'video'",
                },
            ],
        )
        result = _run_finalize(ctx, awaiting_review=True)
        assert result.status == "awaiting_review"
        assert result.blocked_by
        assert result.blocked_by[0].startswith("video_render_failed:")
        assert "ffmpeg" in result.blocked_by[0]

    def test_partial_run_reports_blocker(self, _mute_io) -> None:
        ctx = _gate_context(
            _media_stage_notes=[
                {"event": "video_render_failed", "error": "renderer exploded"},
            ],
        )
        result = _run_finalize(ctx, awaiting_review=False)
        assert result.status == "partial"
        assert any("video_render_failed" in b for b in result.blocked_by)

    def test_video_produced_means_no_blocker(self, _mute_io) -> None:
        ctx = _gate_context(video_path="03_video/output.mp4")
        result = _run_finalize(ctx, awaiting_review=False)
        assert result.blocked_by == []

    def test_failure_note_extraction(self) -> None:
        assert (
            _video_render_failure_note(
                {"_media_stage_notes": [{"event": "video_render_failed", "error": "boom"}]}
            )
            == "boom"
        )
        # No note at all → still an honest generic reason
        assert _video_render_failure_note({}) == "no video artifact was produced"
