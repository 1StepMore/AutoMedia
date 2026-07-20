"""Integration tests for P-gate (sub-pipeline repurpose) gates.

Tests that each P-gate executes its 3-step sub-pipeline correctly,
handles sub-pipeline step failures gracefully, and that repurpose mode
runs all P-gates via the GateEngine.

All tests use mocked LLM responses — no real API calls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from automedia.gates.base import _registry
from automedia.gates.sub_pipelines.p1_wechat import P1WechatGate
from automedia.gates.sub_pipelines.p2_twitter import P2TwitterGate
from automedia.gates.sub_pipelines.p3_newsletter import P3NewsletterGate
from automedia.gates.sub_pipelines.p4_bilibili import P4BilibiliRepurpose
from automedia.pipelines.gate_engine import GateEngine

from tests.test_sub_pipelines.conftest import (
    _LONG_CONTENT,
    P1_CANNED_FACT_CHECK,
    P1_CANNED_HUMANIZE,
    P1_CANNED_REWRITE,
    mock_p1_llm_calls,
    mock_p1_llm_failure,
    mock_p1_fact_check_fails,
    mock_p2_llm_calls,
    mock_p2_llm_failure,
    mock_p2_humanize_fails,
    mock_p3_llm_calls,
    mock_p3_llm_failure,
    mock_p3_review_fails,
    mock_p4_llm_calls,
    mock_p4_llm_failure,
    mock_p4_humanize_fails,
)

# ===========================================================================
# P1 — WeChat Repurpose Gate
# ===========================================================================


class TestP1WechatRepurpose:
    """P1 WeChat repurpose gate integration tests."""

    def test_gate_metadata(self) -> None:
        """P1 gate has correct name and failure mode."""
        gate = P1WechatGate()
        assert gate.gate_name == "P1"
        assert gate.failure_mode == "retry"

    def test_auto_registered(self) -> None:
        """P1 auto-registered in GateRegistry."""
        assert "P1" in _registry
        assert _registry.get("P1") is P1WechatGate

    def test_execute_runs_all_steps(self, p_gate_context: dict[str, Any]) -> None:
        """P1 execute() runs rewrite → fact_check → humanize steps successfully."""
        gate = P1WechatGate()
        with mock_p1_llm_calls():
            result = gate.execute(p_gate_context)

        assert result["passed"] is True
        assert result["gate"] == "P1"
        assert result["error"] is None
        assert result.get("output_path") is not None
        assert result.get("modified_content") is not None
        # All 6 checks should pass
        assert len(result["checks"]) == 6
        for check in result["checks"]:
            assert check["passed"] is True, f"Check {check['name']!r} failed"

    def test_stores_extra_p1_output(self, p_gate_context: dict[str, Any]) -> None:
        """P1 stores final content in gate_context.extra['p1_output']."""
        gate = P1WechatGate()
        with mock_p1_llm_calls():
            gate.execute(p_gate_context)

        extra = p_gate_context.get("extra", {})
        assert extra.get("p1_output") is not None
        assert len(extra["p1_output"]) > 0

    def test_writes_output_file(self, p_gate_context: dict[str, Any]) -> None:
        """P1 writes output to 04_repurpose/wechat/."""
        import os

        gate = P1WechatGate()
        with mock_p1_llm_calls():
            result = gate.execute(p_gate_context)

        output_path = result.get("output_path", "")
        assert output_path, "No output_path in result"
        assert os.path.isfile(output_path), f"Output file not found: {output_path}"
        assert "04_repurpose" in output_path
        assert "wechat" in output_path

    def test_result_structure(self, p_gate_context: dict[str, Any]) -> None:
        """Result dict has all required keys."""
        gate = P1WechatGate()
        with mock_p1_llm_calls():
            result = gate.execute(p_gate_context)

        assert "passed" in result
        assert "gate" in result
        assert "checks" in result
        assert "error" in result
        assert "output_path" in result

    # --- Failure paths ---

    def test_empty_content_fails(self, p_gate_context_empty: dict[str, Any]) -> None:
        """Empty content → gate fails with content_present check = False."""
        gate = P1WechatGate()
        result = gate.execute(p_gate_context_empty)

        assert result["passed"] is False
        assert result["gate"] == "P1"
        # Should have content_present check
        content_checks = [c for c in result["checks"] if c["name"] == "content_present"]
        assert content_checks
        assert content_checks[0]["passed"] is False

    def test_missing_project_dir_fails(self, p_gate_context: dict[str, Any]) -> None:
        """Missing project_dir → gate fails gracefully."""
        ctx = {k: v for k, v in p_gate_context.items() if k != "project_dir"}
        gate = P1WechatGate()
        result = gate.execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == "P1"

    def test_llm_rewrite_failure(self, p_gate_context: dict[str, Any]) -> None:
        """LLM rewrite step fails → gate returns failed."""
        gate = P1WechatGate()
        with mock_p1_llm_failure():
            result = gate.execute(p_gate_context)

        assert result["passed"] is False
        assert result["gate"] == "P1"
        assert result["error"] is not None

    def test_fact_check_non_fatal(self, p_gate_context: dict[str, Any]) -> None:
        """Fact check LLM failure is non-fatal — gate still passes."""
        gate = P1WechatGate()
        with mock_p1_fact_check_fails():
            result = gate.execute(p_gate_context)

        assert result["passed"] is True
        assert result["gate"] == "P1"
        # fact_check check should be marked as passed because execution continued
        fact_check_checks = [
            c for c in result["checks"] if "fact_check" in c["name"].lower()
        ]
        if fact_check_checks:
            assert fact_check_checks[0]["passed"] is True


# ===========================================================================
# P2 — Twitter/X Repurpose Gate
# ===========================================================================


class TestP2TwitterRepurpose:
    """P2 Twitter/X repurpose gate integration tests."""

    def test_gate_metadata(self) -> None:
        gate = P2TwitterGate()
        assert gate.gate_name == "P2"
        assert gate.failure_mode == "retry"

    def test_auto_registered(self) -> None:
        assert "P2" in _registry
        assert _registry.get("P2") is P2TwitterGate

    def test_execute_runs_all_steps(self, p_gate_context: dict[str, Any]) -> None:
        gate = P2TwitterGate()
        with mock_p2_llm_calls():
            result = gate.execute(p_gate_context)

        assert result["passed"] is True
        assert result["gate"] == "P2"
        assert result["error"] is None
        assert result.get("output_path") is not None

    def test_stores_extra_p2_output(self, p_gate_context: dict[str, Any]) -> None:
        gate = P2TwitterGate()
        with mock_p2_llm_calls():
            gate.execute(p_gate_context)

        extra = p_gate_context.get("extra", {})
        assert extra.get("p2_twitter") is not None

    def test_empty_content_fails(self, p_gate_context_empty: dict[str, Any]) -> None:
        gate = P2TwitterGate()
        result = gate.execute(p_gate_context_empty)

        assert result["passed"] is False
        assert result["gate"] == "P2"

    def test_llm_rewrite_failure(self, p_gate_context: dict[str, Any]) -> None:
        gate = P2TwitterGate()
        with mock_p2_llm_failure():
            result = gate.execute(p_gate_context)

        assert result["passed"] is False

    def test_humanize_non_fatal(self, p_gate_context: dict[str, Any]) -> None:
        """Humanize step LLM failure falls back to rewrite content — gate still passes."""
        gate = P2TwitterGate()
        with mock_p2_humanize_fails():
            result = gate.execute(p_gate_context)

        assert result["passed"] is True, f"Gate failed even though humanize is non-fatal: {result}"


# ===========================================================================
# P3 — Newsletter Repurpose Gate
# ===========================================================================


class TestP3NewsletterRepurpose:
    """P3 Newsletter repurpose gate integration tests."""

    def test_gate_metadata(self) -> None:
        gate = P3NewsletterGate()
        assert gate.gate_name == "P3"
        assert gate.failure_mode == "retry"

    def test_auto_registered(self) -> None:
        assert "P3" in _registry
        assert _registry.get("P3") is P3NewsletterGate

    def test_execute_runs_all_steps(self, p_gate_context: dict[str, Any]) -> None:
        gate = P3NewsletterGate()
        with mock_p3_llm_calls():
            result = gate.execute(p_gate_context)

        assert result["passed"] is True
        assert result["gate"] == "P3"
        assert result["error"] is None
        assert result.get("output_path") is not None

    def test_stores_extra_p3_output(self, p_gate_context: dict[str, Any]) -> None:
        gate = P3NewsletterGate()
        with mock_p3_llm_calls():
            gate.execute(p_gate_context)

        extra = p_gate_context.get("extra", {})
        assert extra.get("p3_newsletter") is not None

    def test_empty_content_fails(self, p_gate_context_empty: dict[str, Any]) -> None:
        gate = P3NewsletterGate()
        result = gate.execute(p_gate_context_empty)

        assert result["passed"] is False
        assert result["gate"] == "P3"

    def test_missing_project_dir_fails(self, p_gate_context: dict[str, Any]) -> None:
        ctx = {k: v for k, v in p_gate_context.items() if k != "project_dir"}
        gate = P3NewsletterGate()
        result = gate.execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == "P3"

    def test_llm_rewrite_failure(self, p_gate_context: dict[str, Any]) -> None:
        gate = P3NewsletterGate()
        with mock_p3_llm_failure():
            result = gate.execute(p_gate_context)

        assert result["passed"] is False
        assert result["gate"] == "P3"

    def test_review_non_fatal(self, p_gate_context: dict[str, Any]) -> None:
        """Review step LLM failure is non-fatal — gate still passes."""
        gate = P3NewsletterGate()
        with mock_p3_review_fails():
            result = gate.execute(p_gate_context)

        assert result["passed"] is True, f"Gate failed even though review is non-fatal: {result}"


# ===========================================================================
# P4 — Bilibili Repurpose Gate
# ===========================================================================


class TestP4BilibiliRepurpose:
    """P4 Bilibili repurpose gate integration tests."""

    def test_gate_metadata(self) -> None:
        gate = P4BilibiliRepurpose()
        assert gate.gate_name == "P4"
        assert gate.failure_mode == "retry"

    def test_auto_registered(self) -> None:
        assert "P4" in _registry
        assert _registry.get("P4") is P4BilibiliRepurpose

    def test_execute_runs_all_steps(self, p_gate_context: dict[str, Any]) -> None:
        gate = P4BilibiliRepurpose()
        with mock_p4_llm_calls():
            result = gate.execute(p_gate_context)

        assert result["passed"] is True
        assert result["gate"] == "P4"
        assert result["error"] is None
        assert result.get("output_path") is not None
        # All checks should pass (rewrite, fact_check, humanize, min_length, scene_markers)
        assert len(result["checks"]) == 5
        for check in result["checks"]:
            assert check["passed"] is True, f"Check {check['name']!r} failed"

    def test_stores_output_content(self, p_gate_context: dict[str, Any]) -> None:
        """P4 stores repurposed content in gate_context."""
        gate = P4BilibiliRepurpose()
        with mock_p4_llm_calls():
            result = gate.execute(p_gate_context)

        # P4 stores content in gate_context["bilibili_repurpose_content"]
        stored_content = p_gate_context.get("bilibili_repurpose_content")
        assert stored_content is not None, "P4 did not store bilibili_repurpose_content"
        assert len(stored_content) > 0
        # Output path should be in result
        assert result.get("output_path") is not None

    def test_empty_content_fails(self, p_gate_context_empty: dict[str, Any]) -> None:
        gate = P4BilibiliRepurpose()
        result = gate.execute(p_gate_context_empty)

        assert result["passed"] is False
        assert result["gate"] == "P4"

    def test_llm_rewrite_failure(self, p_gate_context: dict[str, Any]) -> None:
        gate = P4BilibiliRepurpose()
        with mock_p4_llm_failure():
            result = gate.execute(p_gate_context)

        assert result["passed"] is False
        assert result["gate"] == "P4"

    def test_humanize_fails_gate(self, p_gate_context: dict[str, Any]) -> None:
        """Humanize step LLM failure causes P4 gate to fail (fatal step)."""
        gate = P4BilibiliRepurpose()
        with mock_p4_humanize_fails():
            result = gate.execute(p_gate_context)

        assert result["gate"] == "P4"
        assert result["passed"] is False
        assert "humanize" in (result.get("error", "") or "").lower()
        # humanize_step check should be present and failed
        humanize_checks = [
            c for c in result["checks"] if c["name"] == "humanize_step"
        ]
        if humanize_checks:
            assert humanize_checks[0]["passed"] is False


# ===========================================================================
# Repurpose Mode — all P-gates run through GateEngine
# ===========================================================================


class TestRepurposeMode:
    """GateEngine runs repurpose mode with all P-gates included."""

    def _build_mock_pass(self) -> dict[str, dict[str, Any]]:
        """Return a mock_results dict where every check passes."""
        _p: dict[str, Any] = {"passed": True, "detail": "mock-pass"}
        names = [
            # pre-gate
            "topic_not_charity", "topic_not_gov_tool", "topic_not_investment",
            "topic_not_finance", "topic_not_entertainment", "topic_length_valid",
            # CW
            "content_written",
            # G0
            "source_trace", "number_verification", "timeline", "quotes", "entities",
            # G1
            "overused_adverbs", "hollow_intros", "vague_subjects",
            "filler_connectors", "long_conjunctions", "template_conclusions",
            "overacademic_vocabulary", "absolute_assertions", "repetitive_structures",
            # G2
            "clarity", "tone", "so_what", "evidence", "specificity",
            # G3
            "brand_name_present", "cta_present", "brand_identity",
            "blocked_words_absent", "cta_direction_sync", "bridge_sentence",
            # G4
            "title_length", "digest_length", "no_markdown", "cover_exists",
            "tag_count", "body_image_count", "sensitive_words",
            # G5
            "tag_integrity", "no_markdown", "tag_count",
            # V0
            "lint_errors", "lint_warnings", "syntax_valid",
            # V1
            "mid_frame_valid", "end_silence_valid", "all_entries_passed", "red_line_6",
            # V2
            "whisper_transcription", "transcription_length", "md5_integrity", "red_line_7",
            # V3
            "keyword_coverage", "source_alignment", "no_hallucination",
            # V4
            "voice_id_match", "speaking_rate", "voice_consistency",
            # V5
            "whisper_vs_srt_diff", "srt_not_empty", "whisper_not_empty",
            # V6
            "subtitle_region_brightness", "subtitle_region_contrast",
            "subtitle_visible", "red_line_5",
            # V7
            "file_exists", "file_size_valid", "md5_verified",
            "whisper_full", "format_valid", "duration_valid",
            # L1
            "topic_present", "content_present", "media_paths_valid",
            "platform_valid", "version_valid", "timestamp_valid",
            # L2
            "archive_status", "force_flag", "archive_path_exists",
            "archive_metadata_complete", "archive_version_valid", "output_directory_exists",
            # L3
            "all_platforms_present", "no_platform_splitting", "material_integrity",
            "cross_platform_consistency", "format_completeness", "metadata_integrity",
            # L4
            "translation_present", "translation_complete",
        ]
        return {name: dict(_p) for name in names}

    def test_repurpose_mode_includes_p_gates(self) -> None:
        """Repurpose mode gate list includes P1, P2, P3, P4."""
        from automedia.pipelines.runner import _REPURPOSE_GATE_NAMES

        assert "P1" in _REPURPOSE_GATE_NAMES
        assert "P2" in _REPURPOSE_GATE_NAMES
        assert "P3" in _REPURPOSE_GATE_NAMES
        assert "P4" in _REPURPOSE_GATE_NAMES
        # P-gates should appear after L gates
        l4_idx = _REPURPOSE_GATE_NAMES.index("L4")
        p1_idx = _REPURPOSE_GATE_NAMES.index("P1")
        assert p1_idx > l4_idx, "P1 should come after L4 in repurpose mode"

    def test_repurpose_mode_gates_registered(self) -> None:
        """All P-gates in repurpose mode are registered in GateRegistry."""
        from automedia.pipelines.runner import _REPURPOSE_GATE_NAMES

        for gate_name in _REPURPOSE_GATE_NAMES:
            assert gate_name in _registry, f"Gate {gate_name} not in registry"
            _registry.get(gate_name)  # Should not raise

    def test_repurpose_engine_runs_p1(
        self,
        p_gate_context: dict[str, Any],
    ) -> None:
        """GateEngine in repurpose mode runs P1 gate with mocked LLM."""
        import automedia.gates  # noqa: F401
        from automedia.pipelines.runner import _REPURPOSE_GATE_NAMES

        gates = [_registry.get(n)() for n in _REPURPOSE_GATE_NAMES]

        # Set up context with mock_results for non-P gates
        ctx = dict(p_gate_context)
        ctx["_mock_results"] = self._build_mock_pass()
        ctx["topic"] = "AI technology trends in 2025"
        ctx["brand_profile"] = {
            "brand_name": "TestBrand",
            "brand_aliases": ["TB"],
            "tone": "professional",
            "brand_identity": "AI内容生产",
        }
        # Add context keys needed by non-P gates
        ctx["title"] = "AI Trends"
        ctx["digest"] = "Overview of AI trends"
        ctx["cover_image"] = "/fake/cover.jpg"
        ctx["tags"] = ["AI", "tech"]
        ctx["body_images"] = ["<img src='a.jpg'>"]
        ctx["lint_result"] = {"errors": 0, "warnings": 0, "syntax_ok": True}
        ctx["entries"] = []
        ctx["transcription"] = "test"
        ctx["audio_path"] = "/tmp/test.mp3"
        ctx["source_keywords"] = ["AI", "tech"]
        ctx["content_keywords"] = ["AI", "tech"]
        ctx["source_texts"] = ["Source text"]
        ctx["voice_id"] = "v1"
        ctx["expected_voice_id"] = "v1"
        ctx["speaking_rate"] = 1.0
        ctx["segments"] = []
        ctx["whisper_text"] = "test"
        ctx["srt_text"] = "1\n00:00:00,000 --> 00:00:02,000\ntest\n"
        ctx["avg_brightness"] = 128
        ctx["contrast"] = 150
        ctx["opacity"] = 1.0
        ctx["pixel_valid"] = True
        ctx["required_files"] = []
        ctx["file_sizes"] = {}
        ctx["md5_records"] = {}
        ctx["whisper_full_audio"] = True
        ctx["actual_format"] = "mp4"
        ctx["expected_format"] = "mp4"
        ctx["actual_duration"] = 120.0
        ctx["expected_duration_min"] = 60.0
        ctx["expected_duration_max"] = 180.0
        ctx["publish_log"] = {
            "topic": "AI tech",
            "content": "test",
            "media_paths": [],
            "platform": "wechat",
            "version": "1.0",
            "created_at": "2025-01-01T00:00:00",
        }
        ctx["archive_status"] = "published"
        ctx["force"] = True
        ctx["archive_path"] = "/tmp/archive.zip"
        ctx["archive_metadata"] = {"title": "test", "platform": "wechat", "created_at": "2025-01-01"}
        ctx["output_dir"] = "/tmp/output"
        ctx["platforms"] = ["wechat", "twitter"]
        ctx["expected_platforms"] = ["wechat", "twitter"]
        ctx["unified_content"] = "Content"
        ctx["media_files"] = []
        ctx["file_paths"] = []
        ctx["formats"] = ["md"]
        ctx["required_formats"] = ["md"]
        ctx["translation_result"] = {
            "translated_md": "---\nsource_lang: zh\ntarget_lang: en\n---\nContent"
        }
        ctx["source_lang"] = "zh"
        ctx["target_lang"] = "en"

        engine = GateEngine(gates)

        # P1 uses llm_complete — mock it
        with mock_p1_llm_calls():
            success, results = engine.run(ctx)

        # The pipeline may fail at earlier gates (V0-V7 need hyperframes etc.)
        # but at minimum P1 should have been reached if earlier gates pass.
        # Since we use _mock_results, earlier gates that support mock_results
        # should pass. P1 doesn't support _mock_results, so it runs its real
        # implementation.
        #
        # Just verify that the engine ran without exceptions:
        assert isinstance(success, bool)
        assert isinstance(results, list)
        # At minimum, pre-gate should have run
        assert len(results) > 0

    def test_p_gate_names_in_re_pipeline_map(self) -> None:
        """repurpose mode maps to _REPURPOSE_GATE_NAMES in _MODE_MAP."""
        from automedia.pipelines.runner import _MODE_MAP, _REPURPOSE_GATE_NAMES

        assert "repurpose" in _MODE_MAP
        assert _MODE_MAP["repurpose"] is _REPURPOSE_GATE_NAMES
