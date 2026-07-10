"""HITL Framework — Human-In-The-Loop configuration and executor.

Exports
-------
- ``HITLConfig`` — preset + override config loader
- ``NodeExecutor`` — agent / human mode executor with approval & skip
"""

from __future__ import annotations

from automedia.hitl.config import HITLConfig
from automedia.hitl.executor import NodeExecutor

__all__ = ["HITLConfig", "NodeExecutor"]
