"""Tests for AuthFlowEngine — authentication orchestrator.

Tests cover:
* authenticate() routes to correct handler for each AuthType
* start_oauth2_auth_code_flow creates session correctly
* complete_oauth2_flow exchanges code for token
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from automedia.accounts.auth.engine import AuthFlowEngine, AuthSession
from automedia.accounts.models import AuthType, SessionToken


class TestAuthFlowEngineAuthenticate:
    """Routing credentials to the correct auth handler."""

    def test_oauth2_client_cred_returns_session_token(self) -> None:
        """Client credentials flow returns a SessionToken."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {"access_token": "cc_token", "expires_in": 7200}
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_resp

        engine = AuthFlowEngine()
        engine._oauth2_client._http = mock_client

        token = engine.authenticate(
            AuthType.OAUTH2_CLIENT_CRED,
            {
                "token_url": "https://api.example.com/token",
                "client_id": "cid",
                "client_secret": "cs",
            },
        )
        assert isinstance(token, SessionToken)
        assert token.access_token == "cc_token"

    def test_cookie_valid(self) -> None:
        """Valid cookie is returned as string."""
        engine = AuthFlowEngine()
        result = engine.authenticate(AuthType.COOKIE, {"cookie": "session=valid123"})
        assert result == "session=valid123"

    def test_cookie_invalid_raises(self) -> None:
        """Invalid cookie raises ValueError."""
        engine = AuthFlowEngine()
        with pytest.raises(ValueError, match="Invalid cookie"):
            engine.authenticate(AuthType.COOKIE, {"cookie": ""})

    def test_api_key_valid(self) -> None:
        """Valid API key is returned as string."""
        engine = AuthFlowEngine()
        result = engine.authenticate(AuthType.API_KEY, {"api_key": "sk-abcdefghijklmnop"})
        assert result == "sk-abcdefghijklmnop"

    def test_api_key_invalid_raises(self) -> None:
        """Short API key raises ValueError."""
        engine = AuthFlowEngine()
        with pytest.raises(ValueError, match="Invalid API key"):
            engine.authenticate(AuthType.API_KEY, {"api_key": "short"})

    def test_webhook_url_valid(self) -> None:
        """WEBHOOK_URL uses api_key field and validates."""
        engine = AuthFlowEngine()
        result = engine.authenticate(
            AuthType.WEBHOOK_URL, {"webhook_url": "https://hook.example.com/callback"}
        )
        assert result == "https://hook.example.com/callback"

    @patch("automedia.accounts.auth.engine.OAuth2AuthCodeFlow")
    @patch("automedia.accounts.auth.engine.OAuth2LocalhostServer")
    def test_oauth2_auth_code_returns_token(
        self, mock_server_class: MagicMock, mock_flow_class: MagicMock
    ) -> None:
        """OAUTH2_AUTH_CODE now completes the full flow and returns a SessionToken."""
        mock_server = MagicMock()
        mock_server_class.return_value = mock_server
        mock_server.start.return_value = "http://127.0.0.1:9999/callback"
        mock_server.wait_for_code.return_value = ("auth_code_xyz", "state")

        mock_flow_instance = MagicMock()
        mock_flow_class.return_value = mock_flow_instance
        expected_token = SessionToken(
            access_token="exchanged_token",
            refresh_token="new_refresh",
        )
        mock_flow_instance.exchange_code.return_value = expected_token

        engine = AuthFlowEngine()
        token = engine.authenticate(
            AuthType.OAUTH2_AUTH_CODE,
            {
                "auth_url": "https://accounts.example.com/auth",
                "client_id": "cid",
                "client_secret": "cs",
                "token_url": "https://api.example.com/token",
            },
        )
        assert isinstance(token, SessionToken)
        assert token.access_token == "exchanged_token"
        mock_server.wait_for_code.assert_called_once()
        mock_server.stop.assert_called_once()

    def test_unsupported_auth_type_raises(self) -> None:
        """Unknown auth type raises ValueError."""
        engine = AuthFlowEngine()
        with pytest.raises(ValueError, match="Unsupported auth type"):
            engine.authenticate("unsupported", {})  # type: ignore[arg-type]


