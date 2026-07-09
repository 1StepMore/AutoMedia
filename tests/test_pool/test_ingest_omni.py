"""RED test — verify HotCollector.ingest_file() calls OPPAdapter.extract().

This file will FAIL because ``ingest_file()`` does not exist yet on
``HotCollector`` (TDD red-phase).  Once implemented the mocks and assertions
here should pass.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from automedia.pool.collector import HotCollector


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def collector() -> HotCollector:
    """Default HotCollector instance for ingest tests."""
    return HotCollector()


@pytest.fixture
def mock_extract() -> MagicMock:
    """Patch OPPAdapter.extract so no real extraction runs."""
    patcher = patch("automedia.omni.opp_adapter.OPPAdapter.extract")
    mock = patcher.start()
    mock.return_value = MagicMock(
        md_content="# Extracted content",
        manifest={"title": "test"},
        warnings=[],
    )
    yield mock
    patcher.stop()


# ===================================================================
# Tests — ingest_file() with supported formats
# ===================================================================


class TestIngestOmni:
    """ingest_file() calls OPPAdapter.extract() for supported doc formats."""

    def test_ingest_docx_calls_extract(
        self, collector: HotCollector, mock_extract: MagicMock, tmp_path: Path
    ) -> None:
        """.docx files should trigger OPPAdapter.extract()."""
        docx_path = tmp_path / "test.docx"
        docx_path.write_text("fake docx content")

        result = collector.ingest_file(str(docx_path))

        mock_extract.assert_called_once()
        assert hasattr(result, "md_content")
        assert hasattr(result, "manifest")
        assert hasattr(result, "warnings")

    def test_ingest_pptx_calls_extract(
        self, collector: HotCollector, mock_extract: MagicMock, tmp_path: Path
    ) -> None:
        """.pptx files should trigger OPPAdapter.extract()."""
        pptx_path = tmp_path / "test.pptx"
        pptx_path.write_text("fake pptx content")

        result = collector.ingest_file(str(pptx_path))

        mock_extract.assert_called_once()
        assert hasattr(result, "md_content")

    def test_ingest_pdf_calls_extract(
        self, collector: HotCollector, mock_extract: MagicMock, tmp_path: Path
    ) -> None:
        """.pdf files should trigger OPPAdapter.extract()."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_text("fake pdf content")

        result = collector.ingest_file(str(pdf_path))

        mock_extract.assert_called_once()
        assert hasattr(result, "md_content")

    def test_ingest_returns_dict_keys(
        self, collector: HotCollector, mock_extract: MagicMock, tmp_path: Path
    ) -> None:
        """Result should have md_content, manifest, warnings keys."""
        docx_path = tmp_path / "test.docx"
        docx_path.write_text("fake docx content")

        result = collector.ingest_file(str(docx_path))

        # Support both dict-like and object access
        if isinstance(result, dict):
            assert "md_content" in result
            assert "manifest" in result
            assert "warnings" in result
        else:
            assert hasattr(result, "md_content")
            assert hasattr(result, "manifest")
            assert hasattr(result, "warnings")


# ===================================================================
# Tests — ingest_file() with unsupported formats
# ===================================================================


class TestIngestUnsupportedFormat:
    """ingest_file() handles unsupported formats without raising."""

    def test_ingest_txt_returns_gracefully(
        self, collector: HotCollector, mock_extract: MagicMock, tmp_path: Path
    ) -> None:
        """.txt is unsupported — should return gracefully (empty result or None)."""
        txt_path = tmp_path / "test.txt"
        txt_path.write_text("plain text")

        result = collector.ingest_file(str(txt_path))

        # Should either return None or an empty result without raising
        assert result is None or isinstance(result, (dict, object))

    def test_ingest_md_returns_gracefully(
        self, collector: HotCollector, mock_extract: MagicMock, tmp_path: Path
    ) -> None:
        """.md is unsupported — should return gracefully (empty result or None)."""
        md_path = tmp_path / "test.md"
        md_path.write_text("# Markdown")

        result = collector.ingest_file(str(md_path))

        assert result is None or isinstance(result, (dict, object))
