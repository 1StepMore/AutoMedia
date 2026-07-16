"""Shared mutable state for the MCP server.

Contains the global pipeline tracker, its lock, and the server start
timestamp.  Extracted into a dedicated module so that ``tools.py`` and
``server.py`` can both access the same objects without circular imports.
"""

from __future__ import annotations

import threading
import time

from structlog import get_logger

from automedia.pipelines.gate_engine import PipelineProgress

log = get_logger(__name__)

# Global tracker: project_id → PipelineProgress for agent polling.
# Thread-safe via _lock (background pipeline thread vs. MCP query thread).
_pipeline_tracker: dict[str, PipelineProgress] = {}
_lock = threading.Lock()

# Server start timestamp for health-check uptime reporting.
_SERVER_START: float = time.monotonic()
