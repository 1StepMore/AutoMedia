"""MCP path allowlist helpers.

Loads and caches allowed directories from ``mcp_allowlist.yaml``.
All MCP file-system operations are gated through :func:`check_path_allowed`.

.. note::

   This module implements the *MCP server* allowlist (``mcp_allowlist.yaml`` —
   ``allowed_directories`` schema).  There is a separate *Omni adapter*
   allowlist at ``~/.automedia/omni_allowlist.yaml`` (``allowed_paths`` /
   ``write_paths`` schema) consumed by :mod:`automedia.omni.allowlist`.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from structlog import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Allowlist constants
# ---------------------------------------------------------------------------

_ALLOWLIST_FILE = Path(__file__).parent / "mcp_allowlist.yaml"

# Strict allowlist for ``format_output`` target formats.  Anything not in this
# set is rejected *before* any file I/O occurs, preventing path-traversal
# attacks via crafted format strings (e.g. ``"../../etc/passwd"``).
_ALLOWED_OUTPUT_FORMATS: frozenset[str] = frozenset(
    {
        "pdf",
        "docx",
        "txt",
        "html",
        "md",
        "pptx",
        "xlsx",
        "json",
        "csv",
        "xml",
    }
)

# Cache the resolved allowlist directories so we don't re-read YAML on every
# tool call.  Populated by ``_load_allowlist()`` on first access.
_cached_allowlist: list[str] | None = None


# ---------------------------------------------------------------------------
# Allowlist functions
# ---------------------------------------------------------------------------


def _load_allowlist(*, allowlist_path: Path | None = None) -> list[str]:
    """Load and cache allowed directories from the YAML config.

    Parameters
    ----------
    allowlist_path:
        Override path to the allowlist YAML file.  When *None* the
        default ``mcp_allowlist.yaml`` next to this module is used.

    Returns
    -------
    list[str]
        Resolved absolute directory paths.
    """
    global _cached_allowlist
    path = allowlist_path if allowlist_path is not None else _ALLOWLIST_FILE
    if not path.exists():
        _cached_allowlist = []
        return []
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    raw: list[str] = data.get("allowed_directories", []) or []
    resolved = [os.path.realpath(os.path.expanduser(d)) for d in raw]
    _cached_allowlist = resolved
    return resolved


def _reset_allowlist_cache() -> None:
    """Reset the cached allowlist.  Used in tests."""
    global _cached_allowlist
    _cached_allowlist = None
    # Also reset the server module's cache for backward compatibility
    # (tests set ``server._cached_allowlist`` directly).
    try:
        from automedia.mcp import server as _srv

        _srv._cached_allowlist = None  # type: ignore[attr-defined]  # _cached_allowlist is a private cache set dynamically on the server module
    except ImportError:
        pass


def _get_effective_allowlist() -> list[str] | None:
    """Return the effective cached allowlist.

    Checks the server module's ``_cached_allowlist`` first (backward compat
    with tests that set it directly), then this module's own cache, then
    falls back to loading from YAML.
    """
    # Check server module first — tests may have set it directly
    try:
        from automedia.mcp import server as _srv

        srv_cache = getattr(_srv, "_cached_allowlist", None)
        if srv_cache is not None:
            return srv_cache
    except ImportError:
        pass

    if _cached_allowlist is not None:
        return _cached_allowlist
    return _load_allowlist()


def check_path_allowed(path: str, *, allowlist: list[str] | None = None) -> bool:
    """Return *True* if *path* falls under an allowed directory.

    When the allowlist is empty **all paths are blocked** (fail‑closed).

    Parameters
    ----------
    path:
        File or directory path to validate (need not exist).
    allowlist:
        Override list of resolved directory paths.  When *None* the
        cached allowlist from the YAML file is used.
    """
    if allowlist is None:
        allowlist = _get_effective_allowlist()
    if not allowlist:
        return False  # fail‑closed: empty allowlist → deny all
    from pathlib import Path

    real = Path(path).resolve()
    for d in allowlist:
        try:
            real.relative_to(Path(d).resolve())
            return True
        except ValueError:
            continue
    return False


def _require_allowed(path: str, *, tool_name: str = "") -> None:
    """Raise ``PermissionError`` if *path* is not in the allowlist."""
    if not check_path_allowed(path):
        prefix = f"[{tool_name}] " if tool_name else ""
        raise PermissionError(
            f"{prefix}Path {path!r} is not within any allowed directory. "
            f"Configure allowed_directories in mcp_allowlist.yaml."
        )
