"""Cron job definitions for scheduled AutoMedia tasks."""

from structlog import get_logger

log = get_logger(__name__)

__all__ = [
    "run_cron_jobs",
]
