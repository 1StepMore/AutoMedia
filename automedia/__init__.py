"""AutoMedia — automated media production pipeline with Decision Layer."""

from automedia._version import __version__
from automedia.hooks.protocol import GateHook
from automedia.pipelines.gate_engine import (
    AssetInfo,
    GateEngine,
    GateLogEntry,
    Pipeline,
    PipelineResult,
)
from automedia.pipelines.runner import run_full_pipeline

# Decision Layer (PRD-3) — optional imports
try:
    from automedia.asset_library import AssetLibrary
except ImportError:
    AssetLibrary = None  # type: ignore[assignment,misc]

try:
    from automedia.decision import DecisionOrchestrator, BaseDecisionAgent, DecisionArtifact
except ImportError:
    DecisionOrchestrator = None
    BaseDecisionAgent = None
    DecisionArtifact = None

__all__ = [
    "AssetInfo",
    "AssetLibrary",
    "BaseDecisionAgent",
    "DecisionArtifact",
    "DecisionOrchestrator",
    "GateEngine",
    "GateHook",
    "GateLogEntry",
    "Pipeline",
    "PipelineResult",
    "run_full_pipeline",
    "__version__",
]
