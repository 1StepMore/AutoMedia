"""AutoMedia CLI app — stub."""

import typer

from automedia._version import __version__

app = typer.Typer(name="automedia", help="AutoMedia — automated media production pipeline.")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(f"AutoMedia v{__version__}")
