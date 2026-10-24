"""V7 integrity records must not self-verify (issue #270)."""

from __future__ import annotations

from pathlib import Path

from automedia.core.md5_tracker import compute_md5
from automedia.pipelines.runner import _expected_md5_records


def test_records_only_expected(tmp_path: Path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"payload")
    assert _expected_md5_records([str(path)]) == {str(path): {"expected": compute_md5(str(path))}}
