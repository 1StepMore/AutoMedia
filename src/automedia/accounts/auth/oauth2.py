"""OAuth2 authentication flows — client_credentials and authorization_code."""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from automedia.accounts.models import SessionToken

logger = logging.getLogger(__name__)


class OAuth2ClientCredentialsFlow:
    """Server-to-server OAuth2 flow (e.g., WeChat client_credential).

    Usage::

        flow = OAuth2ClientCredentialsFlow()
        token = flow.exchange(
            token_url="https://api.weixin.qq.com/cgi-bin/token",
            client_id="wx_xxx",
            client_secret="yyy",
        )
    """

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        """Initialize the client credentials flow with an optional HTTP client."""
        self._http = http_client or httpx.Client(timeout=30)

    def exchange(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        extra_params: dict[str, str] | None = None,
    ) -> SessionToken:
        """Exchange client credentials for an access token.

        Makes a POST/GET request to *token_url* with client_id and
        client_secret, parses the response, and returns a SessionToken.

        Handles both JSON and form-encoded responses.
        """
        params = {
            "grant_type": "client_credentials",
            "appid": client_id,
            "secret": client_secret,
            **(extra_params or {}),
        }
        resp = self._http.post(token_url, data=params)
        resp.raise_for_status()
        data = resp.json()

        # Parse standard OAuth2 response
        access_token = data.get("access_token", "")
        expires_in = data.get("expires_in", 7200)  # Default 2h
        expires_at = datetime.now() + timedelta(seconds=int(expires_in))

        return SessionToken(
            access_token=access_token,
            expires_at=expires_at,
        )

    def refresh(
        self,
        refresh_url: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        extra_params: dict[str, str] | None = None,
    ) -> SessionToken:
        """Refresh an expired token (for platforms that support it).

        Makes a POST request to *refresh_url* with grant_type=refresh_token
        and the provided refresh_token.
        """
        params = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            **(extra_params or {}),
        }
        resp = self._http.post(refresh_url, data=params)
        resp.raise_for_status()
        data = resp.json()

        access_token = data.get("access_token", "")
        new_refresh_token = data.get("refresh_token", refresh_token)
        expires_in = data.get("expires_in", 3600)
        expires_at = datetime.now() + timedelta(seconds=int(expires_in))

        return SessionToken(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_at=expires_at,
        )


class _RedirectHandler(BaseHTTPRequestHandler):
    """Minimal HTTP request handler that captures the OAuth2 redirect code."""

    def do_GET(self) -> None:
        """Handle the OAuth2 redirect callback."""
        query = parse_qs(urlparse(self.path).query)
        code = query.get("code", [None])[0]
        state = query.get("state", [None])[0]
        error = query.get("error", [None])[0]

        if error:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(f"Authentication failed: {error}".encode())
            self.server.last_error = error  # type: ignore[attr-defined]
        elif code:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Authentication successful! You may close this tab.")
            self.server.auth_code = code  # type: ignore[attr-defined]
            self.server.auth_state = state  # type: ignore[attr-defined]
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No authorization code received.")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: ANN401
        """Suppress default HTTP server logging."""
        return  # Quiet mode


