"""Singleton registry for engine implementations with modality grouping.

Inherits singleton lifecycle and CRUD from :class:`BaseRegistry`.
Each registered engine is optionally tagged with a modality (e.g. ``"tts"``,
``"asr"``, ``"image"``, ``"video"``) so that callers can discover engines
by modality and resolve the configured default engine per modality.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from automedia.core.registry import BaseRegistry

# ---------------------------------------------------------------------------
# Default engine per modality — used when config does not specify one
# ---------------------------------------------------------------------------

_DEFAULT_ENGINES: dict[str, str] = {
    "tts": "edge-tts",
    "asr": "whisper",
    "image": "comfyui",
    "video": "hyperframes",
}
"""Built-in default engine names keyed by modality.

Used as fallback in :meth:`EngineRegistry.get_default` when the caller's
*config* does not contain an entry for the requested modality.
"""

# Engine name validation pattern: lowercase, digits, hyphens, underscores
_VALID_ENGINE_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class EngineRegistry(BaseRegistry):
    """Singleton registry that maps engine names to engine classes.

    Inherits singleton lifecycle and CRUD from :class:`BaseRegistry`.
    Extends the base with modality grouping so that engines can be
    discovered and selected per modality.

    Usage::

        EngineRegistry().register("edge-tts", EdgeTTS, modality="tts")
        EngineRegistry().register("whisper", WhisperASR, modality="asr")

        for name in EngineRegistry().list_by_modality("tts"):
            ...

        cls = EngineRegistry().get_default("tts", config)
    """

    # ------------------------------------------------------------------
    # Modality map — engine-name sets keyed by modality
    # ------------------------------------------------------------------

    _modality_map: ClassVar[dict[str, set[str]]] = {}

    # ------------------------------------------------------------------
    # Singleton lifecycle (per-subclass state)
    # ------------------------------------------------------------------

    def __init_subclass__(cls, **kwargs: Any) -> None:  # noqa: ANN401 — pass-through to super().__init_subclass__
        """Initialize per-subclass modality state when a subclass is created."""
        super().__init_subclass__(**kwargs)
        cls._modality_map = {}

    # ------------------------------------------------------------------
    # Validation hook
    # ------------------------------------------------------------------

    def _validate(self, key: str, value: type) -> None:
        """Enforce engine naming convention: lowercase, no spaces."""
        if not _VALID_ENGINE_NAME_RE.match(key):
            raise ValueError(
                f"Engine name {key!r} violates naming convention. "
                f"Expected pattern: lowercase, digits, hyphens, underscores "
                f"(e.g. 'edge-tts', 'whisper', 'comfyui')."
            )

    # ------------------------------------------------------------------
    # Public CRUD — extended with modality support
    # ------------------------------------------------------------------

    def register(  # type: ignore[override]  # narrower signature than BaseRegistry.register(key, value)
        self,
        key: str,
        value: type,
        modality: str | None = None,
    ) -> None:
        """Register *value* under *key* with an optional *modality* tag.

        Parameters
        ----------
        key:
            Engine name (e.g. ``"edge-tts"``).
        value:
            The engine class.
        modality:
            Modality to associate this engine with (e.g. ``"tts"``,
            ``"asr"``, ``"image"``, ``"video"``).  When provided the
            engine will be returned by :meth:`list_by_modality`.
        """
        super().register(key, value)
        if modality:
            self._modality_map.setdefault(modality, set()).add(key)

    def get(self, key: str) -> type:
        """Look up an engine class by name.

        Raises :class:`KeyError` with a helpful message if *key* is
        not registered.
        """
        if key not in self._registry:
            raise KeyError(
                f"Engine {key!r} is not registered. "
                f"Available engines: {sorted(self._registry)}"
            )
        return self._registry[key]

    # ------------------------------------------------------------------
    # Modality-specific queries
    # ------------------------------------------------------------------

    def list_by_modality(self, modality: str) -> list[str]:
        """Return sorted engine names registered under *modality*.

        Parameters
        ----------
        modality:
            Modality string (e.g. ``"tts"``, ``"asr"``, ``"image"``,
            ``"video"``).

        Returns
        -------
        Sorted list of engine names, or an empty list if the modality
        has no registered engines.
        """
        return sorted(self._modality_map.get(modality, set()))

    def get_default(self, modality: str, config: dict) -> type:
        """Resolve the default engine class for *modality* from *config*.

        Lookup order:

        1. ``config["engines"][modality]["default"]``
        2. ``_DEFAULT_ENGINES[modality]``
        3. :class:`KeyError` if neither source contains an entry

        Parameters
        ----------
        modality:
            Modality string.
        config:
            Merged configuration dictionary (typically from
            :func:`automedia.core.config_loader.load_config`).

        Returns
        -------
        The registered engine class.

        Raises
        ------
        KeyError
            If the modality has no configured default and no built-in
            default, or if the resolved engine name is not registered.
        """
        # 1. Try config
        engine_name: str | None = (
            config.get("engines", {})
            .get(modality, {})
            .get("default")
        )

        # 2. Fall back to built-in default
        if not engine_name:
            engine_name = _DEFAULT_ENGINES.get(modality)

        # 3. Neither source — error
        if not engine_name:
            raise KeyError(
                f"No default engine configured for modality {modality!r} "
                f"in config['engines'] and no built-in default in "
                f"_DEFAULT_ENGINES."
            )

        # 4. Look up in registry
        if engine_name not in self._registry:
            raise KeyError(
                f"Default engine {engine_name!r} for modality {modality!r} "
                f"is not registered. Available engines: {sorted(self._registry)}"
            )

        return self._registry[engine_name]

    def clear(self) -> None:
        """Remove all registrations and modality mappings.

        Used in tests for isolation.  Clears both the engine registry
        and the modality map.
        """
        self._registry.clear()
        self._modality_map.clear()

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"EngineRegistry({len(self)} engines: {', '.join(self.list())})"
        )


# Module-level singleton — used by engine base classes for auto-registration
_engine_registry: EngineRegistry = EngineRegistry()
"""Module-level :class:`EngineRegistry` singleton.

Engine base classes may use this in their ``__init_subclass__`` to
auto-register implementations as they are defined.
"""
