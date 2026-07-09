"""AutoMedia CLI — main Typer application."""

from __future__ import annotations

import typer

from automedia._version import __version__

app = typer.Typer(
    name="automedia",
    help="AutoMedia — automated media production pipeline.",
    no_args_is_help=True,
)


@app.callback()
def main(ctx: typer.Context) -> None:
    """AutoMedia CLI — automated media production pipeline."""
    pass


# ---------------------------------------------------------------------------
# Register sub-commands
# ---------------------------------------------------------------------------

from automedia.cli.commands.pool import app as pool_app  # noqa: E402
from automedia.cli.commands.projects import app as projects_app  # noqa: E402
from automedia.cli.commands.adapter import app as adapter_app  # noqa: E402
from automedia.cli.commands.cron import app as cron_app  # noqa: E402
from automedia.cli.commands.omni import app as omni_app  # noqa: E402
from automedia.cli.commands.hitl import app as hitl_app  # noqa: E402
from automedia.cli.commands.license import app as license_app  # noqa: E402
from automedia.cli.commands.sop import app as sop_app  # noqa: E402
from automedia.cli.commands.tenant import app as tenant_app  # noqa: E402
from automedia.decision.cli.solution import app as solution_app  # noqa: E402

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

from automedia.cli.commands.run import run_cmd  # noqa: E402
from automedia.cli.commands.archive import archive_cmd  # noqa: E402
from automedia.cli.commands.init_cmd import init_cmd  # noqa: E402
from automedia.cli.commands.doctor import doctor_cmd  # noqa: E402

app.command(name="run", help="Execute the full AutoMedia production pipeline.")(run_cmd)
app.command(name="archive", help="Archive a project. Red Line 8: requires --force unless published.")(archive_cmd)
app.command(name="init", help="Initialize AutoMedia configuration.")(init_cmd)
app.command(name="doctor", help="Check system dependencies and environment health.")(doctor_cmd)


def cli_main() -> None:
    """Entry-point for console_scripts."""
    app()
