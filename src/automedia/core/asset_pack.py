"""Best-effort bootstrap of a project's standard video asset pack.

Copies the AssetLibrary's ``video-core`` preset into a freshly created project
and records what was pulled.  Every failure path is a warning: creating a
project must never depend on the asset library being present.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from automedia.core.env_overlay import env_lookup

log = logging.getLogger(__name__)

# Zero-config fallback for the workspace this integration was built for.  Other
# hosts should set ``AUTOMEDIA_ASSET_LIBRARY``; a missing path is non-fatal and
# only skips the pull.
DEFAULT_LIBRARY = Path("/mnt/d/Hermes-Workspace/01-Projects/AutoMedia/AssetLibrary")
_SOURCE_FILENAME = "_source.json"
_RECORD_FILENAME = "_pull_record.json"
_SKIP_VALUES = {"1", "true", "yes"}


def _skip_requested() -> bool:
    value = env_lookup("AUTOMEDIA_SKIP_ASSET_PULL", "")
    return (value or "").strip().lower() in _SKIP_VALUES


def _resolve_library(library_dir: str | Path | None) -> Path:
    if library_dir is not None:
        raw = str(library_dir)
    else:
        raw = env_lookup("AUTOMEDIA_ASSET_LIBRARY", "") or str(DEFAULT_LIBRARY)
    return Path(raw).expanduser().resolve()


def _source_entries(data: object) -> list[dict[str, object]]:
    """Extract the file list from either supported ``_source.json`` shape."""
    if not isinstance(data, dict):
        return []
    files = data.get("files")
    if isinstance(files, list):
        return [item for item in files if isinstance(item, dict)]
    pulls = data.get("pulls")
    if isinstance(pulls, list) and pulls:
        last = pulls[-1]
        if isinstance(last, dict) and isinstance(last.get("files"), list):
            return [item for item in last["files"] if isinstance(item, dict)]
    return []


def _discard_partial_pull(assets: Path, *, existed: bool) -> None:
    """Remove a half-copied pack so the next init retries instead of skipping.

    The pull only runs when ``assets/`` is absent or empty, so anything found
    there after a failure belongs to the failed attempt.
    """
    if not assets.exists():
        return
    try:
        shutil.rmtree(assets)
        if existed:
            assets.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("Could not discard partial asset pull at %s: %s", assets, exc)


def _manifest_summary(source_path: Path) -> tuple[int, str | None]:
    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not read asset source manifest %s: %s", source_path, exc)
        return 0, None

    entries = _source_entries(data)
    pairs = sorted(
        (str(entry["path"]), str(entry.get("sha256") or entry.get("sha256_16")))
        for entry in entries
        if entry.get("path") and (entry.get("sha256") or entry.get("sha256_16"))
    )
    digest = hashlib.sha256(
        "\n".join(f"{path}:{sha}" for path, sha in pairs).encode("utf-8")
    ).hexdigest()
    return len(entries), digest


def pull_video_assets(
    project_dir: str | Path,
    *,
    library_dir: str | Path | None = None,
    preset: str = "video-core",
) -> dict | None:
    """Copy the asset library's standard pack into *project_dir*.

    Returns the pull record on success, ``None`` when skipped or when any step
    fails.  Never raises.
    """
    if _skip_requested():
        log.info("Asset pull skipped via AUTOMEDIA_SKIP_ASSET_PULL")
        return None

    try:
        library = _resolve_library(library_dir)
        script = library / "_tools" / "pull_assets.py"
        if not library.is_dir():
            log.warning("Asset library not found at %s; skipping asset pull", library)
            return None
        if not script.is_file():
            log.warning("Asset pull script not found at %s; skipping asset pull", script)
            return None

        root = Path(project_dir)
        assets = root / "assets"
        assets_existed = assets.is_dir()
        if assets_existed and any(assets.iterdir()):
            log.info("Assets already present in %s; skipping asset pull", assets)
            return None

        try:
            result = subprocess.run(  # noqa: S603 — interpreter and script paths are trusted
                [
                    sys.executable,
                    str(script),
                    "--project",
                    str(project_dir),
                    "--preset",
                    preset,
                ],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except Exception as exc:
            _discard_partial_pull(assets, existed=assets_existed)
            log.warning("Asset pull raised %s: %s", type(exc).__name__, exc)
            return None
        if result.returncode != 0:
            _discard_partial_pull(assets, existed=assets_existed)
            log.warning(
                "Asset pull failed (exit %s): %s",
                result.returncode,
                (result.stderr or result.stdout or "").strip(),
            )
            return None

        file_count, manifest_digest = _manifest_summary(assets / _SOURCE_FILENAME)
        record = {
            "pulled_at": datetime.now(UTC).isoformat(),
            "library": str(library),
            "preset": preset,
            "file_count": file_count,
            "manifest_digest": manifest_digest,
        }
        (assets / _RECORD_FILENAME).write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        log.info(
            "Pulled %s asset pack (%s files) from %s into %s",
            preset,
            file_count,
            library,
            assets,
        )
        return record
    except Exception as exc:
        log.warning("Asset pull raised %s: %s", type(exc).__name__, exc)
        return None
