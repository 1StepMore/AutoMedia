"""Singleton registry for platform adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from automedia.core.registry import BaseRegistry

if TYPE_CHECKING:
    from automedia.adapters.base import BasePlatformAdapter


class AdapterRegistry(BaseRegistry):
    """Global registry that maps platform names to adapter classes.

    Inherits singleton lifecycle from :class:`BaseRegistry`.
    Keeps ``@classmethod`` wrappers for backward compatibility.

    Usage::

        AdapterRegistry.register(WechatPublisher)
        cls = AdapterRegistry.get("wechat")
        for name in AdapterRegistry.list():
            ...
    """

    # ------------------------------------------------------------------
    # Validation hook
    # ------------------------------------------------------------------

    def _validate(self, key: str, value: type[BasePlatformAdapter]) -> None:
        """Enforce non-empty platform name and no duplicates."""
        if not isinstance(key, str) or not key:
            raise ValueError(
                f"{value.__name__}.platform_name must be a non-empty string, got {key!r}"
            )
        if key in self._registry:
            raise KeyError(
                f"Adapter for platform {key!r} is already registered "
                f"({self._registry[key].__name__})"
            )

    # ------------------------------------------------------------------
    # Public API — classmethods for backward compatibility
    # ------------------------------------------------------------------

    @classmethod
    def register(cls, adapter_cls: type[BasePlatformAdapter]) -> None:  # type: ignore[override]
        """Register an adapter class keyed by its ``platform_name``."""
        # Instantiate a temporary adapter to evaluate the @property.
        name = adapter_cls().platform_name
        inst = cls()
        inst._validate(name, adapter_cls)
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
