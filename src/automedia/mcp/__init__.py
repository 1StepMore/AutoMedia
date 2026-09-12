"""MCP (Model Context Protocol) server — JSON-RPC over stdio.

Exposes 68 tools for pipeline execution, topic management, Omni Triad
operations, account management, and platform adapter registration.
"""

from structlog import get_logger

from automedia.mcp.parallel import start_parallel_servers, stop_parallel_servers
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

log = get_logger(__name__)

__all__ = [
    "archive_project",
    "create_server",
    "get_pipeline_status",
    "get_project_assets",
    "list_projects",
    "list_topic_pool",
    "register_platform_adapter",
    "run_pipeline",
    "select_topic",
    "start_parallel_servers",
    "stop_parallel_servers",
]
