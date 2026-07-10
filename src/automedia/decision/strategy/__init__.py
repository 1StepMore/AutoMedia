"""Strategy Engine Decision Agents — go-to-market and content orchestration.

Exports
-------
- ``ProductOptimizationAgent`` — product positioning, feature prioritisation, localisation
- ``ContentMarketingAgent`` — message house, content pillars, channel matrix, calendar
"""

from __future__ import annotations

from automedia.decision.strategy.content_marketing import ContentMarketingAgent
from automedia.decision.strategy.product_optimization import ProductOptimizationAgent

__all__ = [
    "ContentMarketingAgent",
    "ProductOptimizationAgent",
]
