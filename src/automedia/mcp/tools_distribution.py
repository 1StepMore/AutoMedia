"""MCP tool: ``distribute_content`` — multi-platform content distribution.

Shared distribution logic lives in :mod:`automedia.adapters.distribution`;
this module provides the MCP tool wrapper that delegates to it.
"""

from __future__ import annotations

from typing import Any

from structlog import get_logger

from automedia.mcp.mcp_error import MCPErrorCode, error_response, success_response

log = get_logger(__name__)


def distribute_content(
    project_id: str,
    platforms: str | None = None,
    all: bool = False,
    dry_run: bool = False,
    base_dir: str | None = None,
) -> dict[str, Any]:
    """Distribute (publish) a project's content to one or more platforms.

    Delegates to :func:`automedia.adapters.distribution.distribute_to_platforms`
    which discovers the project by ID and publishes through
    :class:`~automedia.adapters.publish_engine.PublishEngine`.

    Parameters
    ----------
    project_id:
        The 12-char hex project identifier returned by ``run_pipeline``.
    platforms:
        Comma-separated list of target platform names
        (e.g. ``"wechat,zhihu,xiaohongshu"``).  Ignored when *all* is
        ``True``.
    all:
        When ``True``, distribute to every registered platform.  Overrides
        *platforms*.
    dry_run:
        When ``True``, validate pre-conditions for each platform without
        actually publishing.  Returns the same result shape with
        ``"dry_run": True``.
    base_dir:
        Root directory containing project directories.  When empty the
        default projects directory is used.

    Returns
    -------
    dict
        ``{"platforms": {"wechat": "success", "twitter": "failed", ...},
        "summary": "2/3 platforms succeeded", "dry_run": false}``
        or an error dict on failure.
    """
    # Validate project_id
    if not project_id or not project_id.strip():
        return error_response(
            MCPErrorCode.INVALID_PARAM,
            "project_id must be a non-empty string",
        )

    # Parse platforms string into list
    parsed_platforms: list[str] | None = None
    if platforms:
        parsed_platforms = [p.strip() for p in platforms.split(",") if p.strip()]
        if not parsed_platforms:
            return error_response(
                MCPErrorCode.INVALID_PARAM,
                "platforms string parsed to empty list. Provide valid platform names "
                "separated by commas (e.g. 'wechat,zhihu') or set all=True.",
            )

    # Ensure at least one of platforms or all is provided
    if not parsed_platforms and not all:
        return error_response(
            MCPErrorCode.INVALID_PARAM,
            "No target platforms. Provide a comma-separated platforms list "
            "or set all=True to distribute to every registered platform.",
        )

    # Validate base_dir against allowlist if provided
    if base_dir:
        try:
            from automedia.mcp.allowlist import _require_allowed  # noqa: PLC0415

            _require_allowed(base_dir, tool_name="distribute_content")
        except Exception:
            # If allowlist check fails, log and fall back to default
            log.warning(
                "distribute_content: base_dir %s not in allowlist, using default",
                base_dir,
            )
            base_dir = None

    try:
        from automedia.adapters.distribution import distribute_to_platforms  # noqa: PLC0415

        result = distribute_to_platforms(
            project_id=project_id.strip(),
            platforms=parsed_platforms,
            all_platforms=all,
            dry_run=dry_run,
            base_dir=base_dir,
        )

        # If there was an error in the distribution logic, wrap it in MCP error format
        if "error" in result:
            err = result["error"]
            return {
                "platforms": result["platforms"],
                "summary": result["summary"],
                "dry_run": dry_run,
                **error_response(
                    MCPErrorCode.PIPELINE_ERROR,
                    str(err) if not isinstance(err, dict) else str(err.get("unknown_platforms", err)),
                    "Check project_id and platform names",
                ),
            }

        return success_response(
            {
                "platforms": result["platforms"],
                "summary": result["summary"],
                "dry_run": dry_run,
            }
        )
    except ImportError as exc:
        return {
            "platforms": {},
            "summary": "Distribution module not available",
            "dry_run": dry_run,
            **error_response(MCPErrorCode.IMPORT_ERROR, str(exc)),
        }
    except Exception as exc:
        log.error("distribute_content.unexpected_error", error=str(exc))
        return {
            "platforms": {},
            "summary": f"Unexpected error: {exc}",
            "dry_run": dry_run,
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
        }
