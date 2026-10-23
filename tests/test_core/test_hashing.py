"""The single MD5 helper shared across subsystems (issue #277)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from automedia.core.hashing import compute_md5, compute_md5_bytes


def test_compute_md5_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "data.bin"
    payload = b"\x00\x01hello\xff"
    path.write_bytes(payload)
    assert compute_md5(path) == hashlib.md5(payload, usedforsecurity=False).hexdigest()


def test_compute_md5_accepts_str_and_path(tmp_path: Path) -> None:
    path = tmp_path / "data.txt"
    path.write_text("hello world", encoding="utf-8")
    assert compute_md5(str(path)) == "5eb63bbbe01eeed093cb22bb8f5acdc3"
    assert compute_md5(path) == "5eb63bbbe01eeed093cb22bb8f5acdc3"


def test_compute_md5_bytes() -> None:
    assert compute_md5_bytes(b"hello world") == "5eb63bbbe01eeed093cb22bb8f5acdc3"


def test_compute_md5_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compute_md5(tmp_path / "missing.bin")
