"""Centralised user-config-directory resolution.

Provides a single point of truth for the AutoMedia user configuration
directory (default ``~/.automedia``).  All modules that need to locate
config files, credentials, overrides or other user data should call
:func:`get_user_config_dir` instead of hard-coding ``Path.home() / ".automedia"``.

Environment-variable override
----------------------------
Set ``AUTOMEDIA_CONFIG_DIR`` to an absolute path to redirect **all**
AutoMedia user configuration (credentials, brand profiles, Omni config,
override rules, audit logs, …) to a different location.  This is
particularly useful in CI/CD, Docker, or other agent environments where
``$HOME`` may not be available or writable.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "get_user_config_dir",
]


def get_user_config_dir() -> Path:
    """Return the user configuration directory.

    Priority
    --------
    1. ``AUTOMEDIA_CONFIG_DIR`` environment variable (if set)
    2. ``~/.automedia`` (default, resolved via :meth:`pathlib.Path.home`)
    3. ``~/.automedia`` via :func:`os.path.expanduser` (fallback when
       :meth:`~pathlib.Path.home` raises ``RuntimeError`` — e.g. in
       containerised or headless environments)

    The returned path is always absolute and resolved.
    """
    override = os.environ.get("AUTOMEDIA_CONFIG_DIR")
    if override:
        resolved = Path(os.path.expanduser(override)).resolve()
        if resolved.exists() and not resolved.is_dir():
            logger.warning(
                "AUTOMEDIA_CONFIG_DIR=%r points to an existing file, not a directory. "
                "Config loading may fail or behave unexpectedly.",
                override,
            )
        return resolved

    try:
        return Path.home() / ".automedia"
    except RuntimeError:
        # Fallback for environments without $HOME (CI, Docker, serverless).
        return Path("~/.automedia").expanduser().resolve()
