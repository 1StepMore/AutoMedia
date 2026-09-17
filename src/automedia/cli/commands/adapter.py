"""``automedia adapter`` — manage platform adapters.

Note: Account management has moved to ``automedia account``.
The ``automedia adapter`` commands are deprecated.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from automedia.adapters.registry import AdapterRegistry
from automedia.cli.output import (
    output_error,
    output_text,
)

if TYPE_CHECKING:
    from typing import Any

try:
    # mirrors automedia.cli.output's context import — mode detection must agree
    from typer._click.globals import get_current_context
except ImportError:
    from click import get_current_context  # type: ignore[no-redef]

app = typer.Typer(name="adapter", help="List and create platform adapters.")


def _force_json_output_mode() -> None:
    """Flip the click context to JSON mode so shared output helpers serialize."""
    ctx = get_current_context(silent=True)
    if ctx is None:
        output_error("Unable to enable JSON output mode: no active command context.")
        return
    obj = ctx.obj if isinstance(ctx.obj, dict) else {}
    obj["json"] = True
    ctx.obj = obj


# ---------------------------------------------------------------------------
# adapter list
# ---------------------------------------------------------------------------


@app.command("list")
def adapter_list(
    real: bool = typer.Option(
        False,
        "--real",
        help="Only platforms with real API automation (is_stub=False).",
    ),
    stub: bool = typer.Option(
        False,
        "--stub",
        help="Only manual-publish stub platforms (is_stub=True).",
    ),
    json_flag: bool = typer.Option(
        False,
        "--json",
        help="Output in JSON format (machine-readable).",
    ),
) -> None:
    """List registered platform adapters with real/stub audit status.

    Platform-audit view for ``automedia adapter list``: every row carries its
    automation status derived from the adapter's ``is_stub`` attribute.
    ``--real`` / ``--stub`` filter the list; ``--json`` (also accepted at the
    app level as ``automedia --json adapter list``) switches to
    machine-readable output.
    """
    if real and stub:
        output_error("--real and --stub cannot be combined. Choose one filter.")

    if json_flag:
        _force_json_output_mode()

    try:
        from automedia.adapters import ensure_registered

        ensure_registered()
    except ImportError:
        from automedia.core._import_helpers import warn_missing_optional

        warn_missing_optional("adapters", feature="platform adapter registration")

    platforms: list[dict[str, Any]] = AdapterRegistry().list_publishable_platforms()
    if real:
        platforms = [p for p in platforms if not p["is_stub"]]
    if stub:
        platforms = [p for p in platforms if p["is_stub"]]

    if output_text(
        None,
        data={
            "status": "ok",
            "adapters": platforms,
            "count": len(platforms),
            "filters": {"real": real, "stub": stub},
        },
    ):
        return

    if not platforms:
        typer.echo("No adapters registered.")
        return

    typer.echo("Registered adapters:")
    for platform in platforms:
        status = "stub" if platform["is_stub"] else "real"
        typer.echo(f"  - {platform['name']}: {status}")


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
        "src/automedia/adapters/platforms",
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
