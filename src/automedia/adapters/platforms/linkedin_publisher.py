"""LinkedIn publisher adapter — creates posts via LinkedIn Posts API v2.

Uses OAuth 2.0 Bearer Token authentication.
Requires ``httpx`` (optional dependency).

Credentials are resolved via :func:`load_credential` with
backward-compatible fallback to the legacy ``LINKEDIN_ACCESS_TOKEN``
environment variable and the standard ``AUTOMEDIA_LINKEDIN_TOKEN``
credential.

LinkedIn API v2
---------------
- GET ``https://api.linkedin.com/v2/userinfo`` — resolve authenticated user info
- POST ``https://api.linkedin.com/v2/posts`` — create a posts
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from structlog import get_logger

from automedia.adapters.base import BasePlatformAdapter, PublishResult
from automedia.core.credential_loader import load_credential

log = get_logger(__name__)

# httpx is an optional dependency — fall back gracefully when unavailable
try:
    import httpx as _httpx

    _HAS_HTTPX = True
except ImportError:  # pragma: no cover
    from automedia.core._import_helpers import warn_missing_optional

    warn_missing_optional("httpx", feature="LinkedIn publishing disabled")
    _HAS_HTTPX = False

# ---------------------------------------------------------------------------
# LinkedIn API endpoints
# ---------------------------------------------------------------------------
LINKEDIN_API_BASE = "https://api.linkedin.com/v2"
LINKEDIN_USERINFO_URL = f"{LINKEDIN_API_BASE}/userinfo"
LINKEDIN_POSTS_URL = f"{LINKEDIN_API_BASE}/posts"


def _load_linkedin_credentials() -> str | None:
    """Load LinkedIn Bearer Token via credential_loader with legacy env fallback.

    Checks ``AUTOMEDIA_LINKEDIN_TOKEN`` (standard credential path)
    first, then ``LINKEDIN_ACCESS_TOKEN`` (legacy env var).
    """
    token = load_credential("linkedin_token")
    if not token:
        token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip() or None
    return token


def _strip_html(text: str) -> str:
    """Strip HTML tags from text, preserving paragraph and line-break structure.

    Converts ``<br>``, ``</p>``, and ``</div>`` to newlines so the
    extracted text retains basic paragraph separation.
    """
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</p>", "\n", text)
    text = re.sub(r"</div>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class LinkedInPublisher(BasePlatformAdapter):
    """Publish content as a post on LinkedIn.

    Uses OAuth 2.0 Bearer Token authentication via the ``Authorization``
    header.  The adapter resolves the authenticated user's LinkedIn person
    URN before posting.

    Content is posted as a text post using the LinkedIn Posts API v2.
    HTML content from the artifact directory is stripped to plain text
    before posting (LinkedIn does not support HTML in the commentary field).
    """

    @property
    def platform_name(self) -> str:
        """Return the platform identifier ``\"linkedin\"``."""
        return "linkedin"

    @property
    def enabled(self) -> bool:
        """Check whether LinkedIn Bearer Token is configured."""
        return bool(_load_linkedin_credentials())

    def validate(self, artifact_dir: str) -> bool:
        """Validate that LinkedIn credentials are present.

        Args:
            artifact_dir: Project artifacts directory (unused in this check).

        Returns:
            ``True`` when a Bearer Token is available.
        """
        _ = artifact_dir
        token = _load_linkedin_credentials()
        if not token:
            log.warning("linkedin.validate.missing_token")
            return False
        return True

    # ------------------------------------------------------------------
    # publish — create a post on LinkedIn
    # ------------------------------------------------------------------

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        """Publish a project as a post on LinkedIn.

        Parameters
        ----------
        artifact_dir:
            Path to the rendered artifact directory.  The method reads
            content from ``<artifact_dir>/drafts/`` (``*.html`` preferred,
            then ``*.md``, then ``*.txt``).
        project:
            Full project dict.  ``project["topic"]`` or ``project["title"]``
            is used as post text when no draft content is available.
        draft_only:
            When ``True``, return a ``"draft_created"`` response without
            posting (LinkedIn does not have a native draft API; this returns
            the post text and a preview URL).

        Returns
        -------
        dict
            ``{"status": "ok", "platform": "linkedin", "url": …,
            "post_id": …}`` on success, or ``{"status": "error",
            "platform": "linkedin", "reason": …}`` on failure.
            When ``draft_only=True`` returns ``{"status": "draft_created",
            "platform": "linkedin", "draft_text": …, "draft_url": …}``.
        """
        # --- pre-flight: credentials -------------------------------------------
        token = _load_linkedin_credentials()
        if not token:
            log.warning("linkedin.publish.missing_token")
            return {
                "status": "error",
                "platform": "linkedin",
                "reason": (
                    "LinkedIn Bearer Token not set "
                    "(AUTOMEDIA_LINKEDIN_TOKEN or LINKEDIN_ACCESS_TOKEN)"
                ),
            }

        # --- pre-flight: httpx -------------------------------------------------
        if not _HAS_HTTPX:
            log.error("linkedin.publish.httpx_not_available")
            return {
                "status": "error",
                "platform": "linkedin",
                "reason": "httpx is not installed",
            }

        # --- read content ------------------------------------------------------
        content_result = self._read_content(artifact_dir, project)
        if content_result.get("status") != "ok":
            return content_result  # type: ignore[return-value]  # content_result is dict[str,Any]; PublishResult TypedDict expected

        post_text = content_result["text"]
        if not post_text:
            return {
                "status": "error",
                "platform": "linkedin",
                "reason": "No content to post",
            }

        # --- resolve author URN (person ID) ------------------------------------
        author_urn = self._resolve_author_urn(token)
        if not author_urn:
            return {
                "status": "error",
                "platform": "linkedin",
                "reason": "Could not resolve LinkedIn author URN — check token validity",
            }

        # --- draft_only: return text without posting ---------------------------
        if draft_only:
            draft_url = "https://www.linkedin.com/in/"
            if author_urn:
                person_id = author_urn.split(":")[-1]
                draft_url = f"https://www.linkedin.com/in/{person_id}"
            log.info(
                "linkedin.draft_only.preview",
                text_preview=post_text[:100],
            )
            return {
                "status": "draft_created",
                "platform": "linkedin",
                "draft_text": post_text,
                "draft_url": draft_url,
            }

        # --- create post -------------------------------------------------------
        result = self._create_post(token, author_urn, post_text)
        if result.get("status") != "ok":
            return result

        post_id = result["post_id"]
        post_url = f"https://www.linkedin.com/feed/update/{post_id}"

        log.info(
            "linkedin.publish.success",
            post_id=post_id,
            url=post_url,
        )

        return {
            "status": "ok",
            "platform": "linkedin",
            "url": post_url,
            "post_id": post_id,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_author_urn(self, token: str) -> str | None:
        """Resolve the authenticated user's LinkedIn person URN.

        Calls GET ``/v2/userinfo`` with the Bearer Token.  Returns the
        ``sub`` claim formatted as ``urn:li:person:{sub}``, or ``None``
        on failure.
        """
        headers = {"Authorization": f"Bearer {token}"}
        try:
            resp = _httpx.get(LINKEDIN_USERINFO_URL, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            sub = data.get("sub")
            if sub:
                return f"urn:li:person:{sub}"
            log.warning("linkedin.resolve_author.no_sub", response=data)
            return None
        except (_httpx.HTTPStatusError, _httpx.RequestError, json.JSONDecodeError) as exc:
            log.warning("linkedin.resolve_author.failed", error=str(exc))
            return None

    def _create_post(
        self,
        token: str,
        author_urn: str,
        text: str,
    ) -> PublishResult:
        """Create a LinkedIn post via ``POST /v2/posts``.

        Returns ``{"status": "ok", "post_id": …}`` on success, or
        ``{"status": "error", "platform": "linkedin", "reason": …}``
        on failure.
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": "202412",
        }

        payload: dict[str, Any] = {
            "author": author_urn,
            "commentary": text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

        try:
            resp = _httpx.post(
                LINKEDIN_POSTS_URL,
                json=payload,
                headers=headers,
                timeout=30.0,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except _httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            try:
                err_detail: dict[str, Any] = exc.response.json()
                err_msg = json.dumps(err_detail) if isinstance(err_detail, dict) else str(err_detail)
            except (json.JSONDecodeError, ValueError):
                err_msg = str(exc)
            log.error(
                "linkedin.create_post.http_error",
                status_code=status_code,
                error=err_msg,
            )
            return {
                "status": "error",
                "platform": "linkedin",
                "reason": f"create post failed (HTTP {status_code}): {err_msg}",
            }
        except _httpx.RequestError as exc:
            log.error(
                "linkedin.create_post.connection_error",
                error=str(exc),
            )
            return {
                "status": "error",
                "platform": "linkedin",
                "reason": f"create post failed: {exc}",
            }

        # LinkedIn Posts API returns the resource ID in the response ``id`` field.
        post_id = data.get("id")
        if not post_id:
            log.warning("linkedin.create_post.missing_id", response=data)
            return {
                "status": "error",
                "platform": "linkedin",
                "reason": "No post ID returned by LinkedIn API",
            }

        return {"status": "ok", "post_id": str(post_id)}

    def _read_content(
        self, artifact_dir: str, project: dict[str, Any]
    ) -> dict[str, Any]:
        """Read post text from the artifact directory.

        Title resolution order (first non-empty wins):
        1. ``project["title"]``
        2. ``project["topic"]``
        3. ``"Untitled"``

        Text resolution order:
        1. ``<artifact_dir>/drafts/*.html`` (stripped of HTML tags)
        2. ``<artifact_dir>/drafts/*.md`` (plain text)
        3. ``<artifact_dir>/drafts/*.txt``
        4. Title as fallback

        Returns ``{"status": "ok", "text": …}``.
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

        # --- Text body ---
        text = ""

        if drafts_dir.is_dir():
            html_files = sorted(drafts_dir.glob("*.html"))
            if html_files:
                raw_html = html_files[0].read_text(encoding="utf-8")
                log.info("linkedin.read_content", source=str(html_files[0]))
                text = _strip_html(raw_html)
            else:
                md_files = sorted(drafts_dir.glob("*.md"))
                if md_files:
                    text = md_files[0].read_text(encoding="utf-8")
                    log.info("linkedin.read_content", source=str(md_files[0]))
                else:
                    txt_files = sorted(drafts_dir.glob("*.txt"))
                    if txt_files:
                        text = txt_files[0].read_text(encoding="utf-8")
                        log.info("linkedin.read_content", source=str(txt_files[0]))

        if not text:
            log.warning("linkedin.content.empty", artifact_dir=artifact_dir)
            text = title

        return {"status": "ok", "text": text}
