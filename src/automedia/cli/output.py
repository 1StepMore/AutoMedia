"""Shared JSON output helpers for the AutoMedia CLI.

Provides :class:`OutputMode`, :func:`get_output_mode`, :func:`output_json`,
and :func:`output_error_json` so every command can branch on the ``--json``
flag without duplicating serialization logic.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

import structlog
import typer

try:
    # typer >= 0.12 vendors click as typer._click — uses its own context
    # stack that is separate from the externally installed click package.
    from typer._click.globals import get_current_context
except ImportError:
    # typer < 0.12 — click is an external dependency; context stack is
    # shared between typer and the externally installed click package.
    from click import get_current_context

logger = structlog.get_logger()


class OutputMode(Enum):
    """CLI output mode."""

    TEXT = "text"
    JSON = "json"


def get_output_mode() -> OutputMode:
    """Read the ``--json`` flag from the current click context and return the output mode."""
    try:
        ctx = get_current_context(silent=True)
        if ctx and ctx.obj and ctx.obj.get("json"):
            return OutputMode.JSON
    except Exception as exc:
        logger.debug("failed to read click context for --json flag", error=str(exc))
    return OutputMode.TEXT


def output_json(data: object) -> None:
    """Serialize *data* as pretty-printed JSON and print it to stdout."""
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def output_error_json(error: str) -> None:
    """Print a JSON error envelope to stdout."""
    output_json({"status": "error", "error": error})


def output_error(msg: str, code: int = 1) -> None:
    """Print an error message (JSON or red text) and optionally exit.

    Args:
        msg: Error message to display.
        code: Exit code (default 1).  Pass ``code=0`` to only print without
            raising ``typer.Exit`` (e.g. when the caller needs to chain
            the exception with ``from exc``).

    Raises:
        typer.Exit: When *code* is non-zero.
    """
    if get_output_mode() == OutputMode.JSON:
        output_error_json(msg)
    else:
        typer.secho(msg, fg=typer.colors.RED, err=True)
    if code:
        raise typer.Exit(code=code)


def output_text(
    msg: str | None = None,
    data: dict[str, Any] | None = None,
    *,
    green: bool = False,
) -> bool:
    """Display a message in the current output mode.

    In JSON mode (*is_json* is true) the *data* dict is printed and the
    function returns ``True`` so callers can ``return`` early.

    In text mode the string *msg* is printed via ``typer.echo`` (or
    ``typer.secho`` with green styling when *green* is ``True``).  When
    *msg* is ``None`` nothing is printed in text mode.

    Args:
        msg: Human-readable message for text mode (``None`` → silent).
        data: Data dict for JSON mode.  When ``None`` the JSON output is
            ``{"message": "<msg>"}``.
        green: Use green styling in text mode.

    Returns:
        ``True`` when the output mode is JSON.
    """
    is_json = get_output_mode() == OutputMode.JSON
    if is_json:
        output_json(data if data is not None else {"message": msg or ""})
        return True
    if msg:
        if green:
            typer.secho(msg, fg=typer.colors.GREEN)
        else:
            typer.echo(msg)
    return False
