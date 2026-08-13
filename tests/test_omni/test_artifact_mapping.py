"""Tests for automedia.omni.artifact_mapping."""

from __future__ import annotations

from pathlib import Path

from automedia.omni.artifact_mapping import ol_output_path, opp_output_path, orf_output_path


class TestOppOutputPath:
    """Verify opp_output_path returns correct path structure."""

    def test_returns_dict_with_four_keys(self, tmp_path: Path) -> None:
        result = opp_output_path(tmp_path, "my_doc")
        assert isinstance(result, dict)
        assert set(result.keys()) == {"md", "xlf", "manifest", "skeleton"}

    def test_all_values_are_paths(self, tmp_path: Path) -> None:
        result = opp_output_path(tmp_path, "my_doc")
        for v in result.values():
            assert isinstance(v, Path)

    def test_all_paths_are_absolute(self, tmp_path: Path) -> None:
        result = opp_output_path(tmp_path, "my_doc")
        for v in result.values():
            assert v.is_absolute()

    def test_base_directory_is_research_data_name(self, tmp_path: Path) -> None:
        result = opp_output_path(tmp_path, "my_doc")
        expected_base = tmp_path.resolve() / "research_data" / "my_doc"
        for v in result.values():
            assert v.parent == expected_base

    def test_md_path_format(self, tmp_path: Path) -> None:
        result = opp_output_path(tmp_path, "my_doc")
        assert result["md"] == tmp_path.resolve() / "research_data" / "my_doc" / "my_doc.md"

    def test_xlf_path_format(self, tmp_path: Path) -> None:
        result = opp_output_path(tmp_path, "my_doc")
        assert result["xlf"] == tmp_path.resolve() / "research_data" / "my_doc" / "my_doc.xlf"

    def test_manifest_path_format(self, tmp_path: Path) -> None:
        result = opp_output_path(tmp_path, "my_doc")
        expected = tmp_path.resolve() / "research_data" / "my_doc" / "my_doc_manifest.json"
        assert result["manifest"] == expected

    def test_skeleton_path_format(self, tmp_path: Path) -> None:
        result = opp_output_path(tmp_path, "my_doc")
        expected = tmp_path.resolve() / "research_data" / "my_doc" / "my_doc.skeleton.zip"
        assert result["skeleton"] == expected

    def test_accepts_str_project_dir(self, tmp_path: Path) -> None:
        result = opp_output_path(str(tmp_path), "doc")
        assert result["md"] == tmp_path.resolve() / "research_data" / "doc" / "doc.md"

    def test_does_not_create_directory_by_default(self, tmp_path: Path) -> None:
        opp_output_path(tmp_path, "my_doc")
        assert not (tmp_path / "research_data").exists()


class TestOlOutputPath:
    """Verify ol_output_path returns correct publish path."""

    def test_returns_path(self, tmp_path: Path) -> None:
        result = ol_output_path(tmp_path, "zh-CN")
        assert isinstance(result, Path)

    def test_path_is_absolute(self, tmp_path: Path) -> None:
        result = ol_output_path(tmp_path, "zh-CN")
        assert result.is_absolute()

    def test_path_ends_with_lang(self, tmp_path: Path) -> None:
        result = ol_output_path(tmp_path, "zh-CN")
        assert result.name == "zh-CN"

    def test_parent_is_05_publish(self, tmp_path: Path) -> None:
        result = ol_output_path(tmp_path, "zh-CN")
        assert result.parent.name == "05_publish"

    def test_full_path_format(self, tmp_path: Path) -> None:
        result = ol_output_path(tmp_path, "ja")
        assert result == tmp_path.resolve() / "05_publish" / "ja"

    def test_accepts_str_project_dir(self, tmp_path: Path) -> None:
        result = ol_output_path(str(tmp_path), "ko")
        assert result == tmp_path.resolve() / "05_publish" / "ko"

    def test_does_not_create_directory_by_default(self, tmp_path: Path) -> None:
        ol_output_path(tmp_path, "zh-CN")
        assert not (tmp_path / "05_publish").exists()


