"""HITL Framework — Protocols for dependency inversion.

Defines the ``NodeProvider`` protocol that the Decision layer (or any
other source) implements to supply node metadata to the HITL framework
without creating a hard import dependency.
"""

from __future__ import annotations

from typing import Any, Protocol


class NodeProvider(Protocol):
    """Abstract source of decision node metadata.

    Any object that exposes a ``list_all_nodes()`` method returning a
    list of node dicts satisfies this protocol.
    """

    def list_all_nodes(self) -> list[dict[str, Any]]: ...
