"""YouTube publisher adapter — video upload via YouTube Data API v3.

Uses the YouTube Data API v3 resumable upload protocol for video
upload and publishing.  Requires ``httpx`` (optional dependency).

OAuth2 authentication (refresh token flow)
------------------------------------------
The adapter supports two authentication modes (in priority order):

1. **Access token** — a pre-obtained ``access_token`` passed directly.
2. **Refresh token** — ``client_id`` + ``client_secret`` + ``refresh_token``
   to obtain a fresh access token via ``oauth2.googleapis.com/token``.

Credentials are resolved via :func:`load_credential` which checks the
standard ``AUTOMEDIA_*`` environment variables:

- ``AUTOMEDIA_YOUTUBE_CLIENT_ID`` — OAuth2 client ID
- ``AUTOMEDIA_YOUTUBE_CLIENT_SECRET`` — OAuth2 client secret
- ``AUTOMEDIA_YOUTUBE_REFRESH_TOKEN`` — OAuth2 refresh token
- ``AUTOMEDIA_YOUTUBE_ACCESS_TOKEN`` — pre-obtained access token (optional)

These can also be stored in ``~/.automedia/oscreds.yaml`` via credential_loader.

Upload flow
-----------
1. Obtain an OAuth2 access token (from direct token or refresh exchange).
2. Read video metadata from the project dict and artifact info file.
3. Find the first video file under ``<artifact_dir>/03_video/``.
4. Initiate a resumable upload session with the YouTube API.
5. Upload the video binary data to the resumable session URI.
6. Return the published video URL.
"""

from __future__ import annotations

import json
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

    warn_missing_optional("httpx", feature="YouTube publishing disabled")
    _HAS_HTTPX = False

# ---------------------------------------------------------------------------
# YouTube API endpoints (module-level constants)
# ---------------------------------------------------------------------------
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
YOUTUBE_UPLOAD_BASE = "https://www.googleapis.com/upload/youtube/v3"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"

# Video file extensions supported for upload (in priority order)
_VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg", ".flv", ".wmv",
})


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------


def _load_youtube_credentials() -> dict[str, str]:
    """Load YouTube OAuth2 credentials via credential_loader.

    Returns a dict with keys ``client_id``, ``client_secret``,
    ``refresh_token``, and/or ``access_token`` depending on what was
    found.  An empty dict is returned when nothing is configured.
    """
    creds: dict[str, str] = {}

    client_id = load_credential("youtube_client_id")
    if client_id:
        creds["client_id"] = client_id

    client_secret = load_credential("youtube_client_secret")
    if client_secret:
        creds["client_secret"] = client_secret

    refresh_token = load_credential("youtube_refresh_token")
    if refresh_token:
        creds["refresh_token"] = refresh_token

    access_token = load_credential("youtube_access_token")
    if access_token:
        creds["access_token"] = access_token

    return creds


# ---------------------------------------------------------------------------
# YouTubePublisher
# ---------------------------------------------------------------------------


