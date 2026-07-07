"""AutoMedia — automated media production pipeline."""

from automedia._version import __version__
from automedia.hooks.protocol import GateHook
from automedia.pipelines.gate_engine import Pipeline, PipelineResult
from automedia.pipelines.runner import run_full_pipeline

__all__ = [
    "Pipeline",
    "PipelineResult",
    "GateHook",
    "run_full_pipeline",
    "__version__",
]
