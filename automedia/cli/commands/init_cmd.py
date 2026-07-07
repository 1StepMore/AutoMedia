"""``automedia init`` — interactive configuration wizard.

Writes ``~/.automedia/model_config.yaml`` with the nested structure
that ``config_loader`` and ``llm_client`` expect.
"""

from __future__ import annotations

from pathlib import Path

import typer
import yaml

_USER_CFG_DIR = Path.home() / ".automedia"
_MODEL_CONFIG_FILE = _USER_CFG_DIR / "model_config.yaml"


def _write_model_config(data: dict) -> None:
    """Write a YAML model_config to ``~/.automedia/model_config.yaml``."""
    _USER_CFG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_MODEL_CONFIG_FILE, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
    typer.secho(f"\nConfiguration written to {_MODEL_CONFIG_FILE}", fg=typer.colors.GREEN)


def init_cmd(
    template: str | None = typer.Option(
        None,
        "--template",
        help="Non-interactive template mode (e.g. 'minimal').",
    ),
) -> None:
    """Initialize AutoMedia configuration.

    Without ``--template`` runs an interactive wizard that writes
    ``~/.automedia/model_config.yaml``.

    With ``--template minimal`` generates a minimal non-interactive config
    in the same location.
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

    provider = typer.prompt("LLM provider", default="openai")
    model = typer.prompt("Model", default="gpt-4o-mini")
    api_key = typer.prompt("API key", hide_input=True)
    base_url = typer.prompt("API base URL (leave blank for default)", default="")

    data = {
        "llm": {
            "text_generation": {
                "provider": provider,
                "model": model,
                "api_key": api_key,
            },
        },
    }
    if base_url:
        data["llm"]["text_generation"]["base_url"] = base_url

    _write_model_config(data)


def _init_minimal() -> None:
    """Non-interactive minimal config generation."""
    data = {
        "llm": {
            "text_generation": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": "",
            },
        },
    }
    _write_model_config(data)
