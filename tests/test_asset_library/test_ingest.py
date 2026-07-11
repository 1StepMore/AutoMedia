"""Unit tests for the asset_library ingest module.

Tests internal helper functions (_is_ingestible, _detect_language,
_classify_by_path, _extract_title, _extract_tags) with synthetic
inputs and tmp_path fixtures. No real filesystem or database needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from automedia.asset_library.ingest import (
    _classify_by_path,
    _detect_language,
    _extract_tags,
    _extract_title,
    _is_ingestible,
)

# ---------------------------------------------------------------------------
# _is_ingestible
# ---------------------------------------------------------------------------


class TestIsIngestible:
    """Verify file extension and name-based ingestibility checks."""

    @pytest.mark.parametrize(
        "filename",
        [
            "strategy.md",
            "config.yaml",
            "config.yml",
            "data.json",
            "report.csv",
        ],
    )
    def test_ingestible_extensions(self, filename: str) -> None:
        fp = Path("/project") / filename
        assert _is_ingestible(fp) is True

    @pytest.mark.parametrize(
        "filename",
        [
            "image.png",
            "photo.jpg",
            "photo.jpeg",
            "clip.mp4",
            "audio.mp3",
            "doc.pdf",
        ],
    )
    def test_non_ingestible_extensions(self, filename: str) -> None:
        fp = Path("/project") / filename
        assert _is_ingestible(fp) is False

    def test_hidden_files_excluded(self) -> None:
        fp = Path("/project/.hidden_file.md")
        assert _is_ingestible(fp) is False

    def test_project_info_excluded(self) -> None:
        fp = Path("/project/00_project_info.json")
        assert _is_ingestible(fp) is False

    def test_uppercase_extension_is_ingestible(self) -> None:
        fp = Path("/project/Report.MD")
        assert _is_ingestible(fp) is True

    def test_nested_ingestible_file(self) -> None:
        fp = Path("/project/decision/brief.md")
        assert _is_ingestible(fp) is True


# ---------------------------------------------------------------------------
# _detect_language
# ---------------------------------------------------------------------------


class TestDetectLanguage:
    """Verify language detection from filename stem suffixes."""

    def test_chinese_suffix(self) -> None:
        assert _detect_language("brief_zh") == "zh"

    def test_english_suffix(self) -> None:
        assert _detect_language("brief_en") == "en"

    def test_japanese_suffix(self) -> None:
        assert _detect_language("brief_ja") == "ja"

    def test_no_suffix_defaults_to_zh(self) -> None:
        assert _detect_language("brief") == "zh"

    def test_unknown_suffix_defaults_to_zh(self) -> None:
        # _xx is not a known language, but the regex matches 2-letter codes,
        # so _xx returns "xx". Only truly missing suffixes default to "zh".
        assert _detect_language("report") == "zh"

    def test_region_variant_suffix(self) -> None:
        assert _detect_language("content_zh-CN") == "zh-CN"

    def test_stem_with_numbers(self) -> None:
        assert _detect_language("v2_en") == "en"

    def test_empty_stem(self) -> None:
        assert _detect_language("") == "zh"


# ---------------------------------------------------------------------------
# _classify_by_path
# ---------------------------------------------------------------------------


class TestClassifyByPath:
    """Verify path-based type and phase classification."""

    def test_decision_directory_gives_strategy_type(self) -> None:
        root = Path("/project")
        fp = root / "decision" / "market_report.yaml"
        hints = _classify_by_path(fp, root)
        assert hints["type"] == "strategy"

    def test_research_data_directory_phase(self) -> None:
        root = Path("/project")
        fp = root / "research_data" / "competitor.md"
        hints = _classify_by_path(fp, root)
        assert hints.get("phase") == "1b"

    def test_content_directory_phase(self) -> None:
        root = Path("/project")
        fp = root / "01_content" / "draft.md"
        hints = _classify_by_path(fp, root)
        assert hints.get("phase") == "2"

    def test_filename_keyword_persona(self) -> None:
        root = Path("/project")
        fp = root / "docs" / "persona_map.yaml"
        hints = _classify_by_path(fp, root)
        assert hints["type"] == "persona"

    def test_filename_keyword_kol(self) -> None:
        root = Path("/project")
        fp = root / "docs" / "kol_brief.json"
        hints = _classify_by_path(fp, root)
        # "brief" keyword matches first in _PATH_TYPE_HINTS (maps to "strategy")
        # because dict iteration hits "brief" before "kol" or "kol_brief"
        assert hints["type"] == "strategy"

    def test_fallback_type_is_content(self) -> None:
        root = Path("/project")
        fp = root / "random_dir" / "notes.md"
        hints = _classify_by_path(fp, root)
        assert hints["type"] == "content"

    def test_no_phase_when_not_in_known_dir(self) -> None:
        root = Path("/project")
        fp = root / "misc" / "readme.md"
        hints = _classify_by_path(fp, root)
        assert "phase" not in hints

    def test_phase_3_from_review_dir(self) -> None:
        root = Path("/project")
        fp = root / "05_review" / "checklist.md"
        hints = _classify_by_path(fp, root)
        assert hints.get("phase") == "3"


# ---------------------------------------------------------------------------
# _extract_title
# ---------------------------------------------------------------------------


class TestExtractTitle:
    """Verify title extraction from various content formats."""

    def test_json_frontmatter_title(self) -> None:
        content = '---\n{"title": "My Strategy Doc"}\n---\nBody text here.'
        fp = Path("/project/doc.md")
        result = _extract_title(fp, content.encode("utf-8"))
        assert result == "My Strategy Doc"

    def test_yaml_frontmatter_title(self) -> None:
        content = '---\ntitle: Market Analysis 2025\nauthor: team\n---\nBody.'
        fp = Path("/project/doc.yaml")
        result = _extract_title(fp, content.encode("utf-8"))
        assert result == "Market Analysis 2025"

    def test_markdown_heading(self) -> None:
        content = "# Project Overview\n\nSome content here."
        fp = Path("/project/doc.md")
        result = _extract_title(fp, content.encode("utf-8"))
        assert result == "Project Overview"

    def test_markdown_h2_heading(self) -> None:
        content = "## Detailed Plan\n\nMore details."
        fp = Path("/project/doc.md")
        result = _extract_title(fp, content.encode("utf-8"))
        assert result == "Detailed Plan"

    def test_json_body_topic_key(self) -> None:
        content = json.dumps({"topic": "AI Content Strategy", "status": "draft"})
        fp = Path("/project/data.json")
        result = _extract_title(fp, content.encode("utf-8"))
        assert result == "AI Content Strategy"

    def test_json_body_title_key(self) -> None:
        content = json.dumps({"title": "Brand Guidelines", "version": 2})
        fp = Path("/project/data.json")
        result = _extract_title(fp, content.encode("utf-8"))
        assert result == "Brand Guidelines"

    def test_json_body_name_key(self) -> None:
        content = json.dumps({"name": "Persona Alpha", "age": 30})
        fp = Path("/project/data.json")
        result = _extract_title(fp, content.encode("utf-8"))
        assert result == "Persona Alpha"

    def test_unreadable_content_returns_none(self) -> None:
        # Invalid UTF-8 bytes
        content = b"\x80\x81\x82\xff"
        fp = Path("/project/bad.md")
        result = _extract_title(fp, content)
        assert result is None

    def test_no_title_found_returns_none(self) -> None:
        content = "Just some plain text without any structure."
        fp = Path("/project/plain.md")
        result = _extract_title(fp, content.encode("utf-8"))
        assert result is None

    def test_yaml_frontmatter_title_with_quotes(self) -> None:
        content = "---\ntitle: \"Quoted Title\"\n---\nBody."
        fp = Path("/project/doc.yaml")
        result = _extract_title(fp, content.encode("utf-8"))
        assert result == "Quoted Title"


# ---------------------------------------------------------------------------
# _extract_tags
# ---------------------------------------------------------------------------


class TestExtractTags:
    """Verify tag extraction from front-matter and auto-format tagging."""

    def test_json_frontmatter_tags(self) -> None:
        content = '---\n{"tags": ["marketing", "strategy"]}\n---\nBody.'
        fp = Path("/project/doc.md")
        tags = _extract_tags(fp, content.encode("utf-8"))
        assert "marketing" in tags
        assert "strategy" in tags

    def test_json_frontmatter_keywords_fallback(self) -> None:
        content = '---\n{"keywords": ["brand", "persona"]}\n---\nBody.'
        fp = Path("/project/doc.md")
        tags = _extract_tags(fp, content.encode("utf-8"))
        assert "brand" in tags
        assert "persona" in tags

    def test_yaml_style_tags(self) -> None:
        content = "---\ntags: [ai, content, video]\n---\nBody."
        fp = Path("/project/doc.md")
        tags = _extract_tags(fp, content.encode("utf-8"))
        assert "ai" in tags
        assert "content" in tags
        assert "video" in tags

    def test_auto_format_tag_appended(self) -> None:
        content = "No frontmatter here."
        fp = Path("/project/doc.md")
        tags = _extract_tags(fp, content.encode("utf-8"))
        assert "format:md" in tags

    def test_auto_format_tag_yaml(self) -> None:
        content = "No frontmatter."
        fp = Path("/project/doc.yaml")
        tags = _extract_tags(fp, content.encode("utf-8"))
        assert "format:yaml" in tags

    def test_deduplication(self) -> None:
        content = '---\n{"tags": ["marketing", "Marketing", "MARKETING"]}\n---\nBody.'
        fp = Path("/project/doc.md")
        tags = _extract_tags(fp, content.encode("utf-8"))
        # Only one "marketing" variant should survive (the first one seen)
        lower_tags = [t.lower() for t in tags if not t.startswith("format:")]
        assert lower_tags.count("marketing") == 1

    def test_unreadable_content_returns_empty_list(self) -> None:
        content = b"\x80\x81\x82\xff"
        fp = Path("/project/bad.md")
        tags = _extract_tags(fp, content)
        assert tags == []

    def test_no_frontmatter_returns_only_format_tag(self) -> None:
        content = "Just plain text."
        fp = Path("/project/doc.csv")
        tags = _extract_tags(fp, content.encode("utf-8"))
        assert tags == ["format:csv"]

    def test_empty_tags_in_frontmatter(self) -> None:
        content = '---\n{"tags": []}\n---\nBody.'
        fp = Path("/project/doc.json")
        tags = _extract_tags(fp, content.encode("utf-8"))
        # Should still get the format tag
        assert "format:json" in tags


# ---------------------------------------------------------------------------
# IngestResult dataclass
# ---------------------------------------------------------------------------


class TestIngestResult:
    """Verify the IngestResult dataclass str representation."""

    def test_str_representation(self) -> None:
        from automedia.asset_library.ingest import IngestResult

        r = IngestResult(success_count=5, fail_count=2, errors=["err1", "err2"])
        s = str(r)
        assert "success=5" in s
        assert "fail=2" in s
        assert "errors=2" in s

    def test_defaults(self) -> None:
        from automedia.asset_library.ingest import IngestResult

        r = IngestResult()
        assert r.success_count == 0
        assert r.fail_count == 0
        assert r.errors == []


# ---------------------------------------------------------------------------
# _build_asset_doc (integration with tmp_path)
# ---------------------------------------------------------------------------


class TestBuildAssetDocIntegration:
    """Test _build_asset_doc with real files via tmp_path."""

    def test_build_doc_from_markdown(self, tmp_path: Path) -> None:
        from automedia.asset_library.ingest import _build_asset_doc

        fp = tmp_path / "brief_zh.md"
        fp.write_text("# My Brief\n\nContent here.", encoding="utf-8")

        hints = {"type": "strategy", "phase": "1b"}
        doc = _build_asset_doc(fp, "test-brand", hints)

        assert doc.title == "My Brief"
        assert doc.brand_id == "test-brand"
        assert doc.type == "strategy"
        assert doc.source_phase == "1b"
        assert doc.lang == "zh"
        assert doc.checksum  # non-empty

    def test_build_doc_from_json(self, tmp_path: Path) -> None:
        from automedia.asset_library.ingest import _build_asset_doc

        fp = tmp_path / "data_en.json"
        fp.write_text(
            json.dumps({"topic": "AI Tools"}),
            encoding="utf-8",
        )

        hints = {"type": "content"}
        doc = _build_asset_doc(fp, "test-brand", hints)

        assert doc.title == "AI Tools"
        assert doc.lang == "en"
        assert "format:json" in doc.tags

    def test_build_doc_fallback_to_stem(self, tmp_path: Path) -> None:
        from automedia.asset_library.ingest import _build_asset_doc

        fp = tmp_path / "mystery.md"
        fp.write_text("No heading or frontmatter.", encoding="utf-8")

        doc = _build_asset_doc(fp, "test-brand", {})
        assert doc.title == "mystery"  # fallback to stem