class TestAuthFlowEngineOAuth2AuthCode:
    """Multi-step OAuth2 authorization_code flow."""

    def test_start_flow_creates_session(self) -> None:
        """start_oauth2_auth_code_flow creates a session with redirect URI."""
        engine = AuthFlowEngine()
        result = engine.start_oauth2_auth_code_flow(
            platform="test_platform",
            auth_url="https://accounts.example.com/auth",
            client_id="test_client",
            scope="read",
        )

        assert "authorization_url" in result
        assert "redirect_uri" in result
        assert "session_id" in result
        assert result["authorization_url"].startswith("https://accounts.example.com/auth")
        assert "code_challenge=" in result["authorization_url"]

        # Verify session was stored
        session_id = result["session_id"]
        assert session_id in engine._sessions
        session = engine._sessions[session_id]
        assert session.auth_type == AuthType.OAUTH2_AUTH_CODE
        assert session.platform == "test_platform"
        assert session.redirect_uri is not None
        assert session.code_verifier is not None

    def test_start_flow_respects_provided_redirect_uri(self) -> None:
        """When redirect_uri is provided, no local server is created."""
        engine = AuthFlowEngine()
        result = engine.start_oauth2_auth_code_flow(
            platform="test",
            auth_url="https://accounts.example.com/auth",
            client_id="cid",
            redirect_uri="http://localhost:9999/callback",
        )

        assert result["redirect_uri"] == "http://localhost:9999/callback"
        assert result["local_server"] is None

    @patch("automedia.accounts.auth.engine.OAuth2AuthCodeFlow")
    def test_complete_flow_exchanges_code(self, mock_flow_class: MagicMock) -> None:
        """complete_oauth2_flow exchanges code and cleans up session."""
        # Arrange
        mock_flow_instance = MagicMock()
        mock_flow_class.return_value = mock_flow_instance

        expected_token = SessionToken(
            access_token="exchanged_token",
            refresh_token="new_refresh",
        )
        mock_flow_instance.exchange_code.return_value = expected_token

        engine = AuthFlowEngine()
        # Store a session directly
        engine._sessions["test_sid"] = AuthSession(
            session_id="test_sid",
            auth_type=AuthType.OAUTH2_AUTH_CODE,
            platform="test",
            state="some_state",
            redirect_uri="http://localhost:9999/callback",
            code_verifier="test_verifier",
        )

        # Act
        token = engine.complete_oauth2_flow(
            session_id="test_sid",
            code="auth_code_xyz",
            client_id="cid",
            client_secret="cs",
            token_url="https://api.example.com/token",
        )

        # Assert
        assert token == expected_token
        assert "test_sid" not in engine._sessions  # Cleaned up

        # Verify exchange_code was called with the right args
        mock_flow_instance.exchange_code.assert_called_once_with(
            token_url="https://api.example.com/token",
            client_id="cid",
            client_secret="cs",
            redirect_uri="http://localhost:9999/callback",
            code="auth_code_xyz",
            code_verifier="test_verifier",
        )

    def test_complete_flow_missing_session_raises(self) -> None:
        """Completing a flow with unknown session ID raises ValueError."""
        engine = AuthFlowEngine()
        with pytest.raises(ValueError, match="Auth session not found"):
            engine.complete_oauth2_flow(
                session_id="nonexistent",
                code="code",
                client_id="cid",
            )


class TestAuthFlowEngineSessions:
    """Auth session management."""

    def test_sessions_initially_empty(self) -> None:
        """Engine starts with no sessions."""
        engine = AuthFlowEngine()
        assert len(engine._sessions) == 0

    def test_multiple_sessions(self) -> None:
        """Multiple concurrent auth sessions are tracked independently."""
        engine = AuthFlowEngine()
        r1 = engine.start_oauth2_auth_code_flow(
            platform="p1",
            auth_url="https://a.example.com/auth",
            client_id="c1",
        )
        r2 = engine.start_oauth2_auth_code_flow(
            platform="p2",
            auth_url="https://b.example.com/auth",
            client_id="c2",
        )

        assert r1["session_id"] != r2["session_id"]
        assert len(engine._sessions) == 2
