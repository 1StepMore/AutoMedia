"""Asset library tools — search_assets."""

from __future__ import annotations

from typing import Any

from automedia.asset_library import search_assets as _search_assets
from automedia.mcp.tools._shared import (
    AutoMediaError,
    MCPErrorCode,
    NonEmptyStr,
    error_response,
    success_response,
)

__all__ = ["search_assets"]


def search_assets(
    query: str,
    brand: NonEmptyStr,
    limit: int = 10,
    type: str | None = None,
    tags: list[str] | None = None,
    lang: str | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    """Search the asset library for brand assets.

    Wraps :func:`automedia.asset_library.search_assets` — delegates to
    SQLite keyword search and Chroma semantic search, returns ranked
    results with relevance scores.

    Parameters
    ----------
    query : str
        Search query (keyword + semantic).  Empty string returns all
        assets filtered by the other criteria.
    brand : str
        Brand identifier to scope the search.
    limit : int
        Maximum number of results to return (default 10).
    type : str or None
        Optional asset type filter (e.g. ``"article"``, ``"brief"``).
    tags : list[str] or None
        Optional tag overlap filter.
    lang : str or None
        Optional language code filter (e.g. ``"zh"``, ``"en"``).
    stage : str or None
        Optional source-phase filter.

    Returns
    -------
    dict
        ``{"results": [...], "count": int, "error": str | None}`` —
        never raises.  Each result is a dict with at least ``title``,
        ``content``, ``_score``, and metadata keys.
    """
    try:
        filters: dict[str, Any] = {}
        if type is not None:
            filters["type"] = type
        if tags is not None:
            filters["tags"] = tags
        if lang is not None:
            filters["lang"] = lang
        if stage is not None:
            filters["phase"] = stage

        raw_results = _search_assets(query=query, brand=brand, filters=filters or None)
        limited = raw_results[:limit]
        return success_response({"results": limited, "count": len(limited), "error": None})
    except ImportError as exc:
        return {"results": [], "count": 0, **error_response(MCPErrorCode.IMPORT_ERROR, str(exc))}
    except AutoMediaError as exc:
        return {"results": [], "count": 0, **error_response(MCPErrorCode.UNKNOWN, str(exc))}
