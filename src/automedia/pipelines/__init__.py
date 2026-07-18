"""Pipeline orchestration — runner, gate engine, and audio/image sub-pipelines.

All heavy imports are deferred via __getattr__ to improve CLI cold-start time.
Accessing ``automedia.pipelines.<name>`` triggers the lazy import for *name*
on first access.
"""

from typing import Any

__all__ = [
    "AssetInfo",
    "AudioPipeline",
    "GateEngine",
    "GateLogEntry",
    "ImagePipeline",
    "ImageValidator",
    "Pipeline",
    "PipelineResult",
    "VisionQADegradation",
    "run_full_pipeline",
]


_LAZY_MAP: dict[str, tuple[str, str]] = {
    "AudioPipeline": ("automedia.pipelines.audio_pipeline", "AudioPipeline"),
    "AssetInfo": ("automedia.pipelines.gate_engine", "AssetInfo"),
    "GateEngine": ("automedia.pipelines.gate_engine", "GateEngine"),
    "GateLogEntry": ("automedia.pipelines.gate_engine", "GateLogEntry"),
    "Pipeline": ("automedia.pipelines.gate_engine", "Pipeline"),
    "PipelineResult": ("automedia.pipelines.gate_engine", "PipelineResult"),
    "ImagePipeline": ("automedia.pipelines.image_pipeline", "ImagePipeline"),
    "ImageValidator": ("automedia.pipelines.image_pipeline", "ImageValidator"),
    "VisionQADegradation": ("automedia.pipelines.image_pipeline", "VisionQADegradation"),
    "run_full_pipeline": ("automedia.pipelines.runner", "run_full_pipeline"),
}


def __getattr__(name: str) -> Any:
    """Lazy-import pipeline names on first attribute access."""
    if name in _LAZY_MAP:
        import importlib

        mod_path, attr_name = _LAZY_MAP[name]
        mod = importlib.import_module(mod_path)
        return getattr(mod, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
