"""MD5 helpers shared by the pipeline, Omni, gates, and asset ingestion."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 8192


def compute_md5_bytes(data: bytes) -> str:
    """Return the MD5 hex digest of *data*."""
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def compute_md5(file_path: str | Path) -> str:
    """Return the MD5 hex digest of *file_path*."""
    digest = hashlib.md5(usedforsecurity=False)
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
