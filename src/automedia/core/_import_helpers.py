"""Helpers for optional-dependency import warnings.

Provides consistent warning messages when optional packages are missing,
pointing users to the correct ``pip install`` command.

Usage::

    from automedia.core._import_helpers import warn_missing_optional

    try:
        import chromadb
    except ImportError:
        warn_missing_optional("chromadb", extra="omni-ml", feature="vector search")
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Default package name → pip extra mapping for automedia-pipeline extras.
# Packages not listed here use their own name as the extra.
_EXTRA_MAP: dict[str, str] = {
    "chromadb": "omni-ml",
    "httpx": "httpx",
    "openai": "openai",
    "anthropic": "anthropic",
    "ol_mcp": "omni",
    "omni_localizer": "omni",
    "mcp": "mcp",
    "rich": "rich",
    "sentence_transformers": "omni-ml",
    "torch": "omni-ml",
    "lxml": "omni-core",
    "docx": "omni-core",
    "pptx": "omni-core",
    "openpyxl": "omni-core",
    "pandas": "omni-core",
    "pymupdf": "omni-pdf",
}


def warn_missing_optional(
    package_name: str,
    *,
    extra: str | None = None,
    install_command: str | None = None,
    feature: str = "",
) -> None:
    """Log a warning when an optional dependency is missing.

    Parameters
    ----------
    package_name:
        The import name of the missing package (e.g. ``"chromadb"``, ``"httpx"``).
    extra:
        The pip extra name to install (e.g. ``"httpx"``, ``"omni-ml"``).
        When *None*, the extra is looked up from :data:`_EXTRA_MAP` or
        falls back to *package_name*.
    install_command:
        Full install command override (e.g. ``"pip install keyring"``).
        Takes precedence over *extra*.
    feature:
        Short description of the feature that will be unavailable
        (e.g. ``"vector search"``, ``"WeChat publishing"``).
    """
    if install_command is None:
        target = extra or _EXTRA_MAP.get(package_name, package_name)
        install_command = f"pip install automedia-pipeline[{target}]"

    parts = [f"{package_name} is not installed"]
    if feature:
        parts.append(f" — {feature}")
    parts.append(f". Install with: {install_command}")
    logger.warning("".join(parts))
