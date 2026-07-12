"""HITL Framework — Human-In-The-Loop configuration and executor.

Exports
-------
- ``HITLConfig`` — preset + override config loader
- ``NodeExecutor`` — agent / human mode executor with approval & skip
- ``NodeProvider`` — protocol for injecting decision node metadata
"""

from __future__ import annotations

from automedia.hitl.config import HITLConfig
from automedia.hitl.executor import NodeExecutor
from automedia.hitl.protocol import NodeProvider

__all__ = ["HITLConfig", "NodeExecutor", "NodeProvider"]
