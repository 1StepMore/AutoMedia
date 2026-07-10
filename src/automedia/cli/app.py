"""AutoMedia CLI — main Typer application."""

from __future__ import annotations

import typer

from automedia._version import __version__
from automedia.cli.commands.adapter import app as adapter_app
from automedia.cli.commands.archive import archive_cmd
from automedia.cli.commands.cron import app as cron_app
from automedia.cli.commands.doctor import doctor_cmd
from automedia.cli.commands.hitl import app as hitl_app
from automedia.cli.commands.init_cmd import init_cmd
from automedia.cli.commands.license import app as license_app
from automedia.cli.commands.omni import app as omni_app
from automedia.cli.commands.onboard import app as onboard_app
from automedia.cli.commands.pool import app as pool_app
from automedia.cli.commands.projects import app as projects_app
from automedia.cli.commands.run import run_cmd
from automedia.cli.commands.sop import app as sop_app
from automedia.cli.commands.tenant import app as tenant_app
from automedia.decision.cli.solution import app as solution_app

app = typer.Typer(
    name="automedia",
    help="AutoMedia — automated media production pipeline.",
    no_args_is_help=True,
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


# ---------------------------------------------------------------------------
# Register sub-commands
# ---------------------------------------------------------------------------


app.add_typer(pool_app, name="pool")
app.add_typer(projects_app, name="projects")
app.add_typer(adapter_app, name="adapter")
app.add_typer(cron_app, name="cron")
app.add_typer(omni_app, name="omni")
app.add_typer(hitl_app, name="hitl")
app.add_typer(license_app, name="license")
app.add_typer(sop_app, name="sop")
app.add_typer(tenant_app, name="tenant")
app.add_typer(solution_app, name="solution")
app.add_typer(onboard_app, name="onboard")


app.command(name="run", help="Execute the full AutoMedia production pipeline.")(run_cmd)
app.command(
    name="archive", help="Archive a project. Red Line 8: requires --force unless published."
)(archive_cmd)
app.command(name="init", help="Initialize AutoMedia configuration.")(init_cmd)
app.command(name="doctor", help="Check system dependencies and environment health.")(doctor_cmd)
