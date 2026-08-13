"""MCP tool handler functions — module-level for testability.

This module is a backward-compatibility re-export shim.
All functions have been moved to ``automedia.mcp.tools/`` submodules.
"""

from automedia.mcp.tools._shared import *  # noqa: F401, F403
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

# Legacy alias — remove once all callers are updated.
__all__ = []  # defined per-submodule
