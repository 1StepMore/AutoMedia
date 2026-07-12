"""Tests for DecisionOrchestrator — build/scale modes, strategy engine, HITL routing.

Covers
------
1. __getattr__ lazy agent instantiation
2. __getattr__ raises AttributeError for unknown agents
3. __init__ with/without hitl_config
4. run_build_mode() — 7 artifacts, correct types
5. run_scale_mode() — 8 artifacts, correct types
6. convert_to_pipeline_input() — extracts topic, brand, mode
7. convert_to_pipeline_input() — falls back to defaults on empty artifacts
8. convert_to_pipeline_input() — brief fallback for brand_name
9. run_strategy_engine() — converges analysis artifacts
10. _run_node() — delegates to agent.execute() without HITL
11. _run_node() — delegates to HITL executor when configured
12. _run_node() — HITL executor returns None (human mode)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.decision.base import DecisionArtifact
from automedia.decision.orchestrator import DecisionOrchestrator


# ---------------------------------------------------------------------------
# Helpers — controlled DecisionArtifact factories
# ---------------------------------------------------------------------------

def _make_artifact(artifact_type: str, content: dict[str, Any] | None = None) -> DecisionArtifact:
    """Create a DecisionArtifact with controlled content."""
    return DecisionArtifact(
        artifact_type=artifact_type,
        content=content or {},
    )


def _brief_artifact(idea: str = "Test idea", brand: str = "TestBrand", mode: str = "build") -> DecisionArtifact:
    return _make_artifact("brief", {"idea": idea, "brand": brand, "mode": mode, "market": "SEA"})


def _brand_dna_artifact() -> DecisionArtifact:
    return _make_artifact("brand_dna", {"brand_name": "EcoBrand", "vision": "Green future"})


def _market_report_artifact() -> DecisionArtifact:
    return _make_artifact("market_report", {"market_size": "$10B", "trend": "growing"})


def _persona_map_artifact() -> DecisionArtifact:
    return _make_artifact("persona_map", {"personas": [{"name": "P1"}, {"name": "P2"}]})


def _competitor_matrix_artifact() -> DecisionArtifact:
    return _make_artifact("competitor_matrix", {"competitors": [{"name": "C1"}]})


def _strategy_doc_artifact() -> DecisionArtifact:
    return _make_artifact("strategy_doc", {
        "content_pillars": [{"name": "Sustainability"}],
        "channels": ["instagram", "tiktok"],
    })


def _product_blueprint_artifact() -> DecisionArtifact:
    return _make_artifact("asset_blueprint", {"features": ["f1"]})


def _content_calendar_artifact() -> DecisionArtifact:
    return _make_artifact("content_calendar", {"posts": [{"day": 1}]})


# ---------------------------------------------------------------------------
# Mock agent helper
# ---------------------------------------------------------------------------

def _mock_agent(artifact: DecisionArtifact) -> MagicMock:
    """Create a mock agent that returns the given artifact from execute()."""
    agent = MagicMock()
    agent.execute.return_value = artifact
    return agent


# ---------------------------------------------------------------------------
# Test class — __getattr__ lazy instantiation
# ---------------------------------------------------------------------------


class TestOrchestratorLazyInit:
    """DecisionOrchestrator.__getattr__ lazily instantiates agents."""

    def test_known_agent_returns_instance(self) -> None:
        """Accessing a registered agent name returns an instantiated agent."""
        orch = DecisionOrchestrator()
        with patch.object(DecisionOrchestrator, "_AGENT_REGISTRY", {
            "_diagnostic": MagicMock(return_value=MagicMock()),
        }):
            agent = orch._diagnostic
            assert agent is not None

    def test_known_agent_is_cached(self) -> None:
        """Accessing the same agent twice returns the same instance."""
        orch = DecisionOrchestrator()
        mock_cls = MagicMock(return_value=MagicMock())
        with patch.object(DecisionOrchestrator, "_AGENT_REGISTRY", {"_diagnostic": mock_cls}):
            first = orch._diagnostic
            second = orch._diagnostic
            assert first is second
            mock_cls.assert_called_once()

    def test_unknown_agent_raises_attribute_error(self) -> None:
        """Accessing an unregistered agent name raises AttributeError."""
        orch = DecisionOrchestrator()
        with pytest.raises(AttributeError, match="no attribute"):
            _ = orch._nonexistent_agent

    def test_attribute_error_message_contains_class_name(self) -> None:
        """The error message includes the orchestrator class name."""
        orch = DecisionOrchestrator()
        with pytest.raises(AttributeError, match="DecisionOrchestrator"):
            _ = orch._bogus


# ---------------------------------------------------------------------------
# Test class — __init__
# ---------------------------------------------------------------------------


class TestOrchestratorInit:
    """DecisionOrchestrator.__init__ with optional HITL config."""

    def test_init_without_hitl_config(self) -> None:
        orch = DecisionOrchestrator()
        assert orch._hitl_config is None
        assert orch._executor is None

    def test_init_with_hitl_config_creates_executor(self) -> None:
        mock_config = MagicMock()
        with patch("automedia.decision.orchestrator.NodeExecutor") as mock_ne:
            mock_executor = MagicMock()
            mock_ne.return_value = mock_executor
            orch = DecisionOrchestrator(hitl_config=mock_config)
            assert orch._hitl_config is mock_config
            assert orch._executor is mock_executor
            mock_ne.assert_called_once_with(mock_config)

    def test_init_with_hitl_config_but_no_nodeexecutor_import(self) -> None:
        """When NodeExecutor is None (import failed), executor stays None."""
        mock_config = MagicMock()
        with patch("automedia.decision.orchestrator.NodeExecutor", None):
            orch = DecisionOrchestrator(hitl_config=mock_config)
            assert orch._hitl_config is mock_config
            assert orch._executor is None


# ---------------------------------------------------------------------------
# Test class — run_build_mode
# ---------------------------------------------------------------------------


class TestRunBuildMode:
    """run_build_mode() runs diagnostic → 4 analysis → 2 strategy = 7 artifacts."""

    def _make_orchestrator(self) -> tuple[DecisionOrchestrator, dict[str, MagicMock]]:
        """Create an orchestrator with mocked agents. Returns (orch, agents_dict)."""
        orch = DecisionOrchestrator()
        agents: dict[str, MagicMock] = {}

        # Phase 0: diagnostic
        agents["_diagnostic"] = _mock_agent(_brief_artifact())
        # Phase 1-B: analysis
        agents["_brand_positioning"] = _mock_agent(_brand_dna_artifact())
        agents["_market_research"] = _mock_agent(_market_report_artifact())
        agents["_audience_seg"] = _mock_agent(_persona_map_artifact())
        agents["_competitor_analysis"] = _mock_agent(_competitor_matrix_artifact())
        # Phase 2: strategy
        agents["_product_opt"] = _mock_agent(_product_blueprint_artifact())
        agents["_content_mkt"] = _mock_agent(_content_calendar_artifact())

        for attr, mock in agents.items():
            object.__setattr__(orch, attr, mock)

        return orch, agents

    def test_returns_seven_artifacts(self) -> None:
        orch, _ = self._make_orchestrator()
        artifacts = orch.run_build_mode("Eco bottle", "EcoBrand")
        assert len(artifacts) == 7

    def test_artifact_types_in_order(self) -> None:
        orch, _ = self._make_orchestrator()
        artifacts = orch.run_build_mode("Eco bottle", "EcoBrand")
        expected_types = [
            "brief",           # diagnostic
            "brand_dna",       # brand positioning
            "market_report",   # market research
            "persona_map",     # audience segmentation
            "competitor_matrix",  # competitor analysis
            "asset_blueprint",    # product optimization
            "content_calendar",   # content marketing
        ]
        actual_types = [a.artifact_type for a in artifacts]
        assert actual_types == expected_types

    def test_diagnostic_called_with_correct_context(self) -> None:
        orch, agents = self._make_orchestrator()
        orch.run_build_mode("Eco bottle", "EcoBrand", market="SEA")
        agents["_diagnostic"].execute.assert_called_once_with(
            {"idea": "Eco bottle", "market": "SEA", "stage": "new"}, None,
        )

    def test_brand_positioning_receives_mode_from_brief(self) -> None:
        orch, agents = self._make_orchestrator()
        orch.run_build_mode("Eco bottle", "EcoBrand")
        call_args = agents["_brand_positioning"].execute.call_args
        ctx = call_args[0][0]
        assert ctx["mode"] == "build"

    def test_market_research_receives_brand_name_from_positioning(self) -> None:
        """When brand_positioning returns brand_name, it's injected into market_research ctx."""
        orch, agents = self._make_orchestrator()
        orch.run_build_mode("Eco bottle", "EcoBrand")
        call_args = agents["_market_research"].execute.call_args
        ctx = call_args[0][0]
        assert ctx.get("brand_name") == "EcoBrand"

    def test_strategy_agents_receive_converged_context(self) -> None:
        """Phase 2 agents receive brand_dna, market_report, persona_map, competitor_matrix."""
        orch, agents = self._make_orchestrator()
        orch.run_build_mode("Eco bottle", "EcoBrand")
        for agent_name in ("_product_opt", "_content_mkt"):
            call_args = agents[agent_name].execute.call_args
            ctx = call_args[0][0]
            assert "brand_dna" in ctx
            assert "market_report" in ctx
            assert "persona_map" in ctx
            assert "competitor_matrix" in ctx


