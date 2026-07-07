"""Gate hook protocol — stub."""

from typing import Any, Protocol


class GateHook(Protocol):
    """Protocol for gate hooks."""

    def __call__(self, context: dict[str, Any]) -> dict[str, Any]:
        ...
