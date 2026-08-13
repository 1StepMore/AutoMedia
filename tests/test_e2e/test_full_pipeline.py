"""E2E: Full pipeline execution in mock mode.

Verifies that the GateEngine can execute gates in sequence with synthetic
data and ``_mock_results``, producing the expected ``PipelineResult`` for
each pipeline mode.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from automedia.gates.base import _registry
from automedia.pipelines.gate_engine import GateEngine
from automedia.pipelines.runner import (
    _AUTO_GATE_NAMES,
    _QA_ONLY_GATE_NAMES,
    _TEXT_ONLY_GATE_NAMES,
    _VIDEO_ONLY_GATE_NAMES,
)


@pytest.fixture(autouse=True)
def _mock_llm_for_content_writer():
    """ContentWriterGate calls llm_complete; patch it so E2E tests stay offline."""
    with patch(
        "automedia.gates.content_writer.llm_complete",
        return_value="# Mock Article\n\nSynthetic content for testing.",
    ):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_gates(names: list[str]) -> list:
    """Instantiate registered gates by name in order."""
    import automedia.gates  # noqa: F401 — ensure all gates are registered

    return [_registry.get(n)() for n in names]


def _build_mock_results() -> dict[str, dict[str, Any]]:
    """Return a comprehensive ``_mock_results`` dict where every check passes."""
    _p = {"passed": True, "detail": "mock-pass"}
    all_checks = [
        # pre-gate
        "topic_not_charity",
        "topic_not_gov_tool",
        "topic_not_investment",
        "topic_not_finance",
        "topic_not_entertainment",
        "topic_length_valid",
        # G0
        "source_trace",
        "number_verification",
        "timeline",
        "quotes",
        "entities",
        # G1
        "overused_adverbs",
        "hollow_intros",
        "vague_subjects",
        "filler_connectors",
        "long_conjunctions",
        "template_conclusions",
        "overacademic_vocabulary",
        "absolute_assertions",
        "repetitive_structures",
        # G2
        "clarity",
        "tone",
        "so_what",
        "evidence",
        "specificity",
        # G3
        "brand_name_present",
        "cta_present",
        "brand_identity",
        "blocked_words_absent",
        "cta_direction_sync",
        "bridge_sentence",
        # G4
        "title_length",
        "digest_length",
        "no_markdown",
        "cover_exists",
        "tag_count",
        "body_image_count",
        "sensitive_words",
        # G5
        "tag_integrity",
        "no_markdown",
        "tag_count",
        # V0
        "lint_errors",
        "lint_warnings",
        "syntax_valid",
        # V1
        "mid_frame_valid",
        "end_silence_valid",
        "all_entries_passed",
        "red_line_6",
        # V2
        "whisper_transcription",
        "transcription_length",
        "md5_integrity",
        "red_line_7",
        # V3
        "keyword_coverage",
        "source_alignment",
        "no_hallucination",
        # V4
        "voice_id_match",
        "speaking_rate",
        "voice_consistency",
        # V5
        "whisper_vs_srt_diff",
        "srt_not_empty",
        "whisper_not_empty",
        # V6
        "subtitle_region_brightness",
        "subtitle_region_contrast",
        "subtitle_visible",
        "red_line_5",
        # V7
        "file_exists",
        "file_size_valid",
        "md5_verified",
        "whisper_full",
        "format_valid",
        "duration_valid",
        # L1
        "topic_present",
        "content_present",
        "media_paths_valid",
        "platform_valid",
        "version_valid",
        "timestamp_valid",
        # L2
        "archive_status",
        "force_flag",
        "archive_path_exists",
        "archive_metadata_complete",
        "archive_version_valid",
        "output_directory_exists",
        # L3
        "all_platforms_present",
        "no_platform_splitting",
        "material_integrity",
        "cross_platform_consistency",
        "format_completeness",
        "metadata_integrity",
    ]
    return {name: _p for name in all_checks}


def _build_full_context(
    sample_topic: str,
    sample_brand_profile: dict[str, Any],
    mock_results: dict[str, dict[str, Any]] | None = None,
    project_dir: str = "/projects/test_project",
) -> dict[str, Any]:
    """Build a mega-context that satisfies every gate's expected keys."""
    if mock_results is None:
        mock_results = _build_mock_results()
    return {
        # Shared
        "topic": sample_topic,
        "project_dir": project_dir,
        "force_provenance": True,
        "content": (
            "TestBrand delivers AI内容生产 solutions. "
            "立即体验 our platform for free. "
            "Contact us to learn more."
        ),
        "brand_profile": sample_brand_profile,
        "source_data": {
            "url": "https://example.com/ai-trends",
            "published_date": "2025-06-01T00:00:00+00:00",
            "key_numbers": {"market_size": "$150 billion"},
            "entities": ["OpenAI"],
            "quotes": ["AI will transform every industry"],
        },
        "_mock_results": mock_results,
        # G4
        "title": "AI趋势",
        "digest": "AI trends overview",
        "cover_image": "https://example.com/cover.jpg",
        "tags": ["AI", "tech", "trends", "2025", "innovation"],
        "body_images": [
            "<img src='a.jpg'>",
            "<img src='b.jpg'>",
            "<img src='c.jpg'>",
            "<img src='d.jpg'>",
        ],
        # V0
        "lint_result": {"errors": 0, "warnings": 0, "syntax_ok": True},
        # V1
        "entries": [
            {
                "mid_frame_path": f"{project_dir}/frame_{i}.png",
                "end_silence_frame_path": f"{project_dir}/end_{i}.png",
                "qa_passed": True,
                "checked": True,
            }
            for i in range(5)
        ],
        # V2
        "transcription": "Full audio transcription text for testing.",
        "audio_path": f"{project_dir}/test.mp3",
        "expected_md5": "",
        "full_audio": True,
        # V3
        "source_keywords": ["AI", "technology", "trends"],
        "content_keywords": ["AI", "technology", "trends"],
        "source_texts": ["Source 1.", "Source 2.", "Source 3."],
        # V4
        "voice_id": "brand_voice_001",
        "expected_voice_id": "brand_voice_001",
        "speaking_rate": 1.0,
        "segments": [
            {"voice_params": {"pitch": 0, "rate": 1.0}},
            {"voice_params": {"pitch": 0, "rate": 1.0}},
        ],
        # V5
        "whisper_text": "Hello world, this is a test transcription.",
        "srt_text": (
            "1\n00:00:00,000 --> 00:00:02,000\nHello world, this is a test transcription.\n"
        ),
        # V6
        "avg_brightness": 128,
        "contrast": 150,
        "opacity": 1.0,
        "pixel_valid": True,
        # V7
        "required_files": [],
        "file_sizes": {},
        "md5_records": {},
        "whisper_full_audio": True,
        "actual_format": "mp4",
        "expected_format": "mp4",
        "actual_duration": 120.0,
        "expected_duration_min": 60.0,
        "expected_duration_max": 180.0,
        # L1
        "publish_log": {
            "topic": sample_topic,
            "content": "Test article content.",
            "media_paths": [f"{project_dir}/video.mp4"],
            "platform": "wechat",
            "version": "1.0",
            "created_at": "2025-06-01T12:00:00",
        },
        # L2
        "archive_status": "published",
        "force": True,
        "archive_path": f"{project_dir}/archive.zip",
        "archive_metadata": {
            "title": "AI Trends 2025",
            "platform": "wechat",
            "created_at": "2025-06-01T12:00:00",
        },
        "archive_version": "1.0",
        "output_dir": f"{project_dir}/output",
        # L3
        "platforms": ["wechat", "weibo"],
        "expected_platforms": ["wechat", "weibo"],
        "unified_content": "Unified content body for all platforms.",
        "media_files": [],
        "file_paths": [],
        "formats": ["mp4", "txt", "json"],
        "required_formats": ["mp4", "txt", "json"],
        # L4
        "translation_result": {
            "translated_md": "---\nsource_lang: zh\ntarget_lang: en\n---\nTranslated content here."
        },
        "source_lang": "zh",
        "target_lang": "en",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestFullPipeline:
    """Full pipeline execution tests for each mode with mock LLM."""

    def test_pipeline_auto_mode_all_gates(
        self,
        sample_topic: str,
        sample_brand_profile: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """GateEngine runs all 18 gates in auto mode with mock → success."""
        gates = _build_gates(_AUTO_GATE_NAMES)
        engine = GateEngine(gates)
        ctx = _build_full_context(sample_topic, sample_brand_profile, project_dir=str(tmp_path))

        success, results = engine.run(ctx)

        assert success is True, f"Pipeline failed. Results: {results}"
        assert len(results) == len(_AUTO_GATE_NAMES), (
            f"Expected {len(_AUTO_GATE_NAMES)} results, got {len(results)}"
        )
        for i, result in enumerate(results):
            gate_name = _AUTO_GATE_NAMES[i]
            assert result.get("passed") is True, f"Gate {gate_name} failed: {result}"

    def test_pipeline_stops_on_gate_failure(
        self,
        sample_topic: str,
        sample_brand_profile: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """G3 (failure_mode='stop') fails → pipeline stops immediately."""
        mock_results = _build_mock_results()
        # Make G3 BrandCTA fail — brand_name_present check fails
        mock_results["brand_name_present"] = {"passed": False, "detail": "brand missing"}

        gates = _build_gates(_AUTO_GATE_NAMES)
        engine = GateEngine(gates)
        ctx = _build_full_context(
            sample_topic, sample_brand_profile, mock_results, project_dir=str(tmp_path)
        )

        success, results = engine.run(ctx)

        assert success is False, "Pipeline should have failed"
        # G3 is at index 3 in _AUTO_GATE_NAMES (pre-gate=0, G0=1, G1=2, G2=3, G3=4)
        # Pipeline stops at G3, so we should have exactly 5 results (pre-gate + G0-G3)
        g3_index = _AUTO_GATE_NAMES.index("G3")
        assert len(results) == g3_index + 1, (
            f"Expected {g3_index + 1} results (stops at G3), got {len(results)}"
        )
        # G3 result should be the failing one
        assert results[-1]["passed"] is False
        assert results[-1]["gate"] == "G3"

    def test_pipeline_continues_on_rewrite(
        self,
        sample_topic: str,
        sample_brand_profile: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """G1 (failure_mode='retry') fails → pipeline continues to next gate."""
        mock_results = _build_mock_results()
        # Make G1 Humanizer fail — overused_adverbs check fails
        mock_results["overused_adverbs"] = {"passed": False, "detail": "found adverbs"}

        gates = _build_gates(_AUTO_GATE_NAMES)
        engine = GateEngine(gates)
        ctx = _build_full_context(
            sample_topic, sample_brand_profile, mock_results, project_dir=str(tmp_path)
        )

        success, results = engine.run(ctx)

        # Pipeline completes successfully — H0 approves the escalation
        assert success is True
        # All 18 gates should have run (G1 is rewrite mode, doesn't stop)
        assert len(results) == len(_AUTO_GATE_NAMES), (
            f"Expected {len(_AUTO_GATE_NAMES)} results (rewrite continues), got {len(results)}"
        )
        # G1 result should be failing
        g1_index = _AUTO_GATE_NAMES.index("G1")
        assert results[g1_index]["passed"] is False
        assert results[g1_index]["gate"] == "G1"
        # Gates after G1 should still have run
        g2_index = _AUTO_GATE_NAMES.index("G2")
        assert results[g2_index]["passed"] is True

    def test_pipeline_mode_text_only(
        self,
        sample_topic: str,
        sample_brand_profile: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """text_only mode runs only G0-G5 + L1-L3 (9 gates)."""
        gates = _build_gates(_TEXT_ONLY_GATE_NAMES)
        engine = GateEngine(gates)
        ctx = _build_full_context(sample_topic, sample_brand_profile, project_dir=str(tmp_path))

        success, results = engine.run(ctx)

        assert success is True, f"Text-only pipeline failed: {results}"
        assert len(results) == len(_TEXT_ONLY_GATE_NAMES)
        # Verify correct gates ran
        result_gates = [r.get("gate") for r in results]
        for name in _TEXT_ONLY_GATE_NAMES:
            assert name in result_gates, f"Gate {name} missing from text_only results"
        # Verify no video gates ran
        for name in _VIDEO_ONLY_GATE_NAMES:
            if name not in _TEXT_ONLY_GATE_NAMES:
                assert name not in result_gates

    def test_pipeline_mode_video_only(
        self,
        sample_topic: str,
        sample_brand_profile: dict[str, Any],
    ) -> None:
        """video_only mode runs only V0-V7 + L1-L3 (11 gates)."""
        gates = _build_gates(_VIDEO_ONLY_GATE_NAMES)
        engine = GateEngine(gates)
        ctx = _build_full_context(sample_topic, sample_brand_profile)

        success, results = engine.run(ctx)

        assert success is True, f"Video-only pipeline failed: {results}"
        assert len(results) == len(_VIDEO_ONLY_GATE_NAMES)
        result_gates = [r.get("gate") for r in results]
        for name in _VIDEO_ONLY_GATE_NAMES:
            assert name in result_gates, f"Gate {name} missing from video_only results"
        # Verify no text-only gates (G0-G5) ran
        for name in ["G0", "G1", "G2", "G3", "G4", "G5"]:
            if name not in _VIDEO_ONLY_GATE_NAMES:
                assert name not in result_gates

    def test_pipeline_mode_qa_only(
        self,
        sample_topic: str,
        sample_brand_profile: dict[str, Any],
    ) -> None:
        """qa_only mode runs only G0,G2,G3,V1,V6 (5 gates)."""
        gates = _build_gates(_QA_ONLY_GATE_NAMES)
        engine = GateEngine(gates)
        ctx = _build_full_context(sample_topic, sample_brand_profile)

        success, results = engine.run(ctx)

        assert success is True, f"QA-only pipeline failed: {results}"
        assert len(results) == len(_QA_ONLY_GATE_NAMES)
        result_gates = [r.get("gate") for r in results]
        for name in _QA_ONLY_GATE_NAMES:
            assert name in result_gates, f"Gate {name} missing from qa_only results"
        # Verify excluded gates did not run
        for name in ["G1", "G4", "G5", "V0", "V2", "V3", "V4", "V5", "V7"]:
            assert name not in result_gates, f"Gate {name} should not run in qa_only mode"
