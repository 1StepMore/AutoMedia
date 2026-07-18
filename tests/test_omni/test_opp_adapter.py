"""Tests for OPPAdapter."""

from __future__ import annotations

from typing import Any

from automedia.omni.opp_adapter import ExtractionResult, OPPAdapter, _parse_md_to_segments


class TestExtractionResult:
    def test_has_all_fields(self, tmp_path: Any) -> None:
        xliff = str(tmp_path / "test.xlf")
        skeleton = str(tmp_path / "skeleton.zip")
        r = ExtractionResult(
            md_content="# Hello",
            manifest={"title": "test"},
            xliff_path=xliff,
            skeleton_path=skeleton,
            warnings=["minor issue"],
        )
        assert r.md_content == "# Hello"
        assert r.manifest == {"title": "test"}
        assert r.xliff_path == xliff
        assert r.skeleton_path == skeleton
        assert r.warnings == ["minor issue"]

    def test_xliff_path_defaults_to_none(self) -> None:
        r = ExtractionResult(md_content="# Hello", manifest={}, warnings=[])
        assert r.xliff_path is None

    def test_skeleton_path_defaults_to_none(self) -> None:
        r = ExtractionResult(md_content="# Hello", manifest={}, warnings=[])
        assert r.skeleton_path is None

    def test_warnings_defaults_to_empty_list(self) -> None:
        r = ExtractionResult(md_content="# Hello", manifest={})
        assert r.warnings == []


class TestOPPAdapterContract:
    def test_opp_adapter_name_returns_opp(self) -> None:
        adapter = OPPAdapter()
        assert adapter.name == "opp"

    def test_opp_adapter_is_concrete(self) -> None:
        adapter = OPPAdapter()
        assert adapter.validate_env() is True

    def test_opp_adapter_extract_returns_extraction_result(self) -> None:
        adapter = OPPAdapter()
        result = adapter.extract("/nonexistent/test.docx")
        assert isinstance(result, ExtractionResult)
        assert result.md_content == ""  # file doesn't exist
        assert len(result.warnings) > 0

    def test_extract_md_returns_extraction_result(self) -> None:
        adapter = OPPAdapter()
        result = adapter.extract_md("# Hello", source_lang="en", target_lang="zh")
        assert isinstance(result, ExtractionResult)
        assert result.md_content == "# Hello"
        assert result.manifest["source_lang"] == "en"
        assert result.manifest["target_lang"] == "zh"

    def test_batch_extract_empty_list(self) -> None:
        adapter = OPPAdapter()
        result = adapter.batch_extract([])
        assert result == []


class TestParseMdToSegments:
    def test_returns_list_of_dicts(self) -> None:
        segments = _parse_md_to_segments("# Hello\nWorld")
        assert isinstance(segments, list)
        assert len(segments) == 2
        assert segments[0] == {"index": 0, "text": "# Hello"}
        assert segments[1] == {"index": 1, "text": "World"}

    def test_empty_string_returns_empty_list(self) -> None:
        assert _parse_md_to_segments("") == []

    def test_single_line(self) -> None:
        segments = _parse_md_to_segments("only one line")
        assert len(segments) == 1
        assert segments[0]["index"] == 0
        assert segments[0]["text"] == "only one line"
