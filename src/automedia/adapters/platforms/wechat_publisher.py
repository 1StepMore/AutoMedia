"""WeChat Official Account publisher — real API implementation.

Uses the WeChat Official Account API (token / draft / publish).
Requires ``httpx`` (optional dependency).

Credentials are resolved via :func:`load_credential` with
backward-compatible fallback to legacy ``WX_APPID`` / ``WX_APPSECRET``
environment variables and the standard ``AUTOMEDIA_WECHAT_APPID`` /
``AUTOMEDIA_WECHAT_APPSECRET`` credentials.
"""

from __future__ import annotations

import re
from typing import Any

from structlog import get_logger

from automedia.adapters.base import BasePlatformAdapter
from automedia.core.credential_loader import load_credential

log = get_logger(__name__)

# httpx is an optional dependency — fall back gracefully when unavailable
try:
    import httpx as _httpx

    _HAS_HTTPX = True
except ImportError:  # pragma: no cover
    from automedia.core._import_helpers import warn_missing_optional

    warn_missing_optional("httpx", feature="WeChat publishing disabled")
    _HAS_HTTPX = False

# ---------------------------------------------------------------------------
# WeChat API endpoints (module-level constants)
# ---------------------------------------------------------------------------
WX_API_BASE = "https://api.weixin.qq.com/cgi-bin"
WX_TOKEN_URL = f"{WX_API_BASE}/token"
WX_DRAFT_ADD_URL = f"{WX_API_BASE}/draft/add"
WX_PUBLISH_SUBMIT_URL = f"{WX_API_BASE}/freepublish/submit"

# Regex matching credential-bearing query parameters that must never appear in logs.
_CREDENTIAL_PARAMS = re.compile(
    r"((?:appid|secret|access_token)=)[^&]*", re.IGNORECASE
)


def _sanitize_url(url: str) -> str:
    """Replace credential query-parameter values with ``***``."""
    return _CREDENTIAL_PARAMS.sub(r"\1***", url)


def _load_wx_credentials() -> tuple[str, str]:
    """Load WeChat appid and secret via credential_loader with legacy env fallback."""
    appid = load_credential("wechat_appid")
    if not appid:
        import os

        appid = os.environ.get("WX_APPID", "").strip() or None

    secret = load_credential("wechat_appsecret")
    if not secret:
        import os

        secret = os.environ.get("WX_APPSECRET", "").strip() or None

    return (appid or "", secret or "")


