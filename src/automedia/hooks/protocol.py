"""Gate hook protocol — readonly observer for gate lifecycle events."""

from typing import Any, Protocol, runtime_checkable

from structlog import get_logger

log = get_logger(__name__)


@runtime_checkable
class GateHook(Protocol):
    """Protocol for gate hooks.

    All methods are readonly observers — they receive context but MUST NOT
    mutate anything or skip gate execution. Every method returns None.

    The context is a DEEP-detached copy (``GateContext.to_dict`` recurses into
    lists/dicts/tuples/sets), so a hook that mutates what it receives cannot
    affect the running pipeline.  Hook exceptions are caught and logged per
    hook: one misbehaving observer never aborts the run.
    """

    def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
        """Called before a gate is executed.

        Args:
            gate_name: Name of the gate about to run.
            context: Current gate context (readonly).
        """
        ...

    def after_gate(self, gate_name: str, context: dict[str, Any], result: dict[str, Any]) -> None:
        """Called after a gate returns a VERDICT — pass *or* fail.

        Despite the historical name, this is not "the gate succeeded": a gate
        that judged the artifact and rejected it also lands here, with
        ``result["passed"] is False``.  Read ``result["passed"]`` and
        ``result["status"]`` to tell the cases apart; never assume success.

        The distinction from :meth:`on_gate_failed` is deliberate and useful:
        * this method — the gate RAN and produced a verdict (including "fail");
        * ``on_gate_failed`` — the gate RAISED, so there is no verdict at all.

        Args:
            gate_name: Name of the gate that ran.
            context: Current gate context (readonly).
            result: The result produced by the gate (readonly).
        """
        ...

    def on_gate_failed(self, gate_name: str, context: dict[str, Any], error: Exception) -> None:
        """Called when a gate RAISES — no verdict was produced.

        This is not the "gate judged the artifact and failed" case; that one
        arrives at :meth:`after_gate` with ``passed=False``.

        Args:
            gate_name: Name of the gate that raised.
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
