"""MCP tool handler functions — domain-specific submodules.

All public symbols are re-exported from submodules so that
``from automedia.mcp.tools import X`` continues to work after
the refactor.
"""

from automedia.mcp.tools._shared import *  # noqa: F401, F403

# Explicitly re-export private helpers used by other modules and tests
from automedia.mcp.tools._shared import (  # noqa: F401
    _discover_projects,
    _get_jobs_yaml_path,
    _get_semaphore,
    _lock,
    _pipeline_result_to_dict,
    _pipeline_tracker,
    _project_assets,
    _read_active_pipelines,
    _read_pipeline_schedules,
    _require_allowed,
    _resolve_projects_dir,
    _update_pipeline_entry,
    _write_pipeline_schedules,
)
from automedia.mcp.tools.approval import *  # noqa: F401, F403
from automedia.mcp.tools.assets import *  # noqa: F401, F403
from automedia.mcp.tools.brands import *  # noqa: F401, F403
from automedia.mcp.tools.config import *  # noqa: F401, F403
from automedia.mcp.tools.cron_tools import *  # noqa: F401, F403
from automedia.mcp.tools.health import *  # noqa: F401, F403
from automedia.mcp.tools.omni import *  # noqa: F401, F403
from automedia.mcp.tools.pipeline import *  # noqa: F401, F403
from automedia.mcp.tools.projects import *  # noqa: F401, F403
from automedia.mcp.tools.prompts_meta import *  # noqa: F401, F403
from automedia.mcp.tools.publishing import *  # noqa: F401, F403
from automedia.mcp.tools.quality import *  # noqa: F401, F403
from automedia.mcp.tools.redlines import *  # noqa: F401, F403
from automedia.mcp.tools.setup import *  # noqa: F401, F403
from automedia.mcp.tools.strategy import *  # noqa: F401, F403
from automedia.mcp.tools.topics import *  # noqa: F401, F403
