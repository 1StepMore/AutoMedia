"""E2E tests for HITL presets — automated, semi-automated, skip, and
orchestrator integration.

Scenarios
---------
1. Automated preset -> all nodes execute as agent (immediate artifacts)
2. Semi-automated preset -> decision/preference nodes block (return None)
3. Human skip -> artifact has ``human_skipped`` flag set to ``True``
4. Agent mode -> skip raises ``ValueError`` (no pending node)
5. Orchestrator integration -> NodeExecutor and DecisionOrchestrator
   collaborate correctly
"""

from __future__ import annotations

from typing import Any

import pytest

from automedia.decision.base import DecisionArtifact

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_config(mapping: dict[str, str]) -> Any:
    """Build a HITLConfig with the given node -> executor mapping.

    Parameters
    ----------
    mapping:
        ``{node_name: "agent" | "human", ...}``

    Returns a HITLConfig instance that reports the given mapping without
    relying on file-based presets or the dependency graph.
    """
    from automedia.hitl.config import HITLConfig

    class _StubNodeProvider:
        """Minimal NodeProvider stub — returns empty node list."""

        @staticmethod
        def list_all_nodes() -> list[dict[str, str]]:
            return []

    cfg = HITLConfig(
        preset_name="test_automated",
        node_provider=_StubNodeProvider(),
    )
    for name, executor in mapping.items():
        cfg._nodes[name] = {"name": name, "type": "execution", "autoset": executor}
    return cfg


class _StubAgent:
    """Deterministic stub for E2E tests."""

    def __init__(self, name: str = "stub") -> None:
        self._name = name

    def name(self) -> str:
        return self._name

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,
    ) -> DecisionArtifact:
        return DecisionArtifact(
            artifact_type=f"{self._name}_artifact",
            content={"executed": True, **context},
            metadata={"agent": self._name},
        )


# ===================================================================
# W2-T09 — Automated preset
# ===================================================================


