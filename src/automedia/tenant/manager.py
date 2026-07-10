"""TenantManager — workspace lifecycle, member management & file isolation."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from automedia.tenant.audit import AuditLog
from automedia.tenant.rbac import ROLES


class TenantManager:
    """Manages multi-tenant workspaces.

    Uses ``~/.automedia/tenants/{workspace_id}/`` for per-tenant file
    isolation.  The workspace registry is held in-memory; a future
    production iteration would replace this with a database (SQLite / PG).
    """

    def __init__(self) -> None:
        # In-memory workspace registry: {workspace_id: {name, members, ...}}
        self._workspaces: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Workspace lifecycle
    # ------------------------------------------------------------------

    def create_workspace(self, name: str) -> dict[str, Any]:
        """Create a new workspace.

        Parameters
        ----------
        name:
            Human-readable workspace name.

        Returns
        -------
        dict
            Workspace info containing ``workspace_id``, ``name``,
            ``created_at`` (ISO-8601), and ``member_count``.
        """
        workspace_id = uuid.uuid4().hex[:12]
        self._workspaces[workspace_id] = {
            "workspace_id": workspace_id,
            "name": name,
            "members": [],
            "tenant_dir": str(self.get_tenant_dir(workspace_id)),
        }
        AuditLog.record(
            who="system",
            action="workspace.create",
            what=workspace_id,
            metadata={"name": name},
        )
        return {
            "workspace_id": workspace_id,
            "name": name,
            "member_count": 0,
        }

    def invite_member(self, workspace_id: str, email: str, role: str) -> bool:
        """Invite a member to a workspace.

        Parameters
        ----------
        workspace_id:
            Target workspace ID.
        email:
            Member email address.
        role:
            One of ``ROLES`` (admin, strategist, editor, operator, viewer).

        Returns
        -------
        bool
            ``True`` on success.  ``False`` if the workspace does not exist
            or the role is invalid.
        """
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return False
        if role not in ROLES:
            return False
        # Avoid duplicate invites
        if any(m["email"] == email for m in ws["members"]):
            return False
        ws["members"].append(
            {
                "email": email,
                "role": role,
            }
        )
        AuditLog.record(
            who="system",
            action="member.invite",
            what=f"{email} -> {workspace_id}",
            metadata={"workspace_id": workspace_id, "role": role},
        )
        return True

    def exit_workspace(self, workspace_id: str) -> bool:
        """Remove (soft-delete) a workspace.

        Parameters
        ----------
        workspace_id:
            The workspace to remove.

        Returns
        -------
        bool
            ``True`` if the workspace existed and was removed.
        """
        if workspace_id not in self._workspaces:
            return False
        del self._workspaces[workspace_id]
        AuditLog.record(
            who="system",
            action="workspace.delete",
            what=workspace_id,
        )
        return True

    def list_members(self, workspace_id: str) -> list[dict[str, Any]]:
        """Return all members of a workspace.

        Parameters
        ----------
        workspace_id:
            Target workspace ID.

        Returns
        -------
        list[dict]
            Each member dict contains ``email`` and ``role`` keys.
            Returns an empty list if the workspace does not exist.
        """
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return []
        return list(ws["members"])

    def list_workspaces(self) -> list[dict[str, Any]]:
        """Return all registered workspaces.

        Returns
        -------
        list[dict]
            Each entry contains ``workspace_id``, ``name``, ``member_count``.
        """
        return [
            {
                "workspace_id": wid,
                "name": w["name"],
                "member_count": len(w["members"]),
            }
            for wid, w in self._workspaces.items()
        ]

    # ------------------------------------------------------------------
    # RBAC helpers
    # ------------------------------------------------------------------

    def get_member_role(self, workspace_id: str, email: str) -> str | None:
        """Return the role assigned to *email* in *workspace_id*.

        Returns ``None`` if the workspace or member is not found.
        """
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return None
        for m in ws["members"]:
            if m["email"] == email:
                return m["role"]
        return None

    def update_member_role(self, workspace_id: str, email: str, new_role: str) -> bool:
        """Change a member's role.

        Returns ``True`` on success, ``False`` if the workspace, member, or
        role is invalid.
        """
        if new_role not in ROLES:
            return False
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return False
        for m in ws["members"]:
            if m["email"] == email:
                old_role = m["role"]
                m["role"] = new_role
                AuditLog.record(
                    who="system",
                    action="member.role_update",
                    what=f"{email} in {workspace_id}",
                    metadata={"from": old_role, "to": new_role},
                )
                return True
        return False

    def remove_member(self, workspace_id: str, email: str) -> bool:
        """Remove a member from a workspace.

        Returns ``True`` on success, ``False`` if the workspace or member is
        not found.
        """
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return False
        before = len(ws["members"])
        ws["members"] = [m for m in ws["members"] if m["email"] != email]
        if len(ws["members"]) < before:
            AuditLog.record(
                who="system",
                action="member.remove",
                what=f"{email} from {workspace_id}",
            )
            return True
        return False

    # ------------------------------------------------------------------
    # File isolation
    # ------------------------------------------------------------------

    @staticmethod
    def get_tenant_dir(tenant_id: str) -> Path:
        """Return the root directory for a tenant's isolated file storage.

        Parameters
        ----------
        tenant_id:
            The tenant (workspace) identifier.

        Returns
        -------
        Path
            ``~/.automedia/tenants/{tenant_id}/``
        """
        return Path.home() / ".automedia" / "tenants" / tenant_id

    @staticmethod
    def get_tenant_asset_library_dir(tenant_id: str, brand: str) -> Path:
        """Return the per-tenant, per-brand asset library directory.

        Parameters
        ----------
        tenant_id:
            The tenant (workspace) identifier.
        brand:
            Brand name.

        Returns
        -------
        Path
            ``~/.automedia/tenants/{tenant_id}/asset-library/{brand}/``
        """
        return Path.home() / ".automedia" / "tenants" / tenant_id / "asset-library" / brand

    @staticmethod
    def get_tenant_config_dir(tenant_id: str) -> Path:
        """Return the per-tenant configuration directory.

        Parameters
        ----------
        tenant_id:
            The tenant (workspace) identifier.

        Returns
        -------
        Path
            ``~/.automedia/tenants/{tenant_id}/config/``
        """
        return Path.home() / ".automedia" / "tenants" / tenant_id / "config"
