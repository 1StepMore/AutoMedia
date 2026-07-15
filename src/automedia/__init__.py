"""AutoMedia — automated media production pipeline."""

from automedia._version import __version__

# Configure structured logging at import time.
try:
    from automedia.core.logging import configure_structlog

    configure_structlog()
except ImportError:
    pass

from automedia.decision.base import DecisionArtifact
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

__all__ = [
    "AssetInfo",
    "GateRegistry",
    "DecisionArtifact",
    "GateEngine",
    "GateHook",
    "GateLogEntry",
    "Pipeline",
    "PipelineProgress",
    "PipelineResult",
    "run_full_pipeline",
    "__version__",
]
