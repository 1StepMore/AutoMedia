"""``automedia adapter`` — manage platform adapters."""

from __future__ import annotations

import textwrap
from pathlib import Path

import typer

from automedia.adapters.registry import AdapterRegistry

app = typer.Typer(name="adapter", help="List and create platform adapters.")


# ---------------------------------------------------------------------------
# adapter list
# ---------------------------------------------------------------------------

@app.command("list")
def adapter_list() -> None:
    """List all registered platform adapters."""
    try:
        import automedia.adapters.platforms  # noqa: F401 — trigger registration
    except ImportError:
        pass

    names = AdapterRegistry.list()
    if not names:
        typer.echo("No adapters registered.")
        return

    typer.echo("Registered adapters:")
    for name in names:
        typer.echo(f"  - {name}")


# ---------------------------------------------------------------------------
# adapter create
# ---------------------------------------------------------------------------

_ADAPTER_TEMPLATE = textwrap.dedent('''\
    """Platform adapter for {name}."""

    from __future__ import annotations

    from typing import Any

    from automedia.adapters.base import BasePlatformAdapter


    class {class_name}Adapter(BasePlatformAdapter):
        """Publish content to {name}."""

        @property
        def platform_name(self) -> str:
            return "{name_lower}"

        def publish(self, artifact_dir: str, project: dict[str, Any]) -> dict[str, Any]:
            """Publish *artifact_dir* to {name}."""
            # TODO: implement publishing logic
            return {{"status": "ok", "platform": self.platform_name}}

        def validate(self, artifact_dir: str) -> bool:
            """Pre-flight checks for {name} publishing."""
            # TODO: implement validation
            return True
''')


@app.command("create")
def adapter_create(
    name: str = typer.Option(..., "--name", "-n", help="Platform name (e.g. youtube)."),
    output_dir: str = typer.Option(
        "automedia/adapters/platforms",
        "--output-dir",
        "-o",
        help="Directory to write the adapter file.",
    ),
) -> None:
    """Generate a new adapter template file."""
    class_name = name.replace("_", " ").replace("-", " ").title().replace(" ", "")
    content = _ADAPTER_TEMPLATE.format(name=name, class_name=class_name, name_lower=name.lower())

    out_path = Path(output_dir) / f"{name}_adapter.py"
    if out_path.exists():
        typer.secho(f"File already exists: {out_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        typer.secho(f"Error writing adapter: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"Adapter created: {out_path}", fg=typer.colors.GREEN)
