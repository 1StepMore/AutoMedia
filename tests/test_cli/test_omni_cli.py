"""Tests for ``automedia omni`` — localize, format-output, ingest."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.omni.opp_adapter import ExtractionResult

runner = CliRunner()


# =========================================================================
# 1. automedia omni localize
# =========================================================================


class TestOmniLocalize:
    """Tests for ``automedia omni localize``."""

    def test_localize_missing_project(self) -> None:
        """Missing --project should exit with error."""
        result = runner.invoke(app, ["omni", "localize", "--target-langs", "en"])
        assert result.exit_code != 0

    def test_localize_missing_langs(self) -> None:
        """Missing --target-langs should exit with error."""
        result = runner.invoke(app, ["omni", "localize", "--project", "/tmp"])
        assert result.exit_code != 0

    def test_localize_project_dir_not_found(self, tmp_path: Path) -> None:
        """Non-existent drafts dir should print error and exit 1."""
        result = runner.invoke(
            app,
            [
                "omni",
                "localize",
                "--project",
                str(tmp_path / "nonexistent"),
                "--target-langs",
                "en",
            ],
        )
        assert result.exit_code == 1

    def test_localize_no_drafts_dir(self, tmp_path: Path) -> None:
        """Project without 01_content/drafts/ should exit 1."""
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

    def test_localize_no_md_files(self, tmp_path: Path) -> None:
        """Empty drafts dir should exit 1."""
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

    @patch("automedia.omni.ol_adapter.OLAdapter.translate")
    def test_localize_success_single_lang(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Happy path: one md file translated into one language."""
        drafts = tmp_path / "01_content" / "drafts"
        drafts.mkdir(parents=True)
        (drafts / "article.md").write_text("# Hello", encoding="utf-8")

        mock_translate.return_value = MagicMock(
            translated_md="# Bonjour",
            warnings=[],
        )

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

        publish_file = tmp_path / "05_publish" / "fr" / "article.md"
        assert publish_file.exists()
        assert publish_file.read_text(encoding="utf-8") == "# Bonjour"

    @patch("automedia.omni.ol_adapter.OLAdapter.translate")
    def test_localize_success_multi_lang(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Happy path: one md translated into two languages."""
        drafts = tmp_path / "01_content" / "drafts"
        drafts.mkdir(parents=True)
        (drafts / "doc.md").write_text("# Hello", encoding="utf-8")

        mock_translate.side_effect = [
            MagicMock(translated_md="# Bonjour", warnings=[]),
            MagicMock(translated_md="# こんにちは", warnings=[]),
        ]

        result = runner.invoke(
            app,
            [
                "omni",
                "localize",
                "--project",
                str(tmp_path),
                "--target-langs",
                "fr,ja",
            ],
        )
        assert result.exit_code == 0
        assert "Localised" in result.output

        assert (tmp_path / "05_publish" / "fr" / "doc.md").exists()
        assert (tmp_path / "05_publish" / "ja" / "doc.md").exists()

    @patch("automedia.omni.ol_adapter.OLAdapter.translate")
    def test_localize_translation_failure(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """When translate() raises, the command should continue with other langs."""
        drafts = tmp_path / "01_content" / "drafts"
        drafts.mkdir(parents=True)
        (drafts / "article.md").write_text("# Hello", encoding="utf-8")

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


# =========================================================================
# 2. automedia omni format-output
# =========================================================================


class TestOmniFormatOutput:
    """Tests for ``automedia omni format-output``."""

    def test_format_output_missing_input(self) -> None:
        """Missing --input should exit with error."""
        result = runner.invoke(
            app,
            [
                "omni",
                "format-output",
                "--target-format",
                "docx",
            ],
        )
        assert result.exit_code != 0

    def test_format_output_missing_format(self) -> None:
        """Missing --target-format should exit with error."""
        result = runner.invoke(
            app,
            [
                "omni",
                "format-output",
                "--input",
                "/tmp/test.md",
            ],
        )
        assert result.exit_code != 0

    def test_format_output_file_not_found(self, tmp_path: Path) -> None:
        """Non-existent input file should exit 1."""
        result = runner.invoke(
            app,
            [
                "omni",
                "format-output",
                "--input",
                str(tmp_path / "missing.md"),
                "--target-format",
                "docx",
            ],
        )
        assert result.exit_code == 1
        assert "Input file not found" in result.output

    @patch("automedia.omni.orf_adapter.ORFAdapter.convert")
    def test_format_output_success(self, mock_convert: MagicMock, tmp_path: Path) -> None:
        """Happy path: md converted to docx."""
        input_file = tmp_path / "input.md"
        input_file.write_text("# Hello", encoding="utf-8")

        expected_output = tmp_path / "input.docx"
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
        assert result.exit_code == 0
        assert "Output:" in result.output
        assert "input.docx" in result.output
        mock_convert.assert_called_once()

    @patch("automedia.omni.orf_adapter.ORFAdapter.convert")
    def test_format_output_conversion_failure(
        self, mock_convert: MagicMock, tmp_path: Path
    ) -> None:
        """When convert() raises, command should exit 1."""
        input_file = tmp_path / "input.md"
        input_file.write_text("# Hello", encoding="utf-8")

        mock_convert.side_effect = RuntimeError("Converter crashed")

        result = runner.invoke(
            app,
            [
                "omni",
                "format-output",
                "--input",
                str(input_file),
                "--target-format",
                "pdf",
            ],
        )
        assert result.exit_code == 1
        assert "Format conversion failed" in result.output


# =========================================================================
# 3. automedia omni ingest
# =========================================================================


class TestOmniIngest:
    """Tests for ``automedia omni ingest``."""

    def test_ingest_missing_dir(self) -> None:
        """Missing --dir should exit with error."""
        result = runner.invoke(
            app,
            [
                "omni",
                "ingest",
                "--output-dir",
                "/tmp/out",
            ],
        )
        assert result.exit_code != 0

    def test_ingest_missing_output_dir(self) -> None:
        """Missing --output-dir should exit with error."""
        result = runner.invoke(
            app,
            [
                "omni",
                "ingest",
                "--dir",
                "/tmp",
            ],
        )
        assert result.exit_code != 0

    def test_ingest_input_dir_not_found(self, tmp_path: Path) -> None:
        """Non-existent input dir should exit 1."""
        result = runner.invoke(
            app,
            [
                "omni",
                "ingest",
                "--dir",
                str(tmp_path / "nonexistent"),
                "--output-dir",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 1
        assert "Input directory not found" in result.output

    def test_ingest_no_supported_files(self, tmp_path: Path) -> None:
        """Dir with no supported file types should print message and exit 0."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "readme.txt").write_text("hello")  # .txt IS supported

        # Use a dir with truly unsupported content
        input_dir2 = tmp_path / "nosupport"
        input_dir2.mkdir()
        (input_dir2 / "image.jpg").write_bytes(b"fake-jpeg")

        output_dir = tmp_path / "output"
        result = runner.invoke(
            app,
            [
                "omni",
                "ingest",
                "--dir",
                str(input_dir2),
                "--output-dir",
                str(output_dir),
            ],
        )
        assert result.exit_code == 0
        assert "No supported documents found" in result.output

    @patch("automedia.omni.opp_adapter.OPPAdapter.extract")
    def test_ingest_success(self, mock_extract: MagicMock, tmp_path: Path) -> None:
        """Happy path: single docx file extracted to md."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "report.docx").write_bytes(b"dummy-docx")
        output_dir = tmp_path / "output"

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
        assert result.exit_code == 0
        assert "Ingested" in result.output
        assert "report.md" in result.output

        out_file = output_dir / "report.md"
        assert out_file.exists()
        assert out_file.read_text(encoding="utf-8") == "# Extracted Report"
        mock_extract.assert_called_once_with(str(input_dir / "report.docx"))

    @patch("automedia.omni.opp_adapter.OPPAdapter.extract")
    def test_ingest_multiple_files(self, mock_extract: MagicMock, tmp_path: Path) -> None:
        """Multiple supported files are all processed."""
        input_dir = tmp_path / "multi"
        input_dir.mkdir()
        (input_dir / "a.docx").write_bytes(b"dummy-a")
        (input_dir / "b.pptx").write_bytes(b"dummy-b")
        (input_dir / "c.pdf").write_bytes(b"dummy-c")
        output_dir = tmp_path / "output"

        mock_extract.side_effect = [
            ExtractionResult(md_content="# A", manifest={}, warnings=[]),
            ExtractionResult(md_content="# B", manifest={}, warnings=[]),
            ExtractionResult(md_content="# C", manifest={}, warnings=[]),
        ]

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
        assert result.exit_code == 0
        assert "Ingested 3 file(s)" in result.output

        assert (output_dir / "a.md").read_text(encoding="utf-8") == "# A"
        assert (output_dir / "b.md").read_text(encoding="utf-8") == "# B"
        assert (output_dir / "c.md").read_text(encoding="utf-8") == "# C"

    @patch("automedia.omni.opp_adapter.OPPAdapter.extract")
    def test_ingest_extraction_failure_skips_file(
        self, mock_extract: MagicMock, tmp_path: Path
    ) -> None:
        """When extract() raises, that file is skipped but others continue."""
        input_dir = tmp_path / "mixed"
        input_dir.mkdir()
        # bad.md comes first alphabetically, then good.docx
        (input_dir / "bad.docx").write_bytes(b"dummy-bad")
        (input_dir / "good.docx").write_bytes(b"dummy-good")
        output_dir = tmp_path / "output"

        # First call (bad.docx) raises, second (good.docx) succeeds
        mock_extract.side_effect = [
            RuntimeError("Corrupted file"),
            ExtractionResult(md_content="# Good", manifest={}, warnings=[]),
        ]

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
        assert result.exit_code == 0
        assert "Extraction failed" in result.output
        assert "Ingested 1 file(s)" in result.output
        assert (output_dir / "good.md").exists()
        # bad.docx should not have an output
        assert not (output_dir / "bad.md").exists()

    @patch("automedia.omni.opp_adapter.OPPAdapter.extract")
    def test_ingest_all_fail(self, mock_extract: MagicMock, tmp_path: Path) -> None:
        """When every extract() raises, exit 1 with message."""
        input_dir = tmp_path / "allbad"
        input_dir.mkdir()
        (input_dir / "bad.docx").write_bytes(b"dummy-bad")
        output_dir = tmp_path / "output"

        mock_extract.side_effect = RuntimeError("Everything broke")

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
        assert result.exit_code == 1
        assert "Extraction failed" in result.output
        assert "No files were successfully processed" in result.output


# =========================================================================
# 4. automedia omni command registration
# =========================================================================


class TestOmniRegistration:
    """Verify the ``omni`` sub-typer registers all expected commands."""

    def test_omni_help_lists_subcommands(self) -> None:
        result = runner.invoke(app, ["omni", "--help"])
        assert result.exit_code == 0
        for cmd in ("start-all", "start", "localize", "format-output", "ingest"):
            assert cmd in result.output

    def test_omni_app_name(self) -> None:
        from automedia.cli.commands.omni import app as omni_app

        assert omni_app.info.name == "omni"
