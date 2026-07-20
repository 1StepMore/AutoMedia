"""AutoMedia CLI — main Typer application."""

from __future__ import annotations

import click
import typer
from typer.core import TyperGroup
from typer.main import (
    get_command as _typer_get_command,
)
from typer.main import (
    get_command_from_info as _get_cmd_from_info,
)
from typer.models import CommandInfo

from automedia._version import __version__

# ---------------------------------------------------------------------------
# Lazy-loading Click group — defers module imports until command dispatch
# ---------------------------------------------------------------------------

class LazyTyperGroup(TyperGroup):
    """Click Group that defers module imports until command dispatch.

    Sub-command modules are registered with static help text so that
    ``--help`` renders instantly.  The actual ``typer.Typer`` instance
    (or callback function) is imported only when the subcommand is
    invoked.
    """

    _lazy_sub_apps: dict[str, tuple[str, str, str]] = {}
    _lazy_fns: dict[str, tuple[str, str, str]] = {}

    # ------------------------------------------------------------------
    # Registration helpers (class-level, called at import time)
    # ------------------------------------------------------------------

    @classmethod
    def register_sub_app(
        cls,
        name: str,
        module_path: str,
        attr_name: str = "app",
        help_text: str = "",
    ) -> None:
        """Register a ``typer.Typer`` sub-app for lazy loading."""
        cls._lazy_sub_apps[name] = (module_path, attr_name, help_text)

    @classmethod
    def register_fn(
        cls,
        name: str,
        module_path: str,
        attr_name: str,
        help_text: str = "",
    ) -> None:
        """Register a standalone Typer-annotated function for lazy loading."""
        cls._lazy_fns[name] = (module_path, attr_name, help_text)

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    def _resolve_sub_app(self, cmd_name: str) -> click.Command | None:
        entry = self._lazy_sub_apps.get(cmd_name)
        if entry is None:
            return None
        import importlib

        mod = importlib.import_module(entry[0])
        app = getattr(mod, entry[1])
        cmd = _typer_get_command(app)
        self.add_command(cmd, name=cmd_name)
        return cmd

    def _resolve_fn(self, cmd_name: str) -> click.Command | None:
        entry = self._lazy_fns.get(cmd_name)
        if entry is None:
            return None
        import importlib

        mod = importlib.import_module(entry[0])
        fn = getattr(mod, entry[1])
        cmd_info = CommandInfo(
            name=cmd_name,
            callback=fn,
            help=entry[2] or None,
        )
        cmd = _get_cmd_from_info(
            cmd_info,
            pretty_exceptions_short=True,
            rich_markup_mode=None,
        )
        self.add_command(cmd, name=cmd_name)
        return cmd

    # ------------------------------------------------------------------
    # Click overrides
    # ------------------------------------------------------------------

    def get_command(
        self, ctx: click.Context, cmd_name: str,
    ) -> click.Command | None:
        # Already-resolved commands take priority.
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None:
            return cmd
        cmd = self._resolve_sub_app(cmd_name)
        if cmd is not None:
            return cmd
        cmd = self._resolve_fn(cmd_name)
        if cmd is not None:
            return cmd
        return None

    def list_commands(self, ctx: click.Context) -> list[str]:
        resolved = set(self.commands.keys())
        lazy_apps = [n for n in self._lazy_sub_apps if n not in resolved]
        lazy_fns = [n for n in self._lazy_fns if n not in resolved]
        return lazy_apps + lazy_fns + super().list_commands(ctx)

    def format_commands(
        self, ctx: click.Context, formatter: click.HelpFormatter,
    ) -> None:
        """Format commands without importing lazy modules."""
        rows: list[tuple[str, str]] = []
        resolved = set(self.commands.keys())

        for sub_name in self.commands:
            cmd = self.commands[sub_name]
            help_str = cmd.short_help or cmd.help or ""
            rows.append((cmd.name or sub_name, help_str))

        for name, (*_, help_text) in sorted(self._lazy_sub_apps.items()):
            if name not in resolved:
                rows.append((name, help_text))

        for name, (*_, help_text) in sorted(self._lazy_fns.items()):
            if name not in resolved:
                rows.append((name, help_text))

        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)


