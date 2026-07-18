"""Rollback infrastructure types and helpers for Gap 9.

Defines the core types used by the rollback system: action enums, result
dataclass, and helper functions for reading/updating project status and
checking rollback eligibility.

These types are used by Task 13 (history CLI) and Task 14 (rollback CLI).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ProjectAction(str, Enum):
    """Actions recorded in the pipeline history log.

    Each value is a short snake_case string stored in the history database.
    """

    RUN_STARTED = "run_started"
    """A pipeline run has started for this project."""

    GATE_PASSED = "gate_passed"
    """A gate completed successfully."""

    GATE_FAILED = "gate_failed"
    """A gate failed (stop or retry)."""

    ROLLED_BACK = "rolled_back"
    """The project was rolled back to a previous state."""

    PUBLISHED = "published"
    """The project was published to one or more platforms."""


@dataclass
class RollbackResult:
    """Result of a rollback operation.

    Attributes
    ----------
    success:
        Whether the rollback completed successfully.
    project_id:
        The project that was rolled back.
    previous_status:
        The project status before the rollback.
    new_status:
        The project status after the rollback (empty string on failure).
    """

    success: bool = True
    project_id: str = ""
    previous_status: str = ""
    new_status: str = ""


# ---------------------------------------------------------------------------
# Project info helpers
# ---------------------------------------------------------------------------


def _info_path(project_dir: str) -> str:
    """Return the absolute path to ``00_project_info.json`` inside *project_dir*."""
    return os.path.join(project_dir, "00_project_info.json")


def read_project_status(project_dir: str) -> str:
    """Read the ``status`` field from ``project_info.json``.

    Parameters
    ----------
    project_dir:
        Absolute path to the project root directory.

    Returns
    -------
    str
        The status string (e.g. ``"draft"``, ``"running"``,
        ``"completed"``, ``"published"``, ``"archived"``), or an empty
        string when the file is missing, corrupt, or has no ``status``
        key.
    """
    info_path = _info_path(project_dir)
    try:
        with open(info_path, encoding="utf-8") as fh:
            data = json.load(fh)
        return str(data.get("status", ""))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return ""


def update_project_status(project_dir: str, new_status: str) -> bool:
    """Set the ``status`` field in ``project_info.json``.

    If the file does not exist or is corrupt the operation is skipped.

    Parameters
    ----------
    project_dir:
        Absolute path to the project root directory.
    new_status:
        The new status value (e.g. ``"completed"``, ``"running"``).

    Returns
    -------
    bool
        ``True`` when the file was read and written successfully,
        ``False`` otherwise.
    """
    info_path = _info_path(project_dir)
    try:
        with open(info_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False

    data["status"] = new_status
    try:
        with open(info_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Rollback eligibility
# ---------------------------------------------------------------------------


def is_eligible_for_rollback(project_dir: str) -> bool:
    """Check whether *project_dir* has past pipeline history for rollback.

    A project is eligible when ``<project_dir>/.automedia/history.db``
    exists and contains data (non-zero file size).  This indicates at
    least one pipeline run was recorded by the history hook.

    Parameters
    ----------
    project_dir:
        Absolute path to the project root directory.

    Returns
    -------
    bool
        ``True`` when the project has recorded history, ``False``
        otherwise.
    """
    history_path = Path(project_dir) / ".automedia" / "history.db"
    try:
        return history_path.is_file() and history_path.stat().st_size > 0
    except OSError:
        return False
