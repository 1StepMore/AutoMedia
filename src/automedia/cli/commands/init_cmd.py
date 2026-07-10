"""``automedia init`` — interactive configuration wizard.

Writes ``~/.automedia/model_config.yaml`` with the nested structure
that ``config_loader`` and ``llm_client`` expect.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import typer
import yaml

from automedia.cli.output import OutputMode, get_output_mode, output_error_json, output_json

_USER_CFG_DIR = Path.home() / ".automedia"
_MODEL_CONFIG_FILE = _USER_CFG_DIR / "model_config.yaml"
_MANIFESTS_DIR = Path(__file__).resolve().parent.parent.parent / "manifests"


def _write_model_config(data: dict) -> None:
    """Write a YAML model_config to ``~/.automedia/model_config.yaml``."""
    _USER_CFG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_MODEL_CONFIG_FILE, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
    os.chmod(_MODEL_CONFIG_FILE, 0o600)
    typer.secho(f"\nConfiguration written to {_MODEL_CONFIG_FILE}", fg=typer.colors.GREEN)


def init_cmd(
    template: str | None = typer.Option(
        None,
        "--template",
        help="Non-interactive template mode (e.g. 'minimal').",
    ),
    omni: bool = typer.Option(
        False,
        "--omni",
        help="Initialize Omni Triad configuration interactively.",
    ),
) -> None:
    """Initialize AutoMedia configuration.

    Without ``--template`` runs an interactive wizard that writes
    ``~/.automedia/model_config.yaml``.

    With ``--template minimal`` generates a minimal non-interactive config
    in the same location.

    With ``--omni`` runs the Omni Triad interactive configuration wizard.
    """
    is_json = get_output_mode() == OutputMode.JSON

    if omni:
        _init_omni(is_json=is_json)
    elif template == "minimal":
        _init_minimal(is_json=is_json)
    elif template is None:
        if is_json:
            output_error_json("Interactive init not supported in --json mode. Use --template minimal.")
            raise typer.Exit(code=1)
        _init_interactive()
    else:
        msg = f"Unknown template: {template!r}"
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
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


def _init_minimal(*, is_json: bool = False) -> None:
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
    if is_json:
        output_json({"status": "ok", "path": str(_MODEL_CONFIG_FILE)})


def _init_omni(*, is_json: bool = False) -> None:
    """Interactive Omni Triad configuration wizard.

    Creates ``~/.automedia/omni_config.yaml``, copies template allowlist and
    localizer config files, and prompts the user for key settings.
    """
    # Check that all required template paths exist before proceeding.
    _required_templates = [
        _MANIFESTS_DIR / "omni_allowlist_template.yaml",
        _MANIFESTS_DIR / "ol_config_template.yaml",
        _MANIFESTS_DIR / "omni_config_template.yaml",
    ]
    missing = [str(p) for p in _required_templates if not p.exists()]
    if missing:
        msg = (
            "Error: The following required template file(s) were not found:\n"
            + "\n".join(f"  • {m}" for m in missing)
        )
        if is_json:
            output_error_json(msg)
        else:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    _USER_CFG_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(
        _MANIFESTS_DIR / "omni_allowlist_template.yaml",
        _USER_CFG_DIR / "omni_allowlist.yaml",
    )
    ol_dir = _USER_CFG_DIR / "omni"
    ol_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        _MANIFESTS_DIR / "ol_config_template.yaml",
        ol_dir / "ol_config.yaml",
    )

    integration_mode = typer.prompt("Integration mode", default="proxy", type=str)
    max_auto_extract_mb = typer.prompt("Max auto-extract (MB)", default=50, type=int)

    omni_config_path = _USER_CFG_DIR / "omni_config.yaml"
    with open(_MANIFESTS_DIR / "omni_config_template.yaml", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    config["integration_mode"] = integration_mode
    config["max_auto_extract_mb"] = max_auto_extract_mb

    with open(omni_config_path, "w", encoding="utf-8") as fh:
        yaml.dump(config, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)

    if is_json:
        output_json({
            "status": "ok",
            "config_dir": str(_USER_CFG_DIR),
            "files": [
                "omni_config.yaml",
                "omni_allowlist.yaml",
                "omni/ol_config.yaml",
            ],
        })
    else:
        typer.secho(f"\nOmni configuration written to {_USER_CFG_DIR}", fg=typer.colors.GREEN)
        typer.secho("  └─ omni_config.yaml", fg=typer.colors.GREEN)
        typer.secho("  └─ omni_allowlist.yaml", fg=typer.colors.GREEN)
        typer.secho("  └─ omni/ol_config.yaml", fg=typer.colors.GREEN)
