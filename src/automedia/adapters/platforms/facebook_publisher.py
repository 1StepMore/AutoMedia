"""Facebook Page publisher — real API implementation via Graph API.

Uses the Facebook Graph API v22.0 to post content to a Facebook Page.
Requires ``httpx`` (optional dependency).

Credentials are resolved via :func:`load_credential` with
backward-compatible fallback to legacy ``FACEBOOK_PAGE_TOKEN`` /
``FACEBOOK_PAGE_ID`` environment variables and the standard
``AUTOMEDIA_FACEBOOK_PAGE_TOKEN`` / ``AUTOMEDIA_FACEBOOK_PAGE_ID``
credentials.

Graph API endpoints
-------------------
- ``POST /{page-id}/feed`` — create a text/link post
- ``POST /{page-id}/photos`` — create a photo post (with optional message)

Rate limits
-----------
Facebook Graph API allows approximately 200 calls/hour per page
access token.  This adapter does not implement automatic retry for
429 responses but reports them clearly.
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

    warn_missing_optional("httpx", feature="Facebook publishing disabled")
    _HAS_HTTPX = False

# ---------------------------------------------------------------------------
# Facebook Graph API constants
# ---------------------------------------------------------------------------
FACEBOOK_API_BASE = "https://graph.facebook.com/v22.0"

# Regex matching credential-bearing query parameters that must never appear in logs.
_CREDENTIAL_PARAMS = re.compile(r"((?:access_token)=)[^&]*", re.IGNORECASE)


def _sanitize_url(url: str) -> str:
    """Replace credential query-parameter values with ``***``."""
    return _CREDENTIAL_PARAMS.sub(r"\1***", url)


# ---------------------------------------------------------------------------
# Credential loading
# ---------------------------------------------------------------------------


def _load_facebook_credentials() -> tuple[str, str]:
    """Load Facebook page token and optional page ID via credential_loader.

    Checks ``AUTOMEDIA_FACEBOOK_PAGE_TOKEN`` (standard credential path)
    first, then ``FACEBOOK_PAGE_TOKEN`` (legacy env var).

    Similarly for ``AUTOMEDIA_FACEBOOK_PAGE_ID`` / ``FACEBOOK_PAGE_ID``.

    Returns:
        ``(page_token, page_id_or_empty)``.
    """
    page_token = load_credential("facebook_page_token")
    if not page_token:
        page_token = os.environ.get("FACEBOOK_PAGE_TOKEN", "").strip() or None

    page_id = load_credential("facebook_page_id")
    if not page_id:
        page_id = os.environ.get("FACEBOOK_PAGE_ID", "").strip() or None

    return (page_token or "", page_id or "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_html(text: str) -> str:
    """Strip HTML tags, preserving paragraph and line-break structure."""
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


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------


class FacebookPublisher(BasePlatformAdapter):
    """Publish content to a Facebook Page via the Graph API.

    Supports three publishing modes:

    * **Text-only** — ``POST /{page-id}/feed`` with a ``message``.
    * **Text + link** — ``POST /{page-id}/feed`` with ``message`` and
      a ``link`` parameter (generates a link preview card).
    * **Text + image** — ``POST /{page-id}/photos`` with ``url`` and
      ``message``.  When a link is also present it is appended to the
      message text (Facebook photos do not support the separate ``link``
      parameter).

    The ``page_id`` is resolved from the following sources (first
    non-empty wins):

    1. ``project.get("facebook_page_id")``
    2. ``project.get("config", {}).get("facebook_page_id")``
    3. ``load_credential("facebook_page_id")`` → ``AUTOMEDIA_FACEBOOK_PAGE_ID``
    4. ``FACEBOOK_PAGE_ID`` legacy env var
    """

    is_stub = False

    @property
    def platform_name(self) -> str:
        """Return the platform identifier ``\"facebook\"``."""
        return "facebook"

    @property
    def enabled(self) -> bool:
        """Check whether a Facebook Page Token is configured."""
        token, _ = _load_facebook_credentials()
        return bool(token)

    def validate(self, artifact_dir: str) -> bool:
        """Validate that Facebook credentials are present and usable.

        Args:
            artifact_dir: Project artifacts directory (unused in this check).

        Returns:
            ``True`` when a Page Token is available.
        """
        _ = artifact_dir
        token, _ = _load_facebook_credentials()
        if not token:
            log.warning("facebook.validate.missing_token")
            return False
        return True

    # ------------------------------------------------------------------
    # publish
    # ------------------------------------------------------------------

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        """Publish a project article to the Facebook Page.

        Parameters
        ----------
        artifact_dir:
            Path to the rendered artifact directory.  The method reads
            content from ``<artifact_dir>/drafts/`` (``*.html`` preferred,
            then ``*.md``).  Images are discovered recursively.
        project:
            Full project dict.  ``project["topic"]`` is used for the
            fallback message.  ``project.get("link")`` or
            ``project.get("url")`` can be set for link posts.
        draft_only:
            When ``True``, return a ``"draft_created"`` response without
            posting.  Facebook does not have a native draft API for Page
            posts, so this returns the message text and a preview URL.

        Returns
        -------
        dict
            ``{"status": "ok", "platform": "facebook", "post_id": …,
            "url": …}`` on success, or ``{"status": "error",
            "platform": "facebook", "reason": …}`` on failure.
            When ``draft_only=True`` returns ``{"status": "draft_created",
            "platform": "facebook", "message_preview": …,
            "draft_url": …}``.
        """
        # --- pre-flight: credentials -------------------------------------------
        token, page_id = _load_facebook_credentials()
        if not token:
            return {
                "status": "error",
                "platform": "facebook",
                "reason": (
                    "Facebook Page Token not set "
                    "(AUTOMEDIA_FACEBOOK_PAGE_TOKEN or FACEBOOK_PAGE_TOKEN)"
                ),
            }

        # Resolve page_id: project config > credential_loader
        resolved_page_id = (
            project.get("facebook_page_id")
            or (project.get("config", {}) if isinstance(project.get("config"), dict) else {}).get(
                "facebook_page_id"
            )  # type: ignore[union-attr]  # project is dict[str,Any] but .get("config") may return non-dict; isinstance narrows at runtime only
            or page_id
        )
        if not resolved_page_id:
            return {
                "status": "error",
                "platform": "facebook",
                "reason": (
                    "Facebook Page ID not set. Provide it via "
                    "AUTOMEDIA_FACEBOOK_PAGE_ID, FACEBOOK_PAGE_ID env var, "
                    "or project['facebook_page_id']."
                ),
            }

        # --- pre-flight: httpx -------------------------------------------------
        if not _HAS_HTTPX:
            log.error("facebook.publish.httpx_not_available")
            return {
                "status": "error",
                "platform": "facebook",
                "reason": "httpx is not installed",
            }

        # --- read content ------------------------------------------------------
        content_result = self._read_content(artifact_dir, project)
        if content_result.get("status") != "ok":
            return content_result  # type: ignore[return-value]  # content_result is dict[str,Any]; PublishResult TypedDict expected

        message = content_result["text"]
        if not message:
            return {
                "status": "error",
                "platform": "facebook",
                "reason": "No content to publish",
            }

        # --- resolve link ------------------------------------------------------
        link = project.get("link") or project.get("url") or None

        # --- discover images ---------------------------------------------------
        images = self._discover_images(artifact_dir)

        # --- draft_only: return preview without posting ------------------------
        if draft_only:
            page_ref = resolved_page_id
            draft_url = f"https://www.facebook.com/{page_ref}"
            log.info(
                "facebook.draft_only.preview",
                message_preview=message[:100],
                image_count=len(images),
                has_link=link is not None,
            )
            return {
                "status": "draft_created",
                "platform": "facebook",
                "message_preview": message[:200],
                "draft_url": draft_url,
            }

        # --- post to Facebook --------------------------------------------------
        if images:
            result = self._post_with_photo(
                token=token,
                page_id=resolved_page_id,
                message=message,
                link=link,
                image_path=images[0],
            )
        else:
            result = self._post_to_feed(
                token=token,
                page_id=resolved_page_id,
                message=message,
                link=link,
            )

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_content(self, artifact_dir: str, project: dict[str, Any]) -> dict[str, Any]:
        """Read post message from the artifact directory.

        Title resolution order (first non-empty wins):
        1. ``project["title"]``
        2. ``project["topic"]``
        3. ``"Untitled"``

        Text resolution order:
        1. ``<artifact_dir>/drafts/*.html`` (stripped of HTML tags)
        2. ``<artifact_dir>/drafts/*.md`` (plain text)
        3. Title as fallback
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

        # --- Text body ---
        text = ""

        if drafts_dir.is_dir():
            html_files = sorted(drafts_dir.glob("*.html"))
            if html_files:
                raw_html = html_files[0].read_text(encoding="utf-8")
                log.info("facebook.read_content", source=str(html_files[0]))
                text = _strip_html(raw_html)
            else:
                md_files = sorted(drafts_dir.glob("*.md"))
                if md_files:
                    text = md_files[0].read_text(encoding="utf-8")
                    log.info("facebook.read_content", source=str(md_files[0]))

        if not text:
            log.warning("facebook.content.empty", artifact_dir=artifact_dir)
            text = title
        else:
            # Prepend title to the message body for Facebook posts
            text = f"{title}\n\n{text}"

        return {"status": "ok", "text": text}

    def _discover_images(self, artifact_dir: str) -> list[Path]:
        """Discover image files under *artifact_dir*.

        Returns sorted list of image paths (``*.png``, ``*.jpg``,
        ``*.jpeg``, ``*.gif``).  At most one image is used per post
        (first found).
        """
        base = Path(artifact_dir)
        media_extensions = ("*.png", "*.jpg", "*.jpeg", "*.gif")
        media_files: list[Path] = []
        for ext in media_extensions:
            media_files.extend(sorted(base.rglob(ext)))
        # Return at most 1 — Facebook /photos endpoint accepts one image
        # per call.  Multiple-image posts require a separate multi-media
        # flow (future enhancement).
        return media_files[:1]

    def _post_to_feed(
        self,
        token: str,
        page_id: str,
        message: str,
        link: str | None = None,
    ) -> PublishResult:
        """Post a text (or text+link) message to the Page feed.

        Calls ``POST /{page-id}/feed``.
        """
        url = f"{FACEBOOK_API_BASE}/{page_id}/feed"
        payload: dict[str, Any] = {
            "message": message,
            "access_token": token,
        }
        if link:
            payload["link"] = link

        safe_url = _sanitize_url(url)
        try:
            resp = _httpx.post(url, json=payload, timeout=30.0)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except _httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            try:
                err_detail: dict[str, Any] = exc.response.json()
                err_msg = err_detail.get("error", {}).get("message", str(exc))
            except (json.JSONDecodeError, ValueError):
                err_msg = str(exc)
            log.error(
                "facebook.feed.http_error",
                status_code=status_code,
                error=err_msg,
            )
            return {
                "status": "error",
                "platform": "facebook",
                "reason": f"feed post failed (HTTP {status_code}): {err_msg}",
            }
        except _httpx.RequestError as exc:
            log.error(
                "facebook.feed.connection_error",
                error=_sanitize_url(str(exc)),
            )
            return {
                "status": "error",
                "platform": "facebook",
                "reason": f"feed post failed ({safe_url}): {type(exc).__name__}",
            }

        post_id = data.get("id", "")
        post_url = f"https://www.facebook.com/{page_id}/posts/{post_id}" if post_id else ""

        log.info(
            "facebook.feed.posted",
            post_id=post_id,
        )
        return {
            "status": "ok",
            "platform": "facebook",
            "post_id": post_id,
            "url": post_url,
        }

    def _post_with_photo(
        self,
        token: str,
        page_id: str,
        message: str,
        link: str | None = None,
        image_path: Path | None = None,
    ) -> PublishResult:
        """Post a photo (with optional message and link) to the Page.

        Calls ``POST /{page-id}/photos``.  Since Facebook's ``/photos``
        endpoint does not accept a separate ``link`` parameter, when a
        link is provided it is appended to the message text.

        When *image_path* is ``None`` or the file does not exist, falls
        back to :meth:`_post_to_feed`.
        """
        if image_path is None or not image_path.exists():
            return self._post_to_feed(token, page_id, message, link)

        url = f"{FACEBOOK_API_BASE}/{page_id}/photos"
        safe_url = _sanitize_url(url)

        # Build the message — append link to message text if present
        final_message = message
        if link and link not in final_message:
            final_message = f"{final_message}\n\n{link}"

        try:
            file_data = image_path.read_bytes()
            ext = image_path.suffix.lower()
            media_type = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
            }.get(ext, "application/octet-stream")

            resp = _httpx.post(
                url,
                data={
                    "message": final_message,
                    "access_token": token,
                },
                files={"source": (image_path.name, file_data, media_type)},
                timeout=60.0,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except _httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            try:
                err_detail: dict[str, Any] = exc.response.json()
                err_msg = err_detail.get("error", {}).get("message", str(exc))
            except (json.JSONDecodeError, ValueError):
                err_msg = str(exc)
            log.error(
                "facebook.photo.http_error",
                status_code=status_code,
                error=err_msg,
            )
            return {
                "status": "error",
                "platform": "facebook",
                "reason": f"photo post failed (HTTP {status_code}): {err_msg}",
            }
        except _httpx.RequestError as exc:
            log.error(
                "facebook.photo.connection_error",
                error=_sanitize_url(str(exc)),
            )
            return {
                "status": "error",
                "platform": "facebook",
                "reason": f"photo post failed ({safe_url}): {type(exc).__name__}",
            }

        post_id = data.get("id", "")
        # The returned id from /photos is the photo id; construct a
        # page-level URL.
        post_url = f"https://www.facebook.com/{page_id}/posts/{post_id}" if post_id else ""

        log.info(
            "facebook.photo.posted",
            post_id=post_id,
            image=image_path.name,
        )
        return {
            "status": "ok",
            "platform": "facebook",
            "post_id": post_id,
            "url": post_url,
        }
