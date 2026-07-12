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

from automedia.core._import_helpers import warn_missing_optional
from automedia.decision.base import BaseDecisionAgent, DecisionArtifact
from automedia.decision.diagnostic import DiagnosticAgent
from automedia.decision.gates import D0Gate

try:
    from automedia.decision.orchestrator import DecisionOrchestrator
except ImportError:
    warn_missing_optional("decision.orchestrator", feature="DecisionOrchestrator disabled")
    DecisionOrchestrator = None  # type: ignore[assignment,misc]

# Build agents
try:
    from automedia.decision.build import (
        AudienceSegmentationAgent,
        BrandPositioningAgent,
        CompetitorAnalysisAgent,
        MarketResearchAgent,
    )
except ImportError:
    warn_missing_optional("decision.build", feature="Build agents disabled")
    BrandPositioningAgent = None  # type: ignore[assignment,misc]
    MarketResearchAgent = None  # type: ignore[assignment,misc]
    AudienceSegmentationAgent = None  # type: ignore[assignment,misc]
    CompetitorAnalysisAgent = None  # type: ignore[assignment,misc]

# Scale agents
try:
    from automedia.decision.scale import (
        AudienceDeepeningAgent,
        BrandHealthDiagnosisAgent,
        CompetitorTrackingAgent,
        ContentAssetAuditAgent,
        MarketRevalidationAgent,
    )
except ImportError:
    warn_missing_optional("decision.scale", feature="Scale agents disabled")
    BrandHealthDiagnosisAgent = None  # type: ignore[assignment,misc]
    MarketRevalidationAgent = None  # type: ignore[assignment,misc]
    AudienceDeepeningAgent = None  # type: ignore[assignment,misc]
    CompetitorTrackingAgent = None  # type: ignore[assignment,misc]
    ContentAssetAuditAgent = None  # type: ignore[assignment,misc]

# Strategy agents
try:
    from automedia.decision.strategy import (
        ContentMarketingAgent,
        ProductOptimizationAgent,
    )
except ImportError:
    warn_missing_optional("decision.strategy", feature="Strategy agents disabled")
    ProductOptimizationAgent = None  # type: ignore[assignment,misc]
    ContentMarketingAgent = None  # type: ignore[assignment,misc]

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
