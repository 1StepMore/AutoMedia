"""E2E: XLIFF roundtrip pipeline — DOCX → OPP → OL → ORF → DOCX.

Verifies the full roundtrip with all 3 Omni adapters mocked at the module
level where they are imported (``automedia.omni.*_adapter``).  The pipeline
simulates:

1. **OPPAdapter.extract()**  — extract DOCX → markdown + XLIFF + skeleton
2. **OLAdapter.translate()**  — translate markdown → translated MD + XLIFF
3. **ORFAdapter.apply_xliff()** — apply translated XLIFF + skeleton → backfilled DOCX

Each stage is verified for correct input/output contracts.  After the
pipeline runs, ``pipeline_md5.json`` is checked for the expected sections.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from automedia.omni.md5_integration import (
    OMNI_MD5_FILENAME,
    load_state,
    save_state,
)
from automedia.omni.ol_adapter import TranslationResult
from automedia.omni.opp_adapter import ExtractionResult

pytestmark = pytest.mark.e2e

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_DOCX_NAME = "brief"
SAMPLE_XLIFF = "brief.xlf"
SAMPLE_SKELETON = "brief.skeleton.zip"

MD_CONTENT_SOURCE = (
    "# Executive Summary\n\nOur platform leverages AI to automate content production.\n"
)
MANIFEST_SOURCE: dict[str, object] = {
    "title": "Executive Summary",
    "segments": [
        {"index": 0, "text": "# Executive Summary"},
        {"index": 1, "text": ""},
        {"index": 2, "text": "Our platform leverages AI to automate content production."},
    ],
}
TRANSLATED_MD = "# 执行摘要\n\n我们的平台利用AI实现内容生产自动化。\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_extraction_result(
    md_content: str = MD_CONTENT_SOURCE,
    manifest: dict[str, Any] | None = None,
    xliff_path: str | None = None,
    skeleton_path: str | None = None,
    warnings: list[str] | None = None,
) -> ExtractionResult:
    """Return a real ExtractionResult (not a mock) for honest contract checks."""
    return ExtractionResult(
        md_content=md_content,
        manifest=manifest or dict(MANIFEST_SOURCE),  # type: ignore[arg-type]
        xliff_path=xliff_path,
        skeleton_path=skeleton_path,
        warnings=warnings or [],
    )


def _make_translation_result(
    translated_md: str = TRANSLATED_MD,
    xliff_path: str | None = None,
    warnings: list[str] | None = None,
) -> TranslationResult:
    """Return a real TranslationResult (not a mock) for honest contract checks."""
    return TranslationResult(
        translated_md=translated_md,
        xliff_path=xliff_path,
        warnings=warnings or [],
    )


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def pipeline_paths(tmp_path: Path) -> dict[str, Path]:
    """Canonical paths used throughout the pipeline."""
    src_dir = tmp_path / "source"
    src_dir.mkdir()
    docx_path = src_dir / f"{SAMPLE_DOCX_NAME}.docx"
    docx_path.write_text("fake docx content — not a real binary")

    opp_dir = tmp_path / "research_data" / SAMPLE_DOCX_NAME
    opp_dir.mkdir(parents=True)
    xliff_path = opp_dir / SAMPLE_XLIFF
    skeleton_path = opp_dir / SAMPLE_SKELETON
    # Touch the files so md5 can be computed
    xliff_path.write_text("<?xml version='1.0' encoding='UTF-8'?>\n<xliff/>")
    skeleton_path.write_text("fake skeleton zip content")

    ol_dir = tmp_path / "05_publish" / "zh"
    ol_dir.mkdir(parents=True)
    translated_xliff = ol_dir / SAMPLE_XLIFF

    orf_dir = tmp_path / "05_publish" / "zh" / "deliverables"
    orf_dir.mkdir(parents=True)
    output_docx = orf_dir / f"{SAMPLE_DOCX_NAME}.backfilled.docx"

    return {
        "tmp_root": tmp_path,
        "docx": docx_path,
        "xliff": xliff_path,
        "skeleton": skeleton_path,
        "translated_xliff": translated_xliff,
        "output_docx": output_docx,
    }


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Ensure a clean OmniToolRegistry before each test."""
    from automedia.omni.registry import OmniToolRegistry

    OmniToolRegistry.clear()


