"""Director HITL preset — human review at every key gate.

The DirectorPreset defines 8 review nodes that map to pipeline gates
where a human director should review and approve before the pipeline
proceeds.  Each node has ``requires_approval=True`` and a 1-hour
timeout.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Director preset node definitions
# ---------------------------------------------------------------------------

DIRECTOR_NODES: list[dict[str, Any]] = [
    {
        "name": "topic_selection",
        "autoset": "human",
        "requires_approval": True,
        "timeout": 3600,
        "description": "Review topic selection before content generation",
    },
    {
        "name": "cw_output",
        "autoset": "human",
        "requires_approval": True,
        "timeout": 3600,
        "description": "Approve/reject content writer draft",
    },
    {
        "name": "g2_copy_review",
        "autoset": "human",
        "requires_approval": True,
        "timeout": 3600,
        "description": "Approve/reject copy review results",
    },
    {
        "name": "v0_lint",
        "autoset": "human",
        "requires_approval": True,
        "timeout": 3600,
        "description": "Approve/reject HTML lint output",
    },
    {
        "name": "v1_vision_qa",
        "autoset": "human",
        "requires_approval": True,
        "timeout": 3600,
        "description": "Approve/reject vision quality assurance",
    },
    {
        "name": "v2_subtitle",
        "autoset": "human",
        "requires_approval": True,
        "timeout": 3600,
        "description": "Approve/reject subtitle rendering",
    },
    {
        "name": "l2_archive",
        "autoset": "human",
        "requires_approval": True,
        "timeout": 3600,
        "description": "Approve/reject archive validation",
    },
    {
        "name": "l3_publish",
        "autoset": "human",
        "requires_approval": True,
        "timeout": 3600,
        "description": "Approve/reject publish per platform",
    },
]


class DirectorPreset:
    """Director HITL preset — human-in-the-loop at every key gate.

    Provides structured node definitions for the ``"director"`` preset
    used by ``HITLConfig``.  Each node maps to a pipeline gate that
    requires human approval (1-hour timeout) before the pipeline
    continues.

    Usage
    -----
    >>> from automedia.hitl.presets.director import DirectorPreset
    >>> preset = DirectorPreset()
    >>> nodes = preset.list_nodes()
    >>> len(nodes)
    8
    """

    PRESET_NAME = "director"

    def __init__(self) -> None:
        """Initialize the director preset with 8 review nodes."""
        self._nodes: list[dict[str, Any]] = list(DIRECTOR_NODES)

    def list_nodes(self) -> list[dict[str, Any]]:
        """Return all review node definitions."""
        return list(self._nodes)

    def get_node(self, name: str) -> dict[str, Any] | None:
        """Return a single node definition by *name*, or ``None``."""
        for node in self._nodes:
            if node["name"] == name:
                return dict(node)
        return None
