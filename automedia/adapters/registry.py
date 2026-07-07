"""Singleton registry for platform adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from automedia.adapters.base import BasePlatformAdapter


class AdapterRegistry:
    """Global registry that maps platform names to adapter classes.

    Usage::

        AdapterRegistry.register(WechatPublisher)
        cls = AdapterRegistry.get("wechat")
        for name in AdapterRegistry.list():
            ...
    """

    _registry: dict[str, type[BasePlatformAdapter]] = {}
    _instance: AdapterRegistry | None = None

    def __new__(cls, *args: object, **kwargs: object) -> AdapterRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, adapter_cls: type[BasePlatformAdapter]) -> None:
        """Register an adapter class keyed by its ``platform_name``."""
        # Instantiate a temporary adapter to evaluate the @property.
        name = adapter_cls().platform_name
        if not isinstance(name, str) or not name:
            raise ValueError(
                f"{adapter_cls.__name__}.platform_name must be a non-empty string, "
                f"got {name!r}"
            )
        if name in cls._registry:
            raise KeyError(
                f"Adapter for platform {name!r} is already registered "
                f"({cls._registry[name].__name__})"
            )
        cls._registry[name] = adapter_cls

    @classmethod
    def get(cls, platform_name: str) -> type[BasePlatformAdapter]:
        """Return the adapter class for *platform_name*.

        Raises ``KeyError`` if not found.
        """
        if platform_name not in cls._registry:
            raise KeyError(
                f"No adapter registered for platform {platform_name!r}. "
                f"Available: {sorted(cls._registry)}"
            )
        return cls._registry[platform_name]

    @classmethod
    def list(cls) -> list[str]:
        """Return sorted list of registered platform names."""
        return sorted(cls._registry)

    @classmethod
    def clear(cls) -> None:
        """Remove all registrations.  Used in tests."""
        cls._registry.clear()
