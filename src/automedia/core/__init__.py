"""Foundation layer — configuration loading, project management, LLM client, and credential resolution."""

from automedia.core.paths import get_user_config_dir
from automedia.core.project import Project

__all__ = [
    "Project",
    "get_user_config_dir",
]
