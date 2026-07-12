"""DecisionOrchestrator — top-level orchestrator for the Decision Layer.

Runs Build or Scale mode through all phases:
1. Diagnostic (phase 0) → routing
2. Analysis agents (phase 1-B or 1-S) → parallel
3. Strategy Engine (phase 2) → converged
4. Output conversion → pipeline input
"""

from __future__ import annotations

from typing import Any

from automedia.decision.base import DecisionArtifact
from automedia.decision.build import (
    AudienceSegmentationAgent,
    BrandPositioningAgent,
    CompetitorAnalysisAgent,
    MarketResearchAgent,
)
from automedia.decision.diagnostic import DiagnosticAgent
from automedia.decision.scale import (
    AudienceDeepeningAgent,
    BrandHealthDiagnosisAgent,
    CompetitorTrackingAgent,
    ContentAssetAuditAgent,
    MarketRevalidationAgent,
)
from automedia.decision.strategy import (
    ContentMarketingAgent,
    ProductOptimizationAgent,
)

try:
    from automedia.hitl.executor import NodeExecutor
except ImportError:
    from automedia.core._import_helpers import warn_missing_optional

    warn_missing_optional("hitl.executor", feature="HITL NodeExecutor disabled")
    NodeExecutor = None  # type: ignore[assignment,misc]


