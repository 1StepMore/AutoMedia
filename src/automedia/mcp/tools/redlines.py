"""Red-line introspection tool — get_redlines."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from automedia.mcp.tools._shared import success_response

__all__ = ["get_redlines"]

_SOURCE = Path(__file__).resolve().parents[2] / "governance" / "redlines.yaml"


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, Any], ...]:
    """Load the single source of truth. Raises if absent — never degrades."""
    if not _SOURCE.is_file():
        raise FileNotFoundError(f"redlines source missing: {_SOURCE}")
    doc = yaml.safe_load(_SOURCE.read_text(encoding="utf-8"))
    return tuple(doc["redlines"])


def get_redlines() -> dict[str, Any]:
    """Return the list of agent red-line constraints.

    Returns
    -------
    dict
        ``{"redlines": [...], "total": N}`` —
        never raises. Each entry is ``{"id", "text", "rationale"}`` sourced
        from ``governance/redlines.yaml`` — the single source of truth. This
        tool performs no independent copy.
    """
    entries = [{"id": r["id"], "text": r["text"], "rationale": r["rationale"]} for r in _load()]
    return success_response({"redlines": entries, "total": len(entries)})