class OAuth2LocalhostServer:
    """Temporary localhost HTTP server for OAuth2 authorization_code flow.

    Usage::

        server = OAuth2LocalhostServer()
        redirect_uri = server.start()  # Starts background thread, returns redirect URI
        # User opens redirect_uri in browser
        # User authorizes, browser redirects to localhost
        code, state = server.wait_for_code(timeout=300)  # Blocks until code received
        server.stop()
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        """Initialize server on *host* (default 127.0.0.1) and *port* (0 = random)."""
        self._host = host
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def redirect_uri(self) -> str:
        """The redirect URI to use in the OAuth2 request."""
        if self._server is None:
            raise RuntimeError("Server not started. Call start() first.")
        return f"http://{self._host}:{self._server.server_address[1]}/callback"

    def start(self) -> str:
        """Start the server in a background thread.

        Returns the redirect URI that the OAuth2 provider should redirect to.
        """
        self._server = HTTPServer((self._host, self._port), _RedirectHandler)
        self._server.auth_code = None  # type: ignore[attr-defined]
        self._server.auth_state = None  # type: ignore[attr-defined]
        self._server.last_error = None  # type: ignore[attr-defined]

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        return self.redirect_uri

    def wait_for_code(self, timeout: float = 300.0) -> tuple[str, str | None]:
        """Wait for the OAuth2 redirect callback.

        Args:
            timeout: Maximum wait time in seconds (default 300s/5min).

        Returns:
            Tuple of (authorization_code, state).

        Raises:
            TimeoutError: If no callback received within timeout.
            RuntimeError: If the provider returned an error.
        """
        deadline = time.monotonic() + timeout
        if self._server is None:
            raise RuntimeError("Server not started. Call start() first.")
        while time.monotonic() < deadline:
            if self._server.last_error:  # type: ignore[attr-defined]
                raise RuntimeError(f"OAuth2 error: {self._server.last_error}")  # type: ignore[attr-defined]
            if self._server.auth_code:  # type: ignore[attr-defined]
                return (self._server.auth_code, self._server.auth_state)  # type: ignore[attr-defined]
            time.sleep(0.1)
        raise TimeoutError(f"No OAuth2 callback received within {timeout}s")

    def stop(self) -> None:
        """Stop the server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __enter__(self) -> OAuth2LocalhostServer:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:  # noqa: ANN401
        self.stop()


class OAuth2AuthCodeFlow:
    """OAuth2 authorization_code flow with PKCE support.

    Usage::

        flow = OAuth2AuthCodeFlow()
        auth_url = flow.create_authorization_url(
            auth_url="https://accounts.google.com/o/oauth2/v2/auth",
            client_id="xxx.apps.googleusercontent.com",
            redirect_uri="http://127.0.0.1:PORT/callback",
            scope="https://www.googleapis.com/auth/youtube.readonly",
        )
        # User opens auth_url in browser
        # After authorization, user is redirected to redirect_uri with ?code=...
        code = "..."
        token = flow.exchange_code(
            token_url="https://oauth2.googleapis.com/token",
            client_id="xxx.apps.googleusercontent.com",
            client_secret="yyy",
            redirect_uri="http://127.0.0.1:PORT/callback",
            code=code,
            code_verifier=flow.code_verifier,
        )
    """

    def __init__(self) -> None:
        """Initialize the auth code flow with PKCE challenge and CSRF state."""
        self._state = secrets.token_urlsafe(32)
        self._code_verifier = secrets.token_urlsafe(64)
        self._code_challenge = self._pkce_challenge(self._code_verifier)

    @property
    def state(self) -> str:
        """OAuth2 state parameter for CSRF protection."""
        return self._state

    @property
    def code_verifier(self) -> str:
        """PKCE code verifier (must be saved between create and exchange)."""
        return self._code_verifier

    @staticmethod
    def _pkce_challenge(verifier: str) -> str:
        """Generate PKCE S256 code challenge from verifier."""
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        return urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def create_authorization_url(
        self,
        auth_url: str,
        client_id: str,
        redirect_uri: str,
        scope: str = "",
        extra_params: dict[str, str] | None = None,
    ) -> str:
        """Build the authorization URL for the user to open in their browser."""
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": self._state,
            "code_challenge": self._code_challenge,
            "code_challenge_method": "S256",
        }
        if scope:
            params["scope"] = scope
        params.update(extra_params or {})
        return f"{auth_url}?{urlencode(params)}"

    def exchange_code(
        self,
        token_url: str,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str,
        code: str,
        code_verifier: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> SessionToken:
        """Exchange the authorization code for tokens.

        Verifies the code verifier against the stored challenge (PKCE).
        """
        http = http_client or httpx.Client(timeout=30)

        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
        }
        if client_secret:
            data["client_secret"] = client_secret
        if code_verifier:
            data["code_verifier"] = code_verifier

        resp = http.post(token_url, data=data)
        resp.raise_for_status()
        token_data = resp.json()

        access_token = token_data.get("access_token", "")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.now() + timedelta(seconds=int(expires_in))

        return SessionToken(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )
