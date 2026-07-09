"""Decision Layer base abstractions.

Public API
----------
- ``BaseDecisionAgent`` — abstract base for all Decision Agents
- ``DecisionArtifact`` — structured artifact dataclass
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class BaseDecisionAgent(ABC):
    """Abstract base for all Decision Layer agents."""

    @abstractmethod
    def name(self) -> str:
        """Agent name for registry and logging."""
        ...

    @abstractmethod
    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any,  # AssetLibrary | None
    ) -> DecisionArtifact:
        """Run agent inference and return a structured artifact."""
        ...

    def search_asset_library(
        self,
        brand: str,
        query: str,
        filters: dict[str, Any] | None = None,
    ) -> list[Any]:
        """Auto-retrieve relevant docs from Asset Library before inference."""
        try:
            from automedia.asset_library import AssetLibrary

            library = AssetLibrary(brand=brand)
            return library.search(query=query, filters=filters or {})
        except Exception:
            return []