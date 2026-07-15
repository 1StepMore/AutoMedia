"""Tests for ORFAdapter."""

from __future__ import annotations

import builtins
import os
import tempfile
from unittest.mock import patch

from automedia.omni.orf_adapter import ORFAdapter


def _patch_orf_import() -> patch:
    """Return a context manager that makes all ``orf.*`` imports fail with ImportError."""

    def _mock_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "orf" or name.startswith("orf."):
            msg = f"No module named '{name}'"
            raise ImportError(msg)
        return original_import(name, *args, **kwargs)

    original_import = builtins.__import__
    return patch("builtins.__import__", side_effect=_mock_import)


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

    def test_orf_adapter_convert_graceful_when_orf_not_installed(self) -> None:
        """When ``orf`` is not installed, ``convert()`` returns error dict, never raises."""
        with _patch_orf_import():
            adapter = ORFAdapter()
            result = adapter.convert("/nonexistent/test.docx")

        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert result["success"] is False
        assert len(result["errors"]) > 0
        assert "orf" in result["errors"][0].lower()

    def test_convert_logs_warning_on_missing_orf(self) -> None:
        """Missing ``orf`` dependency triggers a warning via ``warn_missing_optional``."""
        with (
            patch("automedia.core._import_helpers.warn_missing_optional") as mock_warn,
            _patch_orf_import(),
        ):
            adapter = ORFAdapter()
            result = adapter.convert("/nonexistent/test.docx")
            assert result["success"] is False
            mock_warn.assert_called_once()

    def test_apply_md_writes_file(self, tmp_path: object) -> None:
        adapter = ORFAdapter()
        out_path = os.path.join(str(tmp_path), "test_orf_output.md")
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
