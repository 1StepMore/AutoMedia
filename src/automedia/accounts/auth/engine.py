"""AuthFlowEngine — orchestrates authentication across platforms."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from automedia.accounts.auth.api_key import ApiKeyAuth
from automedia.accounts.auth.cookie import CookieAuth
from automedia.accounts.auth.oauth2 import (
    OAuth2AuthCodeFlow,
    OAuth2ClientCredentialsFlow,
    OAuth2LocalhostServer,
)
from automedia.accounts.models import AuthType, SessionToken

logger = logging.getLogger(__name__)


@dataclass
class AuthSession:
    """Temporary auth session for multi-step flows (OAuth2)."""

    session_id: str
    auth_type: AuthType
    platform: str
    state: str
    redirect_uri: str | None = None
    code_verifier: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None


class AuthFlowEngine:
    """Orchestrates authentication across different auth types.

    Routes to the correct handler based on AuthType and manages
    multi-step auth sessions (OAuth2 PKCE).
    """

    def __init__(self) -> None:
        """Initialize the auth flow engine with empty session state."""
        self._sessions: dict[str, AuthSession] = {}
        self._oauth2_client = OAuth2ClientCredentialsFlow()

    def authenticate(
        self,
        auth_type: AuthType,
        credentials: dict[str, Any],
    ) -> SessionToken | str:
        """Authenticate with the given auth type and credentials.

        For OAuth2 client_credentials: returns a SessionToken.
        For Cookie: validates the cookie, returns the cookie string.
        For API Key: validates the key, returns the key string.

        Raises ValueError on authentication failure.
        """
        if auth_type == AuthType.OAUTH2_CLIENT_CRED:
            token = self._oauth2_client.exchange(
                token_url=credentials.get("token_url", ""),
                client_id=credentials.get("client_id", ""),
                client_secret=credentials.get("client_secret", ""),
            )
            return token

        elif auth_type == AuthType.COOKIE:
            cookie = credentials.get("cookie", "")
            if not CookieAuth.validate_cookie(cookie):
                raise ValueError("Invalid cookie: empty or malformed")
            return cookie

        elif auth_type in (AuthType.API_KEY, AuthType.WEBHOOK_URL):
            key = credentials.get("api_key", "") or credentials.get("webhook_url", "")
            if not ApiKeyAuth.validate_key(key):
                raise ValueError("Invalid API key: too short or empty")
            return key

        elif auth_type == AuthType.OAUTH2_AUTH_CODE:
            raise NotImplementedError(
                "OAuth2 authorization_code requires start_oauth2_auth_code_flow() "
                "for the multi-step redirect process."
            )

        else:
            raise ValueError(f"Unsupported auth type: {auth_type}")

    def start_oauth2_auth_code_flow(
        self,
        platform: str,
        auth_url: str,
        client_id: str,
        redirect_uri: str | None = None,
        scope: str = "",
        extra_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Start an OAuth2 authorization_code flow with localhost redirect.

        Returns a dict with:

        * ``authorization_url`` — URL the user must open
        * ``redirect_uri`` — the localhost redirect URI
        * ``session_id`` — ID to track this auth session

        After the user authorizes, call :meth:`complete_oauth2_flow` with the
        session_id and the returned code.
        """
        # Create localhost server if no redirect_uri provided
        local_server = None
        if not redirect_uri:
            local_server = OAuth2LocalhostServer()
            redirect_uri = local_server.start()

        flow = OAuth2AuthCodeFlow()
        authorization_url = flow.create_authorization_url(
            auth_url=auth_url,
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=scope,
            extra_params=extra_params,
        )

        session_id = f"auth_{uuid.uuid4().hex[:12]}"
        self._sessions[session_id] = AuthSession(
            session_id=session_id,
            auth_type=AuthType.OAUTH2_AUTH_CODE,
            platform=platform,
            state=flow.state,
            redirect_uri=redirect_uri,
            code_verifier=flow.code_verifier,
        )

        return {
            "authorization_url": authorization_url,
            "redirect_uri": redirect_uri,
            "session_id": session_id,
            "local_server": local_server,
        }

    def complete_oauth2_flow(
        self,
        session_id: str,
        code: str,
        client_id: str,
        client_secret: str | None = None,
        token_url: str = "",
    ) -> SessionToken:
        """Complete an OAuth2 authorization_code flow.

        Exchanges the code for tokens using the stored session info.
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Auth session not found: {session_id}")

        flow = OAuth2AuthCodeFlow()
        token = flow.exchange_code(
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=session.redirect_uri or "",
            code=code,
            code_verifier=session.code_verifier,
        )

        # Clean up session
        self._sessions.pop(session_id, None)
        return token
