"""Tests for MD5 file-tracking functions with pipeline_md5.json format."""
from __future__ import annotations

from pathlib import Path

import pytest

from automedia.omni.md5_integration import (
    OMNI_MD5_FILENAME,
    compute_md5,
    get_md5,
    has_changed,
    load_state,
    save_state,
    set_md5,
)


class TestFilename:
    def test_filename_is_pipeline_md5_json(self) -> None:
        assert OMNI_MD5_FILENAME == "pipeline_md5.json"


class TestComputeMd5:
    def test_compute_md5_with_temp_file(self, tmp_path: Path) -> None:
        file = tmp_path / "test.txt"
        file.write_text("hello world")
        digest = compute_md5(file)
        assert isinstance(digest, str)
        assert len(digest) == 32
        assert digest == "5eb63bbbe01eeed093cb22bb8f5acdc3"

    def test_compute_md5_binary_content(self, tmp_path: Path) -> None:
        file = tmp_path / "data.bin"
        file.write_bytes(b"\x00\x01\x02\xff\xfe\xfd")
        digest = compute_md5(file)
        assert isinstance(digest, str)
        assert len(digest) == 32


class TestLoadSaveState:
    def test_load_state_returns_empty_dict_when_no_file(self, tmp_path: Path) -> None:
        state = load_state(tmp_path)
        assert state == {}

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        original = {"omni_inputs": {}}
        save_state(original, tmp_path)
        loaded = load_state(tmp_path)
        assert loaded == original

    def test_state_has_expected_top_level_keys(self, tmp_path: Path) -> None:
        # Set an MD5 and check the state structure
        file = tmp_path / "doc.md"
        file.write_text("content")
        set_md5(file, tmp_path)
        state = load_state(tmp_path)
        # Should have at least omni_extraction
        assert "omni_inputs" in state
        assert "omni_extraction" in state
        assert "omni_translation" in state
        assert "omni_orf_outputs" in state


class TestGetSetMd5:
    def test_get_md5_returns_none_for_untracked(self, tmp_path: Path) -> None:
        file = tmp_path / "untracked.txt"
        file.write_text("content")
        result = get_md5(file, tmp_path)
        assert result is None

    def test_set_md5_stores_and_returns_hash(self, tmp_path: Path) -> None:
        file = tmp_path / "tracked.txt"
        file.write_text("track me")
        digest = set_md5(file, tmp_path)
        assert isinstance(digest, str)
        assert len(digest) == 32

        stored = get_md5(file, tmp_path)
        assert stored == digest

    def test_set_md5_writes_to_omni_extraction(self, tmp_path: Path) -> None:
        file = tmp_path / "brief.docx"
        file.write_text("brief content")
        set_md5(file, tmp_path)
        state = load_state(tmp_path)
        key = str(file.resolve())
        found = False
        for section in ("omni_inputs", "omni_extraction", "omni_translation", "omni_orf_outputs"):
            if key in state.get(section, {}):
                found = True
                break
        assert found, f"File key {key} not found in any omni_* section of state: {list(state.keys())}"


class TestHasChanged:
    def test_has_changed_returns_true_for_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.txt"
        assert has_changed(missing, tmp_path) is True

    def test_has_changed_returns_false_after_set_md5(self, tmp_path: Path) -> None:
        file = tmp_path / "stable.txt"
        file.write_text("stable content")
        set_md5(file, tmp_path)
        assert has_changed(file, tmp_path) is False

    def test_has_changed_returns_true_after_modification(self, tmp_path: Path) -> None:
        file = tmp_path / "modified.txt"
        file.write_text("original")
        set_md5(file, tmp_path)
        assert has_changed(file, tmp_path) is False

        file.write_text("modified")
        assert has_changed(file, tmp_path) is True
