"""Shared singleton registry base class (ADR-001).

All registry implementations (GateRegistry, AdapterRegistry, OmniToolRegistry)
inherit from :class:`BaseRegistry` to eliminate duplicated singleton and CRUD
boilerplate.  Each subclass gets its own ``_registry`` dict and ``_instance``
via ``__init_subclass__``, so test isolation is preserved.
"""

from __future__ import annotations

from typing import Any, ClassVar


class BaseRegistry:
    """Singleton base for string-keyed registries.

    Subclasses automatically receive per-class ``_registry`` and ``_instance``
    class variables.  Override :meth:`_validate` to add registration checks.
    """

    _instance: ClassVar[BaseRegistry | None] = None
    _registry: ClassVar[dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Singleton plumbing
    # ------------------------------------------------------------------

    def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: ANN401 — pass-through to super().__init_subclass__
        """Initialize per-subclass singleton state when a subclass is created."""
        super().__init_subclass__(**kwargs)
        # Each concrete subclass gets its own singleton state.
        cls._instance = None
        cls._registry = {}

    def __new__(cls) -> BaseRegistry:
        """Return the singleton instance for *cls*, creating it if needed."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------
    # Public CRUD API
    # ------------------------------------------------------------------

    def register(self, key: str, value: Any) -> None:  # noqa: ANN401
        """Store *value* under *key* after validation."""
        self._validate(key, value)
        self._registry[key] = value

    def get(self, key: str) -> Any:  # noqa: ANN401
        """Return the value for *key*.

        Raises :class:`KeyError` if *key* is not registered.
        """
        return self._registry[key]

    def list(self) -> list[str]:
        """Return a sorted list of registered keys."""
        return sorted(self._registry)

    def clear(self) -> None:
        """Remove all registrations.  Used in tests for isolation."""
        self._registry.clear()

    # ------------------------------------------------------------------
    # Protocols
    # ------------------------------------------------------------------

    def __contains__(self, key: str) -> bool:
        return key in self._registry

    def __len__(self) -> int:
        return len(self._registry)

    def __repr__(self) -> str:
        cls_name = type(self).__name__
        items = ", ".join(self.list())
        return f"{cls_name}({len(self)} items: {items})"

    # ------------------------------------------------------------------
    # Validation hook — override in subclasses
    # ------------------------------------------------------------------

    def _validate(self, key: str, value: Any) -> None:  # noqa: ANN401
        """No-op validation hook.  Subclasses override to enforce constraints."""
