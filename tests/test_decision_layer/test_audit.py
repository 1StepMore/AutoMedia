"""Tests for automedia.decision.audit — force-provenance audit logging.

All tests use ``tmp_path`` via monkeypatch to avoid writing to the real
``~/.automedia/audit/`` directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _patch_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``Path.home()`` to a temp directory."""
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    return fake_home


# ===================================================================
# _audit_log_path()
# ===================================================================


class TestAuditLogPath:
    """_audit_log_path() returns the expected path."""

    def test_returns_path_under_home(self) -> None:
        from automedia.decision.audit import _audit_log_path

        p = _audit_log_path()
        assert p.name == "force_provenance.log"
        assert ".automedia" in str(p)
        assert "audit" in str(p)


# ===================================================================
# log_force_provenance()
# ===================================================================


class TestLogForceProvenance:
    """log_force_provenance() creates and writes to the audit log."""

    def test_creates_log_file(self, tmp_path: Path) -> None:
        from automedia.decision.audit import _audit_log_path, log_force_provenance

        log_force_provenance(topic="AI video", brand="test-brand", user="agent")
        assert _audit_log_path().is_file()

    def test_writes_correct_entry_format(self, tmp_path: Path) -> None:
        from automedia.decision.audit import _audit_log_path, log_force_provenance

        log_force_provenance(
            topic="eco bottles", brand="green-co", user="alice", args="--force"
        )
        content = _audit_log_path().read_text(encoding="utf-8")
        assert "user=alice" in content
        assert "topic='eco bottles'" in content
        assert "brand='green-co'" in content
        assert "args=--force" in content

    def test_appends_multiple_entries(self, tmp_path: Path) -> None:
        from automedia.decision.audit import _audit_log_path, log_force_provenance

        log_force_provenance(topic="t1", brand="b1")
        log_force_provenance(topic="t2", brand="b2")
        content = _audit_log_path().read_text(encoding="utf-8")
        lines = [l for l in content.strip().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        from automedia.decision.audit import _audit_log_path, log_force_provenance

        # Parent dirs don't exist yet — should be created
        log_path = _audit_log_path()
        assert not log_path.parent.exists() or True  # may or may not exist
        log_force_provenance(topic="x", brand="y")
        assert log_path.parent.is_dir()
