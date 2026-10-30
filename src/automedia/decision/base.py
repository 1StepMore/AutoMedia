"""DecisionArtifact — structured artifact dataclass.

DORMANT SCAFFOLD (plan A4): this dataclass has NO production producer or
consumer today (remediation plan / infrastructure-audit-20261030 §3.3); it
is kept as the type for a future decision-agent integration.  Do not build
new surfaces on it until the decision layer is wired.

Public API
----------
- ``DecisionArtifact`` — structured artifact dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class DecisionArtifact:
    """Structured artifact produced by a Decision Agent.

    Attributes
    ----------
    artifact_type:
        One of ``"brief"``, ``"brand_dna"``, ``"market_report"``,
        ``"persona_map"``, ``"competitor_matrix"``, ``"strategy_doc"``,
        ``"asset_blueprint"``, ``"content_calendar"``.
    content:
        Structured dictionary payload.
    format:
        Serialisation format — ``"yaml"``, ``"markdown"``, or ``"csv"``.
    metadata:
        Provenance information (source agent, timestamp, version, …).
    created_at:
        ISO-8601 timestamp of creation.
    """

    artifact_type: str
    content: dict[str, Any]
    format: str = "yaml"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
