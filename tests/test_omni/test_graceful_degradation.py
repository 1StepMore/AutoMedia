"""Tests for graceful degradation when Omni packages are not installed.

All three adapters must return structured results (never raise) when their
respective external packages (opp, ol_mcp, orf) are missing.

These tests use ``builtins.__import__`` patching to simulate missing packages
deterministically, regardless of whether the packages happen to be installed
in the test environment.
"""

from __future__ import annotations

import builtins
from unittest.mock import patch

from automedia.omni.ol_adapter import OLAdapter, TranslationResult
from automedia.omni.opp_adapter import ExtractionResult, OPPAdapter
from automedia.omni.orf_adapter import ORFAdapter


def _patch_import(prefix: str) -> patch:
    """Return a context manager that makes imports matching *prefix* fail with ImportError."""

    def _mock_import(name: str, *args: object, **kwargs: object) -> object:
        if name == prefix or name.startswith(prefix + "."):
            msg = f"No module named '{name}'"
            raise ImportError(msg)
        return original_import(name, *args, **kwargs)

    original_import = builtins.__import__
    return patch("builtins.__import__", side_effect=_mock_import)


# ===================================================================
# OPPAdapter graceful degradation
# ===================================================================


class TestOPPGracefulDegradation:
    """OPPAdapter must return ``ExtractionResult`` with warnings when ``opp`` is missing."""

    def test_extract_graceful_when_opp_not_installed(self) -> None:
        """When ``opp`` is not available, ``extract()`` returns empty result with warnings."""
        with _patch_import("opp"):
            adapter = OPPAdapter()
            result = adapter.extract("/nonexistent/test.docx")

        assert isinstance(result, ExtractionResult)
        assert result.md_content == ""
        assert len(result.warnings) > 0

    def test_extract_md_does_not_require_opp(self) -> None:
        """``extract_md()`` is a pure method that works without ``opp``."""
        adapter = OPPAdapter()
        result = adapter.extract_md("# Hello")
        assert isinstance(result, ExtractionResult)
        assert result.md_content == "# Hello"

    def test_batch_extract_graceful_on_missing_opp(self) -> None:
        """``batch_extract()`` returns a list even without ``opp``."""
        adapter = OPPAdapter()
        result = adapter.batch_extract([])
        assert result == []


# ===================================================================
# OLAdapter graceful degradation
# ===================================================================


class TestOLGracefulDegradation:
    """OLAdapter must return ``TranslationResult`` with warnings when ``ol_mcp`` is missing."""

    def test_translate_graceful_when_ol_mcp_not_installed(self) -> None:
        """When ``ol_mcp`` is not available, ``translate()`` returns empty result with warnings."""
        with _patch_import("ol_mcp"):
            adapter = OLAdapter()
            result = adapter.translate("# Hello")

        assert isinstance(result, TranslationResult)
        assert result.translated_md == ""
        assert len(result.warnings) > 0

    def test_translate_batch_returns_list(self) -> None:
        """``translate_batch()`` returns a list of results even on empty input."""
        adapter = OLAdapter()
        result = adapter.translate_batch([])
        assert result == []


# ===================================================================
# ORFAdapter graceful degradation
# ===================================================================


class TestORFGracefulDegradation:
    """ORFAdapter must return error dict with warnings when ``orf`` is missing."""

    def test_convert_graceful_when_orf_not_installed(self) -> None:
        """When ``orf`` is not available, ``convert()`` returns error dict, never raises."""
        with _patch_import("orf"):
            adapter = ORFAdapter()
            result = adapter.convert("/nonexistent/test.md")

        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert result["success"] is False
        assert len(result["errors"]) > 0
        assert "orf" in result["errors"][0].lower()

    def test_apply_md_does_not_require_orf(self) -> None:
        """``apply_md()`` is a pure method that works without ``orf``."""
        import os
        import tempfile

        adapter = ORFAdapter()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as fh:
            out_path = fh.name

        try:
            returned = adapter.apply_md("content", out_path)
            assert returned == out_path
            with open(out_path, encoding="utf-8") as f:
                assert f.read() == "content"
        finally:
            os.unlink(out_path)


# ===================================================================
# Cross-adapter: all three produce structured results on missing packages
# ===================================================================


class TestAllAdaptersGracefulDegradation:
    """All three adapters follow the same degradation contract."""

    def test_all_adapters_return_structured_results_when_packages_missing(self) -> None:
        """Every adapter returns structured results, never raises, when all packages are missing."""
        with _patch_import("opp"), _patch_import("ol_mcp"), _patch_import("orf"):
            opp = OPPAdapter()
            ol = OLAdapter()
            orf = ORFAdapter()

            opp_result = opp.extract("/nonexistent/test.docx")
            assert opp_result is not None
            assert hasattr(opp_result, "warnings")

            ol_result = ol.translate("# Hello")
            assert ol_result is not None
            assert hasattr(ol_result, "warnings")

            orf_result = orf.convert("/nonexistent/test.md")
            assert orf_result is not None
            assert "errors" in orf_result or "warnings" in orf_result
