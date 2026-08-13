"""Medium publisher adapter — draft-only post creation via Medium API.

Uses the Medium API (Bearer token) for creating posts as drafts.
Requires ``httpx`` (optional dependency).

Authentication
--------------
Medium uses a personal access token (Bearer token) for API authentication:

1. Obtain a token from https://medium.com/me/settings/security
2. Set it as ``AUTOMEDIA_MEDIUM_TOKEN`` env var or via ``credential_loader``.

Credentials are resolved via :func:`load_credential_or_env` with
backward-compatible support for:

- ``AUTOMEDIA_MEDIUM_TOKEN`` / legacy ``MEDIUM_TOKEN``

Post creation
-------------
The adapter calls ``GET /v1/me`` to resolve the ``authorId`` from the
token, then ``POST /v1/users/{authorId}/posts`` to create a draft post
with markdown content read from the artifact directory.
"""

from __future__ import annotations

import json
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

    warn_missing_optional("httpx", feature="Medium publishing disabled")
    _HAS_HTTPX = False

# ---------------------------------------------------------------------------
# Medium API endpoints (module-level constants)
# ---------------------------------------------------------------------------
MEDIUM_API_BASE = "https://api.medium.com/v1"
MEDIUM_ME_URL = f"{MEDIUM_API_BASE}/me"
MEDIUM_POSTS_URL = f"{MEDIUM_API_BASE}/users/{{author_id}}/posts"

# ---------------------------------------------------------------------------
# Credential loader
# ---------------------------------------------------------------------------


def _load_medium_token() -> str:
    """Load the Medium access token with legacy env var fallback.

    Returns
    -------
    str
        The token string, or empty string if not found.
    """
    return load_credential_or_env("MEDIUM_TOKEN", "medium_token") or ""


# ======================================================================
# Adapter class
# ======================================================================


