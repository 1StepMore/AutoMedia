"""Gate lifecycle hooks — read-only observers for gate execution events.

Hooks implement the GateHook protocol and are notified before/after every
gate execution and on gate failure.  Hooks must never mutate context or
interfere with pipeline execution.

Heavy imports are deferred via __getattr__ to improve CLI cold-start time.
"""

from typing import Any

from automedia.hooks.protocol import GateHook

__all__ = [
    "CostTracker",
    "GateHook",
    "get_pipeline_md5",
    "MetricsHook",
    "PipelineHistoryHook",
    "record_md5",
    "verify_md5",
]


_LAZY_MAP: dict[str, tuple[str, str]] = {
    "CostTracker": ("automedia.hooks.cost_tracker", "CostTracker"),
    "MetricsHook": ("automedia.hooks.metrics", "MetricsHook"),
    "PipelineHistoryHook": ("automedia.hooks.pipeline_history", "PipelineHistoryHook"),
    "get_pipeline_md5": ("automedia.hooks.md5_tracker", "get_pipeline_md5"),
    "record_md5": ("automedia.hooks.md5_tracker", "record_md5"),
    "verify_md5": ("automedia.hooks.md5_tracker", "verify_md5"),
}


def __getattr__(name: str) -> Any:
    """Lazy-import hook names on first attribute access."""
    if name in _LAZY_MAP:
        import importlib  # noqa: PLC0415
        mod_path, attr = _LAZY_MAP[name]
        mod = importlib.import_module(mod_path)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
