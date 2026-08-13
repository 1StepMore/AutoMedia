"""E2E — HotCollector.ingest_file() automatically triggers OPPAdapter.extract().

Verifies that calling ``ingest_file()`` on supported document formats
invokes ``OPPAdapter.extract()`` with the correct path and returns the
``ExtractionResult``.  Also tests unsupported formats and failure paths.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from automedia.omni.opp_adapter import ExtractionResult
from automedia.pool.collector import HotCollector

pytestmark = pytest.mark.e2e

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def collector() -> HotCollector:
    """Fresh HotCollector instance for each test."""
    return HotCollector()


@pytest.fixture
def mock_extract_success() -> MagicMock:
    """Patch OPPAdapter.extract to return a deterministic ExtractionResult."""
    result = ExtractionResult(
        md_content="# Extracted Title\n\nThis is the extracted content.",
        manifest={
            "title": "Extracted Title",
            "segments": [{"index": 0, "text": "# Extracted Title"}],
        },
        xliff_path=None,
        skeleton_path=None,
        warnings=[],
    )
    with patch("automedia.omni.opp_adapter.OPPAdapter.extract") as mock:
        mock.return_value = result
        yield mock


@pytest.fixture
def mock_extract_failure() -> MagicMock:
    """Patch OPPAdapter.extract to raise an exception."""
    with patch("automedia.omni.opp_adapter.OPPAdapter.extract") as mock:
        mock.side_effect = RuntimeError("Mock extraction failure")
        yield mock


# ===================================================================
# Tests — supported formats trigger OPPAdapter.extract()
# ===================================================================


class TestAutoTriggerSupported:
    """Supported formats (.docx, .pptx, .pdf) trigger extract() successfully."""

    def test_docx_triggers_opp_extract(
        self, collector: HotCollector, mock_extract_success: MagicMock, tmp_path: Path
    ) -> None:
        """.docx file → ingest_file calls extract → returns ExtractionResult."""
        docx_path = tmp_path / "test.docx"
        docx_path.write_text("fake docx content")

        result = collector.ingest_file(str(docx_path))

        mock_extract_success.assert_called_once()
        assert isinstance(result, ExtractionResult)
        assert result.md_content == "# Extracted Title\n\nThis is the extracted content."
        assert result.manifest["title"] == "Extracted Title"

    def test_pptx_triggers_opp_extract(
        self, collector: HotCollector, mock_extract_success: MagicMock, tmp_path: Path
    ) -> None:
        """.pptx file → ingest_file calls extract → returns ExtractionResult."""
        pptx_path = tmp_path / "test.pptx"
        pptx_path.write_text("fake pptx content")

        result = collector.ingest_file(str(pptx_path))

        mock_extract_success.assert_called_once()
        assert isinstance(result, ExtractionResult)
        assert result.md_content == "# Extracted Title\n\nThis is the extracted content."

    def test_pdf_triggers_opp_extract(
        self, collector: HotCollector, mock_extract_success: MagicMock, tmp_path: Path
    ) -> None:
        """.pdf file → ingest_file calls extract → returns ExtractionResult."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_text("fake pdf content")

        result = collector.ingest_file(str(pdf_path))

        mock_extract_success.assert_called_once()
        assert isinstance(result, ExtractionResult)
        assert result.md_content == "# Extracted Title\n\nThis is the extracted content."


# ===================================================================
# Tests — mock was called with the correct file path
# ===================================================================


class TestMockContract:
    """Verify the mock is correctly set up and receives the right arguments."""

    def test_mock_receives_correct_path(
        self, collector: HotCollector, mock_extract_success: MagicMock, tmp_path: Path
    ) -> None:
        """The file path passed to ingest_file should be forwarded to extract()."""
        docx_path = tmp_path / "mydoc.docx"
        docx_path.write_text("content")

        collector.ingest_file(str(docx_path))

        mock_extract_success.assert_called_once_with(str(docx_path))

    def test_multiple_calls_multiple_extracts(
        self, collector: HotCollector, mock_extract_success: MagicMock, tmp_path: Path
    ) -> None:
        """Calling ingest_file twice with different files triggers two extract calls."""
        paths = [
            tmp_path / "a.docx",
            tmp_path / "b.pptx",
        ]
        for p in paths:
            p.write_text("content")

        collector.ingest_file(str(paths[0]))
        collector.ingest_file(str(paths[1]))

        assert mock_extract_success.call_count == 2


# ===================================================================
# Tests — unsupported formats
# ===================================================================


class TestUnsupportedFormats:
    """Unsupported formats return None gracefully without calling extract."""

    def test_txt_unsupported_returns_none(
        self, collector: HotCollector, mock_extract_success: MagicMock, tmp_path: Path
    ) -> None:
        """.txt is unsupported → returns None, extract not called."""
        txt_path = tmp_path / "test.txt"
        txt_path.write_text("plain text")

        result = collector.ingest_file(str(txt_path))

        assert result is None
        mock_extract_success.assert_not_called()

    def test_md_unsupported_returns_none(
        self, collector: HotCollector, mock_extract_success: MagicMock, tmp_path: Path
    ) -> None:
        """.md is unsupported → returns None, extract not called."""
        md_path = tmp_path / "test.md"
        md_path.write_text("# Markdown")

        result = collector.ingest_file(str(md_path))

        assert result is None
        mock_extract_success.assert_not_called()


# ===================================================================
# Tests — extract failure
# ===================================================================


class TestExtractFailure:
    """When OPPAdapter.extract() raises, ingest_file returns an ExtractionResult."""

    def test_extract_failure_returns_extraction_result(
        self, collector: HotCollector, mock_extract_failure: MagicMock, tmp_path: Path
    ) -> None:
        """Exception in extract → returns ExtractionResult with error info."""
        from automedia.omni.opp_adapter import ExtractionResult

        docx_path = tmp_path / "fail.docx"
        docx_path.write_text("content")

        result = collector.ingest_file(str(docx_path))

        assert isinstance(result, ExtractionResult), (
            f"Expected ExtractionResult, got {type(result)}"
        )
        assert result.md_content == ""
        assert result.manifest["source_file"] == str(docx_path)
        assert "Mock extraction failure" in result.manifest["error"]

    def test_extract_failure_non_opp_exception(
        self, collector: HotCollector, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Any unexpected exception during ingest is caught and returned as ExtractionResult."""
        from automedia.omni.opp_adapter import ExtractionResult

        def _crash(*args: object, **kwargs: object) -> object:
            raise ValueError("Unexpected crash")

        monkeypatch.setattr("automedia.omni.opp_adapter.OPPAdapter.extract", _crash)

        docx_path = tmp_path / "crash.docx"
        docx_path.write_text("content")

        result = collector.ingest_file(str(docx_path))

        assert isinstance(result, ExtractionResult)
        assert "Unexpected crash" in result.manifest["error"]
        assert result.manifest["source_file"] == str(docx_path)
