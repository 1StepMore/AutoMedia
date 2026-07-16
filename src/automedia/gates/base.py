"""Base gate abstraction for AutoMedia pipelines."""

from __future__ import annotations

import re
import warnings
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from automedia.core.registry import BaseRegistry
from automedia.gates._context import GateContext

_VALID_GATE_NAME_RE = re.compile(r"^(D\d+|G\d+|V\d+|L\d+|H\d+|CW|pre-gate)$")
"""Regex for RL6-enforced gate naming convention: ``G0``–``G5``, ``V0``–``V7``,
``L1``–``L4``, ``H0``, ``CW``, ``pre-gate``."""


class GateRegistry(BaseRegistry):
    """Singleton registry that auto-registers BaseGate subclasses by gate_name.

    Inherits singleton lifecycle and CRUD from :class:`BaseRegistry`.
    Overrides :meth:`_validate` to enforce gate naming convention (RL6)
    and failure-mode coverage (RL7).
    """

    # ------------------------------------------------------------------
    # Validation hook
    # ------------------------------------------------------------------

    def _validate(self, key: str, value: type[BaseGate]) -> None:
        """Enforce RL6 naming convention and RL7 failure-mode coverage."""
        # RL6: Gate naming convention
        if not _VALID_GATE_NAME_RE.match(key):
            raise ValueError(
                f"Gate name {key!r} violates RL6 naming convention. "
                f"Expected pattern: G<digit>, V<digit>, L<digit>, D<digit>, "
                f"CW, or pre-gate."
            )

        if key in self._registry:
            raise KeyError(f"Gate '{key}' is already registered by {self._registry[key]}")

        # RL7: Every registered gate SHOULD have a failure-mode entry
        try:
            from automedia.gates.failure_modes import FAILURE_MODES

            if key not in FAILURE_MODES:
                warnings.warn(
                    f"Gate '{key}' is registered but missing from "
                    f"FAILURE_MODES in failure_modes.py (RL7). "
                    f"Add an entry for debugging support.",
                    stacklevel=2,
                )
        except ImportError:
            from structlog import get_logger

            get_logger(__name__).debug(
                "Could not import failure_modes — RL7 check skipped"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, gate_cls: type[BaseGate]) -> None:  # type: ignore[override]  # narrower signature than BaseRegistry.register(key, value)
        """Register a BaseGate subclass under its ``gate_name``.

        Validates the gate name convention (RL6) and checks that a
        failure-mode entry exists (RL7).
        """
        name: str = gate_cls._gate_name
        super().register(name, gate_cls)

    def get(self, gate_name: str) -> type[BaseGate]:
        """Look up a gate class by name."""
        if gate_name not in self._registry:
            raise KeyError(
                f"Gate '{gate_name}' is not registered. Available: {list(self._registry)}"
            )
        return self._registry[gate_name]

    def get_all(self) -> dict[str, type[BaseGate]]:
        """Return a copy of the full name→class mapping."""
        return dict(self._registry)

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

    # Declared here so mypy knows subclasses define these; no default value
    # so hasattr() in __init_subclass__ still works correctly.
    _gate_name: ClassVar[str]
    _failure_mode: ClassVar[str]

    @property
    def gate_name(self) -> str:
        """Human/short identifier for this gate (e.g. ``"G0"``)."""
        try:
            return self._gate_name
        except AttributeError as err:
            raise NotImplementedError(
                f"{type(self).__name__} must define class-level '_gate_name'"
            ) from err

    @gate_name.setter
    def gate_name(self, _value: str) -> None:
        raise AttributeError("gate_name is read-only")

    @property
    def failure_mode(self) -> str:
        """Behaviour when this gate fails — ``"stop"`` aborts the pipeline."""
        try:
            return self._failure_mode
        except AttributeError as err:
            raise NotImplementedError(
                f"{type(self).__name__} must define class-level '_failure_mode'"
            ) from err

    @failure_mode.setter
    def failure_mode(self, _value: str) -> None:
        raise AttributeError("failure_mode is read-only")

    # -- Required method ---------------------------------------------------

    @abstractmethod
    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Execute the gate's core logic.

        Args:
            gate_context: Pipeline context passed from the previous gate.
                Accepts either a :class:`GateContext` instance or a plain
                dict for backward compatibility (e.g. tests).

        Returns:
            A dictionary representing the gate result (may augment context
            for downstream gates).
        """
        ...

    # -- Automatic registration -------------------------------------------

    def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: ANN401 — pass-through to super().__init_subclass__
        """Auto-register concrete subclasses in the global registry."""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "_gate_name") and hasattr(cls, "_failure_mode"):
            _registry.register(cls)

    # -- String representations -------------------------------------------

    def __str__(self) -> str:
        return f"{self.gate_name}"

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} gate_name={self.gate_name!r}"
            f" failure_mode={self.failure_mode!r}>"
        )
