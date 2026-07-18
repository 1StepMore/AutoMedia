"""Engine abstraction layer — TTS, ASR, Image, Video engines.

Public API
---------
- :func:`resolve_engine` — factory function that resolves & instantiates an
  engine for a given modality based on configuration.
- :class:`EngineRegistry` — singleton registry of engine classes.
- :class:`BaseEngine`, :class:`BaseTTSEngine`, :class:`BaseASREngine`,
  :class:`BaseImageEngine`, :class:`BaseVideoEngine` — abstract base classes.
- :class:`EngineNotFoundError`, :class:`EngineExecutionError`,
  :class:`EngineUnavailableError` — error types.
"""

from __future__ import annotations

from typing import Any

from structlog import get_logger

from automedia.engines.base import (
    BaseASREngine,
    BaseEngine,
    BaseImageEngine,
    BaseTTSEngine,
    BaseVideoEngine,
)
from automedia.engines.errors import (
    EngineExecutionError,
    EngineNotFoundError,
    EngineUnavailableError,
)
from automedia.engines.registry import (  # noqa: PLC2701  # intentional package-internal constant
    _DEFAULT_ENGINES,
    EngineRegistry,
)

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Trigger auto-registration — import concrete implementations so that their
# __init_subclass__ hooks fire into EngineRegistry.
# ---------------------------------------------------------------------------
try:
    import automedia.engines.implementations  # noqa: F401
except ImportError:
    log.exception(
        "Failed to import engine implementations — auto-registration skipped. "
        "Check for missing dependencies (e.g. comfyui, faster-whisper, edge-tts).",
    )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def resolve_engine(
    modality: str,
    config: dict[str, Any] | None = None,
) -> BaseEngine:
    """Resolve and instantiate an engine for *modality* from *config*.

    **Selection flow**

    1. Read ``config["engines"][modality]["default"]`` for the engine name.
    2. Fall back to ``_DEFAULT_ENGINES[modality]`` if not in config.
    3. Look up the engine class via ``EngineRegistry().get(engine_name)``.
    4. Extract engine-specific config:
       ``config["engines"][modality].get(engine_name, {})``.
    5. Instantiate the engine with that config.
    6. Call ``engine.check_available()`` — raise
       :class:`EngineUnavailableError` if it returns ``(False, ...)``.
    7. Return the ready-to-use engine instance.

    Each invocation creates a **new** engine instance — no caching is
    performed.

    Parameters
    ----------
    modality:
        One of ``"tts"``, ``"asr"``, ``"image"``, ``"video"``.
    config:
        The full pipeline configuration dictionary.  May be ``None`` or
        an empty dict — in that case the built-in ``_DEFAULT_ENGINES``
        lookup is used.

    Returns
    -------
    BaseEngine
        An initialised engine whose :meth:`~BaseEngine.check_available`
        has passed.

    Raises
    ------
    EngineNotFoundError
        No engine name could be resolved for *modality* (neither in
        *config* nor in ``_DEFAULT_ENGINES``), or the resolved name
        is not registered in :class:`EngineRegistry`.
    EngineUnavailableError
        The engine class exists but its :meth:`~BaseEngine.check_available`
        returned ``(False, ...)``.
    EngineExecutionError
        :meth:`~BaseEngine.check_available` raised an unexpected exception.
    """
    cfg: dict[str, Any] = config or {}

    # Step 1-2: Determine engine name ---------------------------------------
    engine_cfg: dict[str, Any] = cfg.get("engines", {}).get(modality, {})
    engine_name: str | None = engine_cfg.get("default")

    if engine_name is None:
        engine_name = _DEFAULT_ENGINES.get(modality)

    if engine_name is None:
        registry: EngineRegistry = EngineRegistry()  # type: ignore  # BaseRegistry.__new__ returns base type
        available = ", ".join(registry.list_by_modality(modality))
        raise EngineNotFoundError(
            engine_name=modality,
            modality=modality,
            available=available or "none",
        )

    # Step 3: Look up engine class in the registry --------------------------
    registry = EngineRegistry()  # type: ignore  # BaseRegistry.__new__ returns base type
    try:
        engine_cls: type[BaseEngine] = registry.get(engine_name)
    except KeyError as e:
        available = ", ".join(registry.list_by_modality(modality))
        raise EngineNotFoundError(
            engine_name=engine_name,
            modality=modality,
            available=available or "none",
        ) from e

    # Step 4: Extract engine-specific config --------------------------------
    engine_specific_cfg: dict[str, Any] = engine_cfg.get(engine_name, {})

    # Step 5: Instantiate ---------------------------------------------------
    engine: BaseEngine = engine_cls(engine_config=engine_specific_cfg)

    # Step 6: Verify availability -------------------------------------------
    try:
        available, message = engine.check_available()
    except Exception as e:
        raise EngineExecutionError(
            engine_name=engine_name,
            details=f"check_available() raised an exception: {e}",
            cause=e,
        ) from e

    if not available:
        raise EngineUnavailableError(
            engine_name=engine_name,
            reason=message or "check_available() returned (False, ...)",
            install_hint=(
                f"Verify the dependencies for '{engine_name}' "
                f"are installed and accessible."
            ),
        )

    # Step 7: Return --------------------------------------------------------
    return engine


__all__ = [
    "BaseASREngine",
    "BaseEngine",
    "BaseImageEngine",
    "BaseTTSEngine",
    "BaseVideoEngine",
    "EngineExecutionError",
    "EngineNotFoundError",
    "EngineRegistry",
    "EngineUnavailableError",
    "resolve_engine",
]
