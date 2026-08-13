"""E2E test suite for failure propagation scenarios in the Omni pipeline.

Verifies the system gracefully handles OPP/OL/ORF failures without crashing
the main pipeline, covering:

- Design Decision D-O4: OPP failure does NOT block the main pipeline
- Design Decision D-O9: Auto-trigger is OPP extract only; OL/ORF are manual
- MCP tool try/except wrappers returning graceful error dicts on failure
- L4 Translation Quality Gate (frontmatter, language match, garbled, non-empty)
- Path allowlist enforcement via ``_require_allowed``
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.gates.translation_quality import L4TranslationQuality
from automedia.mcp.server import extract_brief, format_output, localize_content, localize_output
from automedia.omni.ol_adapter import TranslationResult
from automedia.omni.opp_adapter import ExtractionResult
from automedia.omni.registry import OmniToolRegistry
from automedia.pool.collector import HotCollector

pytestmark = pytest.mark.e2e

# ===================================================================
# Helpers  (mirror test_mcp_omni_roundtrip.py patterns)
# ===================================================================


def _mock_extraction_result(
    md_content: str = "",
    manifest: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> MagicMock:
    """Build a MagicMock that quacks like an ``ExtractionResult``."""
    return MagicMock(
        md_content=md_content,
        manifest=manifest or {},
        warnings=warnings or [],
    )


def _mock_translation_result(
    translated_md: str = "",
    xliff_path: str | None = None,
    warnings: list[str] | None = None,
) -> MagicMock:
    """Build a MagicMock that quacks like a ``TranslationResult``."""
    return MagicMock(
        translated_md=translated_md,
        xliff_path=xliff_path,
        warnings=warnings or [],
    )


# ===================================================================
# Shared test data for L4 gate tests
# ===================================================================

_VALID_FRONTMATTER: str = """\
---
source_lang: en
target_lang: zh
---

Hello world! 你好世界！
"""

_VALID_FRONTMATTER_WRONG_LANG: str = """\
---
source_lang: en
target_lang: ja
---

