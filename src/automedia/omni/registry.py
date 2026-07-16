"""Singleton registry for omni adapter instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

from structlog import get_logger

from automedia.core.registry import BaseRegistry

log = get_logger(__name__)

if TYPE_CHECKING:
    from automedia.omni.base import BaseOmniAdapter


class OmniToolRegistry(BaseRegistry):
    """Global registry that maps adapter names to adapter instances.

    Inherits singleton lifecycle from :class:`BaseRegistry`.
    Keeps ``@classmethod`` wrappers for backward compatibility.

    Usage::

        OmniToolRegistry.register(OPPAdapter())
        inst = OmniToolRegistry.get("opp")
        for name in OmniToolRegistry.list_tools(): ...
    """

    # ------------------------------------------------------------------
    # Validation hook
    # ------------------------------------------------------------------

    def _validate(self, key: str, value: BaseOmniAdapter) -> None:
        """Enforce non-empty adapter name and no duplicates."""
        if not isinstance(key, str) or not key:
            raise ValueError(f"Adapter.name must be a non-empty string, got {key!r}")
        if key in self._registry:
            raise KeyError(
                f"Adapter {key!r} is already registered ({type(self._registry[key]).__name__})"
            )

    # ------------------------------------------------------------------
    # Public API — classmethods for backward compatibility
    # ------------------------------------------------------------------

    @classmethod
    def register(cls, adapter: BaseOmniAdapter) -> None:  # type: ignore[override]  # classmethod with narrower signature than BaseRegistry.register(key, value)
        """Register an omni adapter instance under its ``name``."""
        name = adapter.name
        inst = cls()
        inst._validate(name, adapter)
        cls._registry[name] = adapter

    @classmethod
    def get(cls, name: str) -> BaseOmniAdapter:
        """Return the registered adapter for *name*.

        Raises :class:`KeyError` if *name* is not registered.
        """
        if name not in cls._registry:
            raise KeyError(
                f"No adapter registered for {name!r}. Available: {sorted(cls._registry)}"
            )
        return cls._registry[name]

    @classmethod
    def list_tools(cls) -> list[str]:
        """Return sorted list of registered adapter names."""
        return sorted(cls._registry)

    @classmethod
    def clear(cls) -> None:
        """Remove all registered adapters.  Used in tests for isolation."""
        cls._registry.clear()
