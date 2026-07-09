"""``automedia tenant`` / ``automedia rbac`` — multi-tenant CLI."""

from __future__ import annotations

import typer

from automedia.tenant.audit import AuditLog
from automedia.tenant.manager import TenantManager
from automedia.tenant.rbac import ROLES, check_permission

# ---------------------------------------------------------------------------
# Sub-apps
# ---------------------------------------------------------------------------

app = typer.Typer(name="tenant", help="Multi-tenant workspace management.")
rbac_app = typer.Typer(name="rbac", help="Role-based access control.")

app.add_typer(rbac_app, name="rbac")

_tm: TenantManager | None = None


def _get_manager() -> TenantManager:
    global _tm
    if _tm is None:
        _tm = TenantManager()
    return _tm


# ---------------------------------------------------------------------------
# tenant create
# ---------------------------------------------------------------------------


@app.command("create")
def tenant_create(
    name: str = typer.Option(..., "--name", help="Workspace name"),
) -> None:
    """Create a new workspace."""
    tm = _get_manager()
    ws = tm.create_workspace(name)
    typer.secho(
        f"Workspace created: id={ws['workspace_id']}  name={ws['name']}",
        fg=typer.colors.GREEN,
    )


# ---------------------------------------------------------------------------
# tenant invite
# ---------------------------------------------------------------------------


@app.command("invite")
def tenant_invite(
    workspace: str = typer.Option(..., "--workspace", help="Workspace ID"),
    email: str = typer.Option(..., "--email", help="Member email"),
    role: str = typer.Option(
        ..., "--role", help=f"Role: {', '.join(ROLES)}"
    ),
) -> None:
    """Invite a member to a workspace."""
    if role not in ROLES:
        typer.secho(
            f"Invalid role '{role}'. Valid roles: {', '.join(ROLES)}",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    tm = _get_manager()
    ok = tm.invite_member(workspace, email, role)
    if not ok:
        typer.secho(
            f"Failed to invite '{email}' to workspace '{workspace}'. "
            "Does the workspace exist? Is the member already invited?",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    typer.secho(
        f"Invited {email} (role: {role}) to workspace {workspace}",
        fg=typer.colors.GREEN,
    )


# ---------------------------------------------------------------------------
# tenant list
# ---------------------------------------------------------------------------


@app.command("list")
def tenant_list() -> None:
    """List all workspaces."""
    tm = _get_manager()
    workspaces = tm.list_workspaces()
    if not workspaces:
        typer.echo("No workspaces found.")
        return
    typer.echo(f"{'ID':<14} {'Name':<20} {'Members':<8}")
    typer.echo("-" * 44)
    for ws in workspaces:
        typer.echo(
            f"{ws['workspace_id']:<14} {ws['name']:<20} {ws['member_count']:<8}"
        )


# ---------------------------------------------------------------------------
# tenant members
# ---------------------------------------------------------------------------


@app.command("members")
def tenant_members(
    workspace: str = typer.Option(..., "--workspace", help="Workspace ID"),
) -> None:
    """List members of a workspace."""
    tm = _get_manager()
    members = tm.list_members(workspace)
    if not members:
        typer.echo(f"No members in workspace {workspace} (or workspace not found).")
        return
    typer.echo(f"{'Email':<30} {'Role':<12}")
    typer.echo("-" * 42)
    for m in members:
        typer.echo(f"{m['email']:<30} {m['role']:<12}")


# ---------------------------------------------------------------------------
# tenant delete
# ---------------------------------------------------------------------------


@app.command("delete")
def tenant_delete(
    workspace: str = typer.Option(..., "--workspace", help="Workspace ID"),
) -> None:
    """Delete a workspace."""
    tm = _get_manager()
    ok = tm.exit_workspace(workspace)
    if not ok:
        typer.secho(
            f"Workspace '{workspace}' not found.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    typer.secho(f"Workspace {workspace} deleted.", fg=typer.colors.GREEN)


# ---------------------------------------------------------------------------
# tenant audit-log
# ---------------------------------------------------------------------------


@app.command("audit-log")
def tenant_audit_log() -> None:
    """Show the audit log."""
    entries = AuditLog.query()
    if not entries:
        typer.echo("Audit log is empty.")
        return
    for e in entries:
        ts = e["timestamp"][:19]  # strip microseconds
        typer.echo(f"[{ts}] {e['who']} :: {e['action']} :: {e['what']}")


# ---------------------------------------------------------------------------
# rbac grant
# ---------------------------------------------------------------------------


@rbac_app.command("grant")
def rbac_grant(
    workspace: str = typer.Option(..., "--workspace", help="Workspace ID"),
    user: str = typer.Option(..., "--user", help="Member email"),
    role: str = typer.Option(..., "--role", help=f"Role: {', '.join(ROLES)}"),
) -> None:
    """Grant (update) a role to a workspace member."""
    if role not in ROLES:
        typer.secho(
            f"Invalid role '{role}'. Valid roles: {', '.join(ROLES)}",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    tm = _get_manager()
    ok = tm.update_member_role(workspace, user, role)
    if not ok:
        typer.secho(
            f"Failed to grant role. Check workspace '{workspace}' and user '{user}'.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    typer.secho(f"Role '{role}' granted to {user} in workspace {workspace}.", fg=typer.colors.GREEN)


# ---------------------------------------------------------------------------
# rbac revoke
# ---------------------------------------------------------------------------


@rbac_app.command("revoke")
def rbac_revoke(
    workspace: str = typer.Option(..., "--workspace", help="Workspace ID"),
    user: str = typer.Option(..., "--user", help="Member email"),
) -> None:
    """Revoke (remove) a member from a workspace."""
    tm = _get_manager()
    ok = tm.remove_member(workspace, user)
    if not ok:
        typer.secho(
            f"Failed to revoke. Check workspace '{workspace}' and user '{user}'.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    typer.secho(f"Member {user} removed from workspace {workspace}.", fg=typer.colors.GREEN)


# ---------------------------------------------------------------------------
# rbac check
# ---------------------------------------------------------------------------


@rbac_app.command("check")
def rbac_check(
    role: str = typer.Option(..., "--role", help=f"Role: {', '.join(ROLES)}"),
    action: str = typer.Option(..., "--action", help="Action to check, e.g. 'content.create'"),
) -> None:
    """Check whether a role is allowed to perform an action."""
    allowed = check_permission(role, action)
    if allowed:
        typer.secho(f"Role '{role}' IS allowed to perform '{action}'.", fg=typer.colors.GREEN)
    else:
        typer.secho(f"Role '{role}' is NOT allowed to perform '{action}'.", fg=typer.colors.RED)
        raise typer.Exit(1)