class MediumPublisher(BasePlatformAdapter):
    """Publish an article to Medium as a draft.

    The publish flow consists of two API calls:

    1. **Get user info** — ``GET /v1/me`` to resolve the ``authorId``
       from the Bearer token.
    2. **Create post** — ``POST /v1/users/{authorId}/posts`` with the
       article title and markdown body.

    All posts are created as drafts by default (``publishStatus=draft``)
    to allow human review before going live.
    """

    is_stub = False

    @property
    def platform_name(self) -> str:
        """Return the platform identifier ``\"medium\"``."""
        return "medium"

    @property
    def enabled(self) -> bool:
        """Check whether a Medium token is configured."""
        return bool(_load_medium_token())

    def validate(self, artifact_dir: str) -> bool:
        """Validate that a Medium token is present and usable.

        Args:
            artifact_dir: Project artifacts directory (unused in this check).

        Returns:
            ``True`` when a token is available.
        """
        _ = artifact_dir
        token = _load_medium_token()
        if not token:
            log.warning("medium.validate.failed")
            return False
        return True

    # ------------------------------------------------------------------
    # publish — two-step flow
    # ------------------------------------------------------------------

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        """Publish an article to Medium as a draft.

        Parameters
        ----------
        artifact_dir:
            Path to the rendered artifact directory.  The method looks
            for content files under ``<artifact_dir>/drafts/`` (``*.md``
            preferred).
        project:
            Full project dict.  ``project["topic"]`` is used for the
            article title.  An optional ``project["config"]["medium_author_id"]``
            can be provided to skip the ``/v1/me`` API call.
        draft_only:
            When ``True``, the post is created as a draft (this is the
            default behaviour — Medium drafts are not automatically
            published).  The returned ``status`` will be
            ``"draft_created"`` with a ``draft_url``.

        Returns
        -------
        dict
            ``{"status": "ok", "platform": "medium", "article_id": …,
            "url": …}`` on success, or ``{"status": "error",
            "platform": "medium", "reason": …}`` on failure.
            When ``draft_only=True`` returns ``{"status": "draft_created",
            "platform": "medium", "draft_id": …, "draft_url": …}``.
        """
        # --- pre-flight: credentials -------------------------------------------
        token = _load_medium_token()
        if not token:
            return {
                "status": "error",
                "platform": "medium",
                "reason": ("Medium token not set (AUTOMEDIA_MEDIUM_TOKEN or MEDIUM_TOKEN)"),
            }

        # --- pre-flight: httpx --------------------------------------------------
        if not _HAS_HTTPX:
            log.error("medium.httpx.not_available")
            return {
                "status": "error",
                "platform": "medium",
                "reason": "httpx is not installed",
            }

        # 1. Resolve author ID
        author_id: str | None = None
        config = project.get("config") or {}
        if isinstance(config, dict):
            author_id = config.get("medium_author_id")

        if not author_id:
            user_result = self._get_me(token)
            if user_result.get("status") != "ok":
                return user_result
            author_id = user_result["author_id"]

        # 2. Read content from artifact directory
        content_result = self._read_content(artifact_dir, project)
        if content_result.get("status") != "ok":
            return content_result  # type: ignore[return-value]  # content_result is dict[str,Any]; PublishResult TypedDict expected
        title = content_result["title"]
        body_md = content_result["body_md"]

        # 3. Create post on Medium
        publish_status = "draft" if draft_only else "public"
        post_result = self._create_post(token, author_id, title, body_md, publish_status)
        if post_result.get("status") != "ok":
            return post_result

        article_id = post_result["article_id"]
        post_url = post_result.get("url", f"https://medium.com/p/{article_id}")

        if draft_only:
            log.info(
                "medium.draft_only.created",
                article_id=article_id,
                url=post_url,
            )
            return {
                "status": "draft_created",
                "platform": "medium",
                "draft_id": article_id,
                "draft_url": post_url,
            }

        log.info(
            "medium.publish.success",
            article_id=article_id,
            url=post_url,
        )
        return {
            "status": "ok",
            "platform": "medium",
            "article_id": article_id,
            "url": post_url,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_me(token: str) -> PublishResult:
        """Resolve the authenticated user's author ID from the Medium API.

        Calls ``GET /v1/me`` with the Bearer token and returns the
        ``id`` field from the response.
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            resp = _httpx.get(MEDIUM_ME_URL, headers=headers, timeout=10)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except _httpx.HTTPStatusError as exc:
            log.error(
                "medium.me.http_error",
                status_code=exc.response.status_code,
            )
            return {
                "status": "error",
                "platform": "medium",
                "reason": (f"user info request failed (HTTP {exc.response.status_code})"),
            }
        except _httpx.RequestError as exc:
            log.error(
                "medium.me.connection_error",
                error=str(exc),
            )
            return {
                "status": "error",
                "platform": "medium",
                "reason": f"user info request failed: {type(exc).__name__}",
            }

        response_data = data.get("data") if isinstance(data, dict) else None
        if not isinstance(response_data, dict) or "id" not in response_data:
            err_msg = str(data.get("errors", data.get("error", "unknown error")))
            log.error(
                "medium.me.api_error",
                error=err_msg,
            )
            return {
                "status": "error",
                "platform": "medium",
                "reason": f"user info API error: {err_msg}",
            }

        author_id = response_data["id"]
        log.info("medium.me.resolved", author_id=author_id)
        return {"status": "ok", "author_id": author_id}

    @staticmethod
    def _read_content(
        artifact_dir: str,
        project: dict[str, Any],
    ) -> dict[str, Any]:
        """Read article title and markdown body from the artifact directory.

        Title resolution order (first non-empty wins):
        1. ``project["title"]``
        2. ``project["topic"]``
        3. ``"Untitled"``

        Body resolution order:
        1. ``<artifact_dir>/drafts/*.md`` (first file, kept as markdown)
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
                info: dict[str, Any] = json.loads(info_file.read_text(encoding="utf-8"))
                title = str(info.get("title") or info.get("topic") or title)
            except (json.JSONDecodeError, OSError):
                pass

        # --- Body ---
        body_md = ""

        if drafts_dir.is_dir():
            md_files = sorted(drafts_dir.glob("*.md"))
            html_files = sorted(drafts_dir.glob("*.html"))
            txt_files = sorted(drafts_dir.glob("*.txt"))

            if md_files:
                body_md = md_files[0].read_text(encoding="utf-8")
                log.info("medium.read_content", source=str(md_files[0]))
            elif html_files:
                html_content = html_files[0].read_text(encoding="utf-8")
                log.info("medium.read_content", source=str(html_files[0]))
                # Strip HTML tags for markdown fallback
                import re as _re

                body_md = _re.sub(r"<[^>]+>", "", html_content)
                body_md = _re.sub(r"\n{3,}", "\n\n", body_md).strip()
            elif txt_files:
                body_md = txt_files[0].read_text(encoding="utf-8")
                log.info("medium.read_content", source=str(txt_files[0]))

        if not body_md:
            log.warning("medium.content.empty", artifact_dir=artifact_dir)
            body_md = title

        return {"status": "ok", "title": title, "body_md": body_md}

    @staticmethod
    def _create_post(
        token: str,
        author_id: str,
        title: str,
        body_md: str,
        publish_status: str = "draft",
    ) -> PublishResult:
        """Create a Medium post via ``POST /v1/users/{authorId}/posts``.

        Parameters
        ----------
        token:
            Medium Bearer token.
        author_id:
            The Medium author ID to post as.
        title:
            Article title.
        body_md:
            Article body in markdown format.
        publish_status:
            Either ``"draft"`` (default) or ``"public"``.

        Returns
        -------
        dict
            Result with ``"status": "ok"`` and ``article_id`` and ``url``
            on success, or ``"status": "error"`` on failure.
        """
        url = MEDIUM_POSTS_URL.format(author_id=author_id)
        payload: dict[str, Any] = {
            "title": title,
            "contentFormat": "markdown",
            "content": body_md,
            "publishStatus": publish_status,
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            resp = _httpx.post(url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except _httpx.HTTPStatusError as exc:
            log.error(
                "medium.post.http_error",
                status_code=exc.response.status_code,
            )
            return {
                "status": "error",
                "platform": "medium",
                "reason": (f"post creation failed (HTTP {exc.response.status_code})"),
            }
        except _httpx.RequestError as exc:
            log.error(
                "medium.post.connection_error",
                error=str(exc),
            )
            return {
                "status": "error",
                "platform": "medium",
                "reason": f"post creation failed: {type(exc).__name__}",
            }

        response_data = data.get("data") if isinstance(data, dict) else None
        if not isinstance(response_data, dict) or "id" not in response_data:
            err_msg = str(data.get("errors", data.get("error", "unknown error")))
            log.error(
                "medium.post.api_error",
                error=err_msg,
            )
            return {
                "status": "error",
                "platform": "medium",
                "reason": f"post API error: {err_msg}",
            }

        article_id = response_data["id"]
        post_url = response_data.get("url", f"https://medium.com/p/{article_id}")

        log.info(
            "medium.post.created",
            article_id=article_id,
            url=post_url,
            publish_status=publish_status,
        )

        return {
            "status": "ok",
            "article_id": article_id,
            "url": post_url,
        }
