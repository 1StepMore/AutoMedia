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

# Overrides the shipped allowlist path; documented in .env.example and deployments.
_ALLOWLIST_PATH_ENV = "AUTOMEDIA_MCP_ALLOWLIST_PATH"

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


class AllowlistDenied(PermissionError):  # noqa: N818
    """A path was refused because it is not within any allowed directory.

    Subclasses :class:`PermissionError` so every existing
    ``except PermissionError`` handler keeps catching it; callers that need to
    distinguish an allowlist refusal from a real OS permission error catch this
    class explicitly and map it to ``MCPErrorCode.ALLOWLIST_DENIED``.
    """


def _implicit_directories() -> list[str]:
    """Return the app-owned data directories that are always allowed.

    These are directories the application itself writes into (user config
    tree, resolved projects directory).  They are effective without being
    registered in ``mcp_allowlist.yaml`` — an operator's YAML only ever adds
    directories on top of these, never re-scopes them away.

    The repository / current-working-directory root is deliberately **not**
    implicit: granting the whole checkout stays an explicit operator decision
    (see the ``mcp_allowlist.yaml`` header).

    Function-level imports avoid the ``allowlist`` → ``tools._shared`` →
    ``server`` → ``allowlist`` import cycle; on ImportError the affected
    entries are simply absent rather than fatal.
    """
    dirs: list[str] = []
    try:
        from automedia.core.paths import get_user_config_dir

        config_dir = get_user_config_dir()
        dirs.extend(
            [
                str(config_dir / "projects"),
                str(config_dir / "demo"),
                str(config_dir / "output"),
            ]
        )
    except ImportError:
        pass
    try:
        from automedia.mcp.tools._shared import _resolve_projects_dir

        dirs.append(_resolve_projects_dir())
    except ImportError:
        pass
    resolved: list[str] = []
    seen: set[str] = set()
    for d in dirs:
        real = os.path.realpath(os.path.expanduser(d))
        if real not in seen:
            seen.add(real)
            resolved.append(real)
    return resolved


def _merged_allowlist() -> list[str]:
    """Implicit app-owned directories plus the configured YAML entries.

    Deduplicated with order preserved (implicit entries first).  This — not
    the YAML-only :func:`_load_allowlist` result — is what the path checks
    judge paths against, so the app's own data directories are reachable even
    when the operator's YAML (factory default included) does not list them.
    """
    merged: list[str] = []
    seen: set[str] = set()
    for d in [*_implicit_directories(), *(_get_effective_allowlist() or [])]:
        real = os.path.realpath(d)
        if real not in seen:
            seen.add(real)
            merged.append(real)
    return merged


def _resolve_allowlist_path(allowlist_path: Path | None = None) -> Path:
    """The YAML file to read: explicit argument, else env var, else shipped default.

    Honouring :data:`_ALLOWLIST_PATH_ENV` is what makes the escape hatch that
    ``.env.example``, ``docs/user/mcp-setup.md`` and the systemd templates
    advertise actually exist.
    """
    if allowlist_path is not None:
        return allowlist_path
    configured = os.environ.get(_ALLOWLIST_PATH_ENV, "").strip()
    if configured:
        return Path(os.path.expanduser(configured))
    return _ALLOWLIST_FILE


def _load_allowlist(*, allowlist_path: Path | None = None) -> list[str]:
    """Load and cache allowed directories from the YAML config.

    Parameters
    ----------
    allowlist_path:
        Override path to the allowlist YAML file.  When *None* the
        ``AUTOMEDIA_MCP_ALLOWLIST_PATH`` env var is honoured, falling back to
        the ``mcp_allowlist.yaml`` shipped next to this module.

    Returns
    -------
    list[str]
        Resolved absolute directory paths.

    .. note::
       This is the YAML entry list only.  The effective allowlist used by
       :func:`check_path_allowed` is :func:`_merged_allowlist` — these entries
       plus the implicit app-owned directories — so this list is not the
       complete grant.
    """
    global _cached_allowlist
    path = _resolve_allowlist_path(allowlist_path)
    if not path.exists():
        # Fail closed (an empty allowlist denies every path).  A configured
        # path that does not exist is a misconfiguration — substituting the
        # shipped allowlist would silently grant a different, possibly wider
        # set than the operator asked for.
        log.warning("mcp.allowlist.missing", path=str(path))
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

    When the effective allowlist is empty **all paths are blocked**
    (fail‑closed).  The effective allowlist is the implicit app-owned
    directories (:func:`_implicit_directories`) plus the YAML entries —
    an explicit *allowlist* argument overrides both entirely.

    Parameters
    ----------
    path:
        File or directory path to validate (need not exist).
    allowlist:
        Override list of resolved directory paths, judged exactly as given
        (no implicit directories added).  When *None* the merged implicit +
        YAML allowlist is used.
    """
    if allowlist is None:
        allowlist = _merged_allowlist()
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
    """Raise :class:`AllowlistDenied` if *path* is not in the allowlist."""
    if not check_path_allowed(path):
        prefix = f"[{tool_name}] " if tool_name else ""
        effective = _merged_allowlist()
        listing = ", ".join(effective) if effective else "(none)"
        raise AllowlistDenied(
            f"Permission denied: {prefix}Path {path!r} is not within any "
            f"allowed directory. Allowed: {listing}. Add another directory "
            f"in mcp_allowlist.yaml (allowed_directories) or set "
            f"AUTOMEDIA_MCP_ALLOWLIST_PATH."
        )
