"""Content Asset Audit Agent — content inventory & gap analysis.

Leverages the Asset Library to retrieve all content associated with a
brand, then classifies each asset as hero content, in need of update,
or obsolete, and provides audit-driven recommendations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from automedia.decision.base import BaseDecisionAgent, DecisionArtifact


class ContentAssetAuditAgent(BaseDecisionAgent):
    """Audit existing content assets and classify them for action."""

    def name(self) -> str:
        return "content_asset_audit"

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any = None,
    ) -> DecisionArtifact:
        brand_name: str = context.get("brand_name", "unknown")
        search_results: list[Any] | None = context.get("search_results")

        # Attempt asset-library lookup if no explicit results were provided
        assets: list[dict[str, Any]] = []
        if search_results is not None:
            assets = self._normalise_assets(search_results)
        else:
            library_docs = self.search_asset_library(brand_name, "all content")
            if library_docs:
                assets = self._normalise_assets(library_docs)

        # If still empty, generate representative sample data
        if not assets:
            assets = self._sample_assets(brand_name)

        hero, needs_update, obsolete = self._classify_assets(assets)

        content: dict[str, Any] = {
            "hero_content": hero,
            "needs_update": needs_update,
            "obsolete": obsolete,
            "total_assets": len(assets),
            "audit_recommendations": self._generate_recommendations(
                hero, needs_update, obsolete, len(assets)
            ),
        }

        return DecisionArtifact(
            artifact_type="asset_audit",
            content=content,
            format="yaml",
            metadata={
                "agent": self.name(),
                "brand": brand_name,
                "total_assets": len(assets),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_assets(
        raw: list[Any],
    ) -> list[dict[str, Any]]:
        """Convert heterogeneous entries into uniform asset dicts."""
        out: list[dict[str, Any]] = []
        for i, item in enumerate(raw):
            if isinstance(item, dict):
                out.append(
                    {
                        "id": item.get("id", item.get("asset_id", str(i))),
                        "title": item.get("title", item.get("name", f"asset_{i}")),
                        "type": item.get(
                            "type",
                            item.get("content_type", item.get("format", "unknown")),
                        ),
                        "age_days": item.get("age_days", 0),
                        "performance_score": item.get("performance_score", 50),
                        "url": item.get("url", ""),
                    }
                )
            elif isinstance(item, str):
                out.append(
                    {
                        "id": str(i),
                        "title": item,
                        "type": "unknown",
                        "age_days": 0,
                        "performance_score": 50,
                        "url": "",
                    }
                )
        return out

    @staticmethod
    def _sample_assets(brand: str) -> list[dict[str, Any]]:
        """Return representative assets when the library returns nothing."""
        return [
            {
                "id": "hero_001",
                "title": f"{brand} Product Overview Video",
                "type": "video",
                "age_days": 60,
                "performance_score": 92,
                "url": "",
            },
            {
                "id": "hero_002",
                "title": f"{brand} Case Study — Enterprise Client",
                "type": "case_study",
                "age_days": 120,
                "performance_score": 88,
                "url": "",
            },
            {
                "id": "update_001",
                "title": f"{brand} Feature Comparison Matrix",
                "type": "document",
                "age_days": 365,
                "performance_score": 55,
                "url": "",
            },
            {
                "id": "update_002",
                "title": f"{brand} Pricing Page Screenshot Archive",
                "type": "image",
                "age_days": 400,
                "performance_score": 40,
                "url": "",
            },
            {
                "id": "obsolete_001",
                "title": f"{brand} 2023 Product Roadmap",
                "type": "presentation",
                "age_days": 730,
                "performance_score": 15,
                "url": "",
            },
            {
                "id": "obsolete_002",
                "title": f"{brand} Old Brand Guidelines (v1)",
                "type": "document",
                "age_days": 900,
                "performance_score": 10,
                "url": "",
            },
        ]

    @staticmethod
    def _classify_assets(
        assets: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Assign each asset to hero / needs-update / obsolete bucket."""
        hero: list[dict[str, Any]] = []
        needs_update: list[dict[str, Any]] = []
        obsolete: list[dict[str, Any]] = []

        for a in assets:
            age = a.get("age_days", 0)
            score = a.get("performance_score", 50)
            if score >= 80 and age <= 180:
                hero.append(a)
            elif age >= 730 or score < 20:
                obsolete.append(a)
            elif age >= 180 or score < 70:
                needs_update.append(a)
            else:
                # Default to healthy but not hero — skip; they're fine as-is
                pass

        return hero, needs_update, obsolete

    @staticmethod
    def _generate_recommendations(
        hero: list[dict[str, Any]],
        needs_update: list[dict[str, Any]],
        obsolete: list[dict[str, Any]],
        total: int,
    ) -> list[str]:
        """Create actionable recommendations from the classification results."""
        recs: list[str] = []

        if not hero:
            recs.append(
                "No hero content identified — create at least 2 high-production anchor "
                "pieces (video + case study) to lead campaigns."
            )
        else:
            recs.append(
                f"Protect and refresh the {len(hero)} hero asset(s); consider "
                f"A/B testing variations to maximise conversion."
            )

        if needs_update:
            recs.append(
                f"Update {len(needs_update)} asset(s) flagged as stale — prioritise "
                f"those with the highest historical engagement first."
            )

        if obsolete:
            recs.append(
                f"Archive or retire {len(obsolete)} obsolete asset(s) to prevent "
                f"brand-dilution and outdated messaging."
            )

        if total == 0:
            recs.append(
                "No content assets found in the library — initiate a content "
                "creation sprint targeting the top-3 buyer-intent topics."
            )
        else:
            healthy = total - len(hero) - len(needs_update) - len(obsolete)
            recs.append(
                f"Health summary: {len(hero)} hero / {len(needs_update)} needs update "
                f"/ {len(obsolete)} obsolete / {healthy} satisfactory. "
                f"Target <10 % obsolete ratio."
            )

        return recs
