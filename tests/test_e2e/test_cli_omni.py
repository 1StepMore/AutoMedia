"""E2E tests for ``automedia omni`` CLI commands — localize, format-output, ingest.

These tests mock the underlying adapters (OLAdapter, ORFAdapter, OPPAdapter)
but verify the full CLI invocation path through ``CliRunner`` with ``app``,
including argument parsing, error handling, file I/O, and output conventions.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.omni.opp_adapter import ExtractionResult

pytestmark = pytest.mark.e2e

runner = CliRunner()


# =========================================================================
# 1. automedia omni localize — full pipeline and error handling
# =========================================================================


def test_localize_full_pipeline(tmp_path: Path) -> None:
    """Full pipeline: translate one article into en and ja, verify outputs."""
    # ── Arrange ──────────────────────────────────────────────────────
    drafts = tmp_path / "01_content" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "article.md").write_text("# Hello World", encoding="utf-8")

    # ── Act ──────────────────────────────────────────────────────────
    with patch("automedia.omni.ol_adapter.OLAdapter.translate") as mock_translate:
        mock_translate.side_effect = [
            MagicMock(translated_md="# Hello World in English", warnings=[]),
            MagicMock(translated_md="# こんにちは世界", warnings=[]),
        ]

        result = runner.invoke(
            app,
            [
                "omni",
                "localize",
                "--project",
                str(tmp_path),
                "--target-langs",
                "en,ja",
            ],
        )

    # ── Assert ───────────────────────────────────────────────────────
    assert result.exit_code == 0, f"Exit code 0 expected, got {result.exit_code}: {result.output}"
    assert "Localised" in result.output, "Success message not printed"
    assert "article.md" in result.output, "Output file name not in success message"

    en_file = tmp_path / "05_publish" / "en" / "article.md"
    ja_file = tmp_path / "05_publish" / "ja" / "article.md"
    assert en_file.exists(), f"Expected {en_file} to exist"
    assert ja_file.exists(), f"Expected {ja_file} to exist"
    assert en_file.read_text(encoding="utf-8") == "# Hello World in English"
    assert ja_file.read_text(encoding="utf-8") == "# こんにちは世界"

    # Files from 05_publish/en/ match the input file name
    assert en_file.name == "article.md"
    assert ja_file.name == "article.md"


def test_localize_missing_drafts_dir(tmp_path: Path) -> None:
    """Project without 01_content/drafts/ exits with code 1 and error message."""
    result = runner.invoke(
        app,
        [
            "omni",
            "localize",
            "--project",
            str(tmp_path),
            "--target-langs",
            "en",
        ],
    )
    assert result.exit_code == 1
    assert "Drafts directory not found" in result.output


def test_localize_empty_drafts(tmp_path: Path) -> None:
    """Project with empty drafts directory exits with code 1."""
    drafts = tmp_path / "01_content" / "drafts"
    drafts.mkdir(parents=True)

    result = runner.invoke(
        app,
        [
            "omni",
            "localize",
            "--project",
            str(tmp_path),
            "--target-langs",
            "en",
        ],
    )
    assert result.exit_code == 1
    assert "No markdown files found" in result.output


def test_localize_translation_failure(tmp_path: Path) -> None:
    """When OLAdapter.translate() raises, command prints error and exits 1."""
    drafts = tmp_path / "01_content" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "article.md").write_text("# Hello", encoding="utf-8")

    with patch("automedia.omni.ol_adapter.OLAdapter.translate") as mock_translate:
        mock_translate.side_effect = RuntimeError("API timeout")

        result = runner.invoke(
            app,
            [
                "omni",
                "localize",
                "--project",
                str(tmp_path),
                "--target-langs",
                "fr",
            ],
        )
        assert result.exit_code == 1
        assert "Translation failed" in result.output
        assert "No files were produced" in result.output


def test_localize_single_language(tmp_path: Path) -> None:
    """--target-langs fr creates 05_publish/fr/ but not en/ or ja/."""
    drafts = tmp_path / "01_content" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "article.md").write_text("# Hello", encoding="utf-8")

    with patch("automedia.omni.ol_adapter.OLAdapter.translate") as mock_translate:
        mock_translate.return_value = MagicMock(translated_md="# Bonjour", warnings=[])

        result = runner.invoke(
            app,
            [
                "omni",
                "localize",
                "--project",
                str(tmp_path),
                "--target-langs",
                "fr",
            ],
        )
        assert result.exit_code == 0
        assert "Localised" in result.output

        fr_file = tmp_path / "05_publish" / "fr" / "article.md"
        assert fr_file.exists()
        assert fr_file.read_text(encoding="utf-8") == "# Bonjour"

        # No other language directories should have been created
        assert not (tmp_path / "05_publish" / "en").exists()
        assert not (tmp_path / "05_publish" / "ja").exists()


# =========================================================================
# 2. automedia omni format-output — format conversion
# =========================================================================


def test_format_output(tmp_path: Path) -> None:
    """--input <file> --target-format docx calls mocked ORFAdapter and prints output."""
    input_file = tmp_path / "test.md"
    input_file.write_text("# Hello", encoding="utf-8")

    with patch("automedia.omni.orf_adapter.ORFAdapter.convert") as mock_convert:
        expected_output = tmp_path / "test.docx"
        mock_convert.return_value = {
            "output_path": str(expected_output),
            "status": "ok",
            "success": True,
            "errors": [],
        }

        result = runner.invoke(
            app,
            [
                "omni",
                "format-output",
                "--input",
                str(input_file),
                "--target-format",
                "docx",
            ],
        )
        assert result.exit_code == 0, (
            f"Exit code 0 expected, got {result.exit_code}: {result.output}"
        )
        assert "Output:" in result.output
        assert "test.docx" in result.output
        mock_convert.assert_called_once_with(
            file_path=str(input_file),
            output_path=str(expected_output),
        )


# =========================================================================
# 3. automedia omni ingest — document extraction
# =========================================================================


def test_ingest(tmp_path: Path) -> None:
    """--dir <dir> --output-dir <dir> calls mocked OPPAdapter and produces .md files."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "report.docx").write_bytes(b"dummy-docx")
    output_dir = tmp_path / "output"

    with patch("automedia.omni.opp_adapter.OPPAdapter.extract") as mock_extract:
        mock_extract.return_value = ExtractionResult(
            md_content="# Extracted Report",
            manifest={"segments": []},
            warnings=[],
        )

        result = runner.invoke(
            app,
            [
                "omni",
                "ingest",
                "--dir",
                str(input_dir),
                "--output-dir",
                str(output_dir),
            ],
        )
        assert result.exit_code == 0, (
            f"Exit code 0 expected, got {result.exit_code}: {result.output}"
        )
        assert "Ingested" in result.output
        assert "report.md" in result.output

        out_file = output_dir / "report.md"
        assert out_file.exists()
        assert out_file.read_text(encoding="utf-8") == "# Extracted Report"
        mock_extract.assert_called_once_with(str(input_dir / "report.docx"))
