"""WordPress publisher — REST API implementation.

Uses the WordPress REST API (``/wp/v2/posts``) to create and publish
posts.  Supports optional featured-image upload via the media endpoint.

Requires ``httpx`` (optional dependency).

Credentials are resolved via :func:`load_credential` with
backward-compatible fallback to legacy ``AUTOMEDIA_WORDPRESS_URL`` /
``AUTOMEDIA_WORDPRESS_TOKEN`` environment variables and the standard
``AUTOMEDIA_WORDPRESS_URL`` / ``AUTOMEDIA_WORDPRESS_TOKEN`` credentials.

Authentication
--------------
WordPress Application Passwords (recommended):
    ``AUTOMEDIA_WORDPRESS_URL`` — site URL (e.g. ``https://example.com``)
    ``AUTOMEDIA_WORDPRESS_TOKEN`` — ``username:application_password``

The adapter sends an ``Authorization: Basic <base64(token)>`` header.
"""

from __future__ import annotations

import base64
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

    warn_missing_optional("httpx", feature="WordPress publishing disabled")
    _HAS_HTTPX = False

# ---------------------------------------------------------------------------
# WordPress REST API endpoint templates
# ---------------------------------------------------------------------------
WP_POSTS_ENDPOINT = "{site_url}/wp-json/wp/v2/posts"
WP_MEDIA_ENDPOINT = "{site_url}/wp-json/wp/v2/media"
WP_CATEGORIES_ENDPOINT = "{site_url}/wp-json/wp/v2/categories"

# ---------------------------------------------------------------------------
# Public API — WordPressPublisher
# ---------------------------------------------------------------------------


