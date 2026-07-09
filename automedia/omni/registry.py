"""Singleton registry for omni adapter instances."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from automedia.omni.base import BaseOmniAdapter


class OmniToolRegistry:
    """Global registry that maps adapter names to adapter instances.

    Usage::

        OmniToolRegistry.register(OPPAdapter())
        inst = OmniToolRegistry.get("opp")
        for name in OmniToolRegistry.list_tools(): ...
    """

    _registry: dict[str, BaseOmniAdapter] = {}
    _instance: OmniToolRegistry | None = None

    def __new__(cls, *args: object, **kwargs: object) -> OmniToolRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, adapter: BaseOmniAdapter) -> None:
        name = adapter.name
        if not isinstance(name, str) or not name:
            raise ValueError(
                f"Adapter.name must be a non-empty string, got {name!r}"
            )
        if name in cls._registry:
            raise KeyError(
                f"Adapter {name!r} is already registered "
                f"({type(cls._registry[name]).__name__})"
            )
        cls._registry[name] = adapter

    @classmethod
    def get(cls, name: str) -> BaseOmniAdapter:
        if name not in cls._registry:
            raise KeyError(
                f"No adapter registered for {name!r}. "
                f"Available: {sorted(cls._registry)}"
            )
        return cls._registry[name]

    @classmethod
    def list_tools(cls) -> list[str]:
        """Return sorted list of registered adapter names."""
        return sorted(cls._registry)

    @classmethod
    def list(cls) -> list[str]:
        """Deprecated: use list_tools() instead."""
        return cls.list_tools()

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()
