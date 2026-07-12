"""``automedia doctor`` — dependency and environment health check."""

from __future__ import annotations

import platform
from typing import Any

import typer

from automedia.cli.output import OutputMode, get_output_mode, output_json
from automedia.core.doctor import Doctor


def doctor_cmd(
    install_missing: bool = typer.Option(
        False,
        "--install-missing",
        help="Print OS-appropriate install commands for missing dependencies.",
    ),
) -> None:
    """Run a dependency status check and print a formatted table."""
    d = Doctor()
    results = d.check_dependencies()

    if get_output_mode() == OutputMode.JSON:
        all_ok = all(dep["installed"] for dep in results)
        payload: dict[str, Any] = {
            "status": "ok" if all_ok else "error",
            "dependencies": results,
        }
        if install_missing:
            missing_instructions = {}
            for dep in results:
                if not dep["installed"]:
                    instruction = Doctor.get_install_instructions(dep["name"])
                    if instruction:
                        missing_instructions[dep["name"]] = instruction
            if missing_instructions:
                payload["install_instructions"] = missing_instructions
        output_json(payload)
        if not all_ok:
            raise typer.Exit(code=1)
        return

    typer.echo("Dependency Check:")
    typer.echo("-" * 60)
    typer.echo(f"{'Tool':<16} {'Installed':<12} {'Version'}")
    typer.echo("-" * 60)

    all_ok = True
    for dep in results:
        icon = "✓" if dep["installed"] else "✗"
        version = dep.get("version") or "—"
        colour = typer.colors.GREEN if dep["installed"] else typer.colors.RED
        typer.secho(
            f"{icon} {dep['name']:<14} {'yes' if dep['installed'] else 'no':<12} {version}",
            fg=colour,
        )
        if not dep["installed"]:
            all_ok = False

    typer.echo("-" * 60)
    if all_ok:
        typer.secho("All dependencies satisfied.", fg=typer.colors.GREEN)
    else:
        typer.secho("Some dependencies are missing.", fg=typer.colors.YELLOW, err=True)

    if install_missing and not all_ok:
        os_name = platform.system()
        typer.echo("")
        typer.secho(f"Install instructions ({os_name}):", fg=typer.colors.CYAN, bold=True)
        typer.echo("-" * 60)
        for dep in results:
            if not dep["installed"]:
                instruction = Doctor.get_install_instructions(dep["name"])
                if instruction:
                    typer.secho(f"  {dep['name']}:", fg=typer.colors.YELLOW, bold=True)
                    typer.echo(f"    {instruction}")
                else:
                    typer.secho(f"  {dep['name']}:", fg=typer.colors.YELLOW, bold=True)
                    typer.echo("    No automatic install instruction available.")
        typer.echo("-" * 60)

    if not all_ok:
        raise typer.Exit(code=1)
