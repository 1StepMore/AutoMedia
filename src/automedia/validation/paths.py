"""Repository-root anchored paths shared by the validation surfaces (#718).

Every validation surface must resolve a scenario step's relative paths and
the default runs root against the repository root, never the process cwd.
Otherwise the same library yields different evidence depending on where the
command was launched (``validate run --all`` from ``/tmp`` vs the repo root).

This module is deliberately dependency-free so both the CLI and the MCP tool
handlers can share it without importing each other.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_RUNS_ROOT = "validation-runs"
"""Default runs-root directory name, anchored at the repository root."""


def repo_root() -> Path:
    """Repository root, derived from this module's location.

    ``paths.py`` lives at ``<repo>/src/automedia/validation/paths.py``, so
    ``parents[3]`` is the repository root regardless of the process cwd.
    """
    return Path(__file__).resolve().parents[3]


def default_runs_root() -> Path:
    """The default runs root: ``<repo root>/validation-runs``."""
    return repo_root() / DEFAULT_RUNS_ROOT