# ---------------------------------------------------------------------------
# Test class — run_scale_mode
# ---------------------------------------------------------------------------


class TestRunScaleMode:
    """run_scale_mode() runs diagnostic → 5 scale → 2 strategy = 8 artifacts."""

    def _make_orchestrator(self) -> tuple[DecisionOrchestrator, dict[str, MagicMock]]:
        orch = DecisionOrchestrator()
        agents: dict[str, MagicMock] = {}

        agents["_diagnostic"] = _mock_agent(_brief_artifact(mode="scale"))
        agents["_health_diagnosis"] = _mock_agent(_make_artifact("health_report", {"score": 85}))
        agents["_market_reval"] = _mock_agent(_make_artifact("market_scan", {"trend": "up"}))
        agents["_audience_deepen"] = _mock_agent(_make_artifact("audience_deepening", {"clusters": 3}))
        agents["_competitor_track"] = _mock_agent(_make_artifact("competitor_tracking", {"alerts": 2}))
        agents["_asset_audit"] = _mock_agent(_make_artifact("asset_audit", {"total": 50}))
        agents["_product_opt"] = _mock_agent(_product_blueprint_artifact())
        agents["_content_mkt"] = _mock_agent(_content_calendar_artifact())

        for attr, mock in agents.items():
            object.__setattr__(orch, attr, mock)

        return orch, agents

    def test_returns_eight_artifacts(self) -> None:
        orch, _ = self._make_orchestrator()
        artifacts = orch.run_scale_mode("ExistingBrand")
        assert len(artifacts) == 8

    def test_artifact_types_in_order(self) -> None:
        orch, _ = self._make_orchestrator()
        artifacts = orch.run_scale_mode("ExistingBrand")
        expected_types = [
            "brief",             # diagnostic
            "health_report",     # brand health diagnosis
            "market_scan",       # market revalidation
            "audience_deepening",  # audience deepening
            "competitor_tracking",  # competitor tracking
            "asset_audit",       # content asset audit
            "asset_blueprint",   # product optimization
            "content_calendar",  # content marketing
        ]
        actual_types = [a.artifact_type for a in artifacts]
        assert actual_types == expected_types

    def test_diagnostic_called_with_existing_stage(self) -> None:
        orch, agents = self._make_orchestrator()
        orch.run_scale_mode("ExistingBrand", market="EU")
        agents["_diagnostic"].execute.assert_called_once_with(
            {"idea": "ExistingBrand", "market": "EU", "stage": "existing"}, None,
        )

    def test_scale_agents_receive_brand_name_and_mode(self) -> None:
        orch, agents = self._make_orchestrator()
        orch.run_scale_mode("ExistingBrand")
        for agent_name in ("_health_diagnosis", "_market_reval", "_audience_deepen",
                           "_competitor_track", "_asset_audit"):
            call_args = agents[agent_name].execute.call_args
            ctx = call_args[0][0]
            assert ctx["brand_name"] == "ExistingBrand"
            assert ctx["mode"] == "scale"

    def test_strategy_agents_receive_scale_context(self) -> None:
        orch, agents = self._make_orchestrator()
        orch.run_scale_mode("ExistingBrand")
        for agent_name in ("_product_opt", "_content_mkt"):
            call_args = agents[agent_name].execute.call_args
            ctx = call_args[0][0]
            assert "health_report" in ctx
            assert "market_scan" in ctx
            assert "audience_deepening" in ctx
            assert "competitor_tracking" in ctx
            assert "asset_audit" in ctx