class DecisionOrchestrator:
    """Top-level orchestrator for the Decision Layer.

    Usage
    -----
    >>> orch = DecisionOrchestrator()
    >>> artifacts = orch.run_build_mode("Eco water bottle for SEA", "EcoBrand")
    >>> pipeline_input = orch.convert_to_pipeline_input(artifacts)
    """

    _AGENT_REGISTRY: dict[str, type] = {
        "_diagnostic": DiagnosticAgent,
        "_brand_positioning": BrandPositioningAgent,
        "_market_research": MarketResearchAgent,
        "_audience_seg": AudienceSegmentationAgent,
        "_competitor_analysis": CompetitorAnalysisAgent,
        "_health_diagnosis": BrandHealthDiagnosisAgent,
        "_market_reval": MarketRevalidationAgent,
        "_audience_deepen": AudienceDeepeningAgent,
        "_competitor_track": CompetitorTrackingAgent,
        "_asset_audit": ContentAssetAuditAgent,
        "_product_opt": ProductOptimizationAgent,
        "_content_mkt": ContentMarketingAgent,
    }

    def __init__(self, hitl_config: Any = None) -> None:  # noqa: ANN401
        """Initialize orchestrator with optional HITL config.

        Parameters
        ----------
        hitl_config:
            Optional ``HITLConfig`` instance. When provided, the orchestrator
            uses ``NodeExecutor`` to delegate per-node human/agent routing.
            When ``None``, all nodes run in agent mode (default).
        """
        self._hitl_config = hitl_config
        self._executor: Any = None
        if hitl_config is not None and NodeExecutor is not None:
            self._executor = NodeExecutor(hitl_config)

        # Agents are lazily instantiated on first access via __getattr__.

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        cls = self._AGENT_REGISTRY.get(name)
        if cls is None:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        instance = cls()
        object.__setattr__(self, name, instance)
        return instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Internal: node execution with optional HITL routing
    # ------------------------------------------------------------------

    def _run_node(
        self,
        node_name: str,
        agent: Any,  # noqa: ANN401
        context: dict[str, Any],
        asset_library: Any = None,  # noqa: ANN401
    ) -> DecisionArtifact | None:
        """Execute a node, optionally through the HITL executor."""
        if self._executor is not None:
            return self._executor.execute(node_name, agent, context, asset_library)
        return agent.execute(context, asset_library)

    def run_build_mode(
        self,
        idea: str,
        brand: str,
        market: str = "",
    ) -> list[DecisionArtifact]:
        """Run the full Build-mode Decision Layer.

        Steps: Diagnostic → (BrandPositioning + MarketResearch) →
        (AudienceSegmentation + CompetitorAnalysis) → Strategy Engine.

        Returns a list of all DecisionArtifacts produced.
        """
        artifacts: list[DecisionArtifact] = []

        # Phase 0: Diagnostic
        ctx: dict[str, Any] = {"idea": idea, "market": market, "stage": "new"}
        brief = self._diagnostic.execute(ctx, None)
        artifacts.append(brief)

        mode = brief.content.get("mode", "build")

        # Phase 1-B: Parallel analysis agents
        bp_ctx = {**ctx, "mode": mode}
        bp = self._brand_positioning.execute(bp_ctx, None)
        artifacts.append(bp)

        mr_ctx = {**ctx, "mode": mode}
        if bp.content.get("brand_name"):
            mr_ctx["brand_name"] = bp.content["brand_name"]
        mr = self._market_research.execute(mr_ctx, None)
        artifacts.append(mr)

        # Phase 1-B: Dependent agents (need positioning + research)
        as_ctx = {**ctx, **bp.content, "market_report": mr.content}
        as_ = self._audience_seg.execute(as_ctx, None)
        artifacts.append(as_)

        ca_ctx = {**ctx, "market_report": mr.content}
        ca = self._competitor_analysis.execute(ca_ctx, None)
        artifacts.append(ca)

        # Phase 2: Strategy Engine (converged)
        strategy_ctx = {
            "brand_dna": bp.content,
            "market_report": mr.content,
            "persona_map": as_.content,
            "competitor_matrix": ca.content,
        }
        po = self._product_opt.execute(strategy_ctx, None)
        artifacts.append(po)

        cm = self._content_mkt.execute(strategy_ctx, None)
        artifacts.append(cm)

        return artifacts

    def run_scale_mode(
        self,
        brand_name: str,
        market: str = "",
    ) -> list[DecisionArtifact]:
        """Run the full Scale-mode Decision Layer.

        Steps: Diagnostic → (HealthDiagnosis + MarketRevalidation + AudienceDeepening
        + CompetitorTracking + ContentAssetAudit) → Strategy Engine.

        Returns a list of all DecisionArtifacts produced.
        """
        artifacts: list[DecisionArtifact] = []

        # Phase 0: Diagnostic (existing brand)
        ctx: dict[str, Any] = {"idea": brand_name, "market": market, "stage": "existing"}
        brief = self._diagnostic.execute(ctx, None)
        artifacts.append(brief)

        # Phase 1-S: Parallel scale agents
        for agent in [
            self._health_diagnosis,
            self._market_reval,
            self._audience_deepen,
            self._competitor_track,
            self._asset_audit,
        ]:
            a_ctx = {**ctx, "brand_name": brand_name, "mode": "scale"}
            result = agent.execute(a_ctx, None)
            artifacts.append(result)

        # Phase 2: Strategy Engine (converged)
        # Extract key findings from scale artifacts for strategy
        health_report = artifacts[1].content if len(artifacts) > 1 else {}
        market_scan = artifacts[2].content if len(artifacts) > 2 else {}
        deepening = artifacts[3].content if len(artifacts) > 3 else {}
        tracking = artifacts[4].content if len(artifacts) > 4 else {}
        asset_audit_data = artifacts[5].content if len(artifacts) > 5 else {}

        strategy_ctx = {
            "brand_name": brand_name,
            "health_report": health_report,
            "market_scan": market_scan,
            "audience_deepening": deepening,
            "competitor_tracking": tracking,
            "asset_audit": asset_audit_data,
        }
        po = self._product_opt.execute(strategy_ctx, None)
        artifacts.append(po)

        cm = self._content_mkt.execute(strategy_ctx, None)
        artifacts.append(cm)

        return artifacts

    def run_strategy_engine(
        self,
        analysis_artifacts: list[DecisionArtifact],
    ) -> list[DecisionArtifact]:
        """Execute the Strategy Engine (phase 2) on pre-collected analysis artifacts.

        This is the convergence point for both Build and Scale modes.
        """
        strategy_ctx: dict[str, Any] = {}
        for art in analysis_artifacts:
            strategy_ctx[art.artifact_type] = art.content

        po = self._product_opt.execute(strategy_ctx, None)
        cm = self._content_mkt.execute(strategy_ctx, None)
        return [po, cm]

    def convert_to_pipeline_input(
        self,
        artifacts: list[DecisionArtifact],
    ) -> dict[str, Any]:
        """Convert Decision Layer artifacts into ``pipeline.run_full_pipeline()`` input.

        Returns a dict with keys ``topic``, ``brand``, and optionally
        ``mode``, ``default_lang``, etc.
        """
        brief = None
        brand_dna = None
        strategy = None

        for art in artifacts:
            if art.artifact_type == "brief":
                brief = art.content
            elif art.artifact_type == "brand_dna":
                brand_dna = art.content
            elif art.artifact_type == "strategy_doc":
                strategy = art.content

        topic = ""
        if brief:
            topic = brief.get("idea", "")
        if strategy:
            # Use first content pillar as topic if available
            pillars = strategy.get("content_pillars", [])
            if pillars and not topic:
                topic = (
                    pillars[0].get("name", "") if isinstance(pillars[0], dict) else str(pillars[0])
                )

        brand_name = brand_dna.get("brand_name", "") if brand_dna else ""
        if not brand_name and brief:
            brand_name = brief.get("brand", "")

        mode = brief.get("mode", "auto") if brief else "auto"

        return {
            "topic": topic or "Default topic",
            "brand": brand_name or "default",
            "mode": mode,
        }
