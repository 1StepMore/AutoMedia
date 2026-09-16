"""Project management MCP tools — listing, assets, archiving."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from structlog import get_logger

from automedia.mcp.tools._shared import (
    MCPErrorCode,
    NonEmptyStr,
    ProjectStatusFilter,
    _discover_projects,
    _project_assets,
    _require_allowed,
    error_response,
    success_response,
)

log = get_logger(__name__)

__all__ = [
    "archive_project",
    "get_project_assets",
    "list_projects",
]


def list_projects(
    base_dir: str = ".",
    status: ProjectStatusFilter = "",
) -> dict[str, Any]:
    """List all projects found under *base_dir*.

    Parameters
    ----------
    base_dir:
        Root directory to scan for ``00_project_info.json`` files.
    status:
        Optional status filter (e.g. ``"published"``).

    Returns
    -------
    dict
        ``{"projects": [...]}``.
    """
    try:
        _require_allowed(base_dir, tool_name="list_projects")
        projects = _discover_projects(base_dir)
        if status:
            projects = [p for p in projects if p.get("status", "") == status]
        return success_response({"projects": projects, "count": len(projects)})

    except PermissionError as exc:
        return {
            "projects": [],
            "count": 0,
            **error_response(MCPErrorCode.UNKNOWN, f"Permission denied: {exc}"),
        }
    except OSError as exc:
        return {
            "projects": [],
            "count": 0,
            **error_response(MCPErrorCode.UNKNOWN, f"File I/O error scanning projects: {exc}"),
        }
    except Exception as exc:
        return {"projects": [], **error_response(MCPErrorCode.UNKNOWN, str(exc))}


def get_project_assets(
    project_dir: str,
) -> dict[str, Any]:
    """Return the list of asset files inside a project directory.

    Parameters
    ----------
    project_dir:
        Absolute path to the project root.

    Returns
    -------
    dict
        ``{"assets": [...], "count": int}``.
    """
    try:
        _require_allowed(project_dir, tool_name="get_project_assets")
        assets = _project_assets(project_dir)
        return success_response({"assets": assets, "count": len(assets)})

    except PermissionError as exc:
        return {"assets": [], **error_response(MCPErrorCode.UNKNOWN, f"Permission denied: {exc}")}
    except OSError as exc:
        return {
            "assets": [],
            **error_response(MCPErrorCode.UNKNOWN, f"File I/O error scanning assets: {exc}"),
        }
    except Exception as exc:
        return {"assets": [], **error_response(MCPErrorCode.UNKNOWN, str(exc))}


def archive_project(
    project_id: NonEmptyStr,
    base_dir: str = ".",
    force: bool = False,
) -> dict[str, Any]:
    """Archive a project (Red Line 8 enforcement).

    Refuses to archive unless the project status is ``"published"``
    or *force* is ``True``.

    Parameters
    ----------
    project_id:
        The 12-char hex project identifier.
    base_dir:
        Base directory to scan for projects.
    force:
        Force archive even if status is not ``"published"``.

    Returns
    -------
    dict
        ``{"archived": True, "archive_dir": str}`` or error.
    """
    try:
        _require_allowed(base_dir, tool_name="archive_project")

        # Red Line 8: refuse without force when status ≠ published
        projects = _discover_projects(base_dir)
        match = [p for p in projects if p.get("project_id") == project_id]
        if not match:
            return {
                "archived": False,
                **error_response(
                    MCPErrorCode.NOT_FOUND,
                    f"Project {project_id!r} not found",
                    "Verify project_id",
                ),
            }

        proj = match[0]
        status_val = str(proj.get("status", ""))
        if status_val != "published" and not force:
            return {
                "archived": False,
                **error_response(
                    MCPErrorCode.INVALID_PARAM,
                    (
                        f"Refused: project status is '{status_val}', not 'published'. "
                        f"Set force=True to override (Red Line 8)."
                    ),
                ),
            }

        project_dir = Path(proj["_dir"])
        archive_dir = project_dir.parent / f"{project_dir.name}_archived"
        if archive_dir.exists():
            return {
                "archived": False,
                **error_response(
                    MCPErrorCode.INVALID_PARAM,
                    f"Archive target already exists: {archive_dir}",
                ),
            }

        # L2 archive validation: runs after the Red Line 8 eligibility check
        # and before the rename. ``force=True`` short-circuits before L2.
        if not force:
            from automedia.cli.commands.archive import (
                build_l2_archive_context,
                run_l2_archive_gate,
            )

            l2_passed, l2_failure_mode, _l2_result = run_l2_archive_gate(
                build_l2_archive_context(proj, project_dir, archive_dir, force=force)
            )
            if not l2_passed and l2_failure_mode == "stop":
                return {
                    "archived": False,
                    **error_response(
                        MCPErrorCode.GATE_FAILURE,
                        "Refused: L2 archive validation failed (Red Line 8).",
                        "Resolve the archive integrity checks or set force=True.",
                    ),
                }

        project_dir.rename(archive_dir)
        return success_response({"archived": True, "archive_dir": str(archive_dir)})

    except PermissionError as exc:
        return {
            "archived": False,
            **error_response(
                MCPErrorCode.UNKNOWN,
                f"Permission denied: {exc}",
                "Check file permissions",
            ),
        }
    except OSError as exc:
        return {
            "archived": False,
            **error_response(MCPErrorCode.UNKNOWN, f"File operation error: {exc}"),
        }
    except Exception as exc:
        return {"archived": False, **error_response(MCPErrorCode.UNKNOWN, str(exc))}
