"""RED tests for NodeExecutor — agent mode, human mode, integration.

Scenarios
---------
1. Agent mode: execute returns artifact, asset_library passes through
2. Agent mode: skip_node raises ValueError (nothing to skip)
3. Agent mode: approve_node raises ValueError (nothing to approve)
4. Human mode: execute returns None (pending)
5. Human mode: approve_node returns stored artifact
6. Human mode: skip_node returns artifact with human_skipped flag
7. Human mode: pending_nodes() lists correctly
8. Integration: works with real BaseDecisionAgent subclass
"""

from __future__ import annotations

from typing import Any

import pytest

from automedia.decision.base import BaseDecisionAgent, DecisionArtifact


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

    cfg = HITLConfig(preset_name="test_automated")
    for name, executor in mapping.items():
        cfg._nodes[name] = {"name": name, "type": "execution", "autoset": executor}
    return cfg


class _StubAgent(BaseDecisionAgent):
    """Minimal deterministic agent for executor unit tests."""

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
# Agent mode
# ===================================================================


class TestNodeExecutorAgentMode:
    """NodeExecutor.execute() with agent-mode config."""

    def test_execute_returns_artifact(self) -> None:
        """Agent mode returns a DecisionArtifact from agent.execute()."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "agent"})
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test_node")

        result = executor.execute("test_node", agent, {"idea": "test"})

        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "test_node_artifact"
        assert result.content["executed"] is True

    def test_execute_passes_asset_library(self) -> None:
        """Agent mode passes asset_library through to agent.execute()."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "agent"})
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test_node")

        mock_lib = type(
            "MockLib", (), {"search": lambda self, **kw: ["a1"]}
        )()
        result = executor.execute(
            "test_node", agent, {"idea": "test"}, mock_lib,
        )

        assert isinstance(result, DecisionArtifact)

    def test_skip_node_raises_error(self) -> None:
        """Agent mode has no pending nodes -> skip_node raises ValueError."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "agent"})
        executor = NodeExecutor(config)

        with pytest.raises(ValueError, match="No pending node"):
            executor.skip_node("test_node")

    def test_approve_node_raises_error(self) -> None:
        """Agent mode has no pending nodes -> approve_node raises ValueError."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "agent"})
        executor = NodeExecutor(config)

        with pytest.raises(ValueError, match="No pending node"):
            executor.approve_node("test_node")

    def test_unknown_node_raises_key_error(self) -> None:
        """Unknown node name propagates KeyError from config."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "agent"})
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test_node")

        with pytest.raises(KeyError):
            executor.execute("nonexistent", agent, {"idea": "test"})

    def test_pending_is_empty_after_execute(self) -> None:
        """Agent-mode execute leaves no pending nodes."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "agent"})
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test_node")

        executor.execute("test_node", agent, {"idea": "test"})
        assert executor.pending_nodes() == []


# ===================================================================
# Human mode
# ===================================================================


class TestNodeExecutorHumanMode:
    """NodeExecutor.execute() with human-mode config."""

    def test_execute_returns_none(self) -> None:
        """Human mode returns None -- waiting for human approval."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "human"})
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test_node")

        result = executor.execute("test_node", agent, {"idea": "test"})

        assert result is None

    def test_execute_stores_pending(self) -> None:
        """Human mode stores the suggestion in _pending."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "human"})
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test_node")

        executor.execute("test_node", agent, {"idea": "test"})

        assert executor.pending_nodes() == ["test_node"]

    def test_approve_node_returns_artifact(self) -> None:
        """approve_node returns the stored DecisionArtifact."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "human"})
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test_node")

        executor.execute("test_node", agent, {"idea": "test"})
        artifact = executor.approve_node("test_node")

        assert isinstance(artifact, DecisionArtifact)
        assert artifact.artifact_type == "test_node_artifact"
        # After approval the node is no longer pending
        assert executor.pending_nodes() == []

    def test_skip_node_returns_artifact_with_flag(self) -> None:
        """skip_node returns the artifact with human_skipped=True."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "human"})
        executor = NodeExecutor(config)
        agent = _StubAgent(name="test_node")

        executor.execute("test_node", agent, {"idea": "test"})
        artifact = executor.skip_node("test_node")

        assert isinstance(artifact, DecisionArtifact)
        assert artifact.metadata.get("human_skipped") is True
        # After skip the node is no longer pending
        assert executor.pending_nodes() == []

    def test_multiple_pending_nodes(self) -> None:
        """Multiple human-mode nodes can be pending simultaneously."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"node_a": "human", "node_b": "human"})
        executor = NodeExecutor(config)
        agent = _StubAgent()

        executor.execute("node_a", agent, {"idea": "a"})
        executor.execute("node_b", agent, {"idea": "b"})

        pending = executor.pending_nodes()
        assert "node_a" in pending
        assert "node_b" in pending
        assert len(pending) == 2

    def test_skip_unknown_node_raises(self) -> None:
        """skip_node with unknown name raises ValueError."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "human"})
        executor = NodeExecutor(config)

        with pytest.raises(ValueError, match="No pending node"):
            executor.skip_node("nonexistent")

    def test_approve_unknown_node_raises(self) -> None:
        """approve_node with unknown name raises ValueError."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "human"})
        executor = NodeExecutor(config)

        with pytest.raises(ValueError, match="No pending node"):
            executor.approve_node("nonexistent")

    def test_pending_nodes_empty_initially(self) -> None:
        """Fresh executor has no pending nodes."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"test_node": "human"})
        executor = NodeExecutor(config)

        assert executor.pending_nodes() == []

    def test_approve_clears_only_requested_node(self) -> None:
        """Approving one node leaves other pending nodes intact."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"node_a": "human", "node_b": "human"})
        executor = NodeExecutor(config)
        agent = _StubAgent()

        executor.execute("node_a", agent, {"idea": "a"})
        executor.execute("node_b", agent, {"idea": "b"})

        executor.approve_node("node_a")

        assert executor.pending_nodes() == ["node_b"]

    def test_skip_clears_only_requested_node(self) -> None:
        """Skipping one node leaves other pending nodes intact."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({"node_a": "human", "node_b": "human"})
        executor = NodeExecutor(config)
        agent = _StubAgent()

        executor.execute("node_a", agent, {"idea": "a"})
        executor.execute("node_b", agent, {"idea": "b"})

        executor.skip_node("node_a")

        assert executor.pending_nodes() == ["node_b"]


