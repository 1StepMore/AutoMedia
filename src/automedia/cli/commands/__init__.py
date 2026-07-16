"""CLI command modules — each submodule defines a typer sub-application."""

from automedia.cli.commands.account import app as account_app
from automedia.cli.commands.adapter import app as adapter_app
from automedia.cli.commands.archive import archive_cmd
from automedia.cli.commands.cron import app as cron_app
from automedia.cli.commands.doctor import doctor_cmd
from automedia.cli.commands.hitl import app as hitl_app
from automedia.cli.commands.init_cmd import init_cmd
from automedia.cli.commands.omni import app as omni_app
from automedia.cli.commands.onboard import app as onboard_app
from automedia.cli.commands.pool import app as pool_app
from automedia.cli.commands.projects import app as projects_app
from automedia.cli.commands.run import run_cmd

__all__ = [
    "account_app",
    "adapter_app",
    "archive_cmd",
    "cron_app",
    "doctor_cmd",
    "hitl_app",
    "init_cmd",
    "omni_app",
    "onboard_app",
    "pool_app",
    "projects_app",
    "run_cmd",
]
