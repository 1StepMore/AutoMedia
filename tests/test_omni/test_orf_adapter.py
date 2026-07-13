"""Tests for ORFAdapter."""

from __future__ import annotations

import os
import tempfile
from typing import Any

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

    def test_apply_md_writes_file(self, tmp_path: Any) -> None:
        adapter = ORFAdapter()
        out_path = str(tmp_path / "test_orf_output.md")
        returned = adapter.apply_md("content", out_path)
        assert returned == out_path
        assert os.path.isfile(out_path)
        with open(out_path, encoding="utf-8") as fh:
            assert fh.read() == "content"

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