# ---------------------------------------------------------------------------
# Test class — convert_to_pipeline_input
# ---------------------------------------------------------------------------


class TestConvertToPipelineInput:
    """convert_to_pipeline_input() extracts topic, brand, mode from artifacts."""

    def test_extracts_topic_brand_mode_from_brief(self) -> None:
        orch = DecisionOrchestrator()
        artifacts = [
            _brief_artifact(idea="AI fitness app", brand="FitBrand", mode="text_only"),
            _brand_dna_artifact(),
        ]
        result = orch.convert_to_pipeline_input(artifacts)
        assert result["topic"] == "AI fitness app"
        assert result["brand"] == "EcoBrand"  # brand_dna overrides brief
        assert result["mode"] == "text_only"

    def test_brand_from_dna_overrides_brief(self) -> None:
        """brand_dna.brand_name takes precedence over brief.brand."""
        orch = DecisionOrchestrator()
        artifacts = [
            _brief_artifact(brand="BriefBrand"),
            _brand_dna_artifact(),  # brand_name = "EcoBrand"
        ]
        result = orch.convert_to_pipeline_input(artifacts)
        assert result["brand"] == "EcoBrand"

    def test_brief_brand_used_when_no_brand_dna(self) -> None:
        """When no brand_dna artifact, falls back to brief.brand."""
        orch = DecisionOrchestrator()
        artifacts = [_brief_artifact(brand="FallbackBrand")]
        result = orch.convert_to_pipeline_input(artifacts)
        assert result["brand"] == "FallbackBrand"

    def test_topic_from_strategy_content_pillars_when_brief_empty(self) -> None:
        """When brief has no idea, topic comes from first content pillar."""
        orch = DecisionOrchestrator()
        brief = _make_artifact("brief", {"idea": "", "mode": "auto"})
        strategy = _make_artifact("strategy_doc", {
            "content_pillars": [{"name": "Sustainability"}],
        })
        result = orch.convert_to_pipeline_input([brief, strategy])
        assert result["topic"] == "Sustainability"

    def test_topic_from_strategy_pillar_string(self) -> None:
        """Content pillar can be a plain string, not just a dict."""
        orch = DecisionOrchestrator()
        brief = _make_artifact("brief", {"idea": "", "mode": "auto"})
        strategy = _make_artifact("strategy_doc", {
            "content_pillars": ["Eco Living"],
        })
        result = orch.convert_to_pipeline_input([brief, strategy])
        assert result["topic"] == "Eco Living"

    def test_falls_back_to_defaults_on_empty_artifacts(self) -> None:
        """Empty artifact list returns default topic, brand, mode."""
        orch = DecisionOrchestrator()
        result = orch.convert_to_pipeline_input([])
        assert result["topic"] == "Default topic"
        assert result["brand"] == "default"
        assert result["mode"] == "auto"

    def test_all_artifacts_produce_valid_output(self) -> None:
        """A full set of build-mode artifacts produces a complete pipeline input."""
        orch = DecisionOrchestrator()
        artifacts = [
            _brief_artifact(idea="Smart home", brand="HomeBrand", mode="build"),
            _brand_dna_artifact(),
            _market_report_artifact(),
            _persona_map_artifact(),
            _competitor_matrix_artifact(),
            _product_blueprint_artifact(),
            _content_calendar_artifact(),
        ]
        result = orch.convert_to_pipeline_input(artifacts)
        assert result["topic"] == "Smart home"
        assert result["brand"] == "EcoBrand"
        assert result["mode"] == "build"

    def test_mode_defaults_to_auto_when_no_brief(self) -> None:
        orch = DecisionOrchestrator()
        artifacts = [_make_artifact("brand_dna", {"brand_name": "X"})]
        result = orch.convert_to_pipeline_input(artifacts)
        assert result["mode"] == "auto"


