"""Zhihu (知乎) draft publisher — creates drafts via the Zhihu API.

Uses cookie-based authentication.  Requires ``httpx`` (optional dependency).

Credentials are resolved via :func:`load_credential_or_env` with
backward-compatible support for the legacy ``ZHIHU_COOKIE`` environment
variable and the standard ``AUTOMEDIA_ZHIHU_COOKIE`` credential.

Zhihu Draft API
---------------
The adapter POSTs to ``https://www.zhihu.com/api/v4/drafts`` with a
JSON body containing ``title`` and ``content`` (HTML).  A valid session
cookie must be provided.

On success the API returns JSON with an ``id`` field identifying the
newly created draft.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from structlog import get_logger

from automedia.adapters.base import PublishResult, BasePlatformAdapter
from automedia.core.credential_loader import load_credential_or_env

log = get_logger(__name__)

# httpx is an optional dependency; fall back gracefully when unavailable
try:
    import httpx as _httpx

    _HAS_HTTPX = True
except ImportError:  # pragma: no cover
    from automedia.core._import_helpers import warn_missing_optional

    warn_missing_optional("httpx", feature="Zhihu publishing disabled")
    _HAS_HTTPX = False

# ---------------------------------------------------------------------------
# Zhihu API endpoint
# ---------------------------------------------------------------------------
ZHIHU_DRAFT_URL = "https://www.zhihu.com/api/v4/drafts"


class ZhihuPublisher(BasePlatformAdapter):
    """Publish an article as a draft on Zhihu (知乎).

    Authentication is handled via a session cookie stored in the
    ``ZHIHU_COOKIE`` environment variable.

    The adapter reads article content from the artifact directory
    (``<artifact_dir>/drafts/*.html`` or ``*.md``), constructs a
    JSON payload, and POSTs it to the Zhihu draft API.
    """

    @property
    def platform_name(self) -> str:
        return "zhihu"

    @property
    def enabled(self) -> bool:
        """Only enabled when Zhihu credentials are available."""
        return bool(load_credential_or_env("ZHIHU_COOKIE", "zhihu_cookie"))

    def validate(self, artifact_dir: str) -> bool:
        """Check that Zhihu credentials are non-empty."""
        _ = artifact_dir
        cookie = load_credential_or_env("ZHIHU_COOKIE", "zhihu_cookie")
        if not cookie:
            log.warning("zhihu.validate.missing_cookie")
            return False
        return True

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------
    def publish(self, artifact_dir: str, project: dict[str, Any]) -> PublishResult:
        """POST article content to the Zhihu draft API.

        Returns
        -------
        dict
            ``{"status": "ok", "platform": "zhihu", "draft_id": …}``
            on success, or ``{"status": "error", "platform": "zhihu",
            "reason": …}`` on failure.
        """
        # --- pre-flight: cookie -------------------------------------------------
        cookie = load_credential_or_env("ZHIHU_COOKIE", "zhihu_cookie")
        if not cookie:
            log.warning("zhihu.publish.missing_cookie")
            return {
                "status": "error",
                "platform": "zhihu",
                "reason": "ZHIHU_COOKIE is not set",
            }

        # --- pre-flight: httpx --------------------------------------------------
        if not _HAS_HTTPX:
            log.error("zhihu.publish.httpx_not_available")
            return {
                "status": "error",
                "platform": "zhihu",
                "reason": "httpx is not available",
            }

        # --- read content -------------------------------------------------------
        content_result = self._read_content(artifact_dir, project)
        if content_result["status"] == "error":
            return {
                "status": "error",
                "platform": "zhihu",
                "reason": content_result["reason"],
            }

        title = content_result["title"]
        body_html = content_result["body_html"]

        # --- build request ------------------------------------------------------
        headers = {
            "Cookie": cookie,
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.zhihu.com/",
            "Origin": "https://www.zhihu.com",
            "x-requested-with": "XMLHttpRequest",
        }
        payload = {
            "title": title,
            "content": body_html,
        }

        # --- POST ---------------------------------------------------------------
        try:
            resp = _httpx.post(
                ZHIHU_DRAFT_URL,
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
                err_msg = err_detail.get("message", err_detail.get("error", str(exc)))
            except (json.JSONDecodeError, ValueError):
                err_msg = str(exc)
            log.error(
                "zhihu.publish.http_error",
                status_code=status_code,
                error=err_msg,
            )
            return {
                "status": "error",
                "platform": "zhihu",
                "reason": f"draft creation failed (HTTP {status_code}): {err_msg}",
            }
        except _httpx.RequestError as exc:
            log.error("zhihu.publish.connection_error", error=str(exc))
            return {
                "status": "error",
                "platform": "zhihu",
                "reason": f"draft creation failed: {exc}",
            }

        # --- parse response -----------------------------------------------------
        draft_id = data.get("id")
        if not draft_id:
            log.error(
                "zhihu.publish.missing_draft_id",
                response=data,
            )
            return {
                "status": "error",
                "platform": "zhihu",
                "reason": f"unexpected API response: no 'id' field in {data}",
            }

        log.info(
            "zhihu.publish.success",
            draft_id=draft_id,
            title=title,
        )
        return {
            "status": "ok",
            "platform": "zhihu",
            "draft_id": str(draft_id),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _read_content(
        artifact_dir: str, project: dict[str, Any]
    ) -> dict[str, Any]:
        """Read article title and body from the artifact directory.

        Title resolution order (first non-empty wins):
        1. ``project["title"]``
        2. ``project["topic"]``
        3. ``"Untitled"``

        Body resolution order:
        1. ``<artifact_dir>/drafts/*.html`` (first file)
        2. ``<artifact_dir>/drafts/*.md`` (first file)
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
        body_text = ""

        if drafts_dir.is_dir():
            html_files = sorted(drafts_dir.glob("*.html"))
            if html_files:
                body_html = html_files[0].read_text(encoding="utf-8")
                log.info("zhihu.read_content", source=str(html_files[0]))
            else:
                md_files = sorted(drafts_dir.glob("*.md"))
                if md_files:
                    md_content = md_files[0].read_text(encoding="utf-8")
                    log.info("zhihu.read_content", source=str(md_files[0]))
                    body_html = md_content  # Zhihu supports markdown content
                    body_text = md_content
                else:
                    txt_files = sorted(drafts_dir.glob("*.txt"))
                    if txt_files:
                        body_text = txt_files[0].read_text(encoding="utf-8")
                        log.info("zhihu.read_content", source=str(txt_files[0]))

        if not body_html and not body_text:
            log.warning("zhihu.content.empty", artifact_dir=artifact_dir)
            body_html = f"<p>{title}</p>"

        return {
            "status": "ok",
            "title": title,
            "body_html": body_html or body_text,
        }
