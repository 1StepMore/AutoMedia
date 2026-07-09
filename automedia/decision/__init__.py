"""Decision Layer — brand intelligence and strategy agents.

Exports
-------
- ``DecisionOrchestrator`` — top-level orchestrator (full mode routing)
- ``BaseDecisionAgent`` — abstract base for all agents
- ``DecisionArtifact`` — structured artifact dataclass
- ``DiagnosticAgent`` — phase-0 questionnaire / routing / asset scan
- ``D0Gate`` — Decision-Layer provenance gate (Red Line 9)
- All Build / Scale / Strategy agents
"""

from __future__ import annotations

from automedia.decision.base import BaseDecisionAgent, DecisionArtifact
from automedia.decision.diagnostic import DiagnosticAgent

try:
    from automedia.decision.gates.d0_gate import D0Gate
except ImportError:
    D0Gate = None  # type: ignore[assignment,misc]

try:
    from automedia.decision.orchestrator import DecisionOrchestrator
except ImportError:
    DecisionOrchestrator = None  # type: ignore[assignment,misc]

# Build agents
try:
    from automedia.decision.build import (
        BrandPositioningAgent,
        MarketResearchAgent,
        AudienceSegmentationAgent,
        CompetitorAnalysisAgent,
    )
except ImportError:
    BrandPositioningAgent = None  # type: ignore[assignment,misc]
    MarketResearchAgent = None
    AudienceSegmentationAgent = None
    CompetitorAnalysisAgent = None

# Scale agents
try:
    from automedia.decision.scale import (
        BrandHealthDiagnosisAgent,
        MarketRevalidationAgent,
        AudienceDeepeningAgent,
        CompetitorTrackingAgent,
        ContentAssetAuditAgent,
    )
except ImportError:
    BrandHealthDiagnosisAgent = None
    MarketRevalidationAgent = None
    AudienceDeepeningAgent = None
    CompetitorTrackingAgent = None
    ContentAssetAuditAgent = None

# Strategy agents
try:
    from automedia.decision.strategy import (
        ProductOptimizationAgent,
        ContentMarketingAgent,
    )
except ImportError:
    ProductOptimizationAgent = None
    ContentMarketingAgent = None

__all__ = [
    "BaseDecisionAgent",
    "DecisionArtifact",
    "DecisionOrchestrator",
    "DiagnosticAgent",
    "D0Gate",
    "BrandPositioningAgent",
    "MarketResearchAgent",
    "AudienceSegmentationAgent",
    "CompetitorAnalysisAgent",
    "BrandHealthDiagnosisAgent",
    "MarketRevalidationAgent",
    "AudienceDeepeningAgent",
    "CompetitorTrackingAgent",
    "ContentAssetAuditAgent",
    "ProductOptimizationAgent",
    "ContentMarketingAgent",
]