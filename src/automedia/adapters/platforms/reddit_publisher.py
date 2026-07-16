"""Reddit publisher adapter — OAuth2 script app for post creation.

Uses the Reddit API (OAuth2 script app flow) for submitting posts to
target subreddits.  Requires ``httpx`` (optional dependency).

Authentication
--------------
Reddit script app OAuth2 flow:

1. POST ``https://www.reddit.com/api/v1/access_token`` with
   Basic auth (``client_id:client_secret``) and form body
   ``grant_type=password&username=...&password=...``.
2. Use the returned ``access_token`` in Bearer auth for API calls.

Credentials are resolved via :func:`load_credential_or_env` with
backward-compatible support for:

- ``AUTOMEDIA_REDDIT_CLIENT_ID`` / legacy ``REDDIT_CLIENT_ID``
- ``AUTOMEDIA_REDDIT_CLIENT_SECRET`` / legacy ``REDDIT_CLIENT_SECRET``
- ``AUTOMEDIA_REDDIT_USERNAME`` / legacy ``REDDIT_USERNAME``
- ``AUTOMEDIA_REDDIT_PASSWORD`` / legacy ``REDDIT_PASSWORD``

Post creation
-------------
The adapter POSTs to ``https://oauth.reddit.com/api/submit`` with
form data containing ``sr`` (subreddit), ``title``, ``text``/``url``,
and ``kind`` (``self`` for text posts, ``link`` for URL posts).

Subreddit target
----------------
Resolved from (first non-empty wins):
1. ``project["config"]["subreddit"]``
2. ``project["brand_config"]["subreddit"]``
3. ``project["subreddit"]``
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from structlog import get_logger

from automedia.adapters.base import BasePlatformAdapter, PublishResult
from automedia.core.credential_loader import load_credential_or_env

log = get_logger(__name__)

# httpx is an optional dependency — fall back gracefully when unavailable
try:
    import httpx as _httpx

    _HAS_HTTPX = True
except ImportError:  # pragma: no cover
    from automedia.core._import_helpers import warn_missing_optional

    warn_missing_optional("httpx", feature="Reddit publishing disabled")
    _HAS_HTTPX = False

# ---------------------------------------------------------------------------
# Reddit API endpoints (module-level constants)
# ---------------------------------------------------------------------------
REDDIT_OAUTH_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_API_BASE = "https://oauth.reddit.com"
REDDIT_SUBMIT_URL = f"{REDDIT_API_BASE}/api/submit"

# User-Agent required by Reddit API guidelines
_USER_AGENT = "AutoMedia/1.0 (by /u/automedia)"

# ---------------------------------------------------------------------------
# Rate-limit tracking (module-level, shared across calls)
# ---------------------------------------------------------------------------
_last_request_time: float = 0.0
_MIN_REQUEST_INTERVAL = 1.0  # 60 req/min → at most 1 per second


def _throttle() -> None:
    """Ensure we stay within Reddit's 60-requests-per-minute limit."""
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        sleep_time = _MIN_REQUEST_INTERVAL - elapsed
        time.sleep(sleep_time)
    _last_request_time = time.monotonic()


# ---------------------------------------------------------------------------
# Credential loader
# ---------------------------------------------------------------------------


def _load_reddit_credentials() -> tuple[str, str, str, str]:
    """Load Reddit OAuth2 credentials with legacy env var fallback.

    Returns
    -------
    tuple[str, str, str, str]
        ``(client_id, client_secret, username, password)`` — any may be
        empty if not found.
    """
    client_id = (
        load_credential_or_env("REDDIT_CLIENT_ID", "reddit_client_id") or ""
    )
    client_secret = (
        load_credential_or_env("REDDIT_CLIENT_SECRET", "reddit_client_secret") or ""
    )
    username = (
        load_credential_or_env("REDDIT_USERNAME", "reddit_username") or ""
    )
    password = (
        load_credential_or_env("REDDIT_PASSWORD", "reddit_password") or ""
    )
    return client_id, client_secret, username, password


# ---------------------------------------------------------------------------
# Subreddit resolver
# ---------------------------------------------------------------------------


