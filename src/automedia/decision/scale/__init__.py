"""Scale-mode Decision Agents — deep brand intelligence.

Exports
-------
- ``BrandHealthDiagnosisAgent`` — 5-dimension brand health audit
- ``MarketRevalidationAgent`` — market trend scan & opportunity mapping
- ``AudienceDeepeningAgent`` — persona cluster analysis
- ``CompetitorTrackingAgent`` — competitive landscape surveillance
- ``ContentAssetAuditAgent`` — content inventory & gap analysis
"""

from __future__ import annotations

from automedia.decision.scale.audience_deepening import AudienceDeepeningAgent
from automedia.decision.scale.brand_health_diagnosis import BrandHealthDiagnosisAgent
from automedia.decision.scale.competitor_tracking import CompetitorTrackingAgent
from automedia.decision.scale.content_asset_audit import ContentAssetAuditAgent
from automedia.decision.scale.market_revalidation import MarketRevalidationAgent

__all__ = [
    "AudienceDeepeningAgent",
    "BrandHealthDiagnosisAgent",
    "CompetitorTrackingAgent",
    "ContentAssetAuditAgent",
    "MarketRevalidationAgent",
]
