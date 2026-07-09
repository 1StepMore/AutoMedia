"""Tests for ORFAdapter."""

from __future__ import annotations

import os
import tempfile

import pytest

from automedia.omni.orf_adapter import ORFAdapter


class TestORFAdapterContract:
    def test_orf_adapter_name_returns_orf(self) -> None:
        adapter = ORFAdapter()
        assert adapter.name == "orf"

    def test_orf_adapter_validate_env_returns_false_without_env(self) -> None:
        adapter = ORFAdapter()
        assert adapter.validate_env() is False

    def test_orf_adapter_convert_exists_and_callable(self) -> None:
        adapter = ORFAdapter()
        assert callable(adapter.convert)

    def test_orf_adapter_convert_raises_without_env(self) -> None:
        adapter = ORFAdapter()
        with pytest.raises(Exception):
            adapter.convert("/nonexistent/test.docx")

    def test_backfill_returns_translated_md(self) -> None:
        adapter = ORFAdapter()
        result = adapter.backfill("translated", "original")
        assert result == "translated"

    def test_backfill_skeleton_none(self) -> None:
        adapter = ORFAdapter()
        result = adapter.backfill("t", "o", skeleton_path=None)
        assert result == "t"

    def test_apply_md_writes_file(self) -> None:
        adapter = ORFAdapter()
        out_path = "/tmp/test_orf_output.md"
        try:
            returned = adapter.apply_md("content", out_path)
            assert returned == out_path
            assert os.path.isfile(out_path)
            with open(out_path, encoding="utf-8") as fh:
                assert fh.read() == "content"
        finally:
            if os.path.exists(out_path):
                os.remove(out_path)

    def test_apply_md_creates_parent_dirs(self) -> None:
        adapter = ORFAdapter()
        out_dir = tempfile.mkdtemp()
        nested = os.path.join(out_dir, "sub", "output.md")
        try:
            adapter.apply_md("nested content", nested)
            assert os.path.isfile(nested)
            with open(nested, encoding="utf-8") as fh:
                assert fh.read() == "nested content"
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_apply_xliff_returns_path_and_no_raise(self) -> None:
        adapter = ORFAdapter()
        out_dir = tempfile.mkdtemp()
        try:
            result = adapter.apply_xliff("/tmp/test.xlf", out_dir)
            assert isinstance(result, str)
            assert result.endswith(".backfilled.md")
        finally:
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)
