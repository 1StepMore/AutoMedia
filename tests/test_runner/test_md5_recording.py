"""Tests for MD5 recording behavior in runner.py."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from automedia.pipelines.runner import _record_gate_md5s


class TestMd5RecordingErrors:
    """Verify MD5 recording failures produce warnings, not silence."""

    def test_record_md5_oserror_logs_warning(
        self, caplog: pytest.LogCaptureFixture, tmp_path: Path
    ) -> None:
        """When record_md5 raises OSError, a warning must be logged."""
        results = [
            {
                "gate": "G0",
                "output_path": str(tmp_path / "nonexistent" / "file.txt"),
                "passed": True,
            }
        ]
        with caplog.at_level(logging.WARNING, logger="automedia.pipelines.runner"):
            _record_gate_md5s(str(tmp_path), results)

        assert len(caplog.records) >= 1
        assert any(
            "md5" in r.getMessage().lower() or "record" in r.getMessage().lower()
            for r in caplog.records
        )

    def test_record_md5_filenotfound_logs_warning(
        self, caplog: pytest.LogCaptureFixture, tmp_path: Path
    ) -> None:
        """When record_md5 raises FileNotFoundError, a warning must be logged."""
        results = [
            {
                "gate": "G1",
                "output_path": str(tmp_path / "missing.txt"),
                "passed": True,
            }
        ]
        with caplog.at_level(logging.WARNING, logger="automedia.pipelines.runner"):
            _record_gate_md5s(str(tmp_path), results)

        assert len(caplog.records) >= 1
        assert any(
            "md5" in r.getMessage().lower() or "record" in r.getMessage().lower()
            for r in caplog.records
        )

    def test_record_md5_success_no_warning(
        self, caplog: pytest.LogCaptureFixture, tmp_path: Path
    ) -> None:
        """When record_md5 succeeds, no warning should be logged."""
        (tmp_path / "artifact.txt").write_text("valid content")
        results = [
            {
                "gate": "G2",
                "output_path": str(tmp_path / "artifact.txt"),
                "passed": True,
            }
        ]
        with caplog.at_level(logging.WARNING, logger="automedia.pipelines.runner"):
            _record_gate_md5s(str(tmp_path), results)

        md5_warnings = [
            r
            for r in caplog.records
            if "md5" in r.getMessage().lower() or "record" in r.getMessage().lower()
        ]
        assert len(md5_warnings) == 0

    def test_no_results_no_error(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        """Empty results list must not cause any error."""
        _record_gate_md5s(str(tmp_path), [])
        assert len(caplog.records) == 0

    def test_none_output_path_no_error(
        self, caplog: pytest.LogCaptureFixture, tmp_path: Path
    ) -> None:
        """Results without output_path must not cause any error."""
        results = [{"gate": "G3", "passed": True}]
        _record_gate_md5s(str(tmp_path), results)
        assert len(caplog.records) == 0
