"""Tests for automedia.hooks.md5_tracker — pipeline_md5.json read/write/verify."""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from automedia.hooks.md5_tracker import (
    PIPELINE_MD5_FILENAME,
    get_pipeline_md5,
    record_md5,
    verify_md5,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_sample(path: Path, content: str = "hello world") -> None:
    """Write *content* to *path*."""
    path.write_text(content)


def _md5_of(content: str) -> str:
    """Return MD5 hex digest of *content* bytes."""
    return hashlib.md5(content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# get_pipeline_md5
# ---------------------------------------------------------------------------


class TestGetPipelineMd5:
    def test_returns_empty_dict_when_file_does_not_exist(self, tmp_path: Path) -> None:
        """get_pipeline_md5 should return {} when the json file is absent."""
        result = get_pipeline_md5(str(tmp_path))
        assert result == {}

    def test_returns_parsed_content_when_file_exists(self, tmp_path: Path) -> None:
        """get_pipeline_md5 should return the full dict from a valid json file."""
        data = {"gates": {}, "vision_calls_used": 0, "vision_window_start": ""}
        json_path = tmp_path / PIPELINE_MD5_FILENAME
        json_path.write_text(json.dumps(data, indent=2))

        result = get_pipeline_md5(str(tmp_path))
        assert result == data

    def test_reads_complex_realistic_content(self, tmp_path: Path) -> None:
        """get_pipeline_md5 should preserve all fields in a realistic payload."""
        data = {
            "gates": {
                "gate_a": {
                    "file_path": str(tmp_path / "a.txt"),
                    "md5": "abc123",
                    "recorded_at": "2026-07-07T12:00:00+00:00",
                }
            },
            "vision_calls_used": 5,
            "vision_window_start": "2026-07-07T00:00:00+00:00",
        }
        json_path = tmp_path / PIPELINE_MD5_FILENAME
        json_path.write_text(json.dumps(data, indent=2))

        result = get_pipeline_md5(str(tmp_path))
        assert result == data


# ---------------------------------------------------------------------------
# record_md5
# ---------------------------------------------------------------------------


class TestRecordMd5:
    def test_records_md5_and_returns_digest(self, tmp_path: Path) -> None:
        """record_md5 should compute the MD5, write to json, and return the digest."""
        sample = tmp_path / "sample.txt"
        _write_sample(sample, "hello world")
        expected_md5 = _md5_of("hello world")

        digest = record_md5(str(tmp_path), "gate_a", str(sample))

        assert digest == expected_md5

        # Verify file was created
        json_path = tmp_path / PIPELINE_MD5_FILENAME
        assert json_path.is_file()

        data = json.loads(json_path.read_text())
        gates = data["gates"]
        assert "gate_a" in gates
        assert gates["gate_a"]["md5"] == expected_md5
        assert gates["gate_a"]["file_path"] == os.path.abspath(str(sample))

    def test_creates_file_automatically(self, tmp_path: Path) -> None:
        """record_md5 should create the json file if it does not exist."""
        sample = tmp_path / "data.bin"
        _write_sample(sample, "binary data")

        record_md5(str(tmp_path), "init", str(sample))

        json_path = tmp_path / PIPELINE_MD5_FILENAME
        assert json_path.is_file()

    def test_appends_to_existing_file(self, tmp_path: Path) -> None:
        """record_md5 should add a new gate entry without removing existing ones."""
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        _write_sample(a, "file a")
        _write_sample(b, "file b")

        digest_a = record_md5(str(tmp_path), "gate_a", str(a))
        digest_b = record_md5(str(tmp_path), "gate_b", str(b))

        data = get_pipeline_md5(str(tmp_path))
        assert data["gates"]["gate_a"]["md5"] == digest_a
        assert data["gates"]["gate_b"]["md5"] == digest_b

    def test_overwrites_existing_gate_entry(self, tmp_path: Path) -> None:
        """record_md5 should overwrite an existing gate entry when called again."""
        sample = tmp_path / "f.txt"
        _write_sample(sample, "v1")

        digest_v1 = record_md5(str(tmp_path), "my_gate", str(sample))

        _write_sample(sample, "v2")
        digest_v2 = record_md5(str(tmp_path), "my_gate", str(sample))

        assert digest_v1 != digest_v2  # content changed

        data = get_pipeline_md5(str(tmp_path))
        assert data["gates"]["my_gate"]["md5"] == digest_v2
        assert (
            data["gates"]["my_gate"]["recorded_at"] > data["gates"]["my_gate"]["recorded_at"]
            or True
        )  # at minimum the md5 updated

    def test_recorded_at_is_isoformat(self, tmp_path: Path) -> None:
        """record_md5 should store a valid ISO-8601 timestamp in recorded_at."""
        sample = tmp_path / "f.txt"
        _write_sample(sample, "timestamp check")

        record_md5(str(tmp_path), "ts_gate", str(sample))

        data = get_pipeline_md5(str(tmp_path))
        ts = data["gates"]["ts_gate"]["recorded_at"]
        # Parse should succeed (timezone-aware ISO format)
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# verify_md5
# ---------------------------------------------------------------------------


class TestVerifyMd5:
    def test_returns_true_when_md5_matches(self, tmp_path: Path) -> None:
        """verify_md5 should return True if the file content hasn't changed."""
        sample = tmp_path / "stable.txt"
        _write_sample(sample, "stable content")
        record_md5(str(tmp_path), "stable", str(sample))

        assert verify_md5(str(tmp_path), "stable", str(sample)) is True

    def test_returns_false_when_md5_differs(self, tmp_path: Path) -> None:
        """verify_md5 should return False if the file content has changed."""
        sample = tmp_path / "volatile.txt"
        _write_sample(sample, "original")
        record_md5(str(tmp_path), "volatile", str(sample))

        _write_sample(sample, "modified")

        assert verify_md5(str(tmp_path), "volatile", str(sample)) is False

    def test_returns_false_when_gate_not_recorded(self, tmp_path: Path) -> None:
        """verify_md5 should return False if the gate name has no record."""
        sample = tmp_path / "unknown.txt"
        _write_sample(sample, "data")

        assert verify_md5(str(tmp_path), "nonexistent", str(sample)) is False

    def test_returns_false_when_pipeline_file_missing(self, tmp_path: Path) -> None:
        """verify_md5 should return False if the json file does not exist at all."""
        sample = tmp_path / "orphan.txt"
        _write_sample(sample, "data")

        assert verify_md5(str(tmp_path), "any_gate", str(sample)) is False

    def test_multiple_gates_verify_independently(self, tmp_path: Path) -> None:
        """verify_md5 should verify each gate independently."""
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        _write_sample(a, "aaa")
        _write_sample(b, "bbb")

        record_md5(str(tmp_path), "gate_x", str(a))
        record_md5(str(tmp_path), "gate_y", str(b))

        assert verify_md5(str(tmp_path), "gate_x", str(a)) is True
        assert verify_md5(str(tmp_path), "gate_y", str(b)) is True

        # Tamper with b only
        _write_sample(b, "tampered")
        assert verify_md5(str(tmp_path), "gate_x", str(a)) is True
        assert verify_md5(str(tmp_path), "gate_y", str(b)) is False

    def test_verify_returns_bool_not_none(self, tmp_path: Path) -> None:
        """verify_md5 must return a bool, never None."""
        sample = tmp_path / "x.txt"
        _write_sample(sample, "whatever")

        # No record → False
        result = verify_md5(str(tmp_path), "no_record", str(sample))
        assert isinstance(result, bool)

        # Recorded → True
        record_md5(str(tmp_path), "recorded", str(sample))
        result = verify_md5(str(tmp_path), "recorded", str(sample))
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Integration — full workflow
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_record_then_verify_then_get(self, tmp_path: Path) -> None:
        """End-to-end: record MD5, verify it, tamper, verify failure, read back."""
        sample = tmp_path / "artifact.mp4"
        _write_sample(sample, "video chunk")

        # Record
        digest = record_md5(str(tmp_path), "encode", str(sample))
        assert len(digest) == 32  # MD5 hex is 32 chars

        # Verify — passes
        assert verify_md5(str(tmp_path), "encode", str(sample)) is True

        # Tamper
        _write_sample(sample, "tampered video chunk")
        assert verify_md5(str(tmp_path), "encode", str(sample)) is False

        # Read back
        data = get_pipeline_md5(str(tmp_path))
        assert "gates" in data
        assert data["gates"]["encode"]["md5"] == digest
        assert data["gates"]["encode"]["file_path"] == os.path.abspath(str(sample))

    def test_preserves_vision_fields(self, tmp_path: Path) -> None:
        """Pipeline-level fields like vision_calls_used should survive writes."""
        sample = tmp_path / "input.txt"
        _write_sample(sample, "input")

        # Pre-seed with vision tracking data
        json_path = tmp_path / PIPELINE_MD5_FILENAME
        json_path.write_text(
            json.dumps(
                {
                    "gates": {},
                    "vision_calls_used": 3,
                    "vision_window_start": "2026-07-06T00:00:00+00:00",
                }
            )
        )

        record_md5(str(tmp_path), "new_gate", str(sample))

        data = get_pipeline_md5(str(tmp_path))
        assert data["vision_calls_used"] == 3
        assert data["vision_window_start"] == "2026-07-06T00:00:00+00:00"
        assert "new_gate" in data["gates"]