class YouTubePublisher(BasePlatformAdapter):
    """Publish a video to YouTube via the YouTube Data API v3.

    The publish flow consists of four steps:

    1. **Obtain access token** — exchange ``refresh_token`` for a fresh
       ``access_token`` at ``oauth2.googleapis.com/token``, or use a
       pre-obtained access token directly.
    2. **Read metadata** — extract title, description, and tags from the
       project dict and the artifact info file.
    3. **Find video file** — locate the first video file under the
       ``<artifact_dir>/03_video/`` directory.
    4. **Resumable upload** — initiate a resumable upload session with
       the YouTube API, then upload the binary video data.
    """

    @property
    def platform_name(self) -> str:
        """Return the platform identifier ``\"youtube\"``."""
        return "youtube"

    @property
    def enabled(self) -> bool:
        """Check whether YouTube OAuth2 credentials are configured."""
        creds = _load_youtube_credentials()
        return bool(creds)

    def validate(self, artifact_dir: str) -> bool:
        """Validate that YouTube publish credentials are present and usable.

        Args:
            artifact_dir: Project artifacts directory (unused in this check).

        Returns:
            ``True`` when at least one credential source is configured.
        """
        _ = artifact_dir
        creds = _load_youtube_credentials()
        if not creds:
            log.warning("youtube.validate.failed")
            return False
        return True

    # ------------------------------------------------------------------
    # publish — full four-step flow
    # ------------------------------------------------------------------

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        """Publish a project video to YouTube.

        Parameters
        ----------
        artifact_dir:
            Path to the rendered artifact directory.  The method looks
            for video files under ``<artifact_dir>/03_video/``.
        project:
            Full project dict.  ``project["title"]`` or
            ``project["topic"]`` is used for the video title.
        draft_only:
            When ``True``, upload the video as **unlisted** (private)
            instead of public.  The returned ``status`` will be
            ``"draft_created"`` with a ``url``.

        Returns
        -------
        dict
            ``{"status": "ok", "platform": "youtube", "video_id": …,
            "url": …}`` on success, or ``{"status": "error",
            "platform": "youtube", "reason": …}`` on failure.
            When ``draft_only=True`` returns ``{"status": "draft_created",
            "platform": "youtube", "video_id": …, "url": …}``.
        """
        # --- pre-flight: credentials -------------------------------------------
        creds = _load_youtube_credentials()
        if not creds:
            return {
                "status": "error",
                "platform": "youtube",
                "reason": (
                    "YouTube credentials not configured — set "
                    "AUTOMEDIA_YOUTUBE_CLIENT_ID, "
                    "AUTOMEDIA_YOUTUBE_CLIENT_SECRET, and "
                    "AUTOMEDIA_YOUTUBE_REFRESH_TOKEN"
                ),
            }

        # --- pre-flight: httpx --------------------------------------------------
        if not _HAS_HTTPX:
            log.error("youtube.httpx.not_available")
            return {
                "status": "error",
                "platform": "youtube",
                "reason": "httpx is not installed",
            }

        # 1. Get access token
        token_result = self._get_access_token(creds)
        if token_result.get("status") != "ok":
            return token_result
        access_token: str = token_result["access_token"]

        # 2. Read video metadata from project & artifact info
        title, description, tags, privacy = self._read_metadata(
            artifact_dir, project,
        )

        # 3. Find video file
        video_path = self._find_video(artifact_dir)
        if not video_path:
            return {
                "status": "error",
                "platform": "youtube",
                "reason": (
                    f"No video file found in {artifact_dir}/03_video/ "
                    f"(supported: {', '.join(sorted(_VIDEO_EXTENSIONS))})"
                ),
            }

        # 4. Upload video
        upload_result = self._upload_video(
            access_token=access_token,
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status="private" if draft_only else privacy,
        )
        if upload_result.get("status") != "ok":
            return upload_result

        video_id = upload_result.get("video_id", "")
        video_url = (
            f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
        )

        if draft_only:
            log.info(
                "youtube.draft_created",
                video_id=video_id,
                url=video_url,
            )
            return {
                "status": "draft_created",
                "platform": "youtube",
                "video_id": video_id,
                "url": video_url,
            }

        log.info(
            "youtube.publish.success",
            video_id=video_id,
            url=video_url,
        )
        return {
            "status": "ok",
            "platform": "youtube",
            "video_id": video_id,
            "url": video_url,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_access_token(self, creds: dict[str, str]) -> PublishResult:
        """Obtain an OAuth2 access token.

        Priority:
        1. Direct ``access_token`` from credentials (no exchange needed).
        2. Refresh token exchange for a fresh access token.
        """
        # Direct access token — no exchange needed.
        if "access_token" in creds:
            return {"status": "ok", "access_token": creds["access_token"]}

        # Refresh token flow.
        client_id = creds.get("client_id", "")
        client_secret = creds.get("client_secret", "")
        refresh_token = creds.get("refresh_token", "")

        if not client_id or not client_secret or not refresh_token:
            log.error(
                "youtube.token.missing_credentials",
                has_client_id=bool(client_id),
                has_client_secret=bool(client_secret),
                has_refresh_token=bool(refresh_token),
            )
            return {
                "status": "error",
                "platform": "youtube",
                "reason": (
                    "YouTube OAuth2 credentials incomplete — need "
                    "client_id, client_secret, and refresh_token "
                    "(or provide a pre-obtained access_token)"
                ),
            }

        try:
            resp = _httpx.post(
                YOUTUBE_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except _httpx.HTTPStatusError as exc:
            log.error(
                "youtube.token.http_error",
                status_code=exc.response.status_code,
            )
            return {
                "status": "error",
                "platform": "youtube",
                "reason": (
                    f"token refresh failed (HTTP {exc.response.status_code})"
                ),
            }
        except _httpx.RequestError as exc:
            log.error("youtube.token.connection_error", error=str(exc))
            return {
                "status": "error",
                "platform": "youtube",
                "reason": f"token refresh failed: {type(exc).__name__}",
            }

        access_token = data.get("access_token")
        if not access_token:
            log.error("youtube.token.response_no_token")
            return {
                "status": "error",
                "platform": "youtube",
                "reason": "token refresh response did not contain access_token",
            }

        return {"status": "ok", "access_token": access_token}

    def _read_metadata(
        self,
        artifact_dir: str,
        project: dict[str, Any],
    ) -> tuple[str, str, list[str], str]:
        """Read video metadata from project and artifact info files.

        Returns
        -------
        tuple of (title, description, tags, privacy_status)
        """
        title = str(project.get("title") or project.get("topic") or "Untitled")
        description = str(project.get("description") or "")
        raw_tags = project.get("tags", [])
        privacy_status = "private"

        # Try to get richer metadata from project info file.
        info_file = Path(artifact_dir) / "00_project_info.json"
        if info_file.exists():
            try:
                info: dict[str, Any] = json.loads(
                    info_file.read_text(encoding="utf-8"),
                )
                title = str(
                    info.get("title") or info.get("topic") or title
                )
                description = str(
                    info.get("description")
                    or info.get("summary")
                    or description
                )
                if "tags" in info:
                    raw_tags = info["tags"]
            except (json.JSONDecodeError, OSError):
                pass

        # Normalize tags.
        if isinstance(raw_tags, str):
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        elif isinstance(raw_tags, list):
            tags = [str(t).strip() for t in raw_tags if t]
        else:
            tags = []

        return title, description, tags, privacy_status

    def _find_video(self, artifact_dir: str) -> str | None:
        """Find the first video file in the artifact directory.

        Checks the following locations in order:
        1. ``<artifact_dir>/03_video/``
        2. ``<artifact_dir>/video/``
        3. ``<artifact_dir>/`` (root)

        Returns the absolute path as a string, or ``None`` if no video
        file is found.
        """
        base = Path(artifact_dir)

        # Directories to search, in priority order.
        search_dirs: list[Path] = [
            base / "03_video",
            base / "video",
            base,
        ]

        for search_dir in search_dirs:
            if not search_dir.is_dir():
                continue
            for ext in sorted(_VIDEO_EXTENSIONS, reverse=True):
                # Sort to get a deterministic first file.
                files = sorted(search_dir.glob(f"*{ext}"))
                if files:
                    log.info(
                        "youtube.find_video",
                        source=str(files[0]),
                    )
                    return str(files[0])

        log.warning("youtube.video.not_found", artifact_dir=artifact_dir)
        return None

    def _upload_video(
        self,
        access_token: str,
        video_path: str,
        title: str,
        description: str,
        tags: list[str],
        privacy_status: str = "private",
    ) -> PublishResult:
        """Upload a video using the YouTube resumable upload protocol.

        The resumable upload protocol consists of two requests:

        1. **Initiate** — ``POST …/upload/youtube/v3/videos`` with
           ``uploadType=resumable`` and video metadata in the JSON body.
           The response includes a ``Location`` header pointing to the
           resumable session URI.
        2. **Upload** — ``PUT <session_uri>`` with the raw video binary
           data and ``Content-Type: video/*``.
        """
        video_file = Path(video_path)
        if not video_file.is_file():
            return {
                "status": "error",
                "platform": "youtube",
                "reason": f"Video file not found: {video_path}",
            }

        file_size = video_file.stat().st_size

        # ---- Step 1: Initiate resumable upload session ------------------------
        init_url = (
            f"{YOUTUBE_UPLOAD_BASE}/videos"
            f"?uploadType=resumable&part=snippet,status"
        )
        init_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(file_size),
            "X-Upload-Content-Type": "video/*",
        }
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        try:
            init_resp = _httpx.post(
                init_url,
                headers=init_headers,
                json=body,
                timeout=30,
            )
            init_resp.raise_for_status()
        except _httpx.HTTPStatusError as exc:
            log.error(
                "youtube.upload.init.http_error",
                status_code=exc.response.status_code,
            )
            return {
                "status": "error",
                "platform": "youtube",
                "reason": (
                    f"upload initiation failed "
                    f"(HTTP {exc.response.status_code})"
                ),
            }
        except _httpx.RequestError as exc:
            log.error(
                "youtube.upload.init.connection_error",
                error=str(exc),
            )
            return {
                "status": "error",
                "platform": "youtube",
                "reason": (
                    f"upload initiation failed: {type(exc).__name__}"
                ),
            }

        # Get the resumable session URI from the Location header.
        session_uri: str | None = init_resp.headers.get("Location")
        if not session_uri:
            log.error("youtube.upload.no_location_header")
            return {
                "status": "error",
                "platform": "youtube",
                "reason": "upload initiation response missing Location header",
            }

        # ---- Step 2: Upload video binary --------------------------------------
        upload_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "video/*",
            "Content-Length": str(file_size),
        }

        try:
            with open(video_path, "rb") as fh:
                upload_resp = _httpx.put(
                    session_uri,
                    headers=upload_headers,
                    content=fh,
                    timeout=600,  # 10 minutes for large video uploads
                )
            upload_resp.raise_for_status()
        except _httpx.HTTPStatusError as exc:
            log.error(
                "youtube.upload.http_error",
                status_code=exc.response.status_code,
            )
            return {
                "status": "error",
                "platform": "youtube",
                "reason": (
                    f"video upload failed "
                    f"(HTTP {exc.response.status_code})"
                ),
            }
        except _httpx.RequestError as exc:
            log.error(
                "youtube.upload.connection_error",
                error=str(exc),
            )
            return {
                "status": "error",
                "platform": "youtube",
                "reason": (
                    f"video upload failed: {type(exc).__name__}"
                ),
            }

        # Parse the response for the video ID.
        try:
            result: dict[str, Any] = upload_resp.json()
        except json.JSONDecodeError:
            log.error("youtube.upload.invalid_response")
            return {
                "status": "error",
                "platform": "youtube",
                "reason": "upload response was not valid JSON",
            }

        video_id: str | None = result.get("id")
        if not video_id:
            log.error("youtube.upload.no_video_id", response=result)
            return {
                "status": "error",
                "platform": "youtube",
                "reason": "upload response did not contain video ID",
            }

        log.info(
            "youtube.upload.complete",
            video_id=video_id,
            file_size=file_size,
        )
        return {
            "status": "ok",
            "video_id": video_id,
        }