class WordPressPublisher(BasePlatformAdapter):
    """Publish an article to a WordPress site via the REST API.

    The publish flow consists of these steps:

    1. **Resolve credentials** — site URL and application password.
    2. **Read content** — title and HTML body from the artifact directory.
    3. **Create post** — ``POST /wp-json/wp/v2/posts`` with title,
       content, status (``draft`` or ``publish``), and optional meta.
    4. **(optional) Upload featured image** — ``POST /wp-json/wp/v2/media``
       then ``POST /wp-json/wp/v2/posts/{id}`` to set ``featured_media``.
    """

    @property
    def platform_name(self) -> str:
        """Return the platform identifier ``\"wordpress\"``."""
        return "wordpress"

    @property
    def enabled(self) -> bool:
        """Check whether WordPress credentials are configured."""
        url, token = _load_wp_credentials()
        return bool(url) and bool(token)

    def validate(self, artifact_dir: str) -> bool:
        """Validate that WordPress credentials are present and usable.

        Args:
            artifact_dir: Project artifacts directory (unused in this check).

        Returns:
            ``True`` when both URL and token are available.
        """
        _ = artifact_dir
        url, token = _load_wp_credentials()
        if not url or not token:
            log.warning("wordpress.validate.failed")
            return False
        return True

    # ------------------------------------------------------------------
    # publish — full flow
    # ------------------------------------------------------------------

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        """Publish a project article to WordPress.

        Parameters
        ----------
        artifact_dir:
            Path to the rendered artifact directory.  The method looks
            for content files under ``<artifact_dir>/drafts/`` (``*.html``
            preferred, then ``*.md``).
        project:
            Full project dict.  ``project["topic"]`` is used for the
            article title if no ``project["title"]`` is set.
        draft_only:
            When ``True``, the post is created as a draft (``status=draft``)
            instead of published immediately.  The returned ``status``
            will be ``"draft_created"`` with a ``draft_url``.

        Returns
        -------
        dict
            ``{"status": "ok", "platform": "wordpress", "post_id": …,
            "url": …}`` on success, or ``{"status": "error",
            "platform": "wordpress", "reason": …}`` on failure.
            When ``draft_only=True`` returns ``{"status": "draft_created",
            "platform": "wordpress", "post_id": …, "draft_url": …}``.
        """
        # --- pre-flight: credentials -------------------------------------------
        site_url, token = _load_wp_credentials()
        if not site_url or not token:
            return {
                "status": "error",
                "platform": "wordpress",
                "reason": (
                    "WordPress credentials not set "
                    "(AUTOMEDIA_WORDPRESS_URL / AUTOMEDIA_WORDPRESS_TOKEN)"
                ),
            }

        # --- pre-flight: httpx --------------------------------------------------
        if not _HAS_HTTPX:
            log.error("wordpress.httpx.not_available")
            return {
                "status": "error",
                "platform": "wordpress",
                "reason": "httpx is not installed",
            }

        # Guard: strip trailing slash from site URL
        site_url = site_url.rstrip("/")

        # 1. Read content from artifact directory
        content_result = self._read_content(artifact_dir, project)
        if content_result.get("status") != "ok":
            return {
                "status": "error",
                "platform": "wordpress",
                "reason": content_result.get("reason", "unknown error reading content"),
            }
        title = content_result.get("title", "Untitled")
        body_html = content_result.get("body_html", "")

        # 2. Build auth header
        auth_header = _build_auth_header(token)

        # 3. Determine post status
        post_status = "draft" if draft_only else "publish"

        # 4. Optional: resolve categories
        category_ids: list[int] = []
        raw_categories: Any = project.get("wordpress_categories") or project.get(
            "categories"
        )
        if raw_categories:
            try:
                category_ids = self._resolve_categories(
                    site_url, auth_header, raw_categories
                )
            except Exception:
                log.warning("wordpress.category_resolve_failed", exc_info=True)

        # 5. Create the post
        post_payload: dict[str, Any] = {
            "title": title,
            "content": body_html,
            "status": post_status,
        }

        if category_ids:
            post_payload["categories"] = category_ids

        # Optional: excerpt, slug, tags from project metadata
        excerpt = project.get("excerpt") or project.get("description")
        if excerpt:
            post_payload["excerpt"] = excerpt

        slug = project.get("slug")
        if slug:
            post_payload["slug"] = slug

        tags = project.get("tags")
        if tags and isinstance(tags, list):
            post_payload["tags"] = tags

        post_url = WP_POSTS_ENDPOINT.format(site_url=site_url)
        post_result = self._api_post(post_url, auth_header, post_payload, "post.create")
        if post_result.get("status") != "ok":
            return {
                "status": "error",
                "platform": "wordpress",
                "reason": post_result.get("reason", "unknown error creating post"),
            }
        article_id: str = post_result.get("article_id", "")
        edit_url: str = post_result.get("url", "")

        # 6. Optional: upload featured image
        featured_image = project.get("featured_image") or project.get("thumbnail")
        if featured_image and isinstance(featured_image, str) and Path(featured_image).is_file():
            media_result = self._upload_media(
                site_url, auth_header, featured_image, int(article_id)
            )
            if media_result.get("status") == "ok":
                log.info(
                    "wordpress.featured_image.set",
                    article_id=article_id,
                    media_id=media_result.get("media_id"),
                )

        log.info(
            "wordpress.publish.success",
            article_id=article_id,
            status=post_status,
        )

        result: PublishResult = {
            "status": "draft_created" if draft_only else "ok",
            "platform": "wordpress",
            "article_id": str(article_id),
            "url": edit_url,
        }

        if draft_only:
            result["draft_url"] = edit_url
            result["draft_id"] = str(article_id)

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_content(
        self, artifact_dir: str, project: dict[str, Any]
    ) -> dict[str, Any]:
        """Read article title and body from the artifact directory.

        Title resolution order (first non-empty wins):
        1. ``project["title"]``
        2. ``project["topic"]``
        3. ``"Untitled"``

        Body resolution order:
        1. ``<artifact_dir>/drafts/*.html`` (first file)
        2. ``<artifact_dir>/drafts/*.md`` (first file, converted to HTML)
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
        body_html = ""

        if drafts_dir.is_dir():
            html_files = sorted(drafts_dir.glob("*.html"))
            if html_files:
                body_html = html_files[0].read_text(encoding="utf-8")
                log.info("wordpress.read_content", source=str(html_files[0]))
            else:
                md_files = sorted(drafts_dir.glob("*.md"))
                if md_files:
                    md_content = md_files[0].read_text(encoding="utf-8")
                    log.info("wordpress.read_content", source=str(md_files[0]))
                    body_html = _md_to_html(md_content)

        if not body_html:
            log.warning("wordpress.content.empty", artifact_dir=artifact_dir)
            body_html = f"<p>{title}</p>"

        return {"status": "ok", "title": title, "body_html": body_html}

    def _resolve_categories(
        self,
        site_url: str,
        auth_header: dict[str, str],
        raw_categories: Any,
    ) -> list[int]:
        """Resolve category names/IDs to WordPress category IDs.

        Accepts a list of names or IDs (or a comma-separated string).
        For string names, looks up or creates the category via the REST API.
        """
        ids: list[int] = []

        # Normalise to a list of strings
        if isinstance(raw_categories, str):
            items = [c.strip() for c in raw_categories.split(",") if c.strip()]
        elif isinstance(raw_categories, (list, tuple)):
            items = list(raw_categories)
        else:
            return ids

        for item in items:
            item_str = str(item).strip()
            if not item_str:
                continue

            # Already a numeric ID
            if item_str.isdigit():
                ids.append(int(item_str))
                continue

            # Look up by name via the categories endpoint
            cat_url = WP_CATEGORIES_ENDPOINT.format(site_url=site_url)
            try:
                resp = _httpx.get(
                    cat_url,
                    headers=auth_header,
                    params={"search": item_str},
                    timeout=10,
                )
                resp.raise_for_status()
                results: list[dict[str, Any]] = resp.json()
                found = False
                for cat in results:
                    if cat.get("name", "").lower() == item_str.lower():
                        ids.append(int(cat["id"]))
                        found = True
                        break
                if not found:
                    # Create the category
                    create_resp = _httpx.post(
                        cat_url,
                        headers={**auth_header, "Content-Type": "application/json"},
                        json={"name": item_str},
                        timeout=10,
                    )
                    if create_resp.is_success:
                        created = create_resp.json()
                        ids.append(int(created["id"]))
            except _httpx.RequestError:
                log.warning(
                    "wordpress.category_lookup_failed", category=item_str
                )

        return ids

    def _upload_media(
        self,
        site_url: str,
        auth_header: dict[str, str],
        image_path: str,
        post_id: int,
    ) -> PublishResult:
        """Upload an image file as a WordPress media item and attach it to the post.

        Uses ``POST /wp-json/wp/v2/media`` with ``Content-Type`` set to
        the image MIME type, then ``POST /wp-json/wp/v2/posts/{id}`` to
        set ``featured_media``.
        """
        img = Path(image_path)
        if not img.is_file():
            log.warning("wordpress.media.file_not_found", path=image_path)
            return {"status": "error", "platform": "wordpress", "reason": "file not found"}

        # Detect MIME type from extension
        mime_map: dict[str, str] = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime = mime_map.get(img.suffix.lower(), "image/jpeg")

        media_url = WP_MEDIA_ENDPOINT.format(site_url=site_url)
        upload_headers = {
            **auth_header,
            "Content-Type": mime,
            "Content-Disposition": f'attachment; filename="{img.name}"',
        }

        try:
            image_data = img.read_bytes()
            resp = _httpx.post(
                media_url,
                headers=upload_headers,
                content=image_data,
                timeout=30,
            )
            resp.raise_for_status()
            media_data: dict[str, Any] = resp.json()
            media_id: int = media_data["id"]
        except _httpx.HTTPStatusError as exc:
            log.error(
                "wordpress.media.upload_error",
                status_code=exc.response.status_code,
            )
            return {
                "status": "error",
                "platform": "wordpress",
                "reason": f"media upload failed (HTTP {exc.response.status_code})",
            }
        except _httpx.RequestError as exc:
            log.error("wordpress.media.connection_error", error=str(exc))
            return {
                "status": "error",
                "platform": "wordpress",
                "reason": f"media upload connection error: {type(exc).__name__}",
            }

        # Attach as featured image
        post_url = f"{WP_POSTS_ENDPOINT.format(site_url=site_url)}/{post_id}"
        try:
            update_resp = _httpx.post(
                post_url,
                headers={**auth_header, "Content-Type": "application/json"},
                json={"featured_media": media_id},
                timeout=10,
            )
            update_resp.raise_for_status()
        except _httpx.RequestError as exc:
            log.error("wordpress.media.attach_error", error=str(exc))
            return {
                "status": "error",
                "platform": "wordpress",
                "reason": f"featured image attach failed: {type(exc).__name__}",
            }

        return {"status": "ok"}

    def _api_post(
        self,
        url: str,
        auth_header: dict[str, str],
        payload: dict[str, Any],
        action: str,
    ) -> PublishResult:
        """POST JSON to *url* with Basic auth and return parsed result.

        Parameters
        ----------
        url:
            Full API URL.
        auth_header:
            ``Authorization`` header dict.
        payload:
            JSON-serialisable dict to send as the request body.
        action:
            Human-readable label for log messages (e.g. ``"post.create"``).

        Returns
        -------
        dict
            ``{"status": "ok", "post_id": …, …}`` on success, or
            ``{"status": "error", "reason": …}`` on failure.
        """
        try:
            resp = _httpx.post(
                url,
                headers={**auth_header, "Content-Type": "application/json"},
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except _httpx.HTTPStatusError as exc:
            log.error(
                f"wordpress.{action}.http_error",
                status_code=exc.response.status_code,
            )
            reason = _extract_wp_error(exc.response)
            return {
                "status": "error",
                "platform": "wordpress",
                "reason": f"{action} failed (HTTP {exc.response.status_code}): {reason}",
            }
        except _httpx.RequestError as exc:
            log.error(
                f"wordpress.{action}.connection_error",
                error=str(exc),
            )
            return {
                "status": "error",
                "platform": "wordpress",
                "reason": f"{action} failed: {type(exc).__name__}",
            }

        article_id = data.get("id")
        if not article_id:
            log.error(
                f"wordpress.{action}.missing_id",
                response=data,
            )
            return {
                "status": "error",
                "platform": "wordpress",
                "reason": f"{action} succeeded but no post ID returned",
            }

        post_url: str = data.get("link", "") or ""

        return {
            "status": "ok",
            "article_id": str(article_id),
            "url": post_url,
        }


# ======================================================================
# Module-level helpers
# ======================================================================


def _load_wp_credentials() -> tuple[str, str]:
    """Load WordPress site URL and token via credential_loader with legacy env fallback.

    Returns:
        ``(site_url, token)`` tuple.  Either value may be empty string.
    """
    url = load_credential("wordpress_url")
    if not url:
        url = os.environ.get("AUTOMEDIA_WORDPRESS_URL", "").strip() or ""

    token = load_credential("wordpress_token")
    if not token:
        token = os.environ.get("AUTOMEDIA_WORDPRESS_TOKEN", "").strip() or ""
        # Also check for legacy AUTOMEDIA_WORDPRESS_APP_PASSWORD
        if not token:
            token = os.environ.get("AUTOMEDIA_WORDPRESS_APP_PASSWORD", "").strip() or ""

    return (url, token)


def _build_auth_header(token: str) -> dict[str, str]:
    """Build the ``Authorization`` header for WordPress Basic auth.

    The token should be in ``username:application_password`` format.
    If it does not contain a colon, it's used as the password with
    an empty username (some setups accept this).
    """
    encoded = base64.b64encode(token.encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {encoded}"}


def _extract_wp_error(response: _httpx.Response) -> str:
    """Extract a human-readable error message from a WordPress API error response."""
    try:
        data: dict[str, Any] = response.json()
        message = data.get("message", "")
        if message:
            code = data.get("code", "")
            return f"{code}: {message}" if code else message
    except (json.JSONDecodeError, _httpx.RequestError):
        pass
    return response.text[:200] if response.text else f"HTTP {response.status_code}"


def _md_to_html(md_content: str) -> str:
    """Convert simple markdown to HTML for WordPress article body.

    Supports headings, paragraphs, bold, italic, inline code, links,
    images, unordered lists, and line breaks.
    """
    import html as html_mod

    lines = md_content.splitlines()
    html_parts: list[str] = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue

        # Headings
        if stripped.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(
                f"<h3>{_inline_md(html_mod.escape(stripped[4:]))}</h3>"
            )
        elif stripped.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(
                f"<h2>{_inline_md(html_mod.escape(stripped[3:]))}</h2>"
            )
        elif stripped.startswith("# "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(
                f"<h1>{_inline_md(html_mod.escape(stripped[2:]))}</h1>"
            )
        # Unordered list item
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            item_text = html_mod.escape(stripped[2:].strip())
            html_parts.append(f"  <li>{_inline_md(item_text)}</li>")
        # Horizontal rule
        elif stripped in ("---", "***", "___"):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append("<hr>")
        # Paragraph
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(
                f"<p>{_inline_md(html_mod.escape(stripped))}</p>"
            )

    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


def _inline_md(text: str) -> str:
    """Apply inline markdown formatting (bold, italic, code, links, images).

    *text* is expected to already be HTML-escaped.
    """
    # Images: ![alt](url)  →  <img src="url" alt="alt">
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        r'<img src="\2" alt="\1">',
        text,
    )
    # Links: [text](url)  →  <a href="url">text</a>
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    # Italic: *text* or _text_
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", text)
    # Inline code: `code`
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    return text
