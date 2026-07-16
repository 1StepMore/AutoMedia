"""MCP (Model Context Protocol) server — JSON-RPC over stdio.

Exposes 22 tools for pipeline execution, topic management, Omni Triad
operations, account management, and platform adapter registration.
"""

from structlog import get_logger

from automedia.mcp.parallel import start_parallel_servers, stop_parallel_servers

log = get_logger(__name__)
from automedia.mcp.server import (
    archive_project,
    create_server,
    get_pipeline_status,
    get_project_assets,
    list_projects,
    list_topic_pool,
    register_platform_adapter,
    run_pipeline,
    select_topic,
)

__all__ = [
    "create_server",
    "select_topic",
    "run_pipeline",
    "get_pipeline_status",
    "list_projects",
    "get_project_assets",
    "archive_project",
    "list_topic_pool",
    "register_platform_adapter",
    "start_parallel_servers",
    "stop_parallel_servers",
]
