"""``automedia init`` — interactive configuration wizard."""

from __future__ import annotations

from pathlib import Path

import typer

_CONFIG_DIR = Path(".automedia")
_CONFIG_FILE = _CONFIG_DIR / "config.yaml"


def _write_config(data: dict[str, str], path: Path = _CONFIG_FILE) -> None:
    """Write a minimal YAML config without requiring PyYAML at import time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# AutoMedia configuration", ""]
    for key, value in data.items():
        if value:
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: ''")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def init_cmd(
    template: str | None = typer.Option(
        None,
        "--template",
        help="Non-interactive template mode (e.g. 'minimal').",
    ),
) -> None:
    """Initialize AutoMedia configuration.

    Without ``--template`` runs an interactive wizard.
    With ``--template minimal`` generates a minimal non-interactive config.
    """
    if template == "minimal":
        _init_minimal()
    elif template is None:
        _init_interactive()
    else:
        typer.secho(f"Unknown template: {template!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


def _init_interactive() -> None:
    """Interactive configuration wizard."""
    typer.echo("AutoMedia Configuration Wizard")
    typer.echo("=" * 40)

    provider = typer.prompt("LLM provider (openai / anthropic)", default="openai")
    base_url = typer.prompt("API base URL", default="")
    api_key = typer.prompt("API key", hide_input=True, default="")

    _write_config({
        "llm_provider": provider,
        "llm_base_url": base_url,
        "llm_api_key": api_key,
    })

    typer.secho(f"\nConfiguration written to {_CONFIG_FILE}", fg=typer.colors.GREEN)


def _init_minimal() -> None:
    """Non-interactive minimal config generation."""
    _write_config({
        "llm_provider": "openai",
        "llm_base_url": "",
        "llm_api_key": "",
    })
    typer.secho(f"Minimal configuration written to {_CONFIG_FILE}", fg=typer.colors.GREEN)
