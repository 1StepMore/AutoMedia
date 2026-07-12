"""Decision Layer.

Exports
-------
- ``DecisionArtifact`` — structured artifact dataclass.
"""

from __future__ import annotations

from automedia.decision.base import DecisionArtifact

# Pydantic models for MCP tool output validation
from automedia.decision import pydantic  # noqa: F401  # export submodule

__all__ = [
    "DecisionArtifact",
]
