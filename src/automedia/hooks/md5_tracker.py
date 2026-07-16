"""MD5 tracker for pipeline gates — record and verify file integrity."""

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

from structlog import get_logger

log = get_logger(__name__)

PIPELINE_MD5_FILENAME = "pipeline_md5.json"


def _md5_path(project_dir: str) -> str:
    """Return absolute path to pipeline_md5.json under *project_dir*."""
    return os.path.join(project_dir, PIPELINE_MD5_FILENAME)


def _compute_md5(file_path: str) -> str:
    """Compute MD5 hex digest of *file_path*."""
    h = hashlib.md5()  # noqa: S324 — integrity checksum
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def get_pipeline_md5(project_dir: str) -> dict[str, Any]:
    """Read the entire pipeline_md5.json as a dict.

    Returns ``{}`` if the file does not exist.
    """
    path = _md5_path(project_dir)
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return json.load(f)


def record_md5(project_dir: str, gate_name: str, file_path: str) -> str:
    """Compute MD5 of *file_path* and record it under *gate_name*.

    The result is stored in ``{project_dir}/pipeline_md5.json`` under the
    top-level ``"gates"`` key.  If the file does not exist it is created.

    Returns the MD5 hex digest.
    """
    md5_digest = _compute_md5(file_path)
    now = datetime.now(UTC).isoformat()

    data = get_pipeline_md5(project_dir)
    data.setdefault("gates", {})[gate_name] = {
        "file_path": os.path.abspath(file_path),
        "md5": md5_digest,
        "recorded_at": now,
    }

    path = _md5_path(project_dir)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

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
    current_md5 = _compute_md5(file_path)
    return current_md5 == record["md5"]