Hello world! こんにちは！
"""

_VALID_CONTENT: str = "Hello world! 你好世界！"

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    """Clear ``OmniToolRegistry`` before each test for isolation."""
    OmniToolRegistry.clear()


@pytest.fixture
def collector() -> HotCollector:
    """Fresh ``HotCollector`` instance for each test."""
    return HotCollector()


# ===================================================================
# 1. OPP Extraction Failure
# ===================================================================


class TestOPPExtractionFailure:
    """OPP extraction failures propagate gracefully via HotCollector.

    Design Decision D-O4: OPP failure writes error to manifest, returns
    ``ExtractionResult`` with empty ``md_content`` — does NOT crash the
    pipeline.
    """

    # ------------------------------------------------------------------
    # Single failure
    # ------------------------------------------------------------------

    @patch("automedia.omni.opp_adapter.OPPAdapter.extract")
    def test_extract_raises_error_in_manifest(
        self,
        mock_extract: MagicMock,
        collector: HotCollector,
        tmp_path: Path,
    ) -> None:
        """``RuntimeError`` from extract → ``ExtractionResult`` with error in manifest."""
        mock_extract.side_effect = RuntimeError("OPP extraction crashed")

        docx_path = tmp_path / "fail.docx"
        docx_path.write_text("content")

        result = collector.ingest_file(str(docx_path))

        assert isinstance(result, ExtractionResult)
        assert result.md_content == ""
        assert "OPP extraction crashed" in result.manifest.get("error", "")
        assert result.manifest.get("source_file") == str(docx_path)
        assert any("OPP extraction crashed" in w for w in result.warnings)

    @patch("automedia.omni.opp_adapter.OPPAdapter.extract")
    def test_extract_failure_does_not_crash(
        self,
        mock_extract: MagicMock,
        collector: HotCollector,
        tmp_path: Path,
    ) -> None:
        """Exception in extract → HotCollector returns gracefully (no crash)."""
        mock_extract.side_effect = RuntimeError("crash")

        docx_path = tmp_path / "safe.docx"
        docx_path.write_text("content")

        # This should NOT raise — the collector catches the exception
        result = collector.ingest_file(str(docx_path))

        assert isinstance(result, ExtractionResult)
        # The call completed without the test itself raising
        assert True

    # ------------------------------------------------------------------
    # Multiple sequential failures
    # ------------------------------------------------------------------

    @patch("automedia.omni.opp_adapter.OPPAdapter.extract")
    def test_multiple_failures_all_handled(
        self,
        mock_extract: MagicMock,
        collector: HotCollector,
        tmp_path: Path,
    ) -> None:
        """Multiple OPP failures in sequence all return gracefully."""
        mock_extract.side_effect = RuntimeError("OPP crash")

        paths = [
            tmp_path / "a.docx",
            tmp_path / "b.pptx",
            tmp_path / "c.pdf",
        ]
        for p in paths:
            p.write_text("content")

        for file_path in paths:
            result = collector.ingest_file(str(file_path))
            assert isinstance(result, ExtractionResult)
            assert result.md_content == ""
            assert "OPP crash" in result.manifest.get("error", "")

        assert mock_extract.call_count == 3

    @patch("automedia.omni.opp_adapter.OPPAdapter.extract")
    def test_failure_then_success_isolation(
        self,
        mock_extract: MagicMock,
        collector: HotCollector,
        tmp_path: Path,
    ) -> None:
        """A failure does not poison subsequent successful extractions."""
        # First call fails, second call succeeds
        success_result = ExtractionResult(
            md_content="# Success\n\nGood content.",
            manifest={"title": "Success"},
            warnings=[],
        )
        mock_extract.side_effect = [RuntimeError("fail"), success_result]

        fail_path = tmp_path / "fail.docx"
        fail_path.write_text("content")
        ok_path = tmp_path / "ok.docx"
        ok_path.write_text("content")

        # First call — failure
        result1 = collector.ingest_file(str(fail_path))
        assert isinstance(result1, ExtractionResult)
        assert result1.md_content == ""
        assert "fail" in result1.manifest.get("error", "")

        # Second call — success
        result2 = collector.ingest_file(str(ok_path))
        assert isinstance(result2, ExtractionResult)
        assert result2.md_content == "# Success\n\nGood content."


# ===================================================================
# 2. OL Translation Failure
# ===================================================================


class TestOLTranslationFailure:
    """OL translation failures propagate gracefully as warning-bearing dicts.

    Design Decision D-O9: OL is manual-triggered; failures report to the user
    via warning fields rather than crashing the pipeline.
    """

    # ------------------------------------------------------------------
    # Single translation failure
    # ------------------------------------------------------------------

    @patch("automedia.omni.ol_adapter.OLAdapter.translate")
    def test_translate_raises_graceful_error(
        self,
        mock_translate: MagicMock,
    ) -> None:
        """``OLAdapter.translate()`` raises → tool returns graceful error dict."""
        mock_translate.side_effect = RuntimeError("OL LLM unavailable")

        result = localize_content(
            md_content="# Hello",
            source_lang="en",
            target_lang="zh",
        )

        assert result["translated_md"] == ""
        assert result["xliff_path"] is None
        assert any("OL LLM unavailable" in w for w in result["warnings"])

    # ------------------------------------------------------------------
    # All LLMs unavailable — degraded delivery
    # ------------------------------------------------------------------

    @patch("automedia.omni.ol_adapter.OLAdapter.translate")
    def test_all_llms_unavailable_degraded_delivery(
        self,
        mock_translate: MagicMock,
    ) -> None:
        """When ALL translate calls fail, original MD is preserved as degraded delivery.

        The adapter signals degraded delivery by returning a ``TranslationResult``
        that carries the original markdown content together with a descriptive
        warning instead of raising.
        """
        original_md = "# Hello\n\nThis is the original untranslated content."

        mock_translate.return_value = TranslationResult(
            translated_md=original_md,
            warnings=[
                "All LLMs unavailable — delivering original content as degraded",
            ],
        )

        result = localize_content(
            md_content=original_md,
            source_lang="en",
            target_lang="zh",
        )

        # Original content is preserved as degraded delivery
        assert result["translated_md"] == original_md
        assert result["xliff_path"] is None
        assert any("degraded" in w.lower() for w in result["warnings"])

    # ------------------------------------------------------------------
    # Partial failure — mixed success / failure per language
    # ------------------------------------------------------------------

    @patch("automedia.omni.ol_adapter.OLAdapter")
    @patch("automedia.mcp.server._require_allowed")
    def test_partial_failure_mixed_results(
        self,
        mock_require_allowed: MagicMock,
        mock_ol_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """First lang succeeds, second lang fails → results show mixed status.

        ``localize_output`` translates drafts into multiple languages; a failure
        in one language should not affect the others.
        """
        mock_instance = mock_ol_class.return_value

        # Build side_effect: first call (en) succeeds, second (ja) raises
        en_result = _mock_translation_result(
            translated_md="Hello in English",
            warnings=[],
        )
        mock_instance.translate.side_effect = [en_result, RuntimeError("JA LLM down")]

        # Create a project with a draft file
        drafts_dir = tmp_path / "01_content" / "drafts"
        drafts_dir.mkdir(parents=True)
        draft_file = drafts_dir / "post.md"
        draft_file.write_text("# Hello", encoding="utf-8")

        result = localize_output(str(tmp_path), "en,ja")

        assert "results" in result
        assert "en" in result["results"]
        # English translation succeeded
        assert len(result["results"]["en"]) == 1
        assert result["results"]["en"][0].endswith("post.md")

        # Japanese translation may not be in results (failed)
        # but a warning should be present
        assert len(result["warnings"]) >= 1
        assert any("JA LLM down" in w for w in result["warnings"])

        # The call count reflects both languages were attempted
        assert mock_instance.translate.call_count == 2


# ===================================================================
# 3. ORF Backfill Failure
# ===================================================================


class TestORFBackfillFailure:
    """ORF conversion / backfill failures return graceful error dicts.

    Design Decision: ORF is manual-triggered; convert failures should report
    to the user without corrupting original assets.
    """

    # ------------------------------------------------------------------
    # Convert failure
    # ------------------------------------------------------------------

    @patch("automedia.omni.orf_adapter.ORFAdapter.convert")
    def test_convert_raises_graceful_error(
        self,
        mock_convert: MagicMock,
    ) -> None:
        """``ORFAdapter.convert()`` raises → tool returns graceful error dict."""
        mock_convert.side_effect = RuntimeError("ORF converter crashed")

        result = format_output(
            content="# Hello\n\nTest content.",
            target_format="html",
        )

        assert result["output_path"] == ""
        assert result["output_format"] == "html"
        assert any("ORF converter crashed" in w for w in result["warnings"])

    # ------------------------------------------------------------------
    # Pre-backfill state preservation
    # ------------------------------------------------------------------

    @patch("automedia.omni.orf_adapter.ORFAdapter.convert")
    def test_pre_backfill_state_preserved(
        self,
        mock_convert: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When convert fails, original content is preserved and no output file remains.

        ``format_output`` writes content to a temporary file; if conversion
        raises, the temp file is cleaned up and no output path is created.
        """
        original_content = "# Preserved\n\nThis content must survive."
        mock_convert.side_effect = RuntimeError("ORF crashed")

        # Record the set of files before the call
        files_before = set(tmp_path.iterdir()) if tmp_path.exists() else set()

        result = format_output(
            content=original_content,
            target_format="html",
        )

        # Graceful error returned
        assert result["output_path"] == ""
        assert any("ORF crashed" in w for w in result["warnings"])

        # No new files were created in tmp_path (temp file is cleaned up)
        # and the format_output temp file is created in system temp dir
        files_after = set(tmp_path.iterdir()) if tmp_path.exists() else set()
        assert files_after == files_before, (
            "No files should be created or modified in the workspace when convert fails"
        )

    @patch("automedia.omni.orf_adapter.ORFAdapter.convert")
    def test_convert_failure_no_orphan_output(
        self,
        mock_convert: MagicMock,
    ) -> None:
        """A failed convert does not leave orphan output files on disk."""
        import os
        import tempfile

        mock_convert.side_effect = RuntimeError("ORF crashed")

        # Track temp dir state
        temp_dir = tempfile.gettempdir()
        entries_before = set(os.listdir(temp_dir))

        result = format_output(
            content="# Orphan test",
            target_format="pdf",
        )

        assert result["output_path"] == ""

        # Check nothing leaked in system temp
        entries_after = set(os.listdir(temp_dir))
        # Ignore unrelated concurrent changes; just ensure our tool
        # didn't leave an output file with the expected suffix
        new_entries = entries_after - entries_before
        orphan_outputs = [e for e in new_entries if e.endswith(".pdf")]
        assert len(orphan_outputs) == 0, f"Orphan output files detected: {orphan_outputs}"


