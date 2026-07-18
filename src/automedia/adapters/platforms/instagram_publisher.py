"""Instagram publisher adapter — posts image/video content via Instagram Graph API.

Uses the Instagram Graph API (v22.0) container-based publishing flow.
Requires ``httpx`` (optional dependency).

Credentials are resolved via :func:`load_credential` with
backward-compatible fallback to legacy environment variables:

- ``AUTOMEDIA_INSTAGRAM_TOKEN`` (or ``INSTAGRAM_ACCESS_TOKEN``) — long-lived
  Facebook Page access token with ``instagram_basic`` + ``instagram_content_publish``
  permissions.
- ``AUTOMEDIA_INSTAGRAM_USER_ID`` (or ``INSTAGRAM_USER_ID``) — Instagram
  Business Account ID (IG User ID).

Publishing flow
---------------
1. **Create media container** — ``POST /{ig-user-id}/media`` with ``image_url``
   (or ``video_url``) and ``caption``.
2. **Publish container** — ``POST /{ig-user-id}/media_publish`` with the
   returned container ID.

Rate limits: 200 calls per hour per access token.
"""

from __future__ import annotations

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

    warn_missing_optional("httpx", feature="Instagram publishing disabled")
    _HAS_HTTPX = False

# ---------------------------------------------------------------------------
# Instagram Graph API endpoints (module-level constants)
# ---------------------------------------------------------------------------
IG_API_VERSION = "v22.0"
IG_API_BASE = f"https://graph.facebook.com/{IG_API_VERSION}"

# Rate limit: 200 calls/hour — we use a conservative per-step limit.
IG_RATE_LIMIT_HOURLY = 200
IG_TIMEOUT = 30

# Maximum caption length enforced by the Instagram API.
IG_CAPTION_MAX_CHARS = 2200

# Regex matching credential-bearing query parameters that must never appear in logs.
_CREDENTIAL_PARAMS = re.compile(r"((?:access_token)=)[^&]*", re.IGNORECASE)


def _sanitize_url(url: str) -> str:
    """Replace credential query-parameter values with ``***``."""
    return _CREDENTIAL_PARAMS.sub(r"\1***", url)


def _load_instagram_credentials() -> tuple[str, str]:
    """Load Instagram access token and user ID via credential_loader with legacy env fallback.

    Returns
    -------
    tuple[str, str]
        ``(access_token, ig_user_id)`` — each may be empty if not found.
    """
    token = load_credential("instagram_token")
    if not token:
        token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip() or ""

    user_id = load_credential("instagram_user_id")
    if not user_id:
        user_id = os.environ.get("INSTAGRAM_USER_ID", "").strip() or ""

    return token, user_id


def _read_caption(artifact_dir: str, project: dict[str, Any]) -> str:
    """Build a caption from the project content.

    Title resolution order (first non-empty wins):
    1. ``project["title"]``
    2. ``project["topic"]``
    3. ``"Untitled"``

    The caption is assembled as: title + ``\\n\\n`` + body text (truncated to
    ``IG_CAPTION_MAX_CHARS``).
    """
    title = project.get("title") or project.get("topic") or "Untitled"

    # Try to get a nicer title from project info file
    base = Path(artifact_dir)
    info_file = base / "00_project_info.json"
    if info_file.exists():
        try:
            import json

            info: dict[str, Any] = json.loads(info_file.read_text(encoding="utf-8"))
            title = str(info.get("title") or info.get("topic") or title)
        except (json.JSONDecodeError, OSError):
            pass

    # Read body from drafts directory
    drafts_dir = base / "drafts"
    body = ""
    if drafts_dir.is_dir():
        html_files = sorted(drafts_dir.glob("*.html"))
        if html_files:
            raw_html = html_files[0].read_text(encoding="utf-8")
            body = _strip_html(raw_html)
        else:
            md_files = sorted(drafts_dir.glob("*.md"))
            if md_files:
                body = md_files[0].read_text(encoding="utf-8")
            else:
                txt_files = sorted(drafts_dir.glob("*.txt"))
                if txt_files:
                    body = txt_files[0].read_text(encoding="utf-8")

    caption = title
    if body:
        remaining = IG_CAPTION_MAX_CHARS - len(title) - 2
        if remaining > 0:
            caption = f"{title}\n\n{body[:remaining]}"
        else:
            caption = title[:IG_CAPTION_MAX_CHARS]

    return caption


