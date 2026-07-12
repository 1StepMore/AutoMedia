"""PRD-4: Agent Account & Publishing Management Layer.

This subpackage provides the foundation for managing platform accounts
and their credentials across the AutoMedia pipeline.

Wave structure
--------------
- **Wave 1**: Account models, encrypted store, tests
- **Wave 2**: Account manager, health checker, CLI commands
- **Wave 3**: Auth flow engine, OAuth2 flows, cookie, and API key auth
- **Wave 4**: Publishing integration with platform adapters
"""

from automedia.accounts.auth import AuthFlowEngine
from automedia.accounts.registry import AccountRegistry
from automedia.accounts.session import SessionManager
from automedia.accounts.store import AccountStore

__all__ = [
    "AccountRegistry",
    "AccountStore",
    "AuthFlowEngine",
    "SessionManager",
]
