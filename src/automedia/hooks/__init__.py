"""Gate lifecycle hooks — read-only observers for gate execution events.

Hooks implement the GateHook protocol and are notified before/after every
gate execution and on gate failure.  Hooks must never mutate context or
interfere with pipeline execution.
"""

from structlog import get_logger

from automedia.hooks.cost_tracker import CostTracker

log = get_logger(__name__)
from automedia.hooks.md5_tracker import get_pipeline_md5, record_md5, verify_md5
from automedia.hooks.metrics import MetricsHook
from automedia.hooks.pipeline_history import PipelineHistoryHook
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
