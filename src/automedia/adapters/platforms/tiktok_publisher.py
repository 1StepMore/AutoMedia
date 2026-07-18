"""TikTok publisher adapter — video upload via TikTok Content Posting API v2.

Uses the TikTok Content Posting API to upload and publish videos.
Requires ``httpx`` (optional dependency).

Authentication
--------------
The adapter requires an OAuth2 ``access_token`` with the ``video.publish``
scope.  Credentials are resolved via :func:`load_credential` which checks
the standard ``AUTOMEDIA_*`` environment variable:

- ``AUTOMEDIA_TIKTOK_ACCESS_TOKEN`` — the OAuth2 access token

This can also be stored in ``~/.automedia/oscreds.yaml`` via credential_loader.

Upload flow
-----------
1. Obtain an OAuth2 access token (from direct token or credential loader).
2. Read video metadata (title) from the project dict and artifact info file.
3. Find the first video file under ``<artifact_dir>/03_video/``.
4. Upload the video via ``POST /v2/video/upload/`` with multipart form data.
5. Publish the uploaded video via ``POST /v2/video/publish/``.
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

    warn_missing_optional("httpx", feature="TikTok publishing disabled")
    _HAS_HTTPX = False

# ---------------------------------------------------------------------------
# TikTok API endpoints (module-level constants)
# ---------------------------------------------------------------------------
TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"
TIKTOK_UPLOAD_URL = f"{TIKTOK_API_BASE}/video/upload/"
TIKTOK_PUBLISH_URL = f"{TIKTOK_API_BASE}/video/publish/"

# Video file extensions supported for upload (in priority order)
_VIDEO_EXTENSIONS = frozenset(
    {
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".webm",
        ".mpeg",
        ".mpg",
        ".flv",
        ".wmv",
    }
)


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------


def _load_tiktok_credentials() -> dict[str, str]:
    """Load TikTok OAuth2 access token via credential_loader.

    Returns a dict with an ``access_token`` key when found, or an empty
    dict when nothing is configured.
    """
    creds: dict[str, str] = {}

    access_token = load_credential("tiktok_access_token")
    if access_token:
        creds["access_token"] = access_token

    return creds


# ---------------------------------------------------------------------------
# TikTokPublisher
# ---------------------------------------------------------------------------


class TikTokPublisher(BasePlatformAdapter):
    """Publish a video to TikTok via the TikTok Content Posting API v2.

    The publish flow consists of four steps:

    1. **Load access token** — obtain the ``access_token`` from
       credentials (env var / credential_loader).
    2. **Read metadata** — extract title, description, and privacy
       setting from the project dict and artifact info file.
    3. **Find video file** — locate the first video file under the
       ``<artifact_dir>/03_video/`` directory.
    4. **Upload video** — upload the video file via multipart POST to
       the TikTok Content Posting API.
    5. **Publish video** — finalize and publish the uploaded video.
    """

    @property
    def platform_name(self) -> str:
        """Return the platform identifier ``\"tiktok\"``."""
        return "tiktok"

    @property
    def enabled(self) -> bool:
        """Check whether TikTok credentials (access_token) are configured."""
        creds = _load_tiktok_credentials()
        return bool(creds)

    def validate(self, artifact_dir: str) -> bool:
        """Validate that TikTok publish credentials are present and usable.

        Args:
            artifact_dir: Project artifacts directory (unused in this check).

        Returns:
            ``True`` when the access token is available.
        """
        _ = artifact_dir
        creds = _load_tiktok_credentials()
        if not creds:
            log.warning("tiktok.validate.failed")
            return False
        return True

    # ------------------------------------------------------------------
    # publish — full five-step flow
    # ------------------------------------------------------------------

    def publish(
        self,
        artifact_dir: str,
        project: dict[str, Any],
        draft_only: bool = False,
    ) -> PublishResult:
        """Publish a project video to TikTok.

        Parameters
        ----------
        artifact_dir:
            Path to the rendered artifact directory.  The method looks
            for video files under ``<artifact_dir>/03_video/``.
        project:
            Full project dict.  ``project["title"]`` or
            ``project["topic"]`` is used for the video title.
        draft_only:
            When ``True``, upload the video but do **not** submit the
            final publish request.  The returned ``status`` will be
            ``"draft_created"`` with a ``video_id``.

        Returns
        -------
        dict
            ``{"status": "ok", "platform": "tiktok", "video_id": …,
            "url": …}`` on success, or ``{"status": "error",
            "platform": "tiktok", "reason": …}`` on failure.
            When ``draft_only=True`` returns ``{"status": "draft_created",
            "platform": "tiktok", "video_id": …}``.
        """
        # --- pre-flight: credentials -------------------------------------------
        creds = _load_tiktok_credentials()
        if not creds:
            return {
                "status": "error",
                "platform": "tiktok",
                "reason": ("TikTok credentials not configured — set AUTOMEDIA_TIKTOK_ACCESS_TOKEN"),
            }

        access_token: str = creds["access_token"]

        # --- pre-flight: httpx --------------------------------------------------
        if not _HAS_HTTPX:
            log.error("tiktok.httpx.not_available")
            return {
                "status": "error",
                "platform": "tiktok",
                "reason": "httpx is not installed",
            }

        # 1. Read video metadata from project & artifact info
        title, description, privacy_level = self._read_metadata(
            artifact_dir,
            project,
        )

        # 2. Find video file
        video_path = self._find_video(artifact_dir)
        if not video_path:
            return {
                "status": "error",
                "platform": "tiktok",
                "reason": (
                    f"No video file found in {artifact_dir}/03_video/ "
                    f"(supported: {', '.join(sorted(_VIDEO_EXTENSIONS))})"
                ),
            }

        # 3. Upload video
        upload_result = self._upload_video(
            access_token=access_token,
            video_path=video_path,
            title=title,
        )
        if upload_result.get("status") != "ok":
            return upload_result

        video_id: str = upload_result["video_id"]

        # 4. draft_only: skip publish, return upload info
        if draft_only:
            log.info(
                "tiktok.draft_created",
                video_id=video_id,
            )
            return {
                "status": "draft_created",
                "platform": "tiktok",
                "video_id": video_id,
            }

        # 5. Publish video
        publish_result = self._publish_video(
            access_token=access_token,
            video_id=video_id,
            title=title,
            description=description,
            privacy_level=privacy_level,
        )
        if publish_result.get("status") != "ok":
            return publish_result

        video_url = f"https://www.tiktok.com/@i/video/{video_id}"

        log.info(
            "tiktok.publish.success",
            video_id=video_id,
            url=video_url,
        )
        return {
            "status": "ok",
            "platform": "tiktok",
            "video_id": video_id,
            "url": video_url,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_metadata(
        self,
        artifact_dir: str,
        project: dict[str, Any],
    ) -> tuple[str, str, int]:
        """Read video metadata from project and artifact info files.

        Returns
        -------
        tuple of (title, description, privacy_level)
            ``privacy_level`` is 0 (public), 1 (friends only), or 2 (private).
            Defaults to 0.
        """
        title = str(project.get("title") or project.get("topic") or "Untitled")
        description = str(project.get("description") or "")
        privacy_level = 0

        # Try to get richer metadata from project info file.
        info_file = Path(artifact_dir) / "00_project_info.json"
        if info_file.exists():
            try:
                info: dict[str, Any] = json.loads(
                    info_file.read_text(encoding="utf-8"),
                )
                title = str(info.get("title") or info.get("topic") or title)
                description = str(info.get("description") or info.get("summary") or description)
            except (json.JSONDecodeError, OSError):
                pass

        return title, description, privacy_level

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
                        "tiktok.find_video",
                        source=str(files[0]),
                    )
                    return str(files[0])

        log.warning("tiktok.video.not_found", artifact_dir=artifact_dir)
        return None

    def _upload_video(
        self,
        access_token: str,
        video_path: str,
        title: str,
    ) -> PublishResult:
        """Upload a video to TikTok via the Content Posting API.

        Sends a ``POST`` request to ``/v2/video/upload/`` with the video
        file as multipart form data.

        Parameters
        ----------
        access_token:
            OAuth2 access token with ``video.publish`` scope.
        video_path:
            Absolute path to the video file to upload.
        title:
            Video title (used as the post caption).

        Returns
        -------
        dict
            ``{"status": "ok", "video_id": "…"}`` on success, or
            an error dict on failure.
        """
        video_file = Path(video_path)
        if not video_file.is_file():
            return {
                "status": "error",
                "platform": "tiktok",
                "reason": f"Video file not found: {video_path}",
            }

        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        # Use a multipart form upload with the video file.
        try:
            with open(video_path, "rb") as fh:
                resp = _httpx.post(
                    TIKTOK_UPLOAD_URL,
                    headers=headers,
                    files={"video": (video_file.name, fh, "video/mp4")},
                    data={"title": title},
                    timeout=600,  # 10 minutes for large video uploads
                )
                resp.raise_for_status()
        except _httpx.HTTPStatusError as exc:
            log.error(
                "tiktok.upload.http_error",
                status_code=exc.response.status_code,
            )
            return {
                "status": "error",
                "platform": "tiktok",
                "reason": (f"video upload failed (HTTP {exc.response.status_code})"),
            }
        except _httpx.RequestError as exc:
            log.error(
                "tiktok.upload.connection_error",
                error=str(exc),
            )
            return {
                "status": "error",
                "platform": "tiktok",
                "reason": (f"video upload failed: {type(exc).__name__}"),
            }

        # Parse the response for the video/upload ID.
        try:
            result: dict[str, Any] = resp.json()
        except json.JSONDecodeError:
            log.error("tiktok.upload.invalid_response")
            return {
                "status": "error",
                "platform": "tiktok",
                "reason": "upload response was not valid JSON",
            }

        # TikTok v2 API wraps data in a ``data`` envelope.
        data: dict[str, Any] = result.get("data") or result

        video_id: str | None = data.get("id")
        if not video_id:
            log.error("tiktok.upload.no_video_id", response=result)
            return {
                "status": "error",
                "platform": "tiktok",
                "reason": (
                    "upload response did not contain video ID: "
                    f"{json.dumps(result, ensure_ascii=False)}"
                ),
            }

        log.info(
            "tiktok.upload.complete",
            video_id=video_id,
            video_path=video_path,
        )
        return {
            "status": "ok",
            "video_id": video_id,
        }

    def _publish_video(
        self,
        access_token: str,
        video_id: str,
        title: str,
        description: str,
        privacy_level: int = 0,
    ) -> PublishResult:
        """Publish an uploaded video on TikTok.

        Sends a ``POST`` request to ``/v2/video/publish/`` to finalize
        and make the video visible.

        Parameters
        ----------
        access_token:
            OAuth2 access token with ``video.publish`` scope.
        video_id:
            The video ID returned from the upload step.
        title:
            Video title (caption).
        description:
            Video description text.
        privacy_level:
            Privacy level: 0 (public), 1 (friends only), 2 (private).

        Returns
        -------
        dict
            ``{"status": "ok"}`` on success, or an error dict on failure.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

        payload: dict[str, Any] = {
            "post_info": {
                "title": title,
                "privacy_level": privacy_level,
            },
            "source_info": {
                "source": "PULL_FROM_URL",
                "video_id": video_id,
            },
        }

        if description:
            payload["post_info"]["description"] = description

        try:
            resp = _httpx.post(
                TIKTOK_PUBLISH_URL,
                headers=headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
        except _httpx.HTTPStatusError as exc:
            log.error(
                "tiktok.publish.http_error",
                status_code=exc.response.status_code,
            )
            return {
                "status": "error",
                "platform": "tiktok",
                "reason": (f"video publish failed (HTTP {exc.response.status_code})"),
            }
        except _httpx.RequestError as exc:
            log.error(
                "tiktok.publish.connection_error",
                error=str(exc),
            )
            return {
                "status": "error",
                "platform": "tiktok",
                "reason": (f"video publish failed: {type(exc).__name__}"),
            }

        try:
            result: dict[str, Any] = resp.json()
        except json.JSONDecodeError:
            log.error("tiktok.publish.invalid_response")
            return {
                "status": "error",
                "platform": "tiktok",
                "reason": "publish response was not valid JSON",
            }

        # TikTok v2 API wraps data in a ``data`` envelope.
        data: dict[str, Any] = result.get("data") or result
        error_code = data.get("error_code")

        # error_code 0 means success in TikTok's API.
        if error_code is not None and error_code != 0:
            error_msg = data.get("error_message", "unknown error")
            log.error(
                "tiktok.publish.api_error",
                error_code=error_code,
                error_message=error_msg,
            )
            return {
                "status": "error",
                "platform": "tiktok",
                "reason": (f"publish API error ({error_code}): {error_msg}"),
            }

        log.info(
            "tiktok.publish.complete",
            video_id=video_id,
        )
        return {"status": "ok"}
