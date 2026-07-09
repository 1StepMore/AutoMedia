"""E2E: Decision Layer Build Mode — full chain execution.

Verifies that ``DecisionOrchestrator.run_build_mode()`` produces all
required artifacts and that ``convert_to_pipeline_input()`` returns a
valid pipeline configuration dict.

All agents are self-contained and deterministic — no external services
or LLM calls are required.

PRD-3 W1 Decision Layer: T21 — E2E Build Mode Mock Full Chain.
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
        f"Missing artifact type(s): {sorted(missing)}. "
        f"Actual types: {sorted(actual_types)}"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestDecisionBuildMode:
    """E2E tests for Decision Layer Build Mode.

    Every test creates a fresh ``DecisionOrchestrator`` instance and
    runs ``run_build_mode()`` with deterministic synthetic input.
    No mocking is required because all agents are already in mock-safe
    mode by default (``context.get("mock", True)``).
    """

    # ------------------------------------------------------------------
    # Basic contract
    # ------------------------------------------------------------------

    def test_run_build_mode_returns_list_of_artifacts(self) -> None:
        """DecisionOrchestrator.run_build_mode() returns a list[DecisionArtifact]."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="AI fitness app for SEA",
            brand="FitBrand",
        )

        assert isinstance(artifacts, list), (
            f"Expected list, got {type(artifacts).__name__}"
        )
        assert len(artifacts) > 0, "Expected at least one artifact"
        for art in artifacts:
            assert isinstance(art, DecisionArtifact), (
                f"Expected DecisionArtifact, got {type(art).__name__}"
            )

    def test_build_mode_artifact_types(self) -> None:
        """Build mode produces: brief, brand_dna, market_report, persona_map,
        competitor_matrix, and two strategy_doc artifacts."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="AI fitness app for SEA",
            brand="FitBrand",
        )

        _assert_artifact_types(
            artifacts,
            expected_types={
                "brief",
                "brand_dna",
                "market_report",
                "persona_map",
                "competitor_matrix",
                "strategy_doc",
            },
        )

        # Exactly two strategy_doc artifacts (ProductOptimization + ContentMarketing)
        strategy_docs = [a for a in artifacts if a.artifact_type == "strategy_doc"]
        assert len(strategy_docs) == 2, (
            f"Expected exactly 2 strategy_doc artifacts, got {len(strategy_docs)}"
        )

    def test_build_mode_total_artifact_count(self) -> None:
        """Build mode produces exactly 7 artifacts (brief + 4 analysis + 2 strategy)."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="AI fitness app for SEA",
            brand="FitBrand",
        )

        assert len(artifacts) == 7, (
            f"Expected 7 artifacts, got {len(artifacts)}. "
            f"Types: {[a.artifact_type for a in artifacts]}"
        )

    # ------------------------------------------------------------------
    # Artifact content
    # ------------------------------------------------------------------

    def test_build_mode_artifact_content_not_empty(self) -> None:
        """Every artifact has a non-empty content dict."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="AI fitness app for SEA",
            brand="FitBrand",
        )

        for art in artifacts:
            assert isinstance(art.content, dict), (
                f"Artifact '{art.artifact_type}'.content should be a dict, "
                f"got {type(art.content).__name__}"
            )
            assert len(art.content) > 0, (
                f"Artifact '{art.artifact_type}'.content is empty"
            )

    def test_build_mode_brief_content(self) -> None:
        """The brief artifact contains the original idea and inferred mode."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="AI fitness app for SEA",
            brand="FitBrand",
        )

        brief = next(a for a in artifacts if a.artifact_type == "brief")

        assert brief.content["idea"] == "AI fitness app for SEA"
        assert brief.content["mode"] == "build", (
            f"Expected mode 'build', got '{brief.content.get('mode')}'"
        )
        assert "market" in brief.content
        assert "stage" in brief.content

    def test_build_mode_brand_dna_content(self) -> None:
        """The brand_dna artifact contains brand_name, vision, mission, values."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="AI fitness app for SEA",
            brand="FitBrand",
        )

        brand_dna = next(a for a in artifacts if a.artifact_type == "brand_dna")

        assert "brand_name" in brand_dna.content
        assert "vision" in brand_dna.content
        assert "mission" in brand_dna.content
        assert "values" in brand_dna.content
        assert isinstance(brand_dna.content["values"], list)
        assert len(brand_dna.content["values"]) > 0

    def test_build_mode_market_report_content(self) -> None:
        """The market_report artifact contains market_size and consumer_profile."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="AI fitness app for SEA",
            brand="FitBrand",
        )

        market_report = next(
            a for a in artifacts if a.artifact_type == "market_report"
        )

        assert "market_size" in market_report.content
        assert "consumer_profile" in market_report.content
        assert "cultural_taboos" in market_report.content
        assert "compliance_requirements" in market_report.content

    def test_build_mode_persona_map_content(self) -> None:
        """The persona_map artifact contains a list of personas."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="AI fitness app for SEA",
            brand="FitBrand",
        )

        persona_map = next(
            a for a in artifacts if a.artifact_type == "persona_map"
        )

        assert "personas" in persona_map.content
        assert isinstance(persona_map.content["personas"], list)
        assert len(persona_map.content["personas"]) >= 3
        for p in persona_map.content["personas"]:
            assert "name" in p
            assert "pain_points" in p

    def test_build_mode_competitor_matrix_content(self) -> None:
        """The competitor_matrix artifact contains competitor entries and opportunities."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="AI fitness app for SEA",
            brand="FitBrand",
        )

        competitor_matrix = next(
            a for a in artifacts if a.artifact_type == "competitor_matrix"
        )

        assert "competitors" in competitor_matrix.content
        assert isinstance(competitor_matrix.content["competitors"], list)
        assert len(competitor_matrix.content["competitors"]) == 5
        assert "top_opportunities" in competitor_matrix.content
        assert "white_space_recommendations" in competitor_matrix.content

    def test_build_mode_strategy_doc_content(self) -> None:
        """Each strategy_doc contains strategy-related keys."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="AI fitness app for SEA",
            brand="FitBrand",
        )

        strategy_docs = [
            a for a in artifacts if a.artifact_type == "strategy_doc"
        ]
        assert len(strategy_docs) == 2

        # ProductOptimization strategy
        po_doc = strategy_docs[0]
        assert "product_positioning" in po_doc.content
        assert "feature_priorities" in po_doc.content
        assert "optimization_recommendations" in po_doc.content

        # ContentMarketing strategy
        cm_doc = strategy_docs[1]
        assert "content_pillars" in cm_doc.content
        assert "channel_matrix" in cm_doc.content
        assert "content_calendar_framework" in cm_doc.content

    # ------------------------------------------------------------------
    # Artifact metadata
    # ------------------------------------------------------------------

    def test_build_mode_artifacts_have_metadata(self) -> None:
        """Every artifact has a non-empty metadata dict with agent name."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="AI fitness app for SEA",
            brand="FitBrand",
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

    def test_convert_to_pipeline_input_returns_dict(self) -> None:
        """convert_to_pipeline_input() returns a dict with 'topic', 'brand', 'mode'."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="AI fitness app for SEA",
            brand="FitBrand",
        )

        pipeline_input = orch.convert_to_pipeline_input(artifacts)

        assert isinstance(pipeline_input, dict), (
            f"Expected dict, got {type(pipeline_input).__name__}"
        )
        assert "topic" in pipeline_input
        assert "brand" in pipeline_input
        assert "mode" in pipeline_input

        assert isinstance(pipeline_input["topic"], str)
        assert isinstance(pipeline_input["brand"], str)
        assert isinstance(pipeline_input["mode"], str)

        assert len(pipeline_input["topic"]) > 0, "'topic' should not be empty"
        assert len(pipeline_input["brand"]) > 0, "'brand' should not be empty"

    def test_convert_to_pipeline_input_topic_from_brief(self) -> None:
        """Pipeline input topic reflects the original idea from the brief."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="Eco water bottle for Thailand",
            brand="EcoBrand",
        )

        pipeline_input = orch.convert_to_pipeline_input(artifacts)

        # The topic should be derived from the brief's "idea" field
        assert pipeline_input["topic"] == "Eco water bottle for Thailand"

    def test_convert_to_pipeline_input_brand_from_brand_dna(self) -> None:
        """Pipeline input brand reflects the brand_name in brand_dna."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="AI fitness app for SEA",
            brand="FitBrand",
        )

        pipeline_input = orch.convert_to_pipeline_input(artifacts)

        brand_dna = next(
            a for a in artifacts if a.artifact_type == "brand_dna"
        )
        expected_brand = brand_dna.content.get("brand_name", "")
        assert pipeline_input["brand"] == expected_brand, (
            f"Pipeline brand '{pipeline_input['brand']}' should match "
            f"brand_dna brand_name '{expected_brand}'"
        )

    def test_convert_to_pipeline_input_mode(self) -> None:
        """Pipeline input mode is 'build' for build mode."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="AI fitness app for SEA",
            brand="FitBrand",
        )

        pipeline_input = orch.convert_to_pipeline_input(artifacts)
        assert pipeline_input["mode"] == "build"

    # ------------------------------------------------------------------
    # Reproducibility
    # ------------------------------------------------------------------

    def test_build_mode_reproducible(self) -> None:
        """Identical inputs produce identical artifact content."""
        orch = DecisionOrchestrator()

        artifacts_1 = orch.run_build_mode(
            idea="Social media tool for LatAm creators",
            brand="Creativa",
        )
        artifacts_2 = orch.run_build_mode(
            idea="Social media tool for LatAm creators",
            brand="Creativa",
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
    # Edge cases
    # ------------------------------------------------------------------

    def test_build_mode_empty_idea(self) -> None:
        """Empty idea string is handled gracefully."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(idea="", brand="NoName")

        assert len(artifacts) == 7
        brief = next(a for a in artifacts if a.artifact_type == "brief")
        assert brief.content["idea"] == ""
        _assert_artifact_types(
            artifacts,
            {"brief", "brand_dna", "market_report", "persona_map",
             "competitor_matrix", "strategy_doc"},
        )

    def test_build_mode_empty_brand(self) -> None:
        """Empty brand string is handled gracefully (brand_name is derived)."""
        orch = DecisionOrchestrator()
        artifacts = orch.run_build_mode(
            idea="Test product",
            brand="",
        )

        assert len(artifacts) == 7
        brand_dna = next(a for a in artifacts if a.artifact_type == "brand_dna")
        # The brand name is derived from the idea when not provided
        assert brand_dna.content.get("brand_name") == "Test Product"

    def test_build_mode_different_inputs_different_outputs(self) -> None:
        """Different ideas yield different artifact content."""
        orch = DecisionOrchestrator()

        artifacts_a = orch.run_build_mode(
            idea="AI fitness app",
            brand="FitBrand",
        )
        artifacts_b = orch.run_build_mode(
            idea="Organic tea brand",
            brand="TeaBrand",
        )

        # Spot-check that content differs
        brief_a = next(a for a in artifacts_a if a.artifact_type == "brief")
        brief_b = next(a for a in artifacts_b if a.artifact_type == "brief")
        assert brief_a.content != brief_b.content, (
            "Brief content should differ for different ideas"
        )
