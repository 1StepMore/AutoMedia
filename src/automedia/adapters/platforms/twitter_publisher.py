"""Twitter/X publisher adapter — posts tweets via Twitter API v2.

Uses OAuth 2.0 Bearer Token authentication.
Requires ``httpx`` (optional dependency).

Credentials are resolved via :func:`load_credential` with
backward-compatible fallback to the legacy ``TWITTER_BEARER_TOKEN``
environment variable and the standard ``AUTOMEDIA_TWITTER_BEARER_TOKEN``
credential.

Twitter API v2
--------------
- POST ``https://api.twitter.com/2/tweets`` — create a Tweet
- GET ``https://api.twitter.com/2/users/me`` — resolve authenticated user info

Twitter API v1.1 (media upload)
--------------------------------
- POST ``https://upload.twitter.com/1.1/media/upload.json`` — upload media
  (simple upload for images; chunked upload for video is available but
   not implemented in this adapter)
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

    warn_missing_optional("httpx", feature="Twitter/X publishing disabled")
    _HAS_HTTPX = False

# ---------------------------------------------------------------------------
# Twitter API endpoints
# ---------------------------------------------------------------------------
TWITTER_API_BASE = "https://api.twitter.com/2"
TWITTER_TWEET_URL = f"{TWITTER_API_BASE}/tweets"
TWITTER_ME_URL = f"{TWITTER_API_BASE}/users/me"
TWITTER_MEDIA_URL = "https://upload.twitter.com/1.1/media/upload.json"

# Maximum tweet text length enforced by the API.
TWEET_MAX_CHARS = 280


def _load_twitter_credentials() -> str | None:
    """Load Twitter Bearer Token via credential_loader with legacy env fallback.

    Checks ``AUTOMEDIA_TWITTER_BEARER_TOKEN`` (standard credential path)
    first, then ``TWITTER_BEARER_TOKEN`` (legacy env var).
    """
    token = load_credential("twitter_bearer_token")
    if not token:
        token = os.environ.get("TWITTER_BEARER_TOKEN", "").strip() or None
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


def _split_thread(text: str) -> list[str]:
    """Split *text* into tweet-sized chunks for threading.

    Each chunk is at most ``TWEET_MAX_CHARS`` characters.  The split
    prefers sentence boundaries (``.``, ``!``, ``?``, ``\\n``) to keep
    individual tweets readable.

    Returns a list with a single element when *text* fits in one tweet.
    """
    if len(text) <= TWEET_MAX_CHARS:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= TWEET_MAX_CHARS:
            chunks.append(remaining)
            break

        # Try to split at a sentence boundary within the limit
        candidate = remaining[:TWEET_MAX_CHARS]
        split_at = -1
        for sep in (". ", "! ", "? ", ".\n", "!\n", "?\n", "\n\n", "\n"):
            idx = candidate.rfind(sep)
            if idx > split_at:
                split_at = idx + len(sep)

        if split_at <= 0:
            # No sentence boundary found — split at the last space
            idx = candidate.rfind(" ")
            if idx > 0:
                split_at = idx
            else:
                # No space either — hard split at the limit
                split_at = TWEET_MAX_CHARS

        chunk = remaining[:split_at].strip()
        remaining = remaining[split_at:].strip()
        chunks.append(chunk)

    return chunks


class TwitterPublisher(BasePlatformAdapter):
    """Publish content as a Tweet (or thread) on Twitter/X.

    Uses OAuth 2.0 Bearer Token authentication via the ``Authorization``
    header.  Media files found in the artifact directory are uploaded and
    attached to the first tweet (up to 4 images).

    Content longer than 280 characters is split into a tweet thread,
    with each subsequent tweet replying to the previous one.

    Rate-limit note: Twitter API v2 allows 300 tweets per 3-hour window
    per authenticated user.  This adapter does not implement retry logic
    for 429 responses.
    """

    @property
    def platform_name(self) -> str:
        """Return the platform identifier ``\"twitter\"``."""
        return "twitter"

    @property
    def enabled(self) -> bool:
        """Check whether Twitter Bearer Token is configured."""
        return bool(_load_twitter_credentials())

    def validate(self, artifact_dir: str) -> bool:
        """Validate that Twitter credentials are present.

        Args:
            artifact_dir: Project artifacts directory (unused in this check).

        Returns:
            ``True`` when a Bearer Token is available.
        """
        _ = artifact_dir
        token = _load_twitter_credentials()
        if not token:
            log.warning("twitter.validate.missing_token")
            return False
        return True

    # ------------------------------------------------------------------
    # publish — post tweet(s) to Twitter/X
    # ------------------------------------------------------------------

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        """Publish a project as a Tweet (or thread) on Twitter/X.

        Parameters
        ----------
        artifact_dir:
            Path to the rendered artifact directory.  The method reads
            content from ``<artifact_dir>/drafts/`` (``*.html`` preferred,
            then ``*.md``, then ``*.txt``).
        project:
            Full project dict.  ``project["topic"]`` or ``project["title"]``
            is used as tweet text when no draft content is available.
        draft_only:
            When ``True``, return a ``"draft_created"`` response without
            posting (Twitter does not have a native draft API; this returns
            the tweet text and a preview URL).

        Returns
        -------
        dict
            ``{"status": "ok", "platform": "twitter", "url": …,
            "tweet_id": …}`` on success, or ``{"status": "error",
            "platform": "twitter", "reason": …}`` on failure.
            When ``draft_only=True`` returns ``{"status": "draft_created",
            "platform": "twitter", "draft_text": …, "draft_url": …}``.
        """
        # --- pre-flight: credentials -------------------------------------------
        token = _load_twitter_credentials()
        if not token:
            log.warning("twitter.publish.missing_token")
            return {
                "status": "error",
                "platform": "twitter",
                "reason": (
                    "Twitter Bearer Token not set "
                    "(AUTOMEDIA_TWITTER_BEARER_TOKEN or TWITTER_BEARER_TOKEN)"
                ),
            }

        # --- pre-flight: httpx -------------------------------------------------
        if not _HAS_HTTPX:
            log.error("twitter.publish.httpx_not_available")
            return {
                "status": "error",
                "platform": "twitter",
                "reason": "httpx is not installed",
            }

        # --- read content ------------------------------------------------------
        content_result = self._read_content(artifact_dir, project)
        if content_result.get("status") != "ok":
            return content_result  # type: ignore[return-value]  # content_result is dict[str,Any]; PublishResult TypedDict expected

        tweet_text = content_result["text"]
        if not tweet_text:
            return {
                "status": "error",
                "platform": "twitter",
                "reason": "No content to tweet",
            }

        # --- resolve username for URL construction (best-effort) ---------------
        username = self._resolve_username(token)

        # --- resolve user display name for draft URL (best-effort) -------------
        user_display_name = self._resolve_user_display_name(token) or username

        # --- draft_only: return text without posting ---------------------------
        if draft_only:
            draft_url = None
            if user_display_name:
                draft_url = (
                    f"https://twitter.com/{user_display_name}"
                )
            log.info(
                "twitter.draft_only.preview",
                text_preview=tweet_text[:100],
            )
            return {
                "status": "draft_created",
                "platform": "twitter",
                "draft_text": tweet_text,
                "draft_url": draft_url,
            }

        # --- media upload ------------------------------------------------------
        media_ids: list[str] = []
        media_result = self._upload_media(artifact_dir, token)
        if media_result.get("status") == "ok":
            media_ids = media_result.get("media_ids", [])
        # Non-fatal: proceed without media if upload fails

        # --- split into thread chunks ------------------------------------------
        chunks = _split_thread(tweet_text)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        first_tweet_id: str | None = None
        previous_tweet_id: str | None = None
        tweet_ids: list[str] = []

        for i, chunk in enumerate(chunks):
            payload: dict[str, Any] = {"text": chunk}

            # Attach media to the first tweet only
            if i == 0 and media_ids:
                payload["media"] = {"media_ids": media_ids}

            # Reply to the previous tweet to form a thread
            if previous_tweet_id:
                payload["reply"] = {"in_reply_to_tweet_id": previous_tweet_id}

            try:
                resp = _httpx.post(
                    TWITTER_TWEET_URL,
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
                    errors = err_detail.get("errors") or err_detail.get("detail", str(exc))
                    err_msg = json.dumps(errors) if isinstance(errors, list) else str(errors)
                except (json.JSONDecodeError, ValueError):
                    err_msg = str(exc)
                log.error(
                    "twitter.publish.http_error",
                    status_code=status_code,
                    error=err_msg,
                    chunk_index=i,
                )
                if i == 0:
                    return {
                        "status": "error",
                        "platform": "twitter",
                        "reason": f"tweet failed (HTTP {status_code}): {err_msg}",
                    }
                # Partial failure: stop the thread but report what was posted
                break

            except _httpx.RequestError as exc:
                log.error(
                    "twitter.publish.connection_error",
                    error=str(exc),
                    chunk_index=i,
                )
                if i == 0:
                    return {
                        "status": "error",
                        "platform": "twitter",
                        "reason": f"tweet failed: {exc}",
                    }
                break

            tweet_data = data.get("data", {})
            tweet_id = tweet_data.get("id")
            if tweet_id:
                tweet_ids.append(tweet_id)
                if first_tweet_id is None:
                    first_tweet_id = tweet_id
                previous_tweet_id = tweet_id

        if not first_tweet_id:
            return {
                "status": "error",
                "platform": "twitter",
                "reason": "No tweets were posted (unexpected API response)",
            }

        # --- build result ------------------------------------------------------
        tweet_url = _build_tweet_url(first_tweet_id, username)

        log.info(
            "twitter.publish.success",
            tweet_id=first_tweet_id,
            url=tweet_url,
            tweet_count=len(tweet_ids),
        )

        return {
            "status": "ok",
            "platform": "twitter",
            "url": tweet_url,
            "tweet_id": first_tweet_id,
            "tweet_ids": tweet_ids,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_username(self, token: str) -> str | None:
        """Resolve the authenticated user's Twitter handle.

        Calls GET ``/2/users/me`` with the Bearer Token.  Returns
        ``None`` on failure — this is non-fatal; the tweet URL falls
        back to the generic ``i/web/status/{id}`` format.
        """
        headers = {"Authorization": f"Bearer {token}"}
        try:
            resp = _httpx.get(TWITTER_ME_URL, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data.get("data", {}).get("username")
        except (_httpx.HTTPStatusError, _httpx.RequestError, json.JSONDecodeError) as exc:
            log.warning("twitter.resolve_username.failed", error=str(exc))
            return None

    def _resolve_user_display_name(self, token: str) -> str | None:
        """Resolve the authenticated user's display name.

        Calls GET ``/2/users/me`` with user fields.  Returns ``None``
        on failure.  Used for building the draft-only preview URL.
        """
        headers = {"Authorization": f"Bearer {token}"}
        params = {"user.fields": "username"}
        try:
            resp = _httpx.get(
                TWITTER_ME_URL,
                headers=headers,
                params=params,
                timeout=10.0,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data.get("data", {}).get("username")
        except (_httpx.HTTPStatusError, _httpx.RequestError, json.JSONDecodeError) as exc:
            log.warning("twitter.resolve_display_name.failed", error=str(exc))
            return None

    def _upload_media(
        self, artifact_dir: str, token: str
    ) -> dict[str, Any]:
        """Upload media files from the artifact directory to Twitter.

        Scans for images (``*.png``, ``*.jpg``, ``*.jpeg``, ``*.gif``)
        recursively under *artifact_dir*.  Uses the Twitter v1.1
        ``media/upload.json`` endpoint with simple upload (multipart).

        Twitter allows up to 4 media attachments per tweet — only the
        first 4 image files found are uploaded.

        Returns ``{"status": "ok", "media_ids": [...]}`` on success,
        or ``{"status": "error", "reason": ...}`` on failure.
        """
        base = Path(artifact_dir)
        media_extensions = ("*.png", "*.jpg", "*.jpeg", "*.gif")
        media_files: list[Path] = []
        for ext in media_extensions:
            media_files.extend(sorted(base.rglob(ext)))

        if not media_files:
            return {"status": "ok", "media_ids": []}

        # Twitter allows up to 4 media attachments per tweet
        media_files = media_files[:4]

        media_ids: list[str] = []
        headers = {"Authorization": f"Bearer {token}"}

        for media_file in media_files:
            try:
                file_data = media_file.read_bytes()
                ext = media_file.suffix.lower()
                media_type = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".gif": "image/gif",
                }.get(ext, "application/octet-stream")

                resp = _httpx.post(
                    TWITTER_MEDIA_URL,
                    headers=headers,
                    files={"media": (media_file.name, file_data, media_type)},
                    timeout=120.0,
                )
                resp.raise_for_status()
                media_data: dict[str, Any] = resp.json()
                # Prefer the string-form media_id for v2 compatibility
                media_id = media_data.get("media_id_string") or media_data.get("media_id")
                if media_id:
                    media_ids.append(str(media_id))
                    log.info(
                        "twitter.media.uploaded",
                        file=media_file.name,
                        media_id=str(media_id),
                    )
            except (_httpx.HTTPStatusError, _httpx.RequestError) as exc:
                log.warning(
                    "twitter.media.upload_failed",
                    file=media_file.name,
                    error=str(exc),
                )
                # Continue with other media files — one failure shouldn't
                # block all media attachments.

        if not media_ids:
            return {"status": "ok", "media_ids": []}

        return {"status": "ok", "media_ids": media_ids}

    def _read_content(
        self, artifact_dir: str, project: dict[str, Any]
    ) -> dict[str, Any]:
        """Read tweet text from the artifact directory.

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
                log.info("twitter.read_content", source=str(html_files[0]))
                text = _strip_html(raw_html)
            else:
                md_files = sorted(drafts_dir.glob("*.md"))
                if md_files:
                    text = md_files[0].read_text(encoding="utf-8")
                    log.info("twitter.read_content", source=str(md_files[0]))
                else:
                    txt_files = sorted(drafts_dir.glob("*.txt"))
                    if txt_files:
                        text = txt_files[0].read_text(encoding="utf-8")
                        log.info("twitter.read_content", source=str(txt_files[0]))

        if not text:
            log.warning("twitter.content.empty", artifact_dir=artifact_dir)
            text = title

        return {"status": "ok", "text": text}


# ======================================================================
# Module-level helpers
# ======================================================================


def _build_tweet_url(tweet_id: str, username: str | None = None) -> str:
    """Build a human-friendly Twitter/X tweet URL.

    When *username* is available the URL includes the handle, otherwise
    the generic ``i/web/status/{id}`` fallback is used.
    """
    if username:
        return f"https://twitter.com/{username}/status/{tweet_id}"
    return f"https://twitter.com/i/web/status/{tweet_id}"