# ---------------------------------------------------------------------------
# Test class — run_strategy_engine
# ---------------------------------------------------------------------------


class TestRunStrategyEngine:
    """run_strategy_engine() converges analysis artifacts into strategy output."""

    def test_returns_two_artifacts(self) -> None:
        orch = DecisionOrchestrator()
        po = _mock_agent(_product_blueprint_artifact())
        cm = _mock_agent(_content_calendar_artifact())
        object.__setattr__(orch, "_product_opt", po)
        object.__setattr__(orch, "_content_mkt", cm)

        analysis = [_brand_dna_artifact(), _market_report_artifact()]
        result = orch.run_strategy_engine(analysis)
        assert len(result) == 2

    def test_artifact_types_are_strategy(self) -> None:
        orch = DecisionOrchestrator()
        object.__setattr__(orch, "_product_opt", _mock_agent(_product_blueprint_artifact()))
        object.__setattr__(orch, "_content_mkt", _mock_agent(_content_calendar_artifact()))

        result = orch.run_strategy_engine([_brand_dna_artifact()])
        assert result[0].artifact_type == "asset_blueprint"
        assert result[1].artifact_type == "content_calendar"

    def test_strategy_context_uses_artifact_types_as_keys(self) -> None:
        """Each artifact's artifact_type becomes a key in the strategy context."""
        orch = DecisionOrchestrator()
        po = _mock_agent(_product_blueprint_artifact())
        object.__setattr__(orch, "_product_opt", po)
        object.__setattr__(orch, "_content_mkt", _mock_agent(_content_calendar_artifact()))

        analysis = [_brand_dna_artifact(), _market_report_artifact()]
        orch.run_strategy_engine(analysis)
        call_args = po.execute.call_args
        ctx = call_args[0][0]
        assert "brand_dna" in ctx
        assert "market_report" in ctx

    def test_empty_analysis_artifacts(self) -> None:
        """Empty analysis list produces empty strategy context."""
        orch = DecisionOrchestrator()
        po = _mock_agent(_product_blueprint_artifact())
        cm = _mock_agent(_content_calendar_artifact())
        object.__setattr__(orch, "_product_opt", po)
        object.__setattr__(orch, "_content_mkt", cm)

        result = orch.run_strategy_engine([])
        assert len(result) == 2
        call_ctx = po.execute.call_args[0][0]
        assert call_ctx == {}


