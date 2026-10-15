"""Lazy ``.env`` overlay — the one place AutoMedia reads a ``.env`` file.

AutoMedia used to push ``.env`` values into ``os.environ`` at *import* time
(a module-level dotenv-loading call inside
:mod:`automedia.core.credential_loader`).  That made a bare ``import automedia``
mutate the process environment: every subprocess inherited the values, and a
dev machine with a ``~/.automedia/.env`` leaked ``AUTOMEDIA_*`` values into
pytest at collection time — which is exactly what the environment-leak guard in
``tests/conftest.py`` exists to catch.

This module replaces that design with an overlay that is parsed **once**, on
first real need, and is **never** written back into ``os.environ``.

Per-key lookup priority (:func:`env_lookup`)
--------------------------------------------
1. ``os.environ`` — the real environment. A variable that is *present but
   empty* still wins (``""`` beats the ``.env`` value), which is the same
   semantics the retired non-overriding dotenv load had.
2. the ``.env`` overlay — ``$AUTOMEDIA_DOTENV_PATH`` when set, else
   ``~/.automedia/.env``.
3. the caller-supplied *default*.

That keeps the documented config priority intact::

    environment variables > .env > file config > built-in defaults

Because ``os.environ`` is consulted first, every ``AUTOMEDIA_*`` config key set
in ``.env`` still lands in the merged configuration through
:func:`automedia.core.config_loader.load_config` (layer 6a).

Thread-safety and caching
-------------------------
:func:`dotenv_overlay` parses and caches the mapping once per process; the
module-level lock only keeps concurrent callers from parsing twice.
:func:`reset_dotenv_overlay_cache` drops the cache (for tests and for
long-lived processes that swap ``AUTOMEDIA_DOTENV_PATH``).
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import overload

from automedia.core.paths import get_user_config_dir

logger = logging.getLogger(__name__)

__all__ = [
    "DOTENV_PATH_ENV_VAR",
    "dotenv_overlay",
    "env_lookup",
    "reset_dotenv_overlay_cache",
]

#: Bootstrap variable naming the ``.env`` file itself.  Read from the *real*
#: environment only: the overlay cannot be located from the overlay.
DOTENV_PATH_ENV_VAR = "AUTOMEDIA_DOTENV_PATH"

# Cached overlay mapping; ``None`` means "not parsed yet".
_overlay_cache: dict[str, str] | None = None
_lock = threading.Lock()


def _dotenv_file_path() -> Path:
    """Return the ``.env`` file this process reads.

    ``AUTOMEDIA_DOTENV_PATH`` (real env only) overrides the default
    ``~/.automedia/.env`` location.
    """
    override = os.environ.get(DOTENV_PATH_ENV_VAR)
    if override:
        return Path(override)
    return get_user_config_dir() / ".env"


def _parse_overlay(path: Path) -> dict[str, str]:
    """Parse *path* into a flat ``{name: value}`` mapping without touching env.

    Returns ``{}`` when ``python-dotenv`` is not installed, when *path* is not a
    file, or when the file cannot be read.  Never raises, never writes to
    ``os.environ``.
    """
    try:
        from dotenv import dotenv_values
    except ImportError:
        # Keep the optional-dependency warning the retired import-time block
        # emitted — now raised lazily, on the first real .env need instead of
        # on every ``import automedia``.
        from automedia.core._import_helpers import warn_missing_optional

        warn_missing_optional(
            "python-dotenv",
            install_command="pip install automedia-pipeline",
            feature=".env file will not be loaded",
        )
        return {}

    if not path.is_file():
        return {}

    try:
        values = dotenv_values(path)
    except Exception:  # unreadable/malformed file: fall back to "no overlay"
        logger.debug("Could not parse dotenv file %s", path, exc_info=True)
        return {}

    # ``dotenv_values`` yields ``None`` for a bare key written without ``=``;
    # those carry no value to overlay.
    return {name: value for name, value in values.items() if value is not None}


def dotenv_overlay() -> dict[str, str]:
    """Return the cached ``.env`` overlay mapping, parsing it on first use.

    The mapping is read-only by contract — mutating it corrupts the cache for
    the rest of the process.  ``os.environ`` is never written to.
    """
    global _overlay_cache
    if _overlay_cache is None:
        with _lock:
            if _overlay_cache is None:
                _overlay_cache = _parse_overlay(_dotenv_file_path())
    return _overlay_cache


@overload
def env_lookup(name: str, default: str) -> str: ...


@overload
def env_lookup(name: str, default: str | None = None) -> str | None: ...


def env_lookup(name: str, default: str | None = None) -> str | None:
    """Resolve *name*: real environment first, then the ``.env`` overlay.

    Parameters
    ----------
    name:
        Environment-variable name (e.g. ``"AUTOMEDIA_LLM_API_KEY"``).
    default:
        Value returned when *name* is in neither the environment nor ``.env``.

    Returns
    -------
    str | None
        ``os.environ[name]`` when *name* is present in the environment (an
        empty value still wins), else the ``.env`` value, else *default*.

    Never writes to ``os.environ``.
    """
    if name in os.environ:
        return os.environ[name]
    return dotenv_overlay().get(name, default)


def reset_dotenv_overlay_cache() -> None:
    """Drop the cached overlay so the next :func:`dotenv_overlay` re-parses.

    Needed when ``AUTOMEDIA_DOTENV_PATH`` (or the pointed-to file) changes
    inside one process — primarily a test hook.
    """
    global _overlay_cache
    with _lock:
        _overlay_cache = None