class TestOrfOutputPath:
    """Verify orf_output_path returns correct deliverables path."""

    def test_returns_path(self, tmp_path: Path) -> None:
        result = orf_output_path(tmp_path, "zh-CN")
        assert isinstance(result, Path)

    def test_path_is_absolute(self, tmp_path: Path) -> None:
        result = orf_output_path(tmp_path, "zh-CN")
        assert result.is_absolute()

    def test_path_ends_with_deliverables(self, tmp_path: Path) -> None:
        result = orf_output_path(tmp_path, "zh-CN")
        assert result.name == "deliverables"

    def test_parent_is_lang_folder(self, tmp_path: Path) -> None:
        result = orf_output_path(tmp_path, "fr")
        assert result.parent.name == "fr"

    def test_grandparent_is_05_publish(self, tmp_path: Path) -> None:
        result = orf_output_path(tmp_path, "fr")
        assert result.parent.parent.name == "05_publish"

    def test_full_path_format(self, tmp_path: Path) -> None:
        result = orf_output_path(tmp_path, "de")
        expected = tmp_path.resolve() / "05_publish" / "de" / "deliverables"
        assert result == expected

    def test_accepts_str_project_dir(self, tmp_path: Path) -> None:
        result = orf_output_path(str(tmp_path), "es")
        expected = tmp_path.resolve() / "05_publish" / "es" / "deliverables"
        assert result == expected

    def test_does_not_create_directory_by_default(self, tmp_path: Path) -> None:
        orf_output_path(tmp_path, "zh-CN")
        assert not (tmp_path / "05_publish").exists()


class TestMkdirBehavior:
    """Verify the mkdir parameter creates directories."""

    def test_opp_output_path_creates_dir(self, tmp_path: Path) -> None:
        opp_output_path(tmp_path, "my_doc", mkdir=True)
        assert (tmp_path / "research_data" / "my_doc").is_dir()

    def test_opp_output_path_creates_parents(self, tmp_path: Path) -> None:
        opp_output_path(tmp_path, "a/b", mkdir=True)
        assert (tmp_path / "research_data" / "a" / "b").is_dir()

    def test_ol_output_path_creates_dir(self, tmp_path: Path) -> None:
        ol_output_path(tmp_path, "zh-CN", mkdir=True)
        assert (tmp_path / "05_publish" / "zh-CN").is_dir()

    def test_ol_output_path_creates_parents(self, tmp_path: Path) -> None:
        ol_output_path(tmp_path, "zh-CN/sub", mkdir=True)
        assert (tmp_path / "05_publish" / "zh-CN" / "sub").is_dir()

    def test_orf_output_path_creates_dir(self, tmp_path: Path) -> None:
        orf_output_path(tmp_path, "zh-CN", mkdir=True)
        assert (tmp_path / "05_publish" / "zh-CN" / "deliverables").is_dir()

    def test_orf_output_path_creates_parents(self, tmp_path: Path) -> None:
        orf_output_path(tmp_path, "ja/sub", mkdir=True)
        assert (tmp_path / "05_publish" / "ja" / "sub" / "deliverables").is_dir()

    def test_mkdir_is_idempotent(self, tmp_path: Path) -> None:
        opp_output_path(tmp_path, "doc", mkdir=True)
        opp_output_path(tmp_path, "doc", mkdir=True)  # should not raise
        ol_output_path(tmp_path, "en", mkdir=True)
        ol_output_path(tmp_path, "en", mkdir=True)  # should not raise
        assert (tmp_path / "research_data" / "doc").is_dir()
        assert (tmp_path / "05_publish" / "en").is_dir()

    def test_paths_still_correct_after_mkdir(self, tmp_path: Path) -> None:
        result = opp_output_path(tmp_path, "doc", mkdir=True)
        assert result["md"] == tmp_path.resolve() / "research_data" / "doc" / "doc.md"
        assert result["xlf"] == tmp_path.resolve() / "research_data" / "doc" / "doc.xlf"