class WechatPublisher(BasePlatformAdapter):
    """Publish article to WeChat Official Account.

    The publish flow consists of three API calls:

    1. **Get access token** — ``POST /token?grant_type=client_credential``
       using ``WX_APPID`` and ``WX_APPSECRET``.
    2. **Create draft** — ``POST /draft/add`` with article title and body.
    3. **Submit for publication** — ``POST /freepublish/submit`` with the
       returned draft id.
    """

    @property
    def platform_name(self) -> str:
        return "wechat"

    @property
    def enabled(self) -> bool:
        appid, secret = _load_wx_credentials()
        return bool(appid) and bool(secret)

    def validate(self, artifact_dir: str) -> bool:
        _ = artifact_dir
        appid, secret = _load_wx_credentials()
        if not appid or not secret:
            log.warning("wechat.validate.failed")
            return False
        return True

    # ------------------------------------------------------------------
    # publish — full three-step flow
    # ------------------------------------------------------------------

    def publish(
        self, artifact_dir: str, project: dict[str, Any]
    ) -> dict[str, Any]:
        """Publish a project article to WeChat Official Account.

        Parameters
        ----------
        artifact_dir:
            Path to the rendered artifact directory.  The method looks
            for content files under ``<artifact_dir>/drafts/`` (``*.html``
            preferred, then ``*.md``).
        project:
            Full project dict.  At a minimum ``project["topic"]`` is used
            for the article title.

        Returns
        -------
        dict
            ``{"status": "ok", "platform": "wechat", "article_id": …,
            "publish_id": …}`` on success, or ``{"status": "error",
            "platform": "wechat", "reason": …}`` on failure.
        """
        # --- pre-flight: credentials -------------------------------------------
        appid, secret = _load_wx_credentials()
        if not appid or not secret:
            return {
                "status": "error",
                "platform": "wechat",
                "reason": (
                    "WeChat credentials not set "
                    "(WX_APPID/WX_APPSECRET or AUTOMEDIA_WECHAT_APPID/"
                    "AUTOMEDIA_WECHAT_APPSECRET)"
                ),
            }

        # --- pre-flight: httpx --------------------------------------------------
        if not _HAS_HTTPX:
            log.error("wechat.httpx.not_available")
            return {
                "status": "error",
                "platform": "wechat",
                "reason": "httpx is not installed",
            }

        # 1. Get access token
        token_result = self._get_access_token(appid, secret)
        if token_result.get("status") != "ok":
            return token_result
        access_token = token_result["access_token"]

        # 2. Read content from artifact directory
        content_result = self._read_content(artifact_dir, project)
        if content_result.get("status") != "ok":
            return content_result
        title = content_result["title"]
        body_html = content_result["body_html"]

        # 3. Create draft
        draft_result = self._create_draft(access_token, title, body_html, project)
        if draft_result.get("status") != "ok":
            return draft_result
        draft_id = draft_result["draft_id"]

        # 4. Submit for publish
        publish_result = self._submit_publish(access_token, draft_id)
        if publish_result.get("status") != "ok":
            return publish_result
        publish_id = publish_result["publish_id"]

        log.info(
            "wechat.publish.success",
            article_id=draft_id,
            publish_id=publish_id,
        )
        return {
            "status": "ok",
            "platform": "wechat",
            "article_id": draft_id,
            "publish_id": publish_id,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_access_token(self, appid: str, secret: str) -> dict[str, Any]:
        """Obtain a WeChat ``access_token`` via client_credential grant."""
        url = (
            f"{WX_TOKEN_URL}?grant_type=client_credential"
            f"&appid={appid}&secret={secret}"
        )
        safe_url = _sanitize_url(url)
        try:
            resp = _httpx.post(url, timeout=10)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except _httpx.HTTPStatusError as exc:
            log.error(
                "wechat.token.http_error", status_code=exc.response.status_code
            )
            return {
                "status": "error",
                "platform": "wechat",
                "reason": f"token request failed (HTTP {exc.response.status_code})",
            }
        except _httpx.RequestError as exc:
            log.error(
                "wechat.token.connection_error",
                error=_sanitize_url(str(exc)),
            )
            return {
                "status": "error",
                "platform": "wechat",
                "reason": f"token request failed ({safe_url}): {type(exc).__name__}",
            }

        if "access_token" not in data:
            err_msg = data.get("errmsg", "unknown error")
            log.error(
                "wechat.token.api_error",
                errcode=data.get("errcode"),
                errmsg=err_msg,
            )
            return {
                "status": "error",
                "platform": "wechat",
                "reason": f"token API error: {err_msg}",
            }

        return {"status": "ok", "access_token": data["access_token"]}

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
        import json
        from pathlib import Path

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
                log.info("wechat.read_content", source=str(html_files[0]))
            else:
                md_files = sorted(drafts_dir.glob("*.md"))
                if md_files:
                    md_content = md_files[0].read_text(encoding="utf-8")
                    log.info("wechat.read_content", source=str(md_files[0]))
                    body_html = _md_to_html(md_content)

        if not body_html:
            log.warning("wechat.content.empty", artifact_dir=artifact_dir)
            body_html = f"<p>{title}</p>"

        return {"status": "ok", "title": title, "body_html": body_html}

    def _create_draft(
        self,
        access_token: str,
        title: str,
        body_html: str,
        project: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a WeChat draft via the ``/cgi-bin/draft/add`` API."""
        article: dict[str, Any] = {
            "title": title,
            "content": body_html,
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }

        author = project.get("brand", "")
        if author:
            article["author"] = author

        url = f"{WX_DRAFT_ADD_URL}?access_token={access_token}"
        safe_url = _sanitize_url(url)
        payload = {"articles": [article]}

        try:
            resp = _httpx.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except _httpx.HTTPStatusError as exc:
            log.error(
                "wechat.draft.http_error", status_code=exc.response.status_code
            )
            return {
                "status": "error",
                "platform": "wechat",
                "reason": f"draft creation failed (HTTP {exc.response.status_code})",
            }
        except _httpx.RequestError as exc:
            log.error(
                "wechat.draft.connection_error",
                error=_sanitize_url(str(exc)),
            )
            return {
                "status": "error",
                "platform": "wechat",
                "reason": f"draft creation failed ({safe_url}): {type(exc).__name__}",
            }

        if "media_id" not in data:
            err_msg = data.get("errmsg", "unknown error")
            log.error(
                "wechat.draft.api_error",
                errcode=data.get("errcode"),
                errmsg=err_msg,
            )
            return {
                "status": "error",
                "platform": "wechat",
                "reason": f"draft API error: {err_msg}",
            }

        log.info("wechat.draft.created", media_id=data["media_id"])
        return {"status": "ok", "draft_id": data["media_id"]}

    def _submit_publish(
        self, access_token: str, draft_id: str
    ) -> dict[str, Any]:
        """Submit a draft for publication via ``/cgi-bin/freepublish/submit``."""
        url = f"{WX_PUBLISH_SUBMIT_URL}?access_token={access_token}"
        safe_url = _sanitize_url(url)
        payload = {"draft_id": draft_id}

        try:
            resp = _httpx.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except _httpx.HTTPStatusError as exc:
            log.error(
                "wechat.publish.http_error", status_code=exc.response.status_code
            )
            return {
                "status": "error",
                "platform": "wechat",
                "reason": f"publish submission failed (HTTP {exc.response.status_code})",
            }
        except _httpx.RequestError as exc:
            log.error(
                "wechat.publish.connection_error",
                error=_sanitize_url(str(exc)),
            )
            return {
                "status": "error",
                "platform": "wechat",
                "reason": f"publish submission failed ({safe_url}): {type(exc).__name__}",
            }

        if "publish_id" not in data:
            err_msg = data.get("errmsg", "unknown error")
            log.error(
                "wechat.publish.api_error",
                errcode=data.get("errcode"),
                errmsg=err_msg,
            )
            return {
                "status": "error",
                "platform": "wechat",
                "reason": f"publish API error: {err_msg}",
            }

        log.info(
            "wechat.publish.submitted",
            publish_id=data["publish_id"],
            draft_id=draft_id,
        )
        return {"status": "ok", "publish_id": data["publish_id"]}


# ======================================================================
# Module-level helpers
# ======================================================================


def _md_to_html(md_content: str) -> str:
    """Convert simple markdown to HTML for WeChat article body.

    Supports headings, paragraphs, bold, italic, inline code, links, images,
    unordered lists, and line breaks.
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
