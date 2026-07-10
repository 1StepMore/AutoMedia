"""Gate hook protocol — readonly observer for gate lifecycle events."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GateHook(Protocol):
    """Protocol for gate hooks.

    All methods are readonly observers — they receive context but MUST NOT
    mutate anything or skip gate execution. Every method returns None.
    """

    def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
        """Called before a gate is executed.

        Args:
            gate_name: Name of the gate about to run.
            context: Current gate context (readonly).
        """
        ...

    def after_gate(self, gate_name: str, context: dict[str, Any], result: dict[str, Any]) -> None:
        """Called after a gate completes successfully.

        Args:
            gate_name: Name of the gate that ran.
            context: Current gate context (readonly).
            result: The result produced by the gate (readonly).
        """
        ...

    def on_gate_failed(self, gate_name: str, context: dict[str, Any], error: Exception) -> None:
        """Called when a gate raises an exception.

        Args:
            gate_name: Name of the gate that failed.
            context: Current gate context (readonly).
            error: The exception that was raised (readonly).
        """
        ...


class GateObserver:
    """Default no-op implementation of GateHook.

    Subclass and override only the methods you need.
    """

    def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
        return None

    def after_gate(self, gate_name: str, context: dict[str, Any], result: dict[str, Any]) -> None:
        return None

    def on_gate_failed(self, gate_name: str, context: dict[str, Any], error: Exception) -> None:
        return None
