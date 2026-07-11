"""Shared JSON output helpers for the AutoMedia CLI.

Provides :class:`OutputMode`, :func:`get_output_mode`, :func:`output_json`,
and :func:`output_error_json` so every command can branch on the ``--json``
flag without duplicating serialization logic.
"""

from __future__ import annotations

import json
from enum import Enum

import structlog
import typer
from typer._click.globals import get_current_context

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