# ===================================================================
# Integration with real agents
# ===================================================================


class TestNodeExecutorIntegration:
    """NodeExecutor works with real BaseDecisionAgent subclasses."""

    def test_with_diagnostic_agent(self) -> None:
        """Executor runs DiagnosticAgent in agent mode."""
        from automedia.hitl.executor import NodeExecutor
        from automedia.decision.diagnostic import DiagnosticAgent

        config = _build_config({"diagnosis": "agent"})
        executor = NodeExecutor(config)
        agent = DiagnosticAgent()

        result = executor.execute(
            "diagnosis",
            agent,
            {"idea": "AI fitness app", "market": "SEA", "stage": "new"},
        )

        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "brief"

    def test_with_brand_positioning_agent(self) -> None:
        """Executor runs BrandPositioningAgent in agent mode."""
        from automedia.hitl.executor import NodeExecutor
        from automedia.decision.build import BrandPositioningAgent

        config = _build_config({"brand_positioning": "agent"})
        executor = NodeExecutor(config)
        agent = BrandPositioningAgent()

        result = executor.execute(
            "brand_positioning",
            agent,
            {"idea": "Eco water bottle", "market": "Thailand", "stage": "new"},
        )

        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "brand_dna"

    def test_human_mode_with_real_agent(self) -> None:
        """Executor runs a real agent in human mode -- stores pending."""
        from automedia.hitl.executor import NodeExecutor
        from automedia.decision.diagnostic import DiagnosticAgent

        config = _build_config({"diagnosis": "human"})
        executor = NodeExecutor(config)
        agent = DiagnosticAgent()

        # Human mode -> returns None
        result = executor.execute(
            "diagnosis",
            agent,
            {"idea": "Test", "market": "US", "stage": "new"},
        )
        assert result is None
        assert executor.pending_nodes() == ["diagnosis"]

        # Approve and verify the artifact
        artifact = executor.approve_node("diagnosis")
        assert isinstance(artifact, DecisionArtifact)
        assert artifact.artifact_type == "brief"

    def test_human_skip_with_real_agent(self) -> None:
        """Skip a real agent's pending suggestion."""
        from automedia.hitl.executor import NodeExecutor
        from automedia.decision.diagnostic import DiagnosticAgent

        config = _build_config({"diagnosis": "human"})
        executor = NodeExecutor(config)
        agent = DiagnosticAgent()

        executor.execute(
            "diagnosis",
            agent,
            {"idea": "Test", "market": "US", "stage": "new"},
        )
        artifact = executor.skip_node("diagnosis")

        assert artifact.metadata.get("human_skipped") is True
        assert artifact.artifact_type == "brief"

    def test_orchestrator_collaboration_pattern(self) -> None:
        """Simulates how DecisionOrchestrator would use NodeExecutor."""
        from automedia.hitl.executor import NodeExecutor
        from automedia.decision.diagnostic import DiagnosticAgent
        from automedia.decision.build import BrandPositioningAgent

        config = _build_config({
            "diagnosis": "agent",
            "brand_positioning": "agent",
            "market_research": "agent",
        })
        executor = NodeExecutor(config)
        diag_agent = DiagnosticAgent()
        bp_agent = BrandPositioningAgent()

        # Phase 0: Diagnostic
        brief = executor.execute(
            "diagnosis",
            diag_agent,
            {"idea": "AI video app", "market": "SEA", "stage": "new"},
        )
        assert brief is not None
        assert brief.artifact_type == "brief"

        # Phase 1: Brand positioning (uses brief context)
        bp_result = executor.execute(
            "brand_positioning",
            bp_agent,
            {
                **brief.content,
                "idea": "AI video app",
                "market": "SEA",
                "stage": "new",
            },
        )
        assert bp_result is not None
        assert bp_result.artifact_type == "brand_dna"
        assert bp_result.content.get("brand_name")

    def test_pending_survives_multiple_approve_cycles(self) -> None:
        """A node can be approved then a new node executed and approved."""
        from automedia.hitl.executor import NodeExecutor

        config = _build_config({
            "first": "human",
            "second": "human",
        })
        executor = NodeExecutor(config)
        agent = _StubAgent()

        executor.execute("first", agent, {"idea": "first"})
        executor.approve_node("first")

        executor.execute("second", agent, {"idea": "second"})
        assert executor.pending_nodes() == ["second"]

        executor.approve_node("second")
        assert executor.pending_nodes() == []
