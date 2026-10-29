"""MD5 tracker for pipeline gates — record and verify file integrity."""

import contextlib
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from structlog import get_logger

from automedia.core.hashing import compute_md5

log = get_logger(__name__)

PIPELINE_MD5_FILENAME = "pipeline_md5.json"


def write_json_atomic(path: str | Path, data: dict[str, Any]) -> None:
    """Write *data* to *path* as UTF-8 JSON, atomically (tmp file + os.replace).

    Shared primitive for every ``pipeline_md5.json`` writer (this module and
    ``omni.md5_integration``).  Encoding is pinned to UTF-8 so non-ASCII
    project paths never depend on the platform locale, and the tmp+replace
    swap means a crash mid-write can never leave a truncated state file
    behind.  The tmp name carries the pid and thread id so concurrent
    writers cannot collide on the same temp file.
    """
    path = str(path)
    tmp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise


def _md5_path(project_dir: str) -> str:
    """Return absolute path to pipeline_md5.json under *project_dir*."""
    return os.path.join(project_dir, PIPELINE_MD5_FILENAME)


def get_pipeline_md5(project_dir: str) -> dict[str, Any]:
    """Read the entire pipeline_md5.json as a dict.

    Returns ``{}`` if the file does not exist.
    """
    path = _md5_path(project_dir)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def record_md5(project_dir: str, gate_name: str, file_path: str) -> str:
    """Compute MD5 of *file_path* and record it under *gate_name*.

    The result is stored in ``{project_dir}/pipeline_md5.json`` under the
    top-level ``"gates"`` key.  If the file does not exist it is created.

    Returns the MD5 hex digest.
    """
    md5_digest = compute_md5(file_path)
    now = datetime.now(UTC).isoformat()

    data = get_pipeline_md5(project_dir)
    data.setdefault("gates", {})[gate_name] = {
        "file_path": os.path.abspath(file_path),
        "md5": md5_digest,
        "recorded_at": now,
    }

    write_json_atomic(_md5_path(project_dir), data)

    return md5_digest


def verify_md5(project_dir: str, gate_name: str, file_path: str) -> bool:
    """Verify that *file_path* matches the recorded MD5 for *gate_name*.

    Returns ``True`` if the current MD5 of *file_path* equals the recorded
    value, ``False`` otherwise (including when the gate has no record).
    """
    data = get_pipeline_md5(project_dir)
    gates: dict[str, Any] = data.get("gates", {})
    record = gates.get(gate_name)
    if record is None:
        return False
    current_md5 = compute_md5(file_path)
    return current_md5 == record["md5"]