def _find_media_url(artifact_dir: str, project: dict[str, Any]) -> dict[str, Any]:
    """Resolve a media URL for the Instagram container.

    Priority order:
    1. ``project["image_url"]`` — direct URL to a publicly accessible image
    2. ``project["video_url"]`` — direct URL to a publicly accessible video
    3. Scan ``<artifact_dir>/images/``, ``<artifact_dir>/output/``,
       ``<artifact_dir>/thumbnails/`` for local media files (logs warning
       that local paths must be publicly accessible).

    Returns
    -------
    dict
        ``{"media_type": "IMAGE", "media_url": "..."}`` or
        ``{"media_type": "VIDEO", "media_url": "..."}`` or
        ``{"status": "error", "reason": "..."}``.
    """
    # Check for explicitly provided URLs
    image_url = project.get("image_url")
    if image_url:
        return {"media_type": "IMAGE", "media_url": str(image_url)}

    video_url = project.get("video_url")
    if video_url:
        return {"media_type": "VIDEO", "media_url": str(video_url)}

    # Scan artifact directory for media files
    base = Path(artifact_dir)
    image_exts = ("*.png", "*.jpg", "*.jpeg", "*.webp")
    video_exts = ("*.mp4", "*.mov", "*.avi", "*.webm")

    # Search in likely subdirectories
    search_dirs = ["images", "output", "thumbnails", "."]
    for subdir in search_dirs:
        target = base / subdir
        if not target.is_dir():
            continue

        # Image first (preferred)
        for ext in image_exts:
            files = sorted(target.glob(ext))
            if files:
                local_path = str(files[0].resolve())
                log.warning(
                    "instagram.media.local_path",
                    path=local_path,
                    message=(
                        "Local file path must be made publicly accessible "
                        "for Instagram Graph API; set project['image_url'] "
                        "to a public URL"
                    ),
                )
                # Return as a data URI hint — the adapter will attempt the
                # local path but the user should provide a public URL.
                return {"media_type": "IMAGE", "media_url": local_path}

        # Video fallback
        for ext in video_exts:
            files = sorted(target.glob(ext))
            if files:
                local_path = str(files[0].resolve())
                log.warning(
                    "instagram.media.local_path",
                    path=local_path,
                    message=(
                        "Local file path must be made publicly accessible "
                        "for Instagram Graph API; set project['video_url'] "
                        "to a public URL"
                    ),
                )
                return {"media_type": "VIDEO", "media_url": local_path}

    return {
        "status": "error",
        "reason": (
            "No media URL found. Set project['image_url'] or "
            "project['video_url'] to a publicly accessible URL, or "
            "place media files in the artifact directory."
        ),
    }


def _strip_html(text: str) -> str:
    """Strip HTML tags, preserving paragraph/line-break structure."""
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


# ======================================================================
# Adapter class
# ======================================================================