# ---------------------------------------------------------------------------
# Test class — _run_node
# ---------------------------------------------------------------------------


class TestRunNode:
    """_run_node() with and without HITL executor."""

    def test_delegates_to_agent_execute_without_hitl(self) -> None:
        """Without HITL config, _run_node calls agent.execute() directly."""
        orch = DecisionOrchestrator()
        mock_agent = MagicMock()
        expected = _make_artifact("brief", {"idea": "test"})
        mock_agent.execute.return_value = expected

        result = orch._run_node("test_node", mock_agent, {"idea": "test"})
        assert result is expected
        mock_agent.execute.assert_called_once_with({"idea": "test"}, None)

    def test_passes_asset_library_to_agent(self) -> None:
        orch = DecisionOrchestrator()
        mock_agent = MagicMock()
        mock_agent.execute.return_value = _make_artifact("brief")
        mock_lib = MagicMock()

        orch._run_node("test_node", mock_agent, {}, asset_library=mock_lib)
        mock_agent.execute.assert_called_once_with({}, mock_lib)

    def test_delegates_to_hitl_executor_when_configured(self) -> None:
        """With HITL config, _run_node delegates to self._executor.execute()."""
        orch = DecisionOrchestrator()
        mock_executor = MagicMock()
        expected = _make_artifact("brief", {"routed": "hitl"})
        mock_executor.execute.return_value = expected
        orch._executor = mock_executor

        mock_agent = MagicMock()
        result = orch._run_node("brand_questionnaire", mock_agent, {"idea": "test"}, None)
        assert result is expected
        mock_executor.execute.assert_called_once_with(
            "brand_questionnaire", mock_agent, {"idea": "test"}, None,
        )

    def test_hitl_executor_returns_none_for_human_mode(self) -> None:
        """When HITL executor returns None (human mode pending), _run_node returns None."""
        orch = DecisionOrchestrator()
        mock_executor = MagicMock()
        mock_executor.execute.return_value = None
        orch._executor = mock_executor

        mock_agent = MagicMock()
        result = orch._run_node("brand_questionnaire", mock_agent, {}, None)
        assert result is None

    def test_hitl_executor_receives_asset_library(self) -> None:
        orch = DecisionOrchestrator()
        mock_executor = MagicMock()
        mock_executor.execute.return_value = _make_artifact("brief")
        orch._executor = mock_executor

        mock_agent = MagicMock()
        mock_lib = MagicMock()
        orch._run_node("node", mock_agent, {"x": 1}, asset_library=mock_lib)
        mock_executor.execute.assert_called_once_with("node", mock_agent, {"x": 1}, mock_lib)
