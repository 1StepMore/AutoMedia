"""``automedia hitl`` — Human-In-The-Loop configuration management.

Subcommands
-----------
preset --list            List available HITL presets
preset --set <name>      Activate a named preset
config                   Print the current HITL configuration summary
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
import yaml

from automedia.cli.output import output_error, output_text
from automedia.core.paths import get_user_config_dir
from automedia.hitl.config import HITLConfig

logger = logging.getLogger(__name__)

app = typer.Typer(name="hitl", help="Manage Human-In-The-Loop configuration.")

_PRESETS_DIR = Path(__file__).resolve().parent.parent.parent / "hitl" / "presets"
_ACTIVE_PRESET_PATH = get_user_config_dir() / "hitl" / "active_preset.yaml"

# Built-in presets that do not have a file on disk (defined in Python)
_BUILTIN_PRESETS: set[str] = {"test_automated"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _scan_filesystem_presets() -> list[str]:
    """Return preset names from YAML files in the presets directory."""
    if not _PRESETS_DIR.is_dir():
        return []
    return sorted(p.stem for p in _PRESETS_DIR.glob("*.yaml") if p.is_file() and p.stem)


def _read_active_preset() -> str | None:
    """Return the name of the currently active preset, or ``None``."""
    if not _ACTIVE_PRESET_PATH.is_file():
        return None
    try:
        with open(_ACTIVE_PRESET_PATH, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if isinstance(data, dict):
            return data.get("active_preset")
        return None
    except (OSError, yaml.YAMLError):
        logger.warning("Failed to read active HITL preset from %s", _ACTIVE_PRESET_PATH)
        return None


# ---------------------------------------------------------------------------
# hitl preset
# ---------------------------------------------------------------------------


@app.command("preset")
def preset(
    list_presets: bool = typer.Option(
        False,
        "--list",
        "-l",
        help="List available HITL presets.",
    ),
    set_preset: str | None = typer.Option(
        None,
        "--set",
        "-s",
        help="Set the active preset by name.",
    ),
) -> None:
    """List or activate HITL presets.

    **Examples**::

        automedia hitl preset --list
        automedia hitl preset --set automated
    """
    if list_presets:
        _show_presets()
        return

    if set_preset is not None:
        _activate_preset(set_preset)
        return

    # No flags — show current active preset
    current = _read_active_preset()
    if output_text(
        None,
        data={"status": "ok", "active_preset": current or "automated"},
    ):
        return
    if current:
        typer.echo(f"Active preset: {current}")
    else:
        typer.echo("No active preset set. Default is 'automated'.")


def _show_presets() -> None:
    """Print all available presets to stdout."""
    filesystem = _scan_filesystem_presets()
    all_presets = sorted(set(filesystem) | _BUILTIN_PRESETS)

    active = _read_active_preset()
    if output_text(
        None,
        data={
            "status": "ok",
            "presets": [
                {
                    "name": name,
                    "source": "built-in" if name in _BUILTIN_PRESETS else "file",
                    "active": name == active,
                }
                for name in all_presets
            ],
            "active_preset": active,
        },
    ):
        return

    if not all_presets:
        typer.echo("No presets found.")
        return

    typer.echo("Available HITL presets:")
    for name in all_presets:
        marker = "*" if name == active else " "
        source = "built-in" if name in _BUILTIN_PRESETS else "file"
        typer.echo(f"  {marker} {name:<20} ({source})")

    if active:
        typer.echo("\n(* = active)")


def _activate_preset(name: str) -> None:
    """Activate a preset by name (validates it exists first)."""
    filesystem = _scan_filesystem_presets()
    all_presets = set(filesystem) | _BUILTIN_PRESETS

    if name not in all_presets:
        output_error(
            f"Preset {name!r} not found.\n"
            f"Run 'automedia hitl preset --list' to see available presets."
        )

    # Validate the preset loads correctly
    try:
        HITLConfig(preset_name=name)
    except Exception as exc:
        output_error(f"Failed to load preset {name!r}: {exc}", code=0)
        raise typer.Exit(code=1) from exc

    # Write active preset file
    _ACTIVE_PRESET_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(_ACTIVE_PRESET_PATH, "w", encoding="utf-8") as fh:
            yaml.dump({"active_preset": name}, fh, default_flow_style=False)
    except Exception as exc:
        output_error(f"Failed to write active preset: {exc}", code=0)
        raise typer.Exit(code=1) from exc

    output_text(
        f"Active preset set to {name!r}.",
        data={"status": "ok", "active_preset": name},
        green=True,
    )


# ---------------------------------------------------------------------------
# hitl config
# ---------------------------------------------------------------------------


@app.command("config")
def config_cmd() -> None:
    """Print a summary of the current HITL configuration."""
    active_name = _read_active_preset() or "automated"

    try:
        config = HITLConfig(preset_name=active_name)
    except Exception as exc:
        output_error(f"Failed to load HITL config: {exc}", code=0)
        raise typer.Exit(code=1) from exc

    nodes = config.list_nodes()

    # Count by executor type
    human_count = sum(1 for n in nodes if n.get("autoset") == "human")
    agent_count = sum(1 for n in nodes if n.get("autoset") == "agent")

    # Count by type
    type_counts: dict[str, int] = {}
    for n in nodes:
        t = n.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    if output_text(
        None,
        data={
            "status": "ok",
            "active_preset": active_name,
            "total_nodes": len(nodes),
            "human_nodes": human_count,
            "agent_nodes": agent_count,
            "by_type": type_counts,
            "nodes": sorted(nodes, key=lambda x: x.get("name", "")),
        },
    ):
        return

    typer.echo("HITL Configuration Summary")
    typer.echo(f"{'=' * 40}")
    typer.echo(f"  Active preset  : {active_name}")
    typer.echo(f"  Total nodes    : {len(nodes)}")
    typer.echo(f"  Human nodes    : {human_count}")
    typer.echo(f"  Agent nodes    : {agent_count}")
    if type_counts:
        typer.echo(f"  By type        : {type_counts}")
    typer.echo()

    # Print the node breakdown
    typer.echo(f"{'Node':<30} {'Type':<15} {'Executor':<10}")
    typer.echo("-" * 55)
    for n in sorted(nodes, key=lambda x: x.get("name", "")):
        name = n.get("name", "?")
        ntype = n.get("type", "?")
        executor = n.get("autoset", "agent")
        typer.echo(f"  {name:<28} {ntype:<15} {executor:<10}")
