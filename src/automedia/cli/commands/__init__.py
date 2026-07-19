"""CLI command modules — each submodule defines a typer sub-application.

Importing this package does **not** eagerly import any submodule.
Access names via ``lazy_import()`` or import the specific submodule directly::

    from automedia.cli.commands.run import run_cmd
"""

from __future__ import annotations

import importlib
from typing import Any


def lazy_import(name: str) -> Any:
    """Lazy-import a name from ``automedia.cli.commands.<name>``.

    Usage::

        run_cmd = lazy_import("run").run_cmd
    """
    return importlib.import_module(f"automedia.cli.commands.{name}")


# ---------------------------------------------------------------------------
# Legacy explicit imports below are commented out to avoid eager-loading the
# entire command tree when only one subcommand is needed.
#
# Use ``from automedia.cli.commands.run import run_cmd`` instead.
#
# from automedia.cli.commands.account import app as account_app
# from automedia.cli.commands.adapter import app as adapter_app
# from automedia.cli.commands.archive import archive_cmd
# from automedia.cli.commands.cron import app as cron_app
# from automedia.cli.commands.doctor import doctor_cmd
# from automedia.cli.commands.hitl import app as hitl_app
# from automedia.cli.commands.init_cmd import init_cmd
# from automedia.cli.commands.mcp import app as mcp_app
# from automedia.cli.commands.omni import app as omni_app
# from automedia.cli.commands.onboard import app as onboard_app
# from automedia.cli.commands.pool import app as pool_app
# from automedia.cli.commands.projects import app as projects_app
# from automedia.cli.commands.run import run_cmd
# ---------------------------------------------------------------------------