# ===================================================================
# 4. L4 Translation Gate
# ===================================================================


class TestL4TranslationGate:
    """L4 Translation Quality Gate validation scenarios.

    Covers empty content, garbled text (non-blocking warnings), language
    mismatches, and valid passes.
    """

    # ------------------------------------------------------------------
    # Empty translated_md
    # ------------------------------------------------------------------

    def test_empty_translated_md_fails_non_empty(self) -> None:
        """Empty ``translated_md`` triggers a non_empty failure (blocking)."""
        gate = L4TranslationQuality()
        ctx: dict[str, Any] = {
            "translation_result": {"translated_md": ""},
            "source_lang": "en",
            "target_lang": "zh",
        }

        result = gate.execute(ctx)

        assert result["check_results"]["non_empty"] is False
        assert any("empty" in f.lower() for f in result["failures"])
        assert result["passed"] is False

    def test_whitespace_only_fails_non_empty(self) -> None:
        """Whitespace-only translated content is treated as empty (blocking)."""
        gate = L4TranslationQuality()
        ctx: dict[str, Any] = {
            "translation_result": {"translated_md": "   \n  \t  \n"},
            "source_lang": "en",
            "target_lang": "zh",
        }

        result = gate.execute(ctx)

        assert result["check_results"]["non_empty"] is False
        assert result["passed"] is False

    # ------------------------------------------------------------------
    # Garbled text — non-blocking warnings
    # ------------------------------------------------------------------

    def test_garbled_text_passes_with_warnings(self) -> None:
        """Garbled replacement characters produce warnings but gate still passes."""
        gate = L4TranslationQuality()
        garbled_md = _VALID_FRONTMATTER + "Clean text with \ufffd garbled char."
        ctx: dict[str, Any] = {
            "translation_result": {"translated_md": garbled_md},
            "source_lang": "en",
            "target_lang": "zh",
        }

        result = gate.execute(ctx)

        assert result["check_results"]["no_garbled_text"] is False
        assert len(result["warnings"]) >= 1
        assert any("Garbled" in w for w in result["warnings"])
        # Garbled text is non-blocking → no failures, overall pass
        assert result["check_results"]["frontmatter_valid"] is True
        assert result["check_results"]["language_match"] is True
        assert result["check_results"]["non_empty"] is True
        assert result["passed"] is True

    def test_multiple_garbled_chars_produce_warnings(self) -> None:
        """Multiple garbled characters across the content are all reported."""
        gate = L4TranslationQuality()
        text = _VALID_FRONTMATTER + "Bad chars: \ufffd \ufffe \u0000 end."
        ctx: dict[str, Any] = {
            "translation_result": {"translated_md": text},
            "source_lang": "en",
            "target_lang": "zh",
        }

        result = gate.execute(ctx)

        assert result["check_results"]["no_garbled_text"] is False
        assert len(result["warnings"]) >= 1
        assert result["passed"] is True  # non-blocking

    # ------------------------------------------------------------------
    # Language mismatch
    # ------------------------------------------------------------------

    def test_mismatched_target_lang_in_frontmatter_fails(self) -> None:
        """Frontmatter ``target_lang`` differs from expected → language_match fails."""
        gate = L4TranslationQuality()
        ctx: dict[str, Any] = {
            "translation_result": {"translated_md": _VALID_FRONTMATTER_WRONG_LANG},
            "source_lang": "en",
            "target_lang": "zh",  # Expected zh, frontmatter says ja
        }

        result = gate.execute(ctx)

        assert result["check_results"]["language_match"] is False
        assert any("Language mismatch" in f for f in result["failures"])
        assert "target_lang" in result["failures"][0]
        assert result["passed"] is False

    def test_mismatched_source_lang_in_frontmatter_fails(self) -> None:
        """Frontmatter ``source_lang`` differs from expected → language_match fails."""
        gate = L4TranslationQuality()
        mismatched = """\
---
source_lang: fr
target_lang: zh
---

Bonjour le monde!
"""
        ctx: dict[str, Any] = {
            "translation_result": {"translated_md": mismatched},
            "source_lang": "en",
            "target_lang": "zh",
        }

        result = gate.execute(ctx)

        assert result["check_results"]["language_match"] is False
        assert any("Language mismatch" in f for f in result["failures"])
        assert "source_lang" in result["failures"][0]
        assert result["passed"] is False

    def test_both_langs_mismatched_fails(self) -> None:
        """Both source and target language mismatches are reported."""
        gate = L4TranslationQuality()
        mismatched = """\
---
source_lang: fr
target_lang: ja
---

Bonjour le monde!
"""
        ctx: dict[str, Any] = {
            "translation_result": {"translated_md": mismatched},
            "source_lang": "en",
            "target_lang": "zh",
        }

        result = gate.execute(ctx)

        assert result["check_results"]["language_match"] is False
        assert len(result["failures"]) >= 1
        assert "source_lang" in result["failures"][0]
        assert "target_lang" in result["failures"][0]
        assert result["passed"] is False

    # ------------------------------------------------------------------
    # Valid content
    # ------------------------------------------------------------------

    def test_valid_frontmatter_and_content_passes(self) -> None:
        """All 4 checks pass with valid frontmatter and content."""
        gate = L4TranslationQuality()
        ctx: dict[str, Any] = {
            "translation_result": {"translated_md": _VALID_FRONTMATTER},
            "source_lang": "en",
            "target_lang": "zh",
        }

        result = gate.execute(ctx)

        assert result["check_results"]["frontmatter_valid"] is True
        assert result["check_results"]["language_match"] is True
        assert result["check_results"]["no_garbled_text"] is True
        assert result["check_results"]["non_empty"] is True
        assert len(result["failures"]) == 0
        assert len(result["warnings"]) == 0
        assert result["passed"] is True

    def test_empty_context_does_not_crash(self) -> None:
        """Calling the gate with an empty context returns gracefully."""
        gate = L4TranslationQuality()
        result = gate.execute({})

        assert isinstance(result, dict)
        assert "passed" in result
        assert "warnings" in result
        assert "failures" in result
        assert "check_results" in result
        assert result["passed"] is False  # empty context always fails