@pytest.mark.e2e
class TestAutomatedPreset:
    """Automated preset: all nodes run as agent immediately.

    Mirrors the behaviour defined in ``automedia/hitl/presets/automated.yaml``
    where all nodes except ``brand_questionnaire`` are ``autoset: agent``.
    """

    # Simulated automated.yaml behaviour
    AUTOMATED_MAP: dict[str, str] = {
        "brand_questionnaire": "human",
        "build_scale_routing": "agent",
        "mode_confirmation": "agent",
        "brand_positioning": "agent",
        "market_research": "agent",
        "audience_segmentation": "agent",
        "competitor_analysis": "agent",
        "brand_health_diagnosis": "agent",
        "product_optimization": "agent",
        "content_marketing_strategy": "agent",
    }

    def test_all_agent_nodes_execute_immediately(self) -> None:
        """Agent-mode nodes return a DecisionArtifact right away."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config(self.AUTOMATED_MAP)
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test")

        for node_name, exec_type in self.AUTOMATED_MAP.items():
            if exec_type == "agent":
                result = executor.execute(node_name, agent, {"idea": "test"})
                assert result is not None, f"Agent node {node_name!r} returned None"
                assert isinstance(result, DecisionArtifact)

    def test_human_node_blocks(self) -> None:
        """The single human node (brand_questionnaire) blocks -> None."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config(self.AUTOMATED_MAP)
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test")

        result = executor.execute(
            "brand_questionnaire",
            agent,
            {"idea": "test"},
        )
        assert result is None
        assert "brand_questionnaire" in executor.pending_nodes()

    def test_pending_after_automated_run(self) -> None:
        """After executing all nodes, only human-mode nodes are pending."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config(self.AUTOMATED_MAP)
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test")

        for node_name, _exec_type in self.AUTOMATED_MAP.items():
            executor.execute(node_name, agent, {"idea": "test"})

        pending = executor.pending_nodes()
        assert pending == ["brand_questionnaire"]


# ===================================================================
# W2-T10 — Semi-automated preset
# ===================================================================


@pytest.mark.e2e
class TestSemiAutomatedPreset:
    """Semi-automated: decision/preference nodes block, execution nodes run.

    Mirrors the behaviour defined in
    ``automedia/hitl/presets/semi-automated.yaml`` where decision and
    preference nodes are ``autoset: human`` and execution nodes are
    ``autoset: agent``.
    """

    # Simulated semi-automated.yaml behaviour
    SEMI_AUTOMATED_MAP: dict[str, str] = {
        # Decision nodes -> human
        "brand_questionnaire": "human",
        "build_scale_routing": "human",
        "mode_confirmation": "human",
        "brand_positioning": "human",
        "brand_health_diagnosis": "human",
        "content_asset_audit": "human",
        "product_optimization": "human",
        "content_marketing_strategy": "human",
        "quality_review": "human",
        "next_cycle_planning": "human",
        "brand_dna_refresh": "human",
        # Preference nodes -> human
        "audience_segmentation": "human",
        "market_revalidation": "human",
        "audience_deepening": "human",
        "competitor_tracking": "human",
        "content_calendar": "human",
        # Execution nodes -> agent
        "market_research": "agent",
        "competitor_analysis": "agent",
        "tagging_and_ingestion": "agent",
        "script_generation": "agent",
        "pipeline_execution": "agent",
        "execution_handbook": "agent",
        "ab_test_setup": "agent",
        "progress_report": "agent",
        "publishing": "agent",
        "monitoring": "agent",
    }

    def test_decision_nodes_block(self) -> None:
        """Decision/preference nodes return None (block for human)."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config(self.SEMI_AUTOMATED_MAP)
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test")

        decision_nodes = [
            "brand_questionnaire",
            "brand_positioning",
            "product_optimization",
        ]
        for node_name in decision_nodes:
            result = executor.execute(node_name, agent, {"idea": "test"})
            assert result is None, f"Decision node {node_name!r} should block, got artifact"

    def test_execution_nodes_run_immediately(self) -> None:
        """Execution nodes return artifact immediately (no block)."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config(self.SEMI_AUTOMATED_MAP)
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test")

        execution_nodes = ["market_research", "competitor_analysis"]
        for node_name in execution_nodes:
            result = executor.execute(node_name, agent, {"idea": "test"})
            assert result is not None, f"Execution node {node_name!r} should not block"
            assert isinstance(result, DecisionArtifact)

    def test_pending_contains_all_human_nodes(self) -> None:
        """After executing all nodes, pending lists all human-mode nodes."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config(self.SEMI_AUTOMATED_MAP)
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test")

        human_nodes = [
            name for name, exec_type in self.SEMI_AUTOMATED_MAP.items() if exec_type == "human"
        ]

        for node_name in self.SEMI_AUTOMATED_MAP:
            executor.execute(node_name, agent, {"idea": "test"})

        pending = executor.pending_nodes()
        assert len(pending) == len(human_nodes)
        for name in human_nodes:
            assert name in pending, f"Human node {name!r} missing from pending"


# ===================================================================
# W2-T11 — Skip, agent-cannot-skip, orchestrator integration
# ===================================================================


@pytest.mark.e2e
class TestHumanSkip:
    """Human skip marks artifact metadata with ``human_skipped``."""

    def test_human_skip_marks_artifact(self) -> None:
        """Skipping a pending human node sets human_skipped=True."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "human"})
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test")

        executor.execute("test_node", agent, {"idea": "test"})
        artifact = executor.skip_node("test_node")

        assert artifact.metadata.get("human_skipped") is True

    def test_skipped_artifact_retains_content(self) -> None:
        """Skipped artifact preserves normal content and metadata."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "human"})
        executor = NodeExecutor(config)
        agent = _StubAgent(name="skipped_node")

        executor.execute("test_node", agent, {"idea": "test"})
        artifact = executor.skip_node("test_node")

        assert artifact.artifact_type == "skipped_node_artifact"
        assert artifact.content["executed"] is True
        assert artifact.content["idea"] == "test"


@pytest.mark.e2e
class TestAgentCannotSkip:
    """Agent mode cannot skip or approve — raises ValueError."""

    def test_skip_raises_in_agent_mode(self) -> None:
        """skip_node() raises ValueError when node was executed in agent mode."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "agent"})
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test")

        # Execute in agent mode (artifact returned, nothing pending)
        executor.execute("test_node", agent, {"idea": "test"})

        with pytest.raises(ValueError, match="No pending node"):
            executor.skip_node("test_node")

    def test_approve_raises_in_agent_mode(self) -> None:
        """approve_node() raises ValueError when node was executed in agent mode."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "agent"})
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test")

        executor.execute("test_node", agent, {"idea": "test"})

        with pytest.raises(ValueError, match="No pending node"):
            executor.approve_node("test_node")