def _resolve_subreddit(project: dict[str, Any]) -> str | None:
    """Resolve the target subreddit from project metadata.

    Priority (first non-empty wins):
    1. ``project["config"]["subreddit"]``
    2. ``project["brand_config"]["subreddit"]``
    3. ``project["subreddit"]``
    """
    config = project.get("config") or {}
    sub = config.get("subreddit")
    if sub:
        return str(sub)

    brand_config = project.get("brand_config") or {}
    sub = brand_config.get("subreddit")
    if sub:
        return str(sub)

    sub = project.get("subreddit")
    if sub:
        return str(sub)

    return None


# ======================================================================
# Adapter class
# ======================================================================


class RedditPublisher(BasePlatformAdapter):
    """Publish a post to Reddit via the OAuth2 script app API.

    The publish flow consists of two API calls:

    1. **Get access token** — ``POST /api/v1/access_token`` with Basic
       auth (client_id:client_secret) and password grant.
    2. **Submit post** — ``POST /api/submit`` with the access token,
       targeting the configured subreddit.

    Supports both self posts (text) and link posts.
    """

    @property
    def platform_name(self) -> str:
        """Return the platform identifier ``\"reddit\"``."""
        return "reddit"

    @property
    def enabled(self) -> bool:
        """Check whether Reddit credentials are configured."""
        client_id, client_secret, username, password = _load_reddit_credentials()
        return bool(client_id and client_secret and username and password)

    def validate(self, artifact_dir: str) -> bool:
        """Validate that Reddit credentials are present and usable.

        Args:
            artifact_dir: Project artifacts directory (unused in this check).

        Returns:
            ``True`` when all four credentials are available.
        """
        _ = artifact_dir
        client_id, client_secret, username, password = _load_reddit_credentials()
        if not all([client_id, client_secret, username, password]):
            log.warning("reddit.validate.failed")
            return False
        return True

    # ------------------------------------------------------------------
    # publish — full two-step flow
    # ------------------------------------------------------------------

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        """Publish a post to Reddit.

        Parameters
        ----------
        artifact_dir:
            Path to the rendered artifact directory.  The method looks
            for content files under ``<artifact_dir>/drafts/`` (``*.md``
            preferred, then ``*.html``, then ``*.txt``).
        project:
            Full project dict.  ``project["topic"]`` is used for the
            post title.  The target subreddit is resolved from
            ``project["config"]["subreddit"]``,
            ``project["brand_config"]["subreddit"]``, or
            ``project["subreddit"]``.
        draft_only:
            When ``True``, return a ``"draft_created"`` response with
            a status-only result (Reddit does not have a draft API).

        Returns
        -------
        dict
            ``{"status": "ok", "platform": "reddit", "url": …}`` on
            success, or ``{"status": "error", "platform": "reddit",
            "reason": …}`` on failure.
        """
        # --- pre-flight: credentials -------------------------------------------
        client_id, client_secret, username, password = _load_reddit_credentials()
        if not all([client_id, client_secret, username, password]):
            return {
                "status": "error",
                "platform": "reddit",
                "reason": (
                    "Reddit credentials not set "
                    "(AUTOMEDIA_REDDIT_CLIENT_ID, "
                    "AUTOMEDIA_REDDIT_CLIENT_SECRET, "
                    "AUTOMEDIA_REDDIT_USERNAME, "
                    "AUTOMEDIA_REDDIT_PASSWORD)"
                ),
            }

        # --- pre-flight: subreddit ---------------------------------------------
        subreddit = _resolve_subreddit(project)
        if not subreddit:
            return {
                "status": "error",
                "platform": "reddit",
                "reason": (
                    "No target subreddit configured. Set it in project config "
                    "under 'subreddit', 'config.subreddit', or "
                    "'brand_config.subreddit'."
                ),
            }

        # --- pre-flight: httpx --------------------------------------------------
        if not _HAS_HTTPX:
            log.error("reddit.httpx.not_available")
            return {
                "status": "error",
                "platform": "reddit",
                "reason": "httpx is not installed",
            }

        # 1. Get access token
        token_result = self._get_access_token(client_id, client_secret, username, password)
        if token_result.get("status") != "ok":
            return token_result
        access_token = token_result["access_token"]

        # 2. Read content from artifact directory
        content_result = self._read_content(artifact_dir, project)
        if content_result.get("status") != "ok":
            return content_result  # type: ignore[return-value]  # content_result is dict[str,Any]; PublishResult TypedDict expected
        title = content_result["title"]
        body_text = content_result["body_text"]
        post_url = content_result.get("url", "")

        # 3. Submit the post
        submit_result = self._submit_post(
            access_token=access_token,
            subreddit=subreddit,
            title=title,
            body_text=body_text,
            post_url=post_url,
        )
        if submit_result.get("status") != "ok":
            return submit_result

        post_id = submit_result["post_id"]
        post_url_final = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/"

        # 4. draft_only: Reddit has no draft concept, but honour the flag
        if draft_only:
            log.info(
                "reddit.draft_only.created",
                post_id=post_id,
                post_url=post_url_final,
            )
            return {
                "status": "draft_created",
                "platform": "reddit",
                "draft_id": post_id,
                "draft_url": post_url_final,
            }

        log.info(
            "reddit.publish.success",
            post_id=post_id,
            post_url=post_url_final,
            subreddit=subreddit,
        )
        return {
            "status": "ok",
            "platform": "reddit",
            "url": post_url_final,
            "article_id": post_id,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_access_token(
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
    ) -> PublishResult:
        """Obtain a Reddit OAuth2 ``access_token`` via password grant.

        Uses Basic auth with ``client_id:client_secret`` and sends
        ``grant_type=password`` with the user's credentials.
        """
        _throttle()

        auth = _httpx.BasicAuth(username=client_id, password=client_secret)
        data = {
            "grant_type": "password",
            "username": username,
            "password": password,
        }
        headers = {
            "User-Agent": _USER_AGENT,
        }

        try:
            resp = _httpx.post(
                REDDIT_OAUTH_URL,
                auth=auth,
                data=data,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
        except _httpx.HTTPStatusError as exc:
            log.error(
                "reddit.token.http_error",
                status_code=exc.response.status_code,
            )
            return {
                "status": "error",
                "platform": "reddit",
                "reason": (
                    f"token request failed (HTTP {exc.response.status_code})"
                ),
            }
        except _httpx.RequestError as exc:
            log.error(
                "reddit.token.connection_error",
                error=str(exc),
            )
            return {
                "status": "error",
                "platform": "reddit",
                "reason": f"token request failed: {type(exc).__name__}",
            }

        if "access_token" not in result:
            err_msg = result.get("error", result.get("error_description", "unknown error"))
            log.error(
                "reddit.token.api_error",
                error=err_msg,
            )
            return {
                "status": "error",
                "platform": "reddit",
                "reason": f"token API error: {err_msg}",
            }

        return {"status": "ok", "access_token": result["access_token"]}

    @staticmethod
    def _read_content(
        artifact_dir: str,
        project: dict[str, Any],
    ) -> dict[str, Any]:
        """Read post title and body from the artifact directory.

        Title resolution order (first non-empty wins):
        1. ``project["title"]``
        2. ``project["topic"]``
        3. ``"Untitled"``

        Body resolution order:
        1. ``<artifact_dir>/drafts/*.md`` (first file, kept as plain text)
        2. ``<artifact_dir>/drafts/*.html`` (first file, stripped to text)
        3. ``<artifact_dir>/drafts/*.txt`` (first file)
        """
        base = Path(artifact_dir)
        drafts_dir = base / "drafts"

        # --- Title ---
        title = project.get("title") or project.get("topic") or "Untitled"

        # Try to get a nicer title from project info file
        info_file = base / "00_project_info.json"
        if info_file.exists():
            try:
                info: dict[str, Any] = json.loads(
                    info_file.read_text(encoding="utf-8")
                )
                title = str(info.get("title") or info.get("topic") or title)
            except (json.JSONDecodeError, OSError):
                pass

        # --- Body ---
        body_text = ""
        post_url = project.get("url", "")

        if drafts_dir.is_dir():
            md_files = sorted(drafts_dir.glob("*.md"))
            html_files = sorted(drafts_dir.glob("*.html"))
            txt_files = sorted(drafts_dir.glob("*.txt"))

            if md_files:
                body_text = md_files[0].read_text(encoding="utf-8")
                log.info("reddit.read_content", source=str(md_files[0]))
            elif html_files:
                html_content = html_files[0].read_text(encoding="utf-8")
                log.info("reddit.read_content", source=str(html_files[0]))
                # Strip HTML tags to get plain text for Reddit
                import re as _re

                body_text = _re.sub(r"<[^>]+>", "", html_content)
                body_text = _re.sub(r"\n{3,}", "\n\n", body_text).strip()
            elif txt_files:
                body_text = txt_files[0].read_text(encoding="utf-8")
                log.info("reddit.read_content", source=str(txt_files[0]))

        if not body_text:
            log.warning("reddit.content.empty", artifact_dir=artifact_dir)
            body_text = title

        return {
            "status": "ok",
            "title": title,
            "body_text": body_text,
            "url": post_url,
        }

    @staticmethod
    def _submit_post(
        access_token: str,
        subreddit: str,
        title: str,
        body_text: str,
        post_url: str = "",
    ) -> PublishResult:
        """Submit a post to Reddit via ``/api/submit``.

        Determines post kind automatically:
        - If ``post_url`` is provided → ``kind=link`` with ``url=post_url``
        - Otherwise → ``kind=self`` with ``text=body_text``
        """
        _throttle()

        # Determine post kind
        if post_url:
            kind = "link"
            payload: dict[str, Any] = {
                "sr": subreddit,
                "title": title,
                "url": post_url,
                "kind": kind,
                "sendreplies": True,
            }
        else:
            kind = "self"
            payload = {
                "sr": subreddit,
                "title": title,
                "text": body_text,
                "kind": kind,
                "sendreplies": True,
            }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": _USER_AGENT,
        }

        try:
            resp = _httpx.post(
                REDDIT_SUBMIT_URL,
                data=payload,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except _httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            try:
                err_detail: dict[str, Any] = exc.response.json()
                err_msg = (
                    err_detail.get("reason")
                    or str(err_detail.get("json", {}).get("reason", ""))
                    or str(err_detail)
                )
            except (json.JSONDecodeError, ValueError):
                err_msg = str(exc)

            log.error(
                "reddit.submit.http_error",
                status_code=status_code,
                error=err_msg,
            )

            # Handle rate limiting (HTTP 429)
            if status_code == 429:
                retry_after = exc.response.headers.get("Retry-After", "60")
                return {
                    "status": "error",
                    "platform": "reddit",
                    "reason": (
                        f"Rate limited. Retry after {retry_after} seconds."
                    ),
                }

            return {
                "status": "error",
                "platform": "reddit",
                "reason": f"post submission failed (HTTP {status_code}): {err_msg}",
            }
        except _httpx.RequestError as exc:
            log.error(
                "reddit.submit.connection_error",
                error=str(exc),
            )
            return {
                "status": "error",
                "platform": "reddit",
                "reason": f"post submission failed: {type(exc).__name__}",
            }

        # Reddit returns success as {"json": {"errors": [], "data": {…}}}
        json_data = data.get("json", data) if isinstance(data, dict) else {}
        errors = json_data.get("errors", [])

        if errors:
            error_str = "; ".join(
                [": ".join(e) if isinstance(e, (list, tuple)) else str(e) for e in errors]
            )
            log.error(
                "reddit.submit.api_error",
                errors=errors,
            )
            return {
                "status": "error",
                "platform": "reddit",
                "reason": f"post submission rejected: {error_str}",
            }

        post_data = json_data.get("data", {}) if isinstance(json_data, dict) else {}
        post_id = post_data.get("id", "") if isinstance(post_data, dict) else ""

        if not post_id:
            log.error(
                "reddit.submit.missing_post_id",
                response=data,
            )
            return {
                "status": "error",
                "platform": "reddit",
                "reason": (
                    f"unexpected API response: no post id in {data}"
                ),
            }

        log.info(
            "reddit.submit.success",
            post_id=post_id,
            subreddit=subreddit,
            kind=kind,
        )
        return {"status": "ok", "post_id": post_id}