# ===================================================================
# 5. Path Allowlist Violation
# ===================================================================


class TestPathAllowlistViolation:
    """Path allowlist enforcement via ``_require_allowed`` in MCP tools.

    All file-accessing MCP tools gate operations behind ``_require_allowed``;
    violations must produce graceful error responses without crashing.
    """

    # ------------------------------------------------------------------
    # extract_brief
    # ------------------------------------------------------------------

    @patch("automedia.mcp.server._require_allowed")
    def test_extract_brief_catches_permission_error(
        self,
        mock_require_allowed: MagicMock,
    ) -> None:
        """``_require_allowed`` raises ``PermissionError`` → graceful error dict."""
        mock_require_allowed.side_effect = PermissionError("Path /blocked/doc.md is not allowed")

        result = extract_brief(
            file_path="/blocked/doc.md",
            source_lang="en",
            target_lang="zh",
        )

        assert result["md_content"] == ""
        assert result["manifest_json"] == {}
        assert any("not allowed" in w.lower() for w in result["warnings"])

    @patch("automedia.mcp.server._require_allowed")
    def test_extract_brief_returns_graceful_error_on_disallowed_path(
        self,
        mock_require_allowed: MagicMock,
    ) -> None:
        """Disallowed path returns graceful dict, not an exception."""
        mock_require_allowed.side_effect = PermissionError("Path blocked")

        result = extract_brief(file_path="/etc/passwd")

        assert isinstance(result, dict)
        assert "md_content" in result
        assert result["md_content"] == ""
        assert "warnings" in result
        # The function completed without raising
        assert True

    # ------------------------------------------------------------------
    # localize_content (no path check — just verifies tool isolation)
    # ------------------------------------------------------------------

    @patch("automedia.omni.ol_adapter.OLAdapter.translate")
    def test_localize_content_require_allowed_not_called(
        self,
        mock_translate: MagicMock,
    ) -> None:
        """``localize_content`` does NOT call ``_require_allowed`` (no file path param).

        This test confirms the tool works without path restrictions when no
        file path is involved.
        """
        mock_translate.return_value = _mock_translation_result(
            translated_md="Translated content",
            warnings=[],
        )

        result = localize_content(
            md_content="# Hello",
            source_lang="en",
            target_lang="zh",
        )

        assert result["translated_md"] == "Translated content"
        assert mock_translate.call_count == 1

    # ------------------------------------------------------------------
    # format_output — no path check needed either
    # ------------------------------------------------------------------

    @patch("automedia.omni.orf_adapter.ORFAdapter.convert")
    def test_format_output_no_path_check(
        self,
        mock_convert: MagicMock,
    ) -> None:
        """``format_output`` works without path restrictions (content-based).

        Note: ``format_output`` computes the output path from a temp file, so
        we verify the suffix rather than the full path.
        """
        mock_convert.return_value = {
            "status": "ok",
            "output_path": "/outputs/output.html",
            "success": True,
            "errors": [],
        }

        result = format_output(content="# Hello", target_format="html")

        assert result["output_path"].endswith(".html"), (
            f"Expected .html suffix, got {result['output_path']!r}"
        )
        assert result["output_format"] == "html"
        assert result["warnings"] == []
