"""Red-line introspection tool — get_redlines."""

from __future__ import annotations

from typing import Any

from automedia.mcp.tools._shared import success_response

__all__ = ["get_redlines"]


def get_redlines() -> dict[str, Any]:
    """Return the list of agent red-line constraints.

    Returns
    -------
    dict
        ``{"redlines": [...], "total": N}`` —
        never raises. Each entry is a human-readable constraint description
        sourced from AGENTS.md §5.
    """
    redlines: list[str] = [
        "MUST NOT archive projects using --force unless status is 'published'",
        "MUST NOT commit real production data, topic pool contents, or credentials to git",
        "MUST NOT modify automedia/mcp/mcp_allowlist.yaml without explicit user request",
        "MUST use synthetic test fixtures from tests/fixtures/synth/ for testing",
        "MUST use 'automedia archive' command for archiving — never manual dir operations",
        "MUST follow gate naming convention: G0-G5, V0-V7, L1-L4, H0, pre-gate, CW",
        "MUST add new gates to automedia/gates/failure_modes.py",
        "MUST NOT skip pre-commit checks",
        "MUST respect GateHook readonly contract — hooks observe but never mutate",
    ]
    return success_response({"redlines": redlines, "total": len(redlines)})
