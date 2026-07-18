"""Tests for verify_md5 integration in runner resume logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from automedia.hooks.md5_tracker import record_md5
from automedia.pipelines.runner import _verify_resume_integrity


class TestVerifyResumeIntegrity:
    """_verify_resume_integrity must detect tampered assets during resume."""

    def test_all_gates_pass_verification(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When all prior gates' MD5s match, no warnings."""
        # Record some gates
        for name in ["CW", "G0", "G1"]:
            f = tmp_path / f"{name}_output.txt"
            f.write_text(f"content from {name}")
            record_md5(str(tmp_path), name, str(f))

        _verify_resume_integrity(str(tmp_path), "G2", ["CW", "G0", "G1", "G2", "G3"])

        # No warnings for intact gates
        assert not any("md5 mismatch" in r.getMessage().lower() for r in caplog.records)

    def test_tampered_gate_triggers_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When a prior gate's file has been modified, a warning is logged."""
        # Record G0
        f = tmp_path / "G0_output.txt"
        f.write_text("original content")
        record_md5(str(tmp_path), "G0", str(f))

        # Tamper with it
        f.write_text("tampered content")

        _verify_resume_integrity(str(tmp_path), "G1", ["CW", "G0", "G1"])

        warnings = [r for r in caplog.records if "mismatch" in r.getMessage().lower()]
        assert len(warnings) >= 1
        assert "G0" in warnings[0].getMessage()

    def test_missing_file_triggers_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When a prior gate's recorded file no longer exists, a warning is logged."""
        f = tmp_path / "CW_output.txt"
        f.write_text("content")
        record_md5(str(tmp_path), "CW", str(f))

        # Delete the file
        f.unlink()

        _verify_resume_integrity(str(tmp_path), "G0", ["CW", "G0"])

        warnings = [
            r
            for r in caplog.records
            if "mismatch" in r.getMessage().lower() or "missing" in r.getMessage().lower()
        ]
        assert len(warnings) >= 1

    def test_no_previous_records_no_warnings(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When no pipeline_md5.json exists, verification is silently skipped."""
        # No records written yet
        _verify_resume_integrity(str(tmp_path), "CW", ["CW"])
        assert len(caplog.records) == 0

    def test_verify_does_not_check_current_or_future_gates(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Gates at or after the resume point are NOT verified — they haven't run yet in this context."""
        for name in ["CW", "G0"]:
            f = tmp_path / f"{name}_output.txt"
            f.write_text(f"content from {name}")
            record_md5(str(tmp_path), name, str(f))

        # Resume from G0 — only CW should be checked (G0 is the resume point)
        # Tamper with G0 (should be ignored since it's the resume point)
        (tmp_path / "G0_output.txt").write_text("tampered at resume point")

        _verify_resume_integrity(str(tmp_path), "G0", ["CW", "G0"])

        # No warnings (G0 is at resume point, not before it)
        assert not any("mismatch" in r.getMessage().lower() for r in caplog.records)
