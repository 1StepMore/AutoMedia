"""``automedia adapter`` — manage platform adapters.

Note: Account management has moved to ``automedia account``.
The ``automedia adapter`` commands are deprecated.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import typer

from automedia.adapters.registry import AdapterRegistry
from automedia.cli.output import output_error, output_text

app = typer.Typer(name="adapter", help="List and create platform adapters.")


# ---------------------------------------------------------------------------
# adapter list
# ---------------------------------------------------------------------------


@app.command("list")
def adapter_list() -> None:
    """List all registered platform adapters."""
    try:  # noqa: SIM105 — suppress is not clearer here
        import automedia.adapters.platforms  # noqa: F401 — trigger registration
    except ImportError:
        from automedia.core._import_helpers import warn_missing_optional

        warn_missing_optional("adapters.platforms", feature="platform adapter registration")

    names = AdapterRegistry.list()
    if output_text(
        None,
        data={"status": "ok", "adapters": names, "count": len(names)},
    ):
        return

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
            return {{"status": "ok", "platform": self.platform_name}}

        def validate(self, artifact_dir: str) -> bool:
            """Pre-flight checks for {name} publishing."""
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
        output_error(f"File already exists: {out_path}")

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        output_error(f"Error writing adapter: {exc}", code=0)
        raise typer.Exit(code=1) from exc

    output_text(
        f"Adapter created: {out_path}",
        data={"status": "ok", "path": str(out_path)},
        green=True,
    )
