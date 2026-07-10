"""Structured logging configuration using structlog.

Provides :func:`configure_structlog` for one-time setup and
:func:`get_logger` as a convenience wrapper around
``structlog.get_logger``.

When ``AUTOMEDIA_LOG_FORMAT`` is set to ``"json"``, logs are rendered
as single-line JSON (suitable for production / log aggregators).
Otherwise the human-friendly console renderer is used (suitable for
local development).
"""

from __future__ import annotations

import logging
import os

import structlog

_CONFIGURED = False


def configure_structlog() -> None:
    """Configure structlog with sensible defaults.

    Safe to call multiple times — the first call wins; subsequent
    calls are no-ops.

    The renderer is selected by the ``AUTOMEDIA_LOG_FORMAT``
    environment variable:

    * ``"json"`` → :class:`structlog.processors.JSONRenderer`
    * anything else (default) → :class:`structlog.dev.ConsoleRenderer`
    """
    global _CONFIGURED  # noqa: PLW0603
    if _CONFIGURED:
        return
    _CONFIGURED = True

    fmt = os.environ.get("AUTOMEDIA_LOG_FORMAT", "console").lower()

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if fmt == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    # Attach to the root stdlib handler so structlog-wrapped loggers
    # and plain ``logging.getLogger()`` calls both produce output.
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to *name*.

    A thin convenience wrapper — equivalent to
    ``structlog.get_logger(name)`` but ensures the module is
    importable without a direct ``structlog`` dependency at call sites.
    """
    return structlog.get_logger(name)
