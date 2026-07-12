"""``automedia account`` — PRD-4 account management CLI commands."""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.table import Table

from automedia.accounts.registry import AccountRegistry

app = typer.Typer(help="Manage platform accounts for publishing.")
console = Console(width=200)

_registry: AccountRegistry | None = None


def _get_registry() -> AccountRegistry:
    """Lazily initialised AccountRegistry singleton."""
    global _registry  # noqa: PLW0603 — intentional module-level lazy init
    if _registry is None:
        _registry = AccountRegistry()
    return _registry


@app.command()
def connect(
    platform: str = typer.Argument(..., help="Platform name (wechat, zhihu, ...)"),
    auth_type: str = typer.Option("api_key", "--auth-type", help="Authentication type"),
    label: str = typer.Option("", "--label", help="Human-readable label"),
) -> None:
    """Register a new platform account."""
    console.print(f"[bold]Connecting {platform} account...[/bold]")
    console.print("Enter credentials as key=value pairs (one per line, empty line to finish):")

    credentials: dict[str, str] = {}
    while True:
        sys.stdout.write("  ")
        sys.stdout.flush()
        line = sys.stdin.readline()
        if not line or not line.strip():
            break
        if "=" in line:
            key, _, value = line.partition("=")
            credentials[key.strip()] = value.strip()

    if not credentials:
        console.print("[red]No credentials provided. Aborting.[/red]")
        raise typer.Exit(1)

    try:
        meta = _get_registry().register(platform, credentials, label=label, auth_type=auth_type)
        console.print(f"[green]Account registered: [bold]{meta['account_id']}[/bold]")
        console.print(f"  Platform: {meta['platform']}")
        console.print(f"  Label: {meta.get('label', '')}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def list(
    platform: str | None = typer.Option(None, "--platform", "-p", help="Filter by platform"),
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status"),
) -> None:
    """List registered accounts."""
    accounts = _get_registry().list(platform=platform, status=status)

    if not accounts:
        console.print("[yellow]No accounts found.[/yellow]")
        return

    table = Table(title="Platform Accounts")
    table.add_column("ID", style="cyan")
    table.add_column("Platform", style="green")
    table.add_column("Label", style="white")
    table.add_column("Auth Type", style="blue")
    table.add_column("Status", style="yellow")
    table.add_column("Last Used", style="magenta")

    for acc in accounts:
        table.add_row(
            acc.get("account_id", ""),
            acc.get("platform", ""),
            acc.get("label", ""),
            acc.get("auth_type", ""),
            acc.get("status", ""),
            str(acc.get("last_used", "")),
        )

    console.print(table)


@app.command()
def health(
    account_id: str = typer.Argument(..., help="Account ID"),
) -> None:
    """Check account session health."""
    info = _get_registry().get(account_id)
    if not info:
        console.print(f"[red]Account not found: {account_id}[/red]")
        raise typer.Exit(1)

    console.print(f"Account: [bold]{account_id}[/bold]")
    console.print(f"Platform: {info.get('platform', '')}")
    console.print(f"Label: {info.get('label', '')}")
    console.print(f"Status: {info.get('status', '')}")
    console.print(f"Last Health Check: {info.get('last_health_check', 'Never')}")

    if info.get("status") == "active":
        console.print("[green]Account is active[/green]")
    else:
        console.print(f"[yellow]Account status: {info.get('status', 'unknown')}[/yellow]")


@app.command()
def disconnect(
    account_id: str = typer.Argument(..., help="Account ID to disconnect"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Remove a platform account."""
    info = _get_registry().get(account_id)
    if not info:
        console.print(f"[red]Account not found: {account_id}[/red]")
        raise typer.Exit(1)

    if not yes:
        console.print(
            f"About to disconnect: [bold]{account_id}[/bold] "
            f"({info.get('platform', '')} - {info.get('label', '')})"
        )
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            return

    _get_registry().delete(account_id)
    console.print(f"[green]Account disconnected: {account_id}[/green]")


@app.command()
def refresh(
    account_id: str = typer.Argument(..., help="Account ID"),
) -> None:
    """Force refresh an account session."""
    info = _get_registry().get(account_id)
    if not info:
        console.print(f"[red]Account not found: {account_id}[/red]")
        raise typer.Exit(1)

    # Actual refresh logic requires AuthFlowEngine integration (Wave 6+)
    console.print(f"[yellow]Session refresh requested for {account_id}[/yellow]")
    console.print("Full refresh integration requires AuthFlowEngine (Wave 6+).")
