"""Omni allowlist — path-based access control for adapter file operations.

Public API
----------
- ``AllowlistConfig`` dataclass
- ``load_allowlist(path) -> AllowlistConfig``
- ``validate_path(path, allowlist, mode) -> bool``
- ``is_read_only(path, allowlist) -> bool``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class AllowlistConfig:
    """Path-based access control configuration.

    Attributes
    ----------
    allowed_paths:
        Directories/files that are accessible for **read** operations.
    write_paths:
        Directories/files that are additionally accessible for **write**
        operations.  Every path in ``write_paths`` is implicitly readable.
    """

    allowed_paths: list[str] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_allowlist(path: Path | None = None) -> AllowlistConfig:
    """Load an ``omni_allowlist.yaml`` file and return an :class:`AllowlistConfig`.

    When *path* is ``None`` the default location
    ``~/.automedia/omni_allowlist.yaml`` is used.  If the file does not exist
    an **empty** allowlist is returned (fail-CLOSED security — no paths are
    allowed).

    Parameters
    ----------
    path:
        Explicit path to the YAML allowlist file.  ``None`` means default path.

    Returns
    -------
    AllowlistConfig
        A populated allowlist, or an empty one when the file is missing.
    """
    p = path if path is not None else Path.home() / ".automedia" / "omni_allowlist.yaml"

    if not p.is_file():
        return AllowlistConfig()

    with open(p, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise ValueError(
            f"omni_allowlist must be a YAML mapping, got {type(data).__name__}"
        )

    return AllowlistConfig(
        allowed_paths=list(data.get("allowed_paths") or []),
        write_paths=list(data.get("write_paths") or []),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_subpath(child: Path, parent: str) -> bool:
    """Return ``True`` when *child* is a descendant of (or equal to) *parent*."""
    try:
        child.resolve().relative_to(Path(parent).expanduser().resolve())
        return True
    except ValueError:
        return False


def validate_path(path: Path, allowlist: AllowlistConfig, mode: str = "read") -> bool:
    """Check whether *path* is allowed for *mode* (``"read"`` or ``"write"``).

    Parameters
    ----------
    path:
        The filesystem path to check.
    allowlist:
        The active allowlist configuration.
    mode:
        ``"read"`` or ``"write"``.

    Returns
    -------
    bool
        ``True`` if the operation is allowed, ``False`` otherwise.
    """
    # Write mode: only write_paths are eligible
    if mode == "write":
        for allowed in allowlist.write_paths:
            if _is_subpath(path, allowed):
                return True
        return False

    # Read mode: check both allowed_paths and write_paths (write paths are
    # implicitly readable).
    for allowed in allowlist.allowed_paths:
        if _is_subpath(path, allowed):
            return True

    for allowed in allowlist.write_paths:
        if _is_subpath(path, allowed):
            return True

    return False


def is_read_only(path: Path, allowlist: AllowlistConfig) -> bool:
    """Return ``True`` when *path* is allowed for **read** but **not** for write.

    This is useful to prevent accidental writes to read-only locations.

    Parameters
    ----------
    path:
        The filesystem path to check.
    allowlist:
        The active allowlist configuration.

    Returns
    -------
    bool
    """
    return validate_path(path, allowlist, mode="read") and not validate_path(
        path, allowlist, mode="write"
    )
