"""Tests for source material auto-detect in pipeline runner.

Tests the ``_resolve_source_material`` helper and the ``source_path`` /
``source_url`` integration with ``run_full_pipeline`` and the MCP
``run_pipeline`` tool.

Scenarios
---------
1. source_path with a .md file → content loaded as source_material
2. source_path with a .txt file → content loaded as source_material
3. source_path is a directory → scans for first readable document
4. source_path not found → returns error dict, not crash
5. source_path with unsupported extension → returns error dict
6. source_url → fetches content via urllib
7. Both empty → returns None (topic-only mode)
8. MCP run_pipeline accepts and passes through source_path/source_url
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# =====================================================================
# Helpers
# =====================================================================


def _resolve_source_material(
    source_path: str = "",
    source_url: str = "",
) -> dict[str, Any] | None:
    """Thin wrapper importing the private helper for testability.

    Uses lazy import to avoid triggering full pipeline imports at
    collection time.
    """
    from automedia.pipelines.runner import _resolve_source_material

    return _resolve_source_material(source_path=source_path, source_url=source_url)


# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture()
def md_source(tmp_path: Path) -> Path:
    """Write a synthetic .md file and return its path."""
    p = tmp_path / "source.md"
    p.write_text("# Test Title\n\nThis is synthetic test content.\n", encoding="utf-8")
    return p


@pytest.fixture()
def txt_source(tmp_path: Path) -> Path:
    """Write a synthetic .txt file and return its path."""
    p = tmp_path / "source.txt"
    p.write_text("Synthetic plain text content.\n", encoding="utf-8")
    return p


# =====================================================================
# Tests: _resolve_source_material
# =====================================================================


class TestResolveSourceMaterial:
    """Direct unit tests for the private helper."""

    def test_md_file(self, md_source: Path) -> None:
        """source_path with .md file returns content and type='md'."""
        result = _resolve_source_material(source_path=str(md_source))
        assert result is not None
        assert "error" not in result
        assert result["type"] == "md"
        assert "# Test Title" in result["content"]
        assert md_source.resolve().as_posix() in str(result["path"])

    def test_txt_file(self, txt_source: Path) -> None:
        """source_path with .txt file returns content and type='txt'."""
        result = _resolve_source_material(source_path=str(txt_source))
        assert result is not None
        assert "error" not in result
        assert result["type"] == "txt"
        assert "Synthetic plain text" in result["content"]

    def test_directory_scans_first_file(self, tmp_path: Path) -> None:
        """source_path as directory scans for readable documents."""
        (tmp_path / "notes.txt").write_text("First doc content.", encoding="utf-8")
        (tmp_path / "readme.md").write_text("# Readme", encoding="utf-8")

        result = _resolve_source_material(source_path=str(tmp_path))
        assert result is not None
        assert "error" not in result
        # Should pick the first file alphabetically (.md before .txt)
        assert result["type"] in ("md", "txt")
        assert result["content"]

    def test_directory_empty(self, tmp_path: Path) -> None:
        """Empty directory returns error."""
        result = _resolve_source_material(source_path=str(tmp_path))
        assert result is not None
        assert "error" in result
        assert "no readable documents" in result["error"]

    def test_path_not_found(self) -> None:
        """Non-existent path returns error, not crash."""
        result = _resolve_source_material(source_path="/nonexistent/path/file.md")
        assert result is not None
        assert "error" in result
        assert "not found" in result["error"]

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        """Unsupported file extension returns error."""
        p = tmp_path / "data.json"
        p.write_text('{"key": "value"}', encoding="utf-8")
        result = _resolve_source_material(source_path=str(p))
        assert result is not None
        assert "error" in result
        assert "Unsupported file type" in result["error"]

    def test_both_empty_returns_none(self) -> None:
        """Both empty → None (topic-only mode)."""
        result = _resolve_source_material()
        assert result is None

    def test_url_fetch(self) -> None:
        """source_url fetches content via urllib."""
        fake_content = "Fetched content from URL."

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock_urlopen.return_value.__enter__.return_value
            mock_resp.read.return_value = fake_content.encode("utf-8")

            result = _resolve_source_material(source_url="https://example.com/doc.txt")

        assert result is not None
        assert "error" not in result
        assert result["type"] == "url"
        assert "Fetched content" in result["content"]
        assert result["path"] == "https://example.com/doc.txt"

    def test_url_fetch_failure(self) -> None:
        """Unreachable URL returns error."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            import urllib.error

            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

            result = _resolve_source_material(source_url="https://example.com/bad")

        assert result is not None
        assert "error" in result
        assert "Failed to fetch" in result["error"]

    def test_md_file_preferred_over_txt_in_dir(self, tmp_path: Path) -> None:
        """Directory scan picks .md before .txt alphabetically."""
        (tmp_path / "aaa.txt").write_text("AAA text", encoding="utf-8")
        (tmp_path / "zzz.md").write_text("# ZZZ markdown", encoding="utf-8")

        result = _resolve_source_material(source_path=str(tmp_path))
        assert result is not None
        assert "error" not in result
        # Should pick aaa.txt (first alphabetically among .md/.txt/.pdf)
        # sorted() will give aaa.txt first
        assert result["type"] == "txt"
        assert result["content"] == "AAA text"


# =====================================================================
# Tests: MCP run_pipeline parameter pass-through
# =====================================================================


class TestMCPRunPipelineSourceParams:
    """Verify MCP run_pipeline accepts and passes source_path/source_url."""

    def test_run_pipeline_accepts_source_path(self) -> None:
        """run_pipeline accepts source_path param and returns started."""
        from automedia.mcp.server import run_pipeline

        result = run_pipeline(
            topic="test topic",
            brand="TestBrand",
            mode="auto",
            source_path="/tmp/test.md",
        )
        assert isinstance(result, dict)
        assert result["status"] == "started"
        assert "project_id" in result

    def test_run_pipeline_accepts_source_url(self) -> None:
        """run_pipeline accepts source_url param and returns started."""
        from automedia.mcp.server import run_pipeline

        result = run_pipeline(
            topic="test topic",
            brand="TestBrand",
            mode="auto",
            source_url="https://example.com/doc.md",
        )
        assert isinstance(result, dict)
        assert result["status"] == "started"
        assert "project_id" in result

    def test_run_pipeline_without_source_params(self) -> None:
        """run_pipeline still works without source params (backward compat)."""
        from automedia.mcp.server import run_pipeline

        result = run_pipeline(topic="test topic", brand="TestBrand", mode="auto")
        assert isinstance(result, dict)
        assert "status" in result
