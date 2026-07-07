# AutoMedia MCP
from automedia.mcp.server import (
    archive_project,
    create_server,
    get_pipeline_status,
    get_project_assets,
    list_projects,
    list_topic_pool,
    register_omni_adapter,
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
    "register_omni_adapter",
]
