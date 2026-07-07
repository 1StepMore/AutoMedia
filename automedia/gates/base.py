"""Base gate abstraction for AutoMedia pipelines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class GateRegistry:
    """Singleton registry that auto-registers BaseGate subclasses by gate_name."""

    _gates: dict[str, type["BaseGate"]] = {}

    # Singleton instance — module-level code uses the module variable directly.
    def __new__(cls) -> "GateRegistry":
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls)
            cls._instance._gates = {}
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def register(self, gate_cls: type["BaseGate"]) -> None:
        """Register a BaseGate subclass under its ``gate_name``."""
        name: str = gate_cls._gate_name  # type: ignore[attr-defined]
        if name in self._gates:
            raise KeyError(f"Gate '{name}' is already registered by {self._gates[name]}")
        self._gates[name] = gate_cls

    def get(self, gate_name: str) -> type["BaseGate"]:
        """Look up a gate class by name."""
        if gate_name not in self._gates:
            raise KeyError(f"Gate '{gate_name}' is not registered. Available: {list(self._gates)}")
        return self._gates[gate_name]

    def list(self) -> list[str]:
        """Return sorted list of registered gate names."""
        return sorted(self._gates)

    def get_all(self) -> dict[str, type["BaseGate"]]:
        """Return a copy of the full name→class mapping."""
        return dict(self._gates)

    def __contains__(self, name: str) -> bool:
        return name in self._gates

    def __len__(self) -> int:
        return len(self._gates)

    def __repr__(self) -> str:
        return f"GateRegistry({len(self)} gates: {', '.join(self.list())})"


# Module-level singleton — used by __init_subclass__
_registry: GateRegistry = GateRegistry()


class BaseGate(ABC):
    """Abstract base for every pipeline gate.

    Every concrete subclass **must** define:
    - ``gate_name`` as a class-level string (e.g. ``"G0"``)
    - ``failure_mode`` as a class-level string (e.g. ``"stop"``)
    - ``execute(self, gate_context: dict) -> dict``

    Subclasses are automatically registered in the module-level
    ``_registry`` singleton via ``__init_subclass__``.
    """

    @property
    def gate_name(self) -> str:
        """Human/short identifier for this gate (e.g. ``"G0"``)."""
        try:
            return self._gate_name
        except AttributeError:
            raise NotImplementedError(
                f"{type(self).__name__} must define class-level '_gate_name'"
            )

    @gate_name.setter
    def gate_name(self, _value: str) -> None:
        raise AttributeError("gate_name is read-only")

    @property
    def failure_mode(self) -> str:
        """Behaviour when this gate fails — ``"stop"`` aborts the pipeline."""
        try:
            return self._failure_mode
        except AttributeError:
            raise NotImplementedError(
                f"{type(self).__name__} must define class-level '_failure_mode'"
            )

    @failure_mode.setter
    def failure_mode(self, _value: str) -> None:
        raise AttributeError("failure_mode is read-only")

    # -- Required method ---------------------------------------------------

    @abstractmethod
    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
        """Execute the gate's core logic.

        Args:
            gate_context: Pipeline context passed from the previous gate.

        Returns:
            A dictionary representing the gate result (may augment context
            for downstream gates).
        """
        ...

    # -- Automatic registration -------------------------------------------

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Auto-register concrete subclasses in the global registry."""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "_gate_name") and hasattr(cls, "_failure_mode"):
            _registry.register(cls)

    # -- String representations -------------------------------------------

    def __str__(self) -> str:
        return f"{self.gate_name}"

    def __repr__(self) -> str:
        return f"<{type(self).__name__} gate_name={self.gate_name!r} failure_mode={self.failure_mode!r}>"
