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


def __getattr__(name: str):
    """Lazy-import heavy sub-modules on first attribute access."""
    _lazy: dict[str, tuple[str, str]] = {
        "AssetInfo": ("automedia.pipelines.gate_engine", "AssetInfo"),
        "DecisionArtifact": ("automedia.decision.base", "DecisionArtifact"),
        "GateEngine": ("automedia.pipelines.gate_engine", "GateEngine"),
        "GateHook": ("automedia.hooks.protocol", "GateHook"),
        "GateLogEntry": ("automedia.pipelines.gate_engine", "GateLogEntry"),
        "GateRegistry": ("automedia.gates.base", "GateRegistry"),
        "Pipeline": ("automedia.pipelines.gate_engine", "Pipeline"),
        "PipelineProgress": ("automedia.pipelines.gate_engine", "PipelineProgress"),
        "PipelineResult": ("automedia.pipelines.gate_engine", "PipelineResult"),
        "PlatformMediaSpec": ("automedia.core.media_spec", "PlatformMediaSpec"),
        "get_platform_media_spec": ("automedia.core.media_spec", "get_platform_media_spec"),
        "run_full_pipeline": ("automedia.pipelines.runner", "run_full_pipeline"),
    }
    if name in _lazy:
        import importlib  # noqa: PLC0415
        mod_path, attr = _lazy[name]
        mod = importlib.import_module(mod_path)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
