"""E2E: Synthetic fixtures validation.

Verifies that the synthetic fixtures under ``tests/fixtures/synth/`` can be
loaded and used to run gates through ``GateEngine``.  This ensures the
fixture data is correctly shaped, importable, and functional end-to-end.

All data is synthetic — zero production project data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from automedia.gates.base import BaseGate, _registry
from automedia.pipelines.gate_engine import GateEngine
from tests.fixtures.synth.gate_contexts import (
    build_all_pass_mock,
    build_brand_cta_context,
    build_copy_review_context,
    build_full_pipeline_context,
    build_humanizer_context,
    build_single_fail_mock,
    build_topic_selection_context,
    load_brand_profile,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def synth_brand_profile() -> dict[str, Any]:
    """Load the synthetic brand profile from YAML.

    Maps YAML keys to the format expected by gates (``brand_aliases``,
    ``tone``).
    """
    raw = load_brand_profile("testbrand")
    return _normalize_brand_profile(raw)


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


def _normalize_brand_profile(raw: dict[str, Any]) -> dict[str, Any]:
    """Map YAML brand profile keys to the format gates expect.

    YAML uses ``aliases`` and ``tone_guidelines``; gates expect
    ``brand_aliases`` and ``tone``.
    """
    profile = dict(raw)
    if "aliases" in profile and "brand_aliases" not in profile:
        profile["brand_aliases"] = profile.pop("aliases")
    if "tone_guidelines" in profile and "tone" not in profile:
        profile["tone"] = profile.pop("tone_guidelines")
    return profile


def _build_gates(names: list[str]) -> list[BaseGate]:
    """Instantiate registered gates by name in order."""
    import automedia.gates  # noqa: F401 — ensure all gates are registered

    return [_registry.get(n)() for n in names]


# ---------------------------------------------------------------------------
# Tests — Fixture Loading & Shape Validation
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestSynthFixtureLoading:
    """Validate that synthetic fixtures load correctly and are well-shaped."""

    def test_brand_profile_yaml_loads(self) -> None:
        """load_brand_profile('testbrand') returns a non-empty dict."""
        raw = load_brand_profile("testbrand")
        assert isinstance(raw, dict)
        assert len(raw) > 0

    def test_brand_profile_has_required_keys(self) -> None:
        """Raw YAML brand profile contains all required keys."""
        raw = load_brand_profile("testbrand")
        assert "brand_name" in raw, "missing brand_name"
        assert "brand_identity" in raw, "missing brand_identity"
        assert "blocked_words" in raw, "missing blocked_words"
        # YAML uses 'aliases' (not 'brand_aliases')
        assert "aliases" in raw, "missing aliases"

    def test_brand_profile_values_correctly_typed(self) -> None:
        """Brand profile values have correct types."""
        raw = load_brand_profile("testbrand")
        assert isinstance(raw["brand_name"], str)
        assert isinstance(raw["aliases"], list)
        assert isinstance(raw["brand_identity"], str)
        assert isinstance(raw["blocked_words"], list)
        assert isinstance(raw["cta_principles"], list)

    def test_brand_profile_normalization(self, synth_brand_profile: dict[str, Any]) -> None:
        """Normalized profile maps YAML keys to gate-expected keys."""
        assert "brand_aliases" in synth_brand_profile
        assert "tone" in synth_brand_profile
        assert synth_brand_profile["brand_aliases"] == ["TB", "Test B"]
        assert synth_brand_profile["brand_name"] == "TestBrand"

    def test_all_pass_mock_covers_all_checks(self) -> None:
        """build_all_pass_mock() returns entries for every gate check."""
        mock = build_all_pass_mock()
        assert len(mock) > 50, f"Expected 50+ check names, got {len(mock)}"
        for name, result in mock.items():
            assert result["passed"] is True, f"Check {name!r} should pass"

    def test_single_fail_mock_marks_one_check(self) -> None:
        """build_single_fail_mock() fails exactly one check."""
        mock = build_single_fail_mock("brand_name_present")
        assert mock["brand_name_present"]["passed"] is False
        # All other checks should still pass
        others = {k: v for k, v in mock.items() if k != "brand_name_present"}
        for name, result in others.items():
            assert result["passed"] is True, f"Check {name!r} should pass but failed"


# ---------------------------------------------------------------------------
# Tests — Individual Gate Context Builders
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestSynthGateContexts:
    """Validate that gate context builders produce correctly shaped dicts."""

    def test_humanizer_context_shape(self) -> None:
        """build_humanizer_context returns a dict with required keys."""
        ctx = build_humanizer_context()
        assert "content" in ctx
        assert "_mock_results" in ctx
        assert isinstance(ctx["content"], str)
        assert len(ctx["content"]) > 0

    def test_brand_cta_context_shape(self) -> None:
        """build_brand_cta_context returns a dict with required keys."""
        ctx = build_brand_cta_context()
        assert "content" in ctx
        assert "brand_profile" in ctx
        assert "_mock_results" in ctx
        assert "brand_name" in ctx["brand_profile"]

    def test_copy_review_context_shape(self) -> None:
        """build_copy_review_context returns a dict with required keys."""
        ctx = build_copy_review_context()
        assert "content" in ctx
        assert "brand_profile" in ctx
        assert "_mock_results" in ctx

    def test_topic_selection_context_shape(self) -> None:
        """build_topic_selection_context returns a dict with required keys."""
        ctx = build_topic_selection_context()
        assert "topic" in ctx
        assert "_mock_results" in ctx

    def test_full_pipeline_context_has_all_gate_keys(self) -> None:
        """build_full_pipeline_context includes keys for every gate."""
        ctx = build_full_pipeline_context()
        # Spot-check keys needed by specific gates
        required_keys = [
            "topic",
            "content",
            "brand_profile",
            "_mock_results",
            "title",
            "digest",
            "tags",  # G4
            "lint_result",  # V0
            "entries",  # V1
            "transcription",
            "audio_path",  # V2
            "voice_id",
            "expected_voice_id",  # V4
            "whisper_text",
            "srt_text",  # V5
            "avg_brightness",
            "contrast",  # V6
            "publish_log",  # L1
            "archive_status",
            "force",  # L2
            "platforms",
            "expected_platforms",  # L3
        ]
        for key in required_keys:
            assert key in ctx, f"Missing key {key!r} in full pipeline context"


# ---------------------------------------------------------------------------
# Tests — Gate Execution via GateEngine
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestSynthGateExecution:
    """Run individual gates through GateEngine using synthetic fixtures."""

    def test_humanizer_gate_passes(self) -> None:
        """G1 Humanizer passes with all-pass mock results."""
        gates = _build_gates(["G1"])
        engine = GateEngine(gates)
        ctx = build_humanizer_context()

        success, results = engine.run(ctx)

        assert success is True, f"Humanizer failed: {results}"
        assert len(results) == 1
        assert results[0]["passed"] is True
        assert results[0]["gate"] == "G1"

    def test_brand_cta_gate_passes(self) -> None:
        """G3 BrandCTA passes with all-pass mock results."""
        gates = _build_gates(["G3"])
        engine = GateEngine(gates)
        ctx = build_brand_cta_context()

        success, results = engine.run(ctx)

        assert success is True, f"BrandCTA failed: {results}"
        assert len(results) == 1
        assert results[0]["passed"] is True
        assert results[0]["gate"] == "G3"

    def test_brand_cta_gate_fails_on_missing_brand(self) -> None:
        """G3 BrandCTA stops pipeline when brand_name_present fails."""
        fail_mock = build_single_fail_mock("brand_name_present")
        ctx = build_brand_cta_context(mock_results=fail_mock)

        gates = _build_gates(["G3"])
        engine = GateEngine(gates)

        success, results = engine.run(ctx)

        assert success is False
        assert results[0]["passed"] is False
        assert results[0]["gate"] == "G3"

    def test_copy_review_gate_passes(self) -> None:
        """G2 CopyReview passes with all-pass mock results."""
        gates = _build_gates(["G2"])
        engine = GateEngine(gates)
        ctx = build_copy_review_context()

        success, results = engine.run(ctx)

        assert success is True, f"CopyReview failed: {results}"
        assert results[0]["passed"] is True

    def test_topic_selection_gate_passes(self) -> None:
        """pre-gate TopicSelection passes with safe topic."""
        gates = _build_gates(["pre-gate"])
        engine = GateEngine(gates)
        ctx = build_topic_selection_context()

        success, results = engine.run(ctx)

        assert success is True, f"TopicSelection failed: {results}"
        assert results[0]["passed"] is True

    def test_multi_gate_sequence_passes(self) -> None:
        """G1 → G2 → G3 sequence passes with all-pass mocks."""
        gates = _build_gates(["G1", "G2", "G3"])
        engine = GateEngine(gates)

        # Build a merged context that satisfies all three gates
        ctx: dict[str, Any] = {
            **build_humanizer_context(),
            **build_brand_cta_context(),
        }
        # Ensure all check names are covered
        ctx["_mock_results"] = build_all_pass_mock()

        success, results = engine.run(ctx)

        assert success is True, f"Multi-gate sequence failed: {results}"
        assert len(results) == 3
        for i, name in enumerate(["G1", "G2", "G3"]):
            assert results[i]["gate"] == name
            assert results[i]["passed"] is True


# ---------------------------------------------------------------------------
# Tests — Full Pipeline with Synth Fixtures
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestSynthFullPipeline:
    """Run the full pipeline using the synthetic mega-context builder."""

    def test_full_pipeline_auto_mode(
        self,
        tmp_path: Path,
    ) -> None:
        """GateEngine runs all 18 gates in auto mode with synth fixtures."""
        from automedia.pipelines.runner import _AUTO_GATE_NAMES

        gates = _build_gates(_AUTO_GATE_NAMES)
        engine = GateEngine(gates)
        ctx = build_full_pipeline_context(project_dir=str(tmp_path))

        success, results = engine.run(ctx)

        assert success is True, f"Full pipeline failed: {results}"
        assert len(results) == len(_AUTO_GATE_NAMES)
        for i, result in enumerate(results):
            gate_name = _AUTO_GATE_NAMES[i]
            assert result.get("passed") is True, f"Gate {gate_name} failed: {result}"

    def test_full_pipeline_text_only_mode(
        self,
        tmp_path: Path,
    ) -> None:
        """text_only mode runs G0-G5 + L1-L3 with synth fixtures."""
        from automedia.pipelines.runner import _TEXT_ONLY_GATE_NAMES

        gates = _build_gates(_TEXT_ONLY_GATE_NAMES)
        engine = GateEngine(gates)
        ctx = build_full_pipeline_context(project_dir=str(tmp_path))

        success, results = engine.run(ctx)

        assert success is True, f"Text-only pipeline failed: {results}"
        assert len(results) == len(_TEXT_ONLY_GATE_NAMES)

    def test_full_pipeline_stops_on_g3_failure(
        self,
        tmp_path: Path,
    ) -> None:
        """Pipeline stops at G3 when brand_name_present check fails."""
        from automedia.pipelines.runner import _AUTO_GATE_NAMES

        fail_mock = build_single_fail_mock("brand_name_present")
        ctx = build_full_pipeline_context(mock_results=fail_mock, project_dir=str(tmp_path))

        gates = _build_gates(_AUTO_GATE_NAMES)
        engine = GateEngine(gates)

        success, results = engine.run(ctx)

        assert success is False
        # G3 is a stop gate — pipeline halts at G3
        g3_index = _AUTO_GATE_NAMES.index("G3")
        assert len(results) == g3_index + 1
        assert results[-1]["gate"] == "G3"
        assert results[-1]["passed"] is False

    def test_full_pipeline_continues_on_g1_rewrite(
        self,
        tmp_path: Path,
    ) -> None:
        """G1 failure (rewrite mode) doesn't stop the pipeline."""
        from automedia.pipelines.runner import _AUTO_GATE_NAMES

        fail_mock = build_single_fail_mock("overused_adverbs")
        ctx = build_full_pipeline_context(mock_results=fail_mock, project_dir=str(tmp_path))

        gates = _build_gates(_AUTO_GATE_NAMES)
        engine = GateEngine(gates)

        success, results = engine.run(ctx)

        # Pipeline continues (G1 is rewrite mode) but overall success is False
        assert success is False
        assert len(results) == len(_AUTO_GATE_NAMES)
        g1_index = _AUTO_GATE_NAMES.index("G1")
        assert results[g1_index]["passed"] is False
        # Gates after G1 still ran
        g2_index = _AUTO_GATE_NAMES.index("G2")
        assert results[g2_index]["passed"] is True
