"""AutoMedia — automated media production pipeline with Decision Layer."""

import warnings

from automedia._version import __version__

# Configure structured logging at import time.
try:
    from automedia.core.logging import configure_structlog

    configure_structlog()
except ImportError:
    pass

from automedia.gates.base import GateRegistry
from automedia.hooks.protocol import GateHook
from automedia.pipelines.gate_engine import (
    AssetInfo,
    GateEngine,
    GateLogEntry,
    Pipeline,
    PipelineProgress,
    PipelineResult,
)
from automedia.pipelines.runner import run_full_pipeline

# Decision Layer (PRD-3) — optional imports
try:
    from automedia.asset_library import AssetLibrary
except ImportError:
    warnings.warn(
        "AssetLibrary not available. Install with: pip install automedia[omni]",
        ImportWarning,
        stacklevel=2,
    )
    AssetLibrary = None  # type: ignore[assignment,misc]

try:
    from automedia.decision import BaseDecisionAgent, DecisionArtifact, DecisionOrchestrator
except ImportError:
    warnings.warn(
        "DecisionLayer not available. Install with: pip install automedia[omni]",
        ImportWarning,
        stacklevel=2,
    )
    DecisionOrchestrator = None  # type: ignore[assignment,misc]
    BaseDecisionAgent = None  # type: ignore[assignment,misc]
    DecisionArtifact = None  # type: ignore[assignment,misc]

__all__ = [
    "AssetInfo",
    "AssetLibrary",
    "GateRegistry",
    "BaseDecisionAgent",
    "DecisionArtifact",
    "DecisionOrchestrator",
    "GateEngine",
    "GateHook",
    "GateLogEntry",
    "Pipeline",
    "PipelineProgress",
    "PipelineResult",
    "run_full_pipeline",
    "__version__",
]
