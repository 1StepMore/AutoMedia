"""E2E: Decision Layer Scale Mode — full chain execution.

Verifies that ``DecisionOrchestrator.run_scale_mode()`` produces all
required artifacts and that it can coexist with Build mode (different
results from the same orchestrator instance).

All agents are self-contained and deterministic — no external services
or LLM calls are required.

PRD-3 W1 Decision Layer: T22 — E2E Scale Mode Mock Full Chain.
"""

from __future__ import annotations

import pytest

from automedia.decision.base import DecisionArtifact
from automedia.decision.orchestrator import DecisionOrchestrator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_artifact_types(
    artifacts: list[DecisionArtifact],
    expected_types: set[str],
) -> None:
    """Assert that *artifacts* covers exactly the *expected_types*.

    Each type must appear at least once.  Extra types are allowed.
    """
    actual_types = {a.artifact_type for a in artifacts}
    missing = expected_types - actual_types
    assert not missing, (
        f"Missing artifact type(s): {sorted(missing)}. Actual types: {sorted(actual_types)}"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestDecisionScaleMode:
    """E2E tests for Decision Layer Scale Mode.

    Every test creates a fresh ``DecisionOrchestrator`` instance and
    runs ``run_scale_mode()`` with deterministic synthetic input.
    No mocking is required because all agents are already in mock-safe
    mode by default (``context.get("mock", True)``).
    """

    # ------------------------------------------------------------------
    # Basic contract
    # ------------------------------------------------------------------

    def test_run_scale_mode_returns_list_of_artifacts(self) -> None:
        """DecisionOrchestrator.run_scale_mode() returns a list[DecisionArtifact]."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_scale_mode(
            brand_name="EstablishedBrand",
            market="US market",
        )

        assert isinstance(artifacts, list), f"Expected list, got {type(artifacts).__name__}"
        assert len(artifacts) > 0, "Expected at least one artifact"
        for art in artifacts:
            assert isinstance(art, DecisionArtifact), (
                f"Expected DecisionArtifact, got {type(art).__name__}"
            )

    def test_scale_mode_artifact_types(self) -> None:
        """Scale mode produces: brief, brand_health_report, market_scan,
        audience_deepening, competitor_tracking, asset_audit, and two
        strategy_doc artifacts."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_scale_mode(
            brand_name="EstablishedBrand",
            market="US market",
        )

        _assert_artifact_types(
            artifacts,
            expected_types={
                "brief",
                "brand_health_report",
                "market_scan",
                "audience_deepening",
                "competitor_tracking",
                "asset_audit",
                "strategy_doc",
            },
        )

        # Exactly two strategy_doc artifacts (ProductOptimization + ContentMarketing)
        strategy_docs = [a for a in artifacts if a.artifact_type == "strategy_doc"]
        assert len(strategy_docs) == 2, (
            f"Expected exactly 2 strategy_doc artifacts, got {len(strategy_docs)}"
        )

    def test_scale_mode_total_artifact_count(self) -> None:
        """Scale mode produces exactly 8 artifacts (brief + 5 analysis + 2 strategy)."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_scale_mode(
            brand_name="EstablishedBrand",
            market="US market",
        )

        assert len(artifacts) == 8, (
            f"Expected 8 artifacts, got {len(artifacts)}. "
            f"Types: {[a.artifact_type for a in artifacts]}"
        )

    # ------------------------------------------------------------------
    # Artifact content
    # ------------------------------------------------------------------

    def test_scale_mode_artifact_content_not_empty(self) -> None:
        """Every artifact has a non-empty content dict."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_scale_mode(
            brand_name="EstablishedBrand",
            market="US market",
        )

        for art in artifacts:
            assert isinstance(art.content, dict), (
                f"Artifact '{art.artifact_type}'.content should be a dict, "
                f"got {type(art.content).__name__}"
            )
            assert len(art.content) > 0, f"Artifact '{art.artifact_type}'.content is empty"

    def test_scale_mode_brief_content(self) -> None:
        """The brief artifact contains the brand_name and the inferred mode."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_scale_mode(
            brand_name="EstablishedBrand",
            market="US market",
        )

        brief = next(a for a in artifacts if a.artifact_type == "brief")

        assert "idea" in brief.content
        assert brief.content["idea"] == "EstablishedBrand"
        assert "market" in brief.content
        assert brief.content["stage"] == "existing"
        assert brief.content["mode"] == "scale", (
            f"Expected mode 'scale', got '{brief.content.get('mode')}'"
        )

    def test_scale_mode_brand_health_report_content(self) -> None:
        """The brand_health_report artifact contains health dimensions."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_scale_mode(
            brand_name="EstablishedBrand",
            market="US market",
        )

        health = next(a for a in artifacts if a.artifact_type == "brand_health_report")

        assert "awareness" in health.content
        assert "consistency" in health.content
        assert "competitiveness" in health.content
        assert "overall_health" in health.content
        assert "recommendations" in health.content
        assert isinstance(health.content["recommendations"], list)

    def test_scale_mode_market_scan_content(self) -> None:
        """The market_scan artifact contains trends and opportunities."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_scale_mode(
            brand_name="EstablishedBrand",
            market="US market",
        )

        market_scan = next(a for a in artifacts if a.artifact_type == "market_scan")

        assert "category_trends" in market_scan.content
        assert isinstance(market_scan.content["category_trends"], list)
        assert "emerging_opportunities" in market_scan.content
        assert "segment_recommendations" in market_scan.content

    def test_scale_mode_audience_deepening_content(self) -> None:
        """The audience_deepening artifact contains personas and insights."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_scale_mode(
            brand_name="EstablishedBrand",
            market="US market",
        )

        deepening = next(a for a in artifacts if a.artifact_type == "audience_deepening")

        assert "existing_personas" in deepening.content
        assert "breakthrough_personas" in deepening.content
        assert "cluster_insights" in deepening.content

    def test_scale_mode_competitor_tracking_content(self) -> None:
        """The competitor_tracking artifact contains competitors and strategies."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_scale_mode(
            brand_name="EstablishedBrand",
            market="US market",
        )

        tracking = next(a for a in artifacts if a.artifact_type == "competitor_tracking")

        assert "competitors" in tracking.content
        assert isinstance(tracking.content["competitors"], list)
        assert "counter_positioning" in tracking.content
        assert "blue_ocean_opportunities" in tracking.content

    def test_scale_mode_asset_audit_content(self) -> None:
        """The asset_audit artifact contains asset classification and recommendations."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_scale_mode(
            brand_name="EstablishedBrand",
            market="US market",
        )

        audit = next(a for a in artifacts if a.artifact_type == "asset_audit")

        assert "hero_content" in audit.content
        assert "needs_update" in audit.content
        assert "obsolete" in audit.content
        assert "total_assets" in audit.content
        assert "audit_recommendations" in audit.content

    def test_scale_mode_strategy_doc_content(self) -> None:
        """Scale mode strategy docs have the expected structure."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_scale_mode(
            brand_name="EstablishedBrand",
            market="US market",
        )

        strategy_docs = [a for a in artifacts if a.artifact_type == "strategy_doc"]
        assert len(strategy_docs) == 2

        # ProductOptimization
        assert "product_positioning" in strategy_docs[0].content
        assert "feature_priorities" in strategy_docs[0].content

        # ContentMarketing
        assert "content_pillars" in strategy_docs[1].content
        assert "channel_matrix" in strategy_docs[1].content

    # ------------------------------------------------------------------
    # Artifact metadata
    # ------------------------------------------------------------------

    def test_scale_mode_artifacts_have_metadata(self) -> None:
        """Every scale-mode artifact has metadata with agent name."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_scale_mode(
            brand_name="EstablishedBrand",
            market="US market",
        )

        for art in artifacts:
            assert isinstance(art.metadata, dict), (
                f"Artifact '{art.artifact_type}'.metadata should be a dict"
            )
            assert "agent" in art.metadata, (
                f"Artifact '{art.artifact_type}' missing 'agent' in metadata"
            )
            assert isinstance(art.metadata["agent"], str)
            assert len(art.metadata["agent"]) > 0

    # ------------------------------------------------------------------
    # convert_to_pipeline_input
    # ------------------------------------------------------------------

    def test_convert_to_pipeline_input_scale(self) -> None:
        """convert_to_pipeline_input() for scale mode returns dict with topic and brand."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_scale_mode(
            brand_name="EstablishedBrand",
            market="US market",
        )

        pipeline_input = orch.convert_to_pipeline_input(artifacts)

        assert isinstance(pipeline_input, dict)
        assert "topic" in pipeline_input
        assert "brand" in pipeline_input
        assert "mode" in pipeline_input
        assert isinstance(pipeline_input["mode"], str)

    # ------------------------------------------------------------------
    # Reproducibility
    # ------------------------------------------------------------------

    def test_scale_mode_reproducible(self) -> None:
        """Identical scale-mode inputs produce identical artifact content."""
        orch = DecisionOrchestrator()

        artifacts_1 = orch.run_scale_mode(
            brand_name="TestBrand",
            market="APAC market",
        )
        artifacts_2 = orch.run_scale_mode(
            brand_name="TestBrand",
            market="APAC market",
        )

        assert len(artifacts_1) == len(artifacts_2)
        types_1 = [a.artifact_type for a in artifacts_1]
        types_2 = [a.artifact_type for a in artifacts_2]
        assert types_1 == types_2, "Artifact type order differs between runs"

        for i, (a1, a2) in enumerate(zip(artifacts_1, artifacts_2)):
            assert a1.content == a2.content, (
                f"Content differs at index {i} (type='{a1.artifact_type}')"
            )

    # ------------------------------------------------------------------
    # Side-by-side with Build mode
    # ------------------------------------------------------------------

    def test_scale_and_build_modes_produce_different_results(self) -> None:
        """Build mode and Scale mode on the same brand produce different artifacts."""
        orch = DecisionOrchestrator()

        brand = "MultiModeBrand"
        build_artifacts = orch.run_build_mode(
            idea=brand,
            brand=brand,
        )
        scale_artifacts = orch.run_scale_mode(
            brand_name=brand,
            market="Global",
        )

        # Different mode in brief
        build_brief = next(a for a in build_artifacts if a.artifact_type == "brief")
        scale_brief = next(a for a in scale_artifacts if a.artifact_type == "brief")
        assert build_brief.content["mode"] == "build", "Build mode brief should have mode='build'"
        assert scale_brief.content["mode"] == "scale", "Scale mode brief should have mode='scale'"

        # Different artifact types
        build_types = {a.artifact_type for a in build_artifacts}
        scale_types = {a.artifact_type for a in scale_artifacts}

        scale_specific = {
            "brand_health_report",
            "market_scan",
            "audience_deepening",
            "competitor_tracking",
            "asset_audit",
        }
        assert scale_specific.issubset(scale_types), (
            f"Scale mode missing unique types. Scale types: {sorted(scale_types)}"
        )

        build_specific = {
            "brand_dna",
            "market_report",
            "persona_map",
            "competitor_matrix",
        }
        assert build_specific.issubset(build_types), (
            f"Build mode missing unique types. Build types: {sorted(build_types)}"
        )

        # Both have brief and strategy_doc
        assert "brief" in build_types and "brief" in scale_types
        assert "strategy_doc" in build_types and "strategy_doc" in scale_types

    def test_scale_mode_can_run_multiple_times_different_markets(self) -> None:
        """Scale mode with different markets produces different content."""
        orch = DecisionOrchestrator()

        artifacts_us = orch.run_scale_mode(
            brand_name="GlobalBrand",
            market="US market",
        )
        artifacts_eu = orch.run_scale_mode(
            brand_name="GlobalBrand",
            market="EU market",
        )

        scan_us = next(a for a in artifacts_us if a.artifact_type == "market_scan")
        scan_eu = next(a for a in artifacts_eu if a.artifact_type == "market_scan")
        assert scan_us.content != scan_eu.content, (
            "Market scan content should differ for different markets"
        )

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_scale_mode_empty_market(self) -> None:
        """Empty market string is handled gracefully."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_scale_mode(
            brand_name="StandaloneBrand",
            market="",
        )

        assert len(artifacts) == 8
        _assert_artifact_types(
            artifacts,
            {
                "brief",
                "brand_health_report",
                "market_scan",
                "audience_deepening",
                "competitor_tracking",
                "asset_audit",
                "strategy_doc",
            },
        )

        market_scan = next(a for a in artifacts if a.artifact_type == "market_scan")
        assert len(market_scan.content) > 0
