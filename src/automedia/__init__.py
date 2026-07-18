"""AutoMedia — automated media production pipeline."""

from automedia._version import __version__
from automedia.exceptions import (
    AccountError,
    AdapterError,
    AutoMediaError,
    ConfigError,
    GateError,
    PipelineError,
)

# Configure structured logging at import time.
try:
    from automedia.core.logging import configure_structlog

    configure_structlog()
except ImportError:
    pass

from automedia.core.media_spec import PlatformMediaSpec, get_platform_media_spec
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
    "AccountError",
    "AdapterError",
    "AssetInfo",
    "AutoMediaError",
    "ConfigError",
    "DecisionArtifact",
    "GateEngine",
    "GateError",
    "GateHook",
    "GateLogEntry",
    "GateRegistry",
    "Pipeline",
    "PipelineError",
    "PipelineProgress",
    "PipelineResult",
    "PlatformMediaSpec",
    "get_platform_media_spec",
    "run_full_pipeline",
    "__version__",
]
