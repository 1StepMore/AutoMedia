"""RBAC — Role-based access control for multi-tenant workspace management."""

from __future__ import annotations

from typing import Final

ROLES: Final[list[str]] = ["admin", "strategist", "editor", "operator", "viewer"]

ROLE_PERMISSIONS: Final[dict[str, list[str]]] = {
    "admin": [
        "workspace.*",
        "member.*",
        "content.*",
        "publish.*",
        "settings.*",
        "asset_library.*",
        "sop.*",
        "audit.*",
    ],
    "strategist": [
        "content.create",
        "content.edit",
        "content.review",
        "asset_library.*",
        "sop.*",
        "analytics.*",
    ],
    "editor": [
        "content.create",
        "content.edit",
        "asset_library.read",
    ],
    "operator": [
        "content.read",
        "publish.execute",
        "analytics.read",
    ],
    "viewer": [
        "content.read",
        "analytics.read",
        "asset_library.read",
    ],
}


def check_permission(role: str, action: str) -> bool:
    """Check whether *role* is allowed to perform *action*.

    Parameters
    ----------
    role:
        One of ``ROLES``.
    action:
        Dot-notation action string, e.g. ``"content.create"``.
        Wildcard permissions ending in ``.*`` match any action with the
        matching prefix.

    Returns
    -------
    bool
        ``True`` if the action is permitted for the given role.
    """
    if role not in ROLES:
        return False
    perms = ROLE_PERMISSIONS.get(role, [])
    for p in perms:
        if p.endswith(".*"):
            prefix = p[:-2]
            if action.startswith(prefix):
                return True
        elif p == action:
            return True
    return False
