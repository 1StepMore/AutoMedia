"""PRD-4: MCP tools for account management — connect, list, health, disconnect."""

from __future__ import annotations

from typing import Any

from structlog import get_logger

from automedia.accounts.registry import AccountRegistry
from automedia.mcp.mcp_error import MCPErrorCode, error_response, success_response
from automedia.mcp.server_types import NonEmptyStr

log = get_logger(__name__)

_registry: AccountRegistry | None = None


def _get_registry() -> AccountRegistry:
    """Lazy-initialize the account registry (avoid import-time key requirement)."""
    global _registry
    if _registry is None:
        _registry = AccountRegistry()
    return _registry


def connect_account(
    platform: str,
    auth_type: str = "api_key",
    credentials: dict[str, Any] | None = None,
    label: str = "",
) -> dict[str, Any]:
    """Register a new platform account.

    Args:
        platform: Platform name (wechat, zhihu, xiaohongshu, etc.)
        auth_type: Authentication type (api_key, cookie, oauth2_client_cred, etc.)
        credentials: Credential payload dict (key-value pairs)
        label: Human-readable label for the account

    Returns:
        Account metadata including account_id
    """
    if not credentials:
        return error_response(MCPErrorCode.INVALID_PARAM, "credentials must be provided")

    try:
        meta = _get_registry().register(
            platform=platform,
            credentials=credentials,
            label=label,
            auth_type=auth_type,
        )
        return {"success": True, "account": meta}
    except ValueError as e:
        return error_response(MCPErrorCode.INVALID_PARAM, str(e), "Check credentials values")


def list_accounts(
    platform: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """List registered accounts.

    Args:
        platform: Optional platform filter
        status: Optional status filter (active, inactive, stale)

    Returns:
        List of account metadata dicts
    """
    accounts = _get_registry().list(platform=platform, status=status)
    return success_response({"accounts": accounts, "count": len(accounts)})


def get_account_health(account_id: NonEmptyStr) -> dict[str, Any]:
    """Check an account's health status.

    Args:
        account_id: The account ID to check

    Returns:
        Account metadata and health information
    """
    info = _get_registry().get(account_id)
    if not info:
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"Account not found: {account_id}",
            "Verify account_id",
        )

    return success_response({
        "account_id": account_id,
        "platform": info.get("platform"),
        "label": info.get("label"),
        "status": info.get("status"),
        "last_health_check": str(info.get("last_health_check", "")),
    })


def disconnect_account(account_id: NonEmptyStr) -> dict[str, Any]:
    """Remove a platform account.

    Args:
        account_id: The account ID to disconnect

    Returns:
        Success or error message
    """
    info = _get_registry().get(account_id)
    if not info:
        return error_response(
            MCPErrorCode.NOT_FOUND,
            f"Account not found: {account_id}",
            "Verify account_id",
        )

    _get_registry().delete(account_id)
    return {"success": True, "account_id": account_id, "platform": info.get("platform")}


__all__ = [
    "connect_account",
    "list_accounts",
    "get_account_health",
    "disconnect_account",
]