# ---------------------------------------------------------------------------
# Register all sub-commands lazily
# ---------------------------------------------------------------------------

LazyTyperGroup.register_sub_app(
    "account",
    "automedia.cli.commands.account",
    help_text="Manage platform accounts (connect, list, health, disconnect).",
)
LazyTyperGroup.register_sub_app(
    "adapter",
    "automedia.cli.commands.adapter",
    help_text="Manage platform adapters.",
)
LazyTyperGroup.register_sub_app(
    "cron",
    "automedia.cli.commands.cron",
    help_text="Execute scheduled cron jobs + pipeline runs.",
)
LazyTyperGroup.register_sub_app(
    "hitl",
    "automedia.cli.commands.hitl",
    help_text="Human-in-the-loop review operations.",
)
LazyTyperGroup.register_sub_app(
    "mcp",
    "automedia.cli.commands.mcp",
    help_text="MCP server management.",
)
LazyTyperGroup.register_sub_app(
    "omni",
    "automedia.cli.commands.omni",
    help_text="Omni Triad operations (ingest, localize, format-output).",
)
LazyTyperGroup.register_fn(
    "effects",
    "automedia.effects.cli",
    "effects_cmd",
    help_text="Compute content analytics for a project.",
)
LazyTyperGroup.register_sub_app(
    "onboard",
    "automedia.cli.commands.onboard",
    help_text="Onboarding wizard.",
)
LazyTyperGroup.register_sub_app(
    "pool",
    "automedia.cli.commands.pool",
    help_text="Topic pool management (list, add, score).",
)
LazyTyperGroup.register_sub_app(
    "projects",
    "automedia.cli.commands.projects",
    help_text="List and manage production projects.",
)

LazyTyperGroup.register_fn(
    "archive",
    "automedia.cli.commands.archive",
    "archive_cmd",
    help_text="Archive a project. Requires --force unless published.",
)
LazyTyperGroup.register_fn(
    "doctor",
    "automedia.cli.commands.doctor",
    "doctor_cmd",
    help_text="Check system dependencies and environment health.",
)
LazyTyperGroup.register_fn(
    "history",
    "automedia.cli.commands.history_cmd",
    "history_cmd",
    help_text="Show pipeline execution history for a project.",
)
LazyTyperGroup.register_fn(
    "init",
    "automedia.cli.commands.init_cmd",
    "init_cmd",
    help_text="Initialize AutoMedia configuration.",
)
LazyTyperGroup.register_fn(
    "rollback",
    "automedia.cli.commands.rollback",
    "rollback_cmd",
    help_text="Roll back a project: archive it and revert status to draft.",
)
LazyTyperGroup.register_fn(
    "run",
    "automedia.cli.commands.run",
    "run_cmd",
    help_text="Execute the full AutoMedia production pipeline.",
)
LazyTyperGroup.register_fn(
    "distribute",
    "automedia.cli.commands.distribute",
    "distribute_cmd",
    help_text="Run D-gates to prepare project content for distribution platforms.",
)


# ---------------------------------------------------------------------------
# Main Typer application
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="automedia",
    cls=LazyTyperGroup,
    help="AutoMedia — automated media production pipeline.",
    no_args_is_help=True,
    epilog=(
        f"AutoMedia v{__version__} — automated media production pipeline. "
        "Documentation: https://github.com/1stepmore/automedia"
    ),
)


def _version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the AutoMedia version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
    json_flag: bool = typer.Option(
        False,
        "--json",
        help="Output in JSON format (machine-readable).",
    ),
) -> None:
    """AutoMedia CLI — automated media production pipeline."""
    ctx.obj = {"version": version, "json": json_flag}