class InstagramPublisher(BasePlatformAdapter):
    """Publish image/video content to Instagram via the Graph API.

    The publish flow consists of two API calls:

    1. **Create media container** — ``POST /{ig-user-id}/media`` with
       ``image_url`` (or ``video_url``) and ``caption``.
    2. **Publish container** — ``POST /{ig-user-id}/media_publish`` with the
       returned container ``creation_id``.

    .. note::
       The ``image_url`` / ``video_url`` **must** be a publicly accessible
       URL.  Instagram's servers fetch the media from this URL, so local
       file paths (``file://``) will **not** work.
    """

    @property
    def platform_name(self) -> str:
        """Return the platform identifier ``\"instagram\"``."""
        return "instagram"

    @property
    def enabled(self) -> bool:
        """Check whether Instagram credentials (token + user ID) are configured."""
        token, user_id = _load_instagram_credentials()
        return bool(token) and bool(user_id)

    def validate(self, artifact_dir: str) -> bool:
        """Validate that Instagram publish credentials are present and usable.

        Args:
            artifact_dir: Project artifacts directory (unused in this check).

        Returns:
            ``True`` when both access token and user ID are available.
        """
        _ = artifact_dir
        token, user_id = _load_instagram_credentials()
        if not token or not user_id:
            log.warning("instagram.validate.failed")
            return False
        return True

    # ------------------------------------------------------------------
    # publish — full two-step container flow
    # ------------------------------------------------------------------

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        """Publish a project image/video to Instagram.

        Parameters
        ----------
        artifact_dir:
            Path to the rendered artifact directory.  The method looks for
            media files under ``<artifact_dir>/images/``, ``output/``, or
            ``thumbnails/`` (in that order), or uses ``project["image_url"]``
            / ``project["video_url"]`` if provided.
        project:
            Full project dict.  ``project["title"]`` or ``project["topic"]``
            is used as the caption.  Optionally ``project["image_url"]`` or
            ``project["video_url"]`` for the media.
        draft_only:
            When ``True``, return a ``"draft_created"`` response without
            submitting for publish (Instagram does not have a draft API;
            this returns the caption preview and media URL).

        Returns
        -------
        dict
            ``{"status": "ok", "platform": "instagram", "media_id": …,
            "url": …}`` on success, or ``{"status": "error",
            "platform": "instagram", "reason": …}`` on failure.
            When ``draft_only=True`` returns ``{"status": "draft_created",
            "platform": "instagram", "caption_preview": …,
            "media_url": …}``.
        """
        # --- pre-flight: credentials -------------------------------------------
        token, user_id = _load_instagram_credentials()
        if not token or not user_id:
            return {
                "status": "error",
                "platform": "instagram",
                "reason": (
                    "Instagram credentials not set "
                    "(AUTOMEDIA_INSTAGRAM_TOKEN / "
                    "AUTOMEDIA_INSTAGRAM_USER_ID or "
                    "INSTAGRAM_ACCESS_TOKEN / INSTAGRAM_USER_ID)"
                ),
            }

        # --- pre-flight: httpx --------------------------------------------------
        if not _HAS_HTTPX:
            log.error("instagram.publish.httpx_not_available")
            return {
                "status": "error",
                "platform": "instagram",
                "reason": "httpx is not installed",
            }

        # --- resolve media URL --------------------------------------------------
        media_result = _find_media_url(artifact_dir, project)
        if media_result.get("status") == "error":
            return {
                "status": "error",
                "platform": "instagram",
                "reason": media_result["reason"],
            }

        media_type = media_result["media_type"]  # "IMAGE" or "VIDEO"
        media_url = media_result["media_url"]

        # --- build caption ------------------------------------------------------
        caption = _read_caption(artifact_dir, project)

        # --- draft_only: return preview without posting -------------------------
        if draft_only:
            log.info(
                "instagram.draft_only.preview",
                caption_preview=caption[:100],
                media_url=media_url,
            )
            return {
                "status": "draft_created",
                "platform": "instagram",
                "caption_preview": caption,
                "media_url": media_url,
            }  # type: ignore[typeddict-item]  # caption_preview and media_url are not defined in PublishResult TypedDict

        # 1. Create media container
        container_result = self._create_media_container(
            token, user_id, media_type, media_url, caption
        )
        if container_result.get("status") != "ok":
            return container_result  # type: ignore[return-value]  # container_result is dict[str,Any]; PublishResult expected but dict literal OK at runtime
        creation_id = container_result["creation_id"]

        # 2. Publish the container
        publish_result = self._publish_container(token, user_id, creation_id)
        if publish_result.get("status") != "ok":
            return publish_result  # type: ignore[return-value]  # publish_result is dict[str,Any]; PublishResult TypedDict expected
        published_media_id = publish_result["media_id"]

        # Build the Instagram post URL
        post_url = f"https://www.instagram.com/p/{published_media_id}/"

        log.info(
            "instagram.publish.success",
            media_id=published_media_id,
            url=post_url,
        )
        return {
            "status": "ok",
            "platform": "instagram",
            "media_id": published_media_id,
            "url": post_url,
        }  # type: ignore[typeddict-item]  # media_id and url are defined in PublishResult but out-of-order key assignment confuses mypy

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_media_container(
        self,
        token: str,
        user_id: str,
        media_type: str,
        media_url: str,
        caption: str,
    ) -> dict[str, Any]:
        """Create an Instagram media container via ``POST /{ig-user-id}/media``.

        The container is a temporary object that holds the reference to the
        media file and its caption.  It must be published via
        :meth:`_publish_container` within 24 hours.
        """
        url = f"{IG_API_BASE}/{user_id}/media"
        params: dict[str, str] = {
            "access_token": token,
            "caption": caption,
        }

        if media_type == "IMAGE":
            params["image_url"] = media_url
        elif media_type == "VIDEO":
            params["media_type"] = "VIDEO"
            params["video_url"] = media_url
        else:
            return {
                "status": "error",
                "platform": "instagram",
                "reason": f"Unsupported media type: {media_type}",
            }

        safe_url = _sanitize_url(f"{url}?{_urlencode_params(params)}")

        try:
            resp = _httpx.post(url, data=params, timeout=IG_TIMEOUT)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except _httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            try:
                err_detail: dict[str, Any] = exc.response.json()
                err_msg = err_detail.get("error", {}).get("message", str(exc))
            except (ValueError, TypeError):
                err_msg = str(exc)
            log.error(
                "instagram.container.http_error",
                status_code=status_code,
                error=err_msg,
            )
            return {
                "status": "error",
                "platform": "instagram",
                "reason": (f"media container creation failed (HTTP {status_code}): {err_msg}"),
            }
        except _httpx.RequestError as exc:
            log.error(
                "instagram.container.connection_error",
                error=_sanitize_url(str(exc)),
            )
            return {
                "status": "error",
                "platform": "instagram",
                "reason": (f"media container creation failed ({safe_url}): {type(exc).__name__}"),
            }

        container_id = data.get("id")
        if not container_id:
            err_msg = data.get("error", {}).get("message", "unknown error")
            log.error(
                "instagram.container.api_error",
                error=err_msg,
            )
            return {
                "status": "error",
                "platform": "instagram",
                "reason": f"container API error: {err_msg}",
            }

        log.info("instagram.container.created", container_id=container_id)
        return {"status": "ok", "creation_id": container_id}

    def _publish_container(
        self,
        token: str,
        user_id: str,
        creation_id: str,
    ) -> dict[str, Any]:
        """Publish a previously created media container.

        Calls ``POST /{ig-user-id}/media_publish`` with the ``creation_id``
        returned by :meth:`_create_media_container`.
        """
        url = f"{IG_API_BASE}/{user_id}/media_publish"
        params: dict[str, str] = {
            "access_token": token,
            "creation_id": creation_id,
        }
        safe_url = _sanitize_url(f"{url}?{_urlencode_params(params)}")

        try:
            resp = _httpx.post(url, data=params, timeout=IG_TIMEOUT)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except _httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            try:
                err_detail: dict[str, Any] = exc.response.json()
                err_msg = err_detail.get("error", {}).get("message", str(exc))
            except (ValueError, TypeError):
                err_msg = str(exc)

            # Handle rate-limit specifically
            if status_code == 429:
                log.error(
                    "instagram.publish.rate_limited",
                    error=err_msg,
                )
                return {
                    "status": "error",
                    "platform": "instagram",
                    "reason": (
                        f"Instagram rate limit exceeded "
                        f"({IG_RATE_LIMIT_HOURLY} calls/hour). "
                        f"Retry later."
                    ),
                }

            log.error(
                "instagram.publish.http_error",
                status_code=status_code,
                error=err_msg,
            )
            return {
                "status": "error",
                "platform": "instagram",
                "reason": (f"publish failed (HTTP {status_code}): {err_msg}"),
            }
        except _httpx.RequestError as exc:
            log.error(
                "instagram.publish.connection_error",
                error=_sanitize_url(str(exc)),
            )
            return {
                "status": "error",
                "platform": "instagram",
                "reason": (f"publish failed ({safe_url}): {type(exc).__name__}"),
            }

        published_id = data.get("id")
        if not published_id:
            err_msg = data.get("error", {}).get("message", "unknown error")
            log.error(
                "instagram.publish.api_error",
                error=err_msg,
            )
            return {
                "status": "error",
                "platform": "instagram",
                "reason": f"publish API error: {err_msg}",
            }

        log.info(
            "instagram.publish.submitted",
            media_id=published_id,
            creation_id=creation_id,
        )
        return {"status": "ok", "media_id": published_id}


# ======================================================================
# Module-level helpers
# ======================================================================


def _urlencode_params(params: dict[str, str]) -> str:
    """URL-encode a dictionary of query parameters."""
    from urllib.parse import urlencode

    return urlencode(params)
