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
from automedia.engines.registry import (  # intentional package-internal constant
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
        is_available, message = engine.check_available()
    except Exception as e:
        raise EngineExecutionError(
            engine_name=engine_name,
            details=f"check_available() raised an exception: {e}",
            cause=e,
        ) from e

    if not is_available:
        raise EngineUnavailableError(
            engine_name=engine_name,
            reason=message or "check_available() returned (False, ...)",
            install_hint=(
                f"Verify the dependencies for '{engine_name}' are installed and accessible."
            ),
        )

    # Step 7: Return --------------------------------------------------------
    return engine


def _dedupe(names: list[str]) -> list[str]:
    """Return *names* with duplicates removed, preserving first occurrence."""
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _chain_names(
    modality: str,
    engine_cfg: dict[str, Any] | None,
    registry: EngineRegistry,
) -> list[str]:
    """Resolve the ordered engine names a chain should try for *modality*.

    An explicit ``chain`` list wins.  Otherwise the configured (or built-in)
    default comes first, followed by the legacy ``fallback`` list and then
    every other engine registered for the modality in registration order.
    """
    if isinstance(engine_cfg, dict):
        chain = engine_cfg.get("chain")
        if isinstance(chain, str):
            return _dedupe([chain])
        if isinstance(chain, (list, tuple)):
            return _dedupe([str(name) for name in chain if name])

    names: list[str] = []
    default_name: str | None = None
    if isinstance(engine_cfg, dict):
        raw_default = engine_cfg.get("default")
        if raw_default:
            default_name = str(raw_default)
        fallback = engine_cfg.get("fallback")
        if isinstance(fallback, str):
            names.extend([fallback])
        elif isinstance(fallback, (list, tuple)):
            names.extend(str(name) for name in fallback if name)

    if default_name is None:
        default_name = _DEFAULT_ENGINES.get(modality)

    try:
        registered = registry.list_by_modality_ordered(modality)
    except Exception:  # pragma: no cover - defensive against registry swaps
        registered = []

    ordered = ([default_name] if default_name else []) + names + registered
    return _dedupe(ordered)


def resolve_engine_chain(
    modality: str,
    config: dict[str, Any] | None = None,
) -> list[BaseEngine]:
    """Resolve an ordered chain of available engines for *modality*.

    Reads ``config["engines"][modality]["chain"]`` (a list of engine names)
    when present::

        {"chain": ["edge-tts", "piper"], "piper": {...}}

    Without a ``chain`` key the order is the configured ``default`` (or the
    built-in default), then the legacy ``fallback`` list, then every other
    engine registered for the modality in registration order.  Duplicates are
    removed while preserving order.

    Each candidate is instantiated through :func:`resolve_engine`, which also
    runs its availability check.  Unavailable, unknown, or misconfigured
    engines are skipped with a debug log.

    This function **never raises**: callers decide what an empty chain means
    (direct subprocess fallback for audio, "no image" for image).

    Parameters
    ----------
    modality:
        One of ``"tts"``, ``"asr"``, ``"image"``, ``"video"``.
    config:
        Full pipeline configuration dictionary (may be ``None``).

    Returns
    -------
    list[BaseEngine]
        Ready-to-use engines in preference order (possibly empty).
    """
    try:
        cfg: dict[str, Any] = config or {}
        engines_section = cfg.get("engines")
        engine_cfg = engines_section.get(modality) if isinstance(engines_section, dict) else None
        if engine_cfg is not None and not isinstance(engine_cfg, dict):
            log.debug(
                "Ignoring non-dict engines.%s config (%s)", modality, type(engine_cfg).__name__
            )
            engine_cfg = None

        registry: EngineRegistry = EngineRegistry()
        names = _chain_names(modality, engine_cfg, registry)

        chain: list[BaseEngine] = []
        for name in names:
            per_modality = dict(engine_cfg or {})
            per_modality["default"] = name
            new_engines = dict(engines_section) if isinstance(engines_section, dict) else {}
            new_engines[modality] = per_modality
            candidate_cfg = dict(cfg)
            candidate_cfg["engines"] = new_engines
            try:
                chain.append(resolve_engine(modality, candidate_cfg))
            except Exception as exc:
                log.debug("Engine chain: skipping %r for modality %r: %s", name, modality, exc)
                continue
        return chain
    except Exception as exc:  # pragma: no cover - chain resolution never raises
        log.debug("Engine chain resolution failed for %r: %s", modality, exc)
        return []


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
    "resolve_engine_chain",
]
