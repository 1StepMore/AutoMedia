"""Tests for OAuth2 authentication flows.

Tests cover:
* OAuth2ClientCredentialsFlow — token exchange with mock httpx
* OAuth2LocalhostServer — start/wait/stop lifecycle
* OAuth2AuthCodeFlow — authorization URL generation with PKCE params
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from automedia.accounts.auth.oauth2 import (
    OAuth2AuthCodeFlow,
    OAuth2ClientCredentialsFlow,
    OAuth2LocalhostServer,
)
from automedia.accounts.models import SessionToken

# ---------------------------------------------------------------------------
# OAuth2ClientCredentialsFlow
# ---------------------------------------------------------------------------


class TestOAuth2ClientCredentialsFlow:
    """Token exchange via client_credentials grant."""

    def test_exchange_returns_session_token(self) -> None:
        """Successful exchange returns a SessionToken with access_token."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {
            "access_token": "test_access_token_123",
            "expires_in": 7200,
        }

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_resp

        flow = OAuth2ClientCredentialsFlow(http_client=mock_client)
        token = flow.exchange(
            token_url="https://api.example.com/token",
            client_id="test_client",
            client_secret="test_secret",
        )

        assert isinstance(token, SessionToken)
        assert token.access_token == "test_access_token_123"
        assert token.expires_at is not None

        # Verify the HTTP call included the correct params
        _, kwargs = mock_client.post.call_args
        assert kwargs["data"]["grant_type"] == "client_credentials"
        assert kwargs["data"]["appid"] == "test_client"
        assert kwargs["data"]["secret"] == "test_secret"

    def test_exchange_with_extra_params(self) -> None:
        """Extra params are forwarded to the token request."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {"access_token": "tok", "expires_in": 3600}

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_resp

        flow = OAuth2ClientCredentialsFlow(http_client=mock_client)
        flow.exchange(
            token_url="https://api.example.com/token",
            client_id="cid",
            client_secret="cs",
            extra_params={"scope": "read write"},
        )

        _, kwargs = mock_client.post.call_args
        assert kwargs["data"]["scope"] == "read write"

    def test_exchange_raises_on_http_error(self) -> None:
        """HTTP errors are propagated."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=MagicMock()
        )

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_resp

        flow = OAuth2ClientCredentialsFlow(http_client=mock_client)
        with pytest.raises(httpx.HTTPStatusError):
            flow.exchange(
                token_url="https://api.example.com/token",
                client_id="cid",
                client_secret="cs",
            )

    def test_refresh_returns_new_token(self) -> None:
        """Refresh call returns a SessionToken with new access_token."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {
            "access_token": "refreshed_token",
            "refresh_token": "new_refresh",
            "expires_in": 3600,
        }

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_resp

        flow = OAuth2ClientCredentialsFlow(http_client=mock_client)
        token = flow.refresh(
            refresh_url="https://api.example.com/refresh",
            client_id="cid",
            client_secret="cs",
            refresh_token="old_refresh",
        )

        assert token.access_token == "refreshed_token"
        assert token.refresh_token == "new_refresh"

        _, kwargs = mock_client.post.call_args
        assert kwargs["data"]["grant_type"] == "refresh_token"
        assert kwargs["data"]["refresh_token"] == "old_refresh"


# ---------------------------------------------------------------------------
# OAuth2LocalhostServer
# ---------------------------------------------------------------------------


class TestOAuth2LocalhostServer:
    """Localhost redirect server lifecycle."""

    def test_start_provides_redirect_uri(self) -> None:
        """start() returns a valid redirect URI."""
        server = OAuth2LocalhostServer(host="127.0.0.1", port=0)
        try:
            redirect_uri = server.start()
            assert redirect_uri.startswith("http://127.0.0.1:")
            assert redirect_uri.endswith("/callback")
        finally:
            server.stop()

    def test_context_manager(self) -> None:
        """Context manager starts and stops the server."""
        with OAuth2LocalhostServer() as server:
            assert server.redirect_uri.startswith("http://127.0.0.1:")

    def test_wait_for_code_timeout(self) -> None:
        """wait_for_code raises TimeoutError when no callback arrives."""
        server = OAuth2LocalhostServer(host="127.0.0.1", port=0)
        try:
            server.start()
            with pytest.raises(TimeoutError, match="No OAuth2 callback received"):
                server.wait_for_code(timeout=0.1)
        finally:
            server.stop()

    def test_stop_multiple_safe(self) -> None:
        """Calling stop() multiple times does not raise."""
        server = OAuth2LocalhostServer()
        server.start()
        server.stop()
        server.stop()  # Second call should be safe


# ---------------------------------------------------------------------------
# OAuth2AuthCodeFlow
# ---------------------------------------------------------------------------


class TestOAuth2AuthCodeFlow:
    """Authorization URL generation and code exchange."""

    def test_create_authorization_url_includes_pkce(self) -> None:
        """Authorization URL includes PKCE challenge and state."""
        flow = OAuth2AuthCodeFlow()
        auth_url = flow.create_authorization_url(
            auth_url="https://accounts.example.com/auth",
            client_id="test_client",
            redirect_uri="http://127.0.0.1:9999/callback",
            scope="read write",
        )

        assert "response_type=code" in auth_url
        assert "client_id=test_client" in auth_url
        assert "code_challenge=" in auth_url
        assert "code_challenge_method=S256" in auth_url
        assert "state=" in auth_url
        assert "scope=read+write" in auth_url or "scope=read%20write" in auth_url
        assert "redirect_uri=http" in auth_url

    def test_state_and_verifier_are_random(self) -> None:
        """Each flow instance generates unique state and verifier."""
        flow1 = OAuth2AuthCodeFlow()
        flow2 = OAuth2AuthCodeFlow()

        assert flow1.state != flow2.state
        assert flow1.code_verifier != flow2.code_verifier

    def test_exchange_code_returns_session_token(self) -> None:
        """Code exchange returns a SessionToken."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {
            "access_token": "auth_code_token",
            "refresh_token": "refresh_abc",
            "expires_in": 3600,
        }

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_resp

        flow = OAuth2AuthCodeFlow()
        token = flow.exchange_code(
            token_url="https://api.example.com/token",
            client_id="cid",
            client_secret="cs",
            redirect_uri="http://127.0.0.1:9999/callback",
            code="auth_code_123",
            code_verifier=flow.code_verifier,
            http_client=mock_client,
        )

        assert isinstance(token, SessionToken)
        assert token.access_token == "auth_code_token"
        assert token.refresh_token == "refresh_abc"

        # Verify HTTP call includes the code
        _, kwargs = mock_client.post.call_args
        assert kwargs["data"]["code"] == "auth_code_123"
        assert kwargs["data"]["grant_type"] == "authorization_code"
        assert kwargs["data"]["code_verifier"] == flow.code_verifier

    def test_exchange_code_sans_secret(self) -> None:
        """Code exchange works without a client_secret (PKCE-only flow)."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {"access_token": "pkce_token", "expires_in": 3600}

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_resp

        flow = OAuth2AuthCodeFlow()
        token = flow.exchange_code(
            token_url="https://api.example.com/token",
            client_id="cid",
            client_secret=None,
            redirect_uri="http://127.0.0.1:9999/callback",
            code="code",
            code_verifier=flow.code_verifier,
            http_client=mock_client,
        )

        assert token.access_token == "pkce_token"

    def test_pkce_challenge_deterministic(self) -> None:
        """Same verifier always produces the same challenge."""
        v1 = OAuth2AuthCodeFlow._pkce_challenge("test_verifier_123")
        v2 = OAuth2AuthCodeFlow._pkce_challenge("test_verifier_123")
        assert v1 == v2

    def test_pkce_challenge_different_verifiers(self) -> None:
        """Different verifiers produce different challenges."""
        v1 = OAuth2AuthCodeFlow._pkce_challenge("verifier_a")
        v2 = OAuth2AuthCodeFlow._pkce_challenge("verifier_b")
        assert v1 != v2