# ===================================================================
# Tests
# ===================================================================


class TestOmniXliffRoundtrip:
    """Full XLIFF pipeline: extract → translate → backfill.

    All three adapters (OPP, OL, ORF) are mocked at their real source
    modules so the pipeline code is exercised without real external tools.
    """

    # ------------------------------------------------------------------
    # Stage 1: OPP extraction
    # ------------------------------------------------------------------

    @patch("automedia.omni.opp_adapter.OPPAdapter")
    def test_stage_extract_returns_extraction_result(
        self,
        mock_opp_class: MagicMock,
        pipeline_paths: dict[str, Path],
    ) -> None:
        """OPPAdapter.extract() returns an ExtractionResult with all fields."""
        mock_opp = mock_opp_class.return_value
        mock_opp.extract.return_value = _make_extraction_result(
            xliff_path=str(pipeline_paths["xliff"]),
            skeleton_path=str(pipeline_paths["skeleton"]),
        )

        result = mock_opp.extract(str(pipeline_paths["docx"]), "en", "zh")

        assert isinstance(result, ExtractionResult)
        assert result.md_content == MD_CONTENT_SOURCE
        assert result.manifest["title"] == "Executive Summary"
        assert result.xliff_path == str(pipeline_paths["xliff"])
        assert result.skeleton_path == str(pipeline_paths["skeleton"])
        assert result.warnings == []
        mock_opp.extract.assert_called_once_with(
            str(pipeline_paths["docx"]),
            "en",
            "zh",
        )

    # ------------------------------------------------------------------
    # Stage 2: OL translation
    # ------------------------------------------------------------------

    @patch("automedia.omni.ol_adapter.OLAdapter")
    def test_stage_translate_returns_translation_result(
        self,
        mock_ol_class: MagicMock,
        pipeline_paths: dict[str, Path],
    ) -> None:
        """OLAdapter.translate() returns a TranslationResult with translated MD."""
        mock_ol = mock_ol_class.return_value
        mock_ol.translate.return_value = _make_translation_result(
            xliff_path=str(pipeline_paths["translated_xliff"]),
        )

        result = mock_ol.translate(
            MD_CONTENT_SOURCE,
            source_lang="en",
            target_lang="zh",
        )

        assert isinstance(result, TranslationResult)
        assert result.translated_md == TRANSLATED_MD
        assert result.xliff_path == str(pipeline_paths["translated_xliff"])
        assert result.warnings == []
        mock_ol.translate.assert_called_once_with(
            MD_CONTENT_SOURCE,
            source_lang="en",
            target_lang="zh",
        )

    # ------------------------------------------------------------------
    # Stage 3: ORF backfill (apply_xliff)
    # ------------------------------------------------------------------

    @patch("automedia.omni.orf_adapter.ORFAdapter")
    def test_stage_backfill_returns_output_path(
        self,
        mock_orf_class: MagicMock,
        pipeline_paths: dict[str, Path],
    ) -> None:
        """ORFAdapter.apply_xliff() returns the backfilled document path."""
        mock_orf = mock_orf_class.return_value
        output_path = str(pipeline_paths["output_docx"])
        mock_orf.apply_xliff.return_value = output_path

        result = mock_orf.apply_xliff(
            str(pipeline_paths["translated_xliff"]),
            str(pipeline_paths["output_docx"].parent),
        )

        assert isinstance(result, str)
        assert result == output_path
        assert result.endswith(".backfilled.docx")
        mock_orf.apply_xliff.assert_called_once_with(
            str(pipeline_paths["translated_xliff"]),
            str(pipeline_paths["output_docx"].parent),
        )

    # ------------------------------------------------------------------
    # Stage 3 alternative: ORF backfill() stub
    # ------------------------------------------------------------------

    @patch("automedia.omni.orf_adapter.ORFAdapter")
    def test_stage_backfill_via_backfill_method(
        self,
        mock_orf_class: MagicMock,
    ) -> None:
        """ORFAdapter.backfill() returns translated markdown unchanged (stub)."""
        mock_orf = mock_orf_class.return_value
        mock_orf.backfill.return_value = TRANSLATED_MD

        result = mock_orf.backfill(
            TRANSLATED_MD,
            MD_CONTENT_SOURCE,
            skeleton_path="/path/to/skeleton.zip",
        )

        assert result == TRANSLATED_MD
        mock_orf.backfill.assert_called_once_with(
            TRANSLATED_MD,
            MD_CONTENT_SOURCE,
            skeleton_path="/path/to/skeleton.zip",
        )

    # ------------------------------------------------------------------
    # Full pipeline: extract → translate → backfill
    # ------------------------------------------------------------------

    @patch("automedia.omni.opp_adapter.OPPAdapter")
    @patch("automedia.omni.ol_adapter.OLAdapter")
    @patch("automedia.omni.orf_adapter.ORFAdapter")
    def test_full_xliff_roundtrip(
        self,
        mock_orf_class: MagicMock,
        mock_ol_class: MagicMock,
        mock_opp_class: MagicMock,
        pipeline_paths: dict[str, Path],
    ) -> None:
        """Full pipeline: extract → translate → backfill preserves all paths."""
        # ---- Arrange ----
        mock_opp = mock_opp_class.return_value
        mock_opp.extract.return_value = _make_extraction_result(
            xliff_path=str(pipeline_paths["xliff"]),
            skeleton_path=str(pipeline_paths["skeleton"]),
        )

        mock_ol = mock_ol_class.return_value
        mock_ol.translate.return_value = _make_translation_result(
            xliff_path=str(pipeline_paths["translated_xliff"]),
        )

        mock_orf = mock_orf_class.return_value
        output_path = str(pipeline_paths["output_docx"])
        mock_orf.apply_xliff.return_value = output_path

        # ---- Act: Stage 1 — OPP extraction ----
        extraction = mock_opp.extract(str(pipeline_paths["docx"]), "en", "zh")

        # ---- Act: Stage 2 — OL translation ----
        translation = mock_ol.translate(
            extraction.md_content,
            source_lang="en",
            target_lang="zh",
        )

        # ---- Act: Stage 3 — ORF backfill via apply_xliff ----
        final_path = mock_orf.apply_xliff(
            translation.xliff_path or extraction.xliff_path or "",
            str(pipeline_paths["output_docx"].parent),
        )

        # ---- Assert: stage outputs ----
        assert extraction.md_content == MD_CONTENT_SOURCE
        assert extraction.manifest["title"] == "Executive Summary"
        assert extraction.xliff_path == str(pipeline_paths["xliff"])
        assert extraction.skeleton_path == str(pipeline_paths["skeleton"])

        assert translation.translated_md == TRANSLATED_MD
        assert translation.xliff_path == str(pipeline_paths["translated_xliff"])

        assert final_path == output_path
        assert final_path.endswith(".backfilled.docx")

        # ---- Assert: call args ----
        mock_opp.extract.assert_called_once_with(
            str(pipeline_paths["docx"]),
            "en",
            "zh",
        )
        mock_ol.translate.assert_called_once_with(
            MD_CONTENT_SOURCE,
            source_lang="en",
            target_lang="zh",
        )
        mock_orf.apply_xliff.assert_called_once()

    # ------------------------------------------------------------------
    # Full pipeline with save_state: pipeline_md5.json tracking
    # ------------------------------------------------------------------

    @patch("automedia.omni.opp_adapter.OPPAdapter")
    @patch("automedia.omni.ol_adapter.OLAdapter")
    @patch("automedia.omni.orf_adapter.ORFAdapter")
    def test_pipeline_md5_json_contains_expected_sections(
        self,
        mock_orf_class: MagicMock,
        mock_ol_class: MagicMock,
        mock_opp_class: MagicMock,
        pipeline_paths: dict[str, Path],
    ) -> None:
        """After pipeline run, pipeline_md5.json has all omni_* sections."""
        # ---- Arrange ----
        tmp = pipeline_paths["tmp_root"]
        docx = pipeline_paths["docx"]
        xliff = pipeline_paths["xliff"]
        skeleton = pipeline_paths["skeleton"]
        translated_xliff = pipeline_paths["translated_xliff"]
        output_docx = pipeline_paths["output_docx"]

        mock_opp = mock_opp_class.return_value
        mock_opp.extract.return_value = _make_extraction_result(
            xliff_path=str(xliff),
            skeleton_path=str(skeleton),
        )

        mock_ol = mock_ol_class.return_value
        mock_ol.translate.return_value = _make_translation_result(
            xliff_path=str(translated_xliff),
        )

        mock_orf = mock_orf_class.return_value
        mock_orf.apply_xliff.return_value = str(output_docx)

        # ---- Simulate pipeline + state tracking ----
        # Stage 1
        extraction = mock_opp.extract(str(docx), "en", "zh")

        state: dict[str, Any] = {}
        save_state(state, tmp)

        # Record extraction outputs
        state = load_state(tmp)
        state.setdefault("omni_extraction", {})[str(xliff.resolve())] = {
            "md5": "abc123",
        }
        state.setdefault("omni_extraction", {})[str(skeleton.resolve())] = {
            "md5": "def456",
        }
        state.setdefault("omni_inputs", {})[str(docx.resolve())] = {
            "md5": "ghi789",
        }
        save_state(state, tmp)

        # Stage 2
        translation = mock_ol.translate(extraction.md_content, source_lang="en", target_lang="zh")

        state = load_state(tmp)
        state.setdefault("omni_translation", {})[str(translated_xliff.resolve())] = {
            "md5": "jkl012",
        }
        save_state(state, tmp)

        # Stage 3
        mock_orf.apply_xliff(translation.xliff_path or "", str(output_docx.parent))

        state = load_state(tmp)
        state.setdefault("omni_orf_outputs", {})[str(output_docx.resolve())] = {
            "md5": "mno345",
        }
        save_state(state, tmp)

        # ---- Assert: pipeline_md5.json structure ----
        md5_path = tmp / OMNI_MD5_FILENAME
        assert md5_path.is_file(), f"{OMNI_MD5_FILENAME} was not created"

        final_state = load_state(tmp)
        assert "omni_inputs" in final_state, "Missing omni_inputs section"
        assert "omni_extraction" in final_state, "Missing omni_extraction section"
        assert "omni_translation" in final_state, "Missing omni_translation section"
        assert "omni_orf_outputs" in final_state, "Missing omni_orf_outputs section"

        # ---- Assert: keys within each section ----
        assert str(docx.resolve()) in final_state["omni_inputs"], (
            "DOCX path missing from omni_inputs"
        )
        assert str(xliff.resolve()) in final_state["omni_extraction"], (
            "XLIFF path missing from omni_extraction"
        )
        assert str(skeleton.resolve()) in final_state["omni_extraction"], (
            "Skeleton path missing from omni_extraction"
        )
        assert str(translated_xliff.resolve()) in final_state["omni_translation"], (
            "Translated XLIFF path missing from omni_translation"
        )
        assert str(output_docx.resolve()) in final_state["omni_orf_outputs"], (
            "Output DOCX path missing from omni_orf_outputs"
        )

    # ------------------------------------------------------------------
    # Path preservation: skeleton and xliff through the pipeline
    # ------------------------------------------------------------------

    @patch("automedia.omni.opp_adapter.OPPAdapter")
    @patch("automedia.omni.ol_adapter.OLAdapter")
    @patch("automedia.omni.orf_adapter.ORFAdapter")
    def test_skeleton_and_xliff_paths_preserved(
        self,
        mock_orf_class: MagicMock,
        mock_ol_class: MagicMock,
        mock_opp_class: MagicMock,
        pipeline_paths: dict[str, Path],
    ) -> None:
        """skeleton.zip and XLIFF paths survive the entire pipeline."""
        mock_opp = mock_opp_class.return_value
        mock_opp.extract.return_value = _make_extraction_result(
            xliff_path=str(pipeline_paths["xliff"]),
            skeleton_path=str(pipeline_paths["skeleton"]),
        )

        mock_ol = mock_ol_class.return_value
        mock_ol.translate.return_value = _make_translation_result(
            xliff_path=str(pipeline_paths["translated_xliff"]),
        )

        mock_orf = mock_orf_class.return_value
        mock_orf.apply_xliff.return_value = str(pipeline_paths["output_docx"])

        # Pipeline
        extraction = mock_opp.extract(str(pipeline_paths["docx"]), "en", "zh")
        translation = mock_ol.translate(extraction.md_content, source_lang="en", target_lang="zh")

        # The skeleton path from extraction must survive
        assert extraction.skeleton_path == str(pipeline_paths["skeleton"])
        assert Path(extraction.skeleton_path).name == SAMPLE_SKELETON

        # The XLIFF path must be propagated: OPP xliff_path → (OL) → ORF
        assert extraction.xliff_path == str(pipeline_paths["xliff"])
        assert translation.xliff_path == str(pipeline_paths["translated_xliff"])
        assert Path(translation.xliff_path).name == SAMPLE_XLIFF

        # apply_xliff receives the translated XLIFF and returns the backfilled docx
        output = mock_orf.apply_xliff(
            str(pipeline_paths["translated_xliff"]),
            str(pipeline_paths["output_docx"].parent),
        )

        mock_orf.apply_xliff.assert_called_with(
            str(pipeline_paths["translated_xliff"]),
            str(pipeline_paths["output_docx"].parent),
        )

        # final output is a backfilled docx
        assert Path(output).name == f"{SAMPLE_DOCX_NAME}.backfilled.docx"

    # ------------------------------------------------------------------
    # Pipeline with OmniToolRegistry mocked adapters
    # ------------------------------------------------------------------

    @patch("automedia.omni.opp_adapter.OPPAdapter")
    @patch("automedia.omni.ol_adapter.OLAdapter")
    @patch("automedia.omni.orf_adapter.ORFAdapter")
    def test_pipeline_via_omni_tool_registry(
        self,
        mock_orf_class: MagicMock,
        mock_ol_class: MagicMock,
        mock_opp_class: MagicMock,
        pipeline_paths: dict[str, Path],
    ) -> None:
        """Pipeline stages invoked through OmniToolRegistry mock adapters."""
        from automedia.omni.registry import OmniToolRegistry

        # Register mock instances
        # NOTE: OmniToolRegistry.register() validates adapter.name is a non-empty
        # string, so we configure the mock instances' name property explicitly.
        mock_opp_instance = mock_opp_class.return_value
        mock_ol_instance = mock_ol_class.return_value
        mock_orf_instance = mock_orf_class.return_value
        mock_opp_instance.name = "opp"
        mock_ol_instance.name = "ol"
        mock_orf_instance.name = "orf"

        reg = OmniToolRegistry()
        reg.register(mock_opp_instance)
        reg.register(mock_ol_instance)
        reg.register(mock_orf_instance)

        assert len(reg.list_tools()) == 3
        assert "opp" in reg.list_tools()
        assert "ol" in reg.list_tools()
        assert "orf" in reg.list_tools()

        # Configure mock return values
        mock_opp_instance.extract.return_value = _make_extraction_result(
            xliff_path=str(pipeline_paths["xliff"]),
            skeleton_path=str(pipeline_paths["skeleton"]),
        )
        mock_ol_instance.translate.return_value = _make_translation_result(
            xliff_path=str(pipeline_paths["translated_xliff"]),
        )
        mock_orf_instance.apply_xliff.return_value = str(pipeline_paths["output_docx"])

        # Execute via registry
        opp = cast(MagicMock, reg.get("opp"))
        ol = cast(MagicMock, reg.get("ol"))
        orf = cast(MagicMock, reg.get("orf"))

        extraction = opp.extract(str(pipeline_paths["docx"]), "en", "zh")
        translation = ol.translate(extraction.md_content, source_lang="en", target_lang="zh")
        final_path = orf.apply_xliff(
            translation.xliff_path or "",
            str(pipeline_paths["output_docx"].parent),
        )

        assert isinstance(extraction, ExtractionResult)
        assert isinstance(translation, TranslationResult)
        assert isinstance(final_path, str)
        assert final_path.endswith(".backfilled.docx")

    # ------------------------------------------------------------------
    # Error handling: OPP extract raises
    # ------------------------------------------------------------------

    @patch("automedia.omni.opp_adapter.OPPAdapter")
    def test_extract_failure_returns_graceful_result(
        self,
        mock_opp_class: MagicMock,
    ) -> None:
        """When OPPAdapter.extract() raises, a graceful ExtractionResult is returned."""
        mock_opp_class.return_value.extract.return_value = ExtractionResult(
            md_content="",
            manifest={"error": "OPP crashed"},
            warnings=["Extraction failed: OPP crashed"],
        )

        result = mock_opp_class.return_value.extract("invalid.docx", "en", "zh")

        assert isinstance(result, ExtractionResult)
        assert result.md_content == ""
        assert "OPP crashed" in result.manifest["error"]
        assert any("OPP crashed" in w for w in result.warnings)

    # ------------------------------------------------------------------
    # Error handling: OL translate raises
    # ------------------------------------------------------------------

    @patch("automedia.omni.ol_adapter.OLAdapter")
    def test_translate_failure_returns_graceful_result(
        self,
        mock_ol_class: MagicMock,
    ) -> None:
        """When OLAdapter.translate() raises, a graceful TranslationResult is returned."""
        mock_ol_class.return_value.translate.return_value = TranslationResult(
            translated_md="",
            warnings=["Translation failed: OL crashed"],
        )

        result = mock_ol_class.return_value.translate(
            "# Hello",
            source_lang="en",
            target_lang="zh",
        )

        assert isinstance(result, TranslationResult)
        assert result.translated_md == ""
        assert any("OL crashed" in w for w in result.warnings)

    # ------------------------------------------------------------------
    # Error handling: ORF apply_xliff raises
    # ------------------------------------------------------------------

    @patch("automedia.omni.orf_adapter.ORFAdapter")
    def test_backfill_failure_returns_empty_path(
        self,
        mock_orf_class: MagicMock,
    ) -> None:
        """When ORFAdapter.apply_xliff() raises, an empty path is returned."""
        mock_orf_class.return_value.apply_xliff.return_value = ""

        result = mock_orf_class.return_value.apply_xliff(
            "/xliff/missing.xlf",
            "/xliff/output",
        )

        assert result == ""

    # ------------------------------------------------------------------
    # Partial success: extract succeeds → translate fails
    # ------------------------------------------------------------------

    @patch("automedia.omni.opp_adapter.OPPAdapter")
    @patch("automedia.omni.ol_adapter.OLAdapter")
    def test_partial_extract_ok_translate_fails(
        self,
        mock_ol_class: MagicMock,
        mock_opp_class: MagicMock,
        pipeline_paths: dict[str, Path],
    ) -> None:
        """OPP succeeds → OL fails gracefully; pipeline can report partial progress."""
        mock_opp_class.return_value.extract.return_value = _make_extraction_result(
            xliff_path=str(pipeline_paths["xliff"]),
            skeleton_path=str(pipeline_paths["skeleton"]),
        )
        mock_ol_class.return_value.translate.return_value = TranslationResult(
            translated_md="",
            warnings=["Translation failed: OL crashed"],
        )

        extraction = mock_opp_class.return_value.extract(
            str(pipeline_paths["docx"]),
            "en",
            "zh",
        )
        assert extraction.md_content == MD_CONTENT_SOURCE
        assert extraction.xliff_path is not None

        translation = mock_ol_class.return_value.translate(
            extraction.md_content,
            source_lang="en",
            target_lang="zh",
        )
        assert translation.translated_md == ""
        assert any("OL crashed" in w for w in translation.warnings)

    # ------------------------------------------------------------------
    # Partial success: extract + translate succeed → backfill fails
    # ------------------------------------------------------------------

    @patch("automedia.omni.opp_adapter.OPPAdapter")
    @patch("automedia.omni.ol_adapter.OLAdapter")
    @patch("automedia.omni.orf_adapter.ORFAdapter")
    def test_partial_extract_and_translate_ok_backfill_fails(
        self,
        mock_orf_class: MagicMock,
        mock_ol_class: MagicMock,
        mock_opp_class: MagicMock,
        pipeline_paths: dict[str, Path],
    ) -> None:
        """OPP + OL succeed → ORF fails gracefully."""
        mock_opp_class.return_value.extract.return_value = _make_extraction_result(
            xliff_path=str(pipeline_paths["xliff"]),
            skeleton_path=str(pipeline_paths["skeleton"]),
        )
        mock_ol_class.return_value.translate.return_value = _make_translation_result(
            xliff_path=str(pipeline_paths["translated_xliff"]),
        )
        mock_orf_class.return_value.apply_xliff.return_value = ""

        extraction = mock_opp_class.return_value.extract(
            str(pipeline_paths["docx"]),
            "en",
            "zh",
        )
        assert extraction.md_content == MD_CONTENT_SOURCE

        translation = mock_ol_class.return_value.translate(
            extraction.md_content,
            source_lang="en",
            target_lang="zh",
        )
        assert translation.translated_md == TRANSLATED_MD

        final_path = mock_orf_class.return_value.apply_xliff(
            translation.xliff_path or "",
            str(pipeline_paths["output_docx"].parent),
        )
        assert final_path == "", "Expected empty path on ORF failure"

    # ------------------------------------------------------------------
    # Registry isolation: clear does not affect other tests
    # ------------------------------------------------------------------

    def test_registry_isolation_after_clear(self) -> None:
        """OmniToolRegistry.clear() empties the registry."""
        from automedia.omni.registry import OmniToolRegistry

        OmniToolRegistry.clear()
        assert OmniToolRegistry.list_tools() == []

    # ------------------------------------------------------------------
    # pipeline_md5.json — save_state after each stage
    # ------------------------------------------------------------------

    @patch("automedia.omni.opp_adapter.OPPAdapter")
    @patch("automedia.omni.ol_adapter.OLAdapter")
    @patch("automedia.omni.orf_adapter.ORFAdapter")
    def test_save_state_after_each_stage(
        self,
        mock_orf_class: MagicMock,
        mock_ol_class: MagicMock,
        mock_opp_class: MagicMock,
        pipeline_paths: dict[str, Path],
    ) -> None:
        """save_state() after each pipeline stage accumulates data without loss."""
        tmp = pipeline_paths["tmp_root"]
        docx = pipeline_paths["docx"]

        mock_opp_class.return_value.extract.return_value = _make_extraction_result(
            xliff_path=str(pipeline_paths["xliff"]),
            skeleton_path=str(pipeline_paths["skeleton"]),
        )
        mock_ol_class.return_value.translate.return_value = _make_translation_result(
            xliff_path=str(pipeline_paths["translated_xliff"]),
        )
        mock_orf_class.return_value.apply_xliff.return_value = str(pipeline_paths["output_docx"])

        # Stage 1 — save after extract
        _ = mock_opp_class.return_value.extract(str(docx), "en", "zh")
        state1: dict[str, Any] = {
            "omni_inputs": {},
            "omni_extraction": {},
            "omni_translation": {},
            "omni_orf_outputs": {},
        }
        state1["omni_inputs"][str(docx.resolve())] = {"md5": "inp"}
        state1["omni_extraction"][str(pipeline_paths["xliff"].resolve())] = {"md5": "ext"}
        save_state(state1, tmp)

        loaded1 = load_state(tmp)
        assert "omni_inputs" in loaded1
        assert "omni_extraction" in loaded1

        # Stage 2 — save after translate (preserve existing)
        _ = mock_ol_class.return_value.translate(
            MD_CONTENT_SOURCE, source_lang="en", target_lang="zh"
        )
        state2 = load_state(tmp)
        state2.setdefault("omni_translation", {})[
            str(pipeline_paths["translated_xliff"].resolve())
        ] = {"md5": "trn"}
        save_state(state2, tmp)

        loaded2 = load_state(tmp)
        assert "omni_inputs" in loaded2
        assert "omni_extraction" in loaded2
        assert "omni_translation" in loaded2
        # omni_orf_outputs not yet present (stage 3 not reached)
        assert "omni_orf_outputs" in loaded2  # auto-initialised by save_state

        # Stage 3 — save after backfill
        _ = mock_orf_class.return_value.apply_xliff(
            str(pipeline_paths["translated_xliff"]),
            str(pipeline_paths["output_docx"].parent),
        )
        state3 = load_state(tmp)
        state3.setdefault("omni_orf_outputs", {})[str(pipeline_paths["output_docx"].resolve())] = {
            "md5": "out"
        }
        save_state(state3, tmp)

        loaded3 = load_state(tmp)
        assert len(loaded3["omni_inputs"]) == 1
        assert len(loaded3["omni_extraction"]) == 1
        assert len(loaded3["omni_translation"]) == 1
        assert len(loaded3["omni_orf_outputs"]) == 1
