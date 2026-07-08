"""RED tests for automedia.core.compat_scanner — W1-T32 TDD contract.

These tests define the API contract for the compatibility scanner module.
The scanner must verify that new ``automedia.core.project.Project`` can
recognise historical project structures from ``automedia-package/``.

All tests should FAIL (``ModuleNotFoundError``) until
``automedia/core/compat_scanner.py`` is implemented.

Run::

    pytest tests/test_compat_scanner.py -v
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from tests.fixtures.synth.historical_projects import (
    build_historical_project_dir,
    build_historical_project_dir_with_assets,
    build_historical_record,
    build_malformed_project_dir,
    build_minimal_project_dir,
)

# Deferred import — the module does not exist yet (RED phase).
# Each test will fail individually with ModuleNotFoundError rather than
# crashing at collection time.
try:
    from automedia.core.compat_scanner import (
        check_asset_paths,
        check_dir_structure,
        detect_info_format,
        generate_report,
        load_registry,
        map_fields,
        parse_historical_info,
        scan_all,
        scan_project,
    )
    _SCANNER_AVAILABLE = True
except ImportError:
    _SCANNER_AVAILABLE = False


@pytest.fixture(autouse=True)
def _require_compat_scanner():
    """Fail (not skip) every test when the scanner module is missing."""
    if not _SCANNER_AVAILABLE:
        pytest.fail(
            "automedia.core.compat_scanner is not yet implemented — "
            "RED tests expected to fail.",
            pytrace=False,
        )


# ===================================================================
# TestCompatScannerMetadata — module-level API surface
# ===================================================================


class TestCompatScannerMetadata:
    """The scanner module exposes all expected public functions."""

    def test_load_registry_is_callable(self):
        assert callable(load_registry)

    def test_detect_info_format_is_callable(self):
        assert callable(detect_info_format)

    def test_parse_historical_info_is_callable(self):
        assert callable(parse_historical_info)

    def test_map_fields_is_callable(self):
        assert callable(map_fields)

    def test_check_asset_paths_is_callable(self):
        assert callable(check_asset_paths)

    def test_check_dir_structure_is_callable(self):
        assert callable(check_dir_structure)

    def test_scan_project_is_callable(self):
        assert callable(scan_project)

    def test_scan_all_is_callable(self):
        assert callable(scan_all)

    def test_generate_report_is_callable(self):
        assert callable(generate_report)


# ===================================================================
# TestCompatScannerParsing — Form A (flat) & Form B (nested)
# ===================================================================


class TestCompatScannerParsing:
    """Detect and parse both historical info-file layout forms."""

    # -- Form detection -------------------------------------------------

    def test_detect_form_a_flat_file(self, tmp_path):
        """Form A: ``00_project_info.json`` at project root."""
        project_dir = build_historical_project_dir(tmp_path, form="a")
        result = detect_info_format(project_dir)
        assert result == "a"

    def test_detect_form_b_nested_dir(self, tmp_path):
        """Form B: ``00_project_info/project_info.json``."""
        project_dir = build_historical_project_dir(tmp_path, form="b")
        result = detect_info_format(project_dir)
        assert result == "b"

    def test_detect_returns_none_when_missing(self, tmp_path):
        """A directory with no info file returns ``None``."""
        empty_dir = tmp_path / "empty-project"
        empty_dir.mkdir()
        result = detect_info_format(empty_dir)
        assert result is None

    # -- Parsing --------------------------------------------------------

    def test_parse_form_a_returns_info_dict(self, tmp_path):
        """Parsing Form A yields the original ``info`` dict contents."""
        record = build_historical_record()
        project_dir = build_historical_project_dir(tmp_path, form="a", record=record)
        info = parse_historical_info(project_dir)
        assert info["project_id"] == record["info"]["project_id"]
        assert info["topic"] == record["info"]["topic"]
        assert info["created_at"] == record["info"]["created_at"]

    def test_parse_form_b_returns_info_dict(self, tmp_path):
        """Parsing Form B yields the same dict as Form A for the same record."""
        record = build_historical_record()
        project_dir = build_historical_project_dir(tmp_path, form="b", record=record)
        info = parse_historical_info(project_dir)
        assert info["project_id"] == record["info"]["project_id"]
        assert info["topic"] == record["info"]["topic"]

    def test_parse_preserves_all_fields(self, tmp_path):
        """All fields from the info file are preserved in the parsed dict."""
        record = build_historical_record()
        project_dir = build_historical_project_dir(tmp_path, form="a", record=record)
        info = parse_historical_info(project_dir)
        for key in ("project_id", "topic_id", "source", "topic", "topic_slug",
                     "category", "created_at", "status", "angle", "bridge",
                     "cta", "keywords"):
            assert key in info, f"Missing key: {key}"


# ===================================================================
# TestCompatScannerFieldMapping — historical → new schema
# ===================================================================


class TestCompatScannerFieldMapping:
    """Map legacy fields to the new ``Project`` dataclass schema."""

    def test_project_id_maps_to_project_id(self, tmp_path):
        """Historical ``project_id`` → new ``project_id``."""
        record = build_historical_record()
        project_dir = build_historical_project_dir(tmp_path, form="a", record=record)
        info = parse_historical_info(project_dir)
        mapping = map_fields(info)
        assert mapping["project_id"] == record["info"]["project_id"]

    def test_topic_maps_to_topic(self, tmp_path):
        """Historical ``topic`` → new ``topic``."""
        record = build_historical_record()
        project_dir = build_historical_project_dir(tmp_path, form="a", record=record)
        info = parse_historical_info(project_dir)
        mapping = map_fields(info)
        assert mapping["topic"] == record["info"]["topic"]

    def test_created_at_maps_to_created_at(self, tmp_path):
        """Historical ``created_at`` → new ``created_at``."""
        record = build_historical_record()
        project_dir = build_historical_project_dir(tmp_path, form="a", record=record)
        info = parse_historical_info(project_dir)
        mapping = map_fields(info)
        assert mapping["created_at"] == record["info"]["created_at"]

    def test_historical_only_fields_in_separate_key(self, tmp_path):
        """Fields that have no new-schema equivalent are grouped under
        ``historical_only`` so consumers can still access them."""
        record = build_historical_record()
        project_dir = build_historical_project_dir(tmp_path, form="a", record=record)
        info = parse_historical_info(project_dir)
        mapping = map_fields(info)

        historical_only = mapping.get("historical_only", {})
        for field in ("topic_id", "source", "category", "angle",
                       "bridge", "cta", "keywords"):
            assert field in historical_only, (
                f"{field} should be in historical_only, got keys: "
                f"{list(historical_only.keys())}"
            )

    def test_historical_only_values_preserved(self, tmp_path):
        """The values in ``historical_only`` match the original info."""
        record = build_historical_record()
        project_dir = build_historical_project_dir(tmp_path, form="a", record=record)
        info = parse_historical_info(project_dir)
        mapping = map_fields(info)

        ho = mapping["historical_only"]
        assert ho["topic_id"] == record["info"]["topic_id"]
        assert ho["source"] == record["info"]["source"]
        assert ho["category"] == record["info"]["category"]
        assert ho["angle"] == record["info"]["angle"]
        assert ho["bridge"] == record["info"]["bridge"]
        assert ho["cta"] == record["info"]["cta"]
        assert ho["keywords"] == record["info"]["keywords"]

    def test_brand_defaults_to_empty_string(self, tmp_path):
        """Historical records have no ``brand``; mapping defaults it to ``""``."""
        record = build_historical_record()
        project_dir = build_historical_project_dir(tmp_path, form="a", record=record)
        info = parse_historical_info(project_dir)
        mapping = map_fields(info)
        assert mapping.get("brand", "") == ""

    def test_tenant_id_defaults_to_default(self, tmp_path):
        """Historical records have no ``tenant_id``; mapping defaults to ``"default"``."""
        record = build_historical_record()
        project_dir = build_historical_project_dir(tmp_path, form="a", record=record)
        info = parse_historical_info(project_dir)
        mapping = map_fields(info)
        assert mapping.get("tenant_id", "default") == "default"


# ===================================================================
# TestCompatScannerAssetPaths — directory-structure & media recognition
# ===================================================================


class TestCompatScannerAssetPaths:
    """Recognise legacy media-asset layout."""

    def test_detects_video_final_mp4(self, tmp_path):
        """``03_video/video_final.mp4`` is recognised as the final video."""
        project_dir = build_historical_project_dir_with_assets(tmp_path)
        result = check_asset_paths(project_dir)
        assert "03_video/video_final.mp4" in result.get("video_paths", [])

    def test_detects_publish_log_json(self, tmp_path):
        """``05_publish/publish_log.json`` is recognised."""
        project_dir = build_historical_project_dir_with_assets(tmp_path)
        result = check_asset_paths(project_dir)
        assert "05_publish/publish_log.json" in result.get("publish_paths", [])

    def test_no_assets_returns_empty_lists(self, tmp_path):
        """A project dir with only info file has no assets."""
        project_dir = build_historical_project_dir(tmp_path, form="a")
        result = check_asset_paths(project_dir)
        assert result.get("video_paths", []) == []
        assert result.get("publish_paths", []) == []

    def test_video_path_value_matches_convention(self, tmp_path):
        """The video path follows the ``03_video/video_final.mp4`` convention."""
        record = build_historical_record()
        project_dir = build_historical_project_dir_with_assets(
            tmp_path, record=record,
        )
        result = check_asset_paths(project_dir)
        # Must contain the exact relative path used in historical projects
        assert any("video_final.mp4" in p for p in result.get("video_paths", []))


# ===================================================================
# TestCompatScannerDirStructure — full directory layout check
# ===================================================================


class TestCompatScannerDirStructure:
    """Check the directory structure of a historical project."""

    def test_reports_standard_subdirs(self, tmp_path):
        """Recognises the historical subdirectory layout."""
        project_dir = build_historical_project_dir_with_assets(tmp_path)
        result = check_dir_structure(project_dir)
        # Must include at least these subdirectories
        assert "03_video" in result.get("present", [])
        assert "05_publish" in result.get("present", [])

    def test_reports_missing_subdirs(self, tmp_path):
        """Missing subdirectories are listed under ``missing``."""
        project_dir = build_historical_project_dir(tmp_path, form="a")
        result = check_dir_structure(project_dir)
        # 03_video and 05_publish were not created
        assert "03_video" in result.get("missing", []) or \
               "03_video" not in result.get("present", [])


# ===================================================================
# TestCompatScannerEdgeCases — malformed / minimal / missing data
# ===================================================================


class TestCompatScannerEdgeCases:
    """Graceful degradation when historical data is incomplete or broken."""

    def test_missing_info_file_returns_error(self, tmp_path):
        """A project dir with no info file produces an error result."""
        empty_dir = tmp_path / "no-info"
        empty_dir.mkdir()
        result = scan_project(empty_dir)
        assert result.get("compatible") is False
        assert "error" in result or "errors" in result

    def test_malformed_json_returns_error(self, tmp_path):
        """Invalid JSON in the info file produces a parse-error result."""
        project_dir = build_malformed_project_dir(tmp_path, form="a")
        result = scan_project(project_dir)
        assert result.get("compatible") is False
        # Should mention JSON parse failure
        errors = result.get("errors", [])
        assert any("json" in str(e).lower() or "parse" in str(e).lower()
                    for e in errors)

    def test_malformed_json_form_b(self, tmp_path):
        """Malformed JSON in Form B layout is also caught."""
        project_dir = build_malformed_project_dir(tmp_path, form="b")
        result = scan_project(project_dir)
        assert result.get("compatible") is False

    def test_empty_record_scans_without_crash(self, tmp_path):
        """An info file with minimal fields does not crash the scanner."""
        project_dir = build_minimal_project_dir(tmp_path, form="a")
        result = scan_project(project_dir)
        # Should complete without raising; compatibility depends on
        # whether required fields (project_id, topic, created_at) are present
        assert "compatible" in result

    def test_minimal_record_is_compatible(self, tmp_path):
        """A minimal record (no optional fields) is still compatible when
        it contains the three required mapped fields."""
        project_dir = build_minimal_project_dir(tmp_path, form="a")
        result = scan_project(project_dir)
        assert result.get("compatible") is True

    def test_minimal_record_historical_only_has_no_optional(self, tmp_path):
        """Minimal records produce an empty ``historical_only`` for optional
        marketing fields (angle, bridge, cta, keywords)."""
        project_dir = build_minimal_project_dir(tmp_path, form="a")
        result = scan_project(project_dir)
        ho = result.get("field_mapping", {}).get("historical_only", {})
        for field in ("angle", "bridge", "cta", "keywords"):
            assert field not in ho, f"{field} should be absent in minimal record"


# ===================================================================
# TestCompatScannerRegistry — load_registry from JSON
# ===================================================================


class TestCompatScannerRegistry:
    """Load and validate the PROJECT_REGISTRY.json file."""

    def test_load_registry_returns_list(self, tmp_path):
        """``load_registry`` returns a list of project records."""
        registry_path = tmp_path / "PROJECT_REGISTRY.json"
        registry_data = {
            "generated_at": "2026-07-01 12:00:00",
            "active": [
                build_historical_record(),
            ],
        }
        registry_path.write_text(
            json.dumps(registry_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        records = load_registry(registry_path)
        assert isinstance(records, list)
        assert len(records) == 1

    def test_load_registry_preserves_record_structure(self, tmp_path):
        """Loaded records retain the original ``id``, ``info``, ``path`` keys."""
        record = build_historical_record()
        registry_path = tmp_path / "PROJECT_REGISTRY.json"
        registry_data = {
            "generated_at": "2026-07-01 12:00:00",
            "active": [record],
        }
        registry_path.write_text(
            json.dumps(registry_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        records = load_registry(registry_path)
        loaded = records[0]
        assert loaded["id"] == record["id"]
        assert loaded["info"]["project_id"] == record["info"]["project_id"]
        assert "path" in loaded

    def test_load_registry_empty_active(self, tmp_path):
        """An empty ``active`` list returns an empty list."""
        registry_path = tmp_path / "PROJECT_REGISTRY.json"
        registry_data = {"generated_at": "2026-07-01 12:00:00", "active": []}
        registry_path.write_text(
            json.dumps(registry_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        records = load_registry(registry_path)
        assert records == []

    def test_load_registry_nonexistent_file_raises(self, tmp_path):
        """Loading from a non-existent file raises ``FileNotFoundError``."""
        with pytest.raises(FileNotFoundError):
            load_registry(tmp_path / "nonexistent.json")


# ===================================================================
# TestCompatScannerScanAll — multi-project scanning
# ===================================================================


class TestCompatScannerScanAll:
    """Scan multiple project directories at once."""

    def test_scan_all_returns_list(self, tmp_path):
        """``scan_all`` returns a list of per-project results."""
        d1 = build_historical_project_dir(tmp_path / "p1", form="a")
        d2 = build_historical_project_dir(tmp_path / "p2", form="b")
        results = scan_all([d1, d2])
        assert isinstance(results, list)
        assert len(results) == 2

    def test_scan_all_each_has_compatible_key(self, tmp_path):
        """Every result dict includes a ``compatible`` boolean."""
        d1 = build_historical_project_dir(tmp_path / "p1", form="a")
        d2 = build_historical_project_dir(tmp_path / "p2", form="b")
        results = scan_all([d1, d2])
        for r in results:
            assert "compatible" in r

    def test_scan_all_empty_list(self):
        """Scanning zero projects returns an empty list."""
        results = scan_all([])
        assert results == []


# ===================================================================
# TestCompatScannerReport — report structure
# ===================================================================


class TestCompatScannerReport:
    """The compatibility report has the expected top-level structure."""

    def _make_scan_results(self, tmp_path: Path) -> list[dict]:
        """Helper: create two scan results (one compatible, one broken)."""
        good_dir = build_historical_project_dir(tmp_path / "good", form="a")
        bad_dir = build_malformed_project_dir(tmp_path / "bad", form="a")
        return scan_all([good_dir, bad_dir])

    def test_report_has_generated_at(self, tmp_path):
        """Report includes an ISO-8601 ``generated_at`` timestamp."""
        results = self._make_scan_results(tmp_path)
        report = generate_report(results)
        assert "generated_at" in report
        # Must parse as a valid datetime string
        datetime.fromisoformat(report["generated_at"])

    def test_report_has_total_projects(self, tmp_path):
        """``total_projects`` equals the number of scanned projects."""
        results = self._make_scan_results(tmp_path)
        report = generate_report(results)
        assert report["total_projects"] == 2

    def test_report_has_compatible_count(self, tmp_path):
        """``compatible`` counts projects that passed."""
        results = self._make_scan_results(tmp_path)
        report = generate_report(results)
        assert isinstance(report["compatible"], int)
        assert report["compatible"] >= 1

    def test_report_has_incompatible_count(self, tmp_path):
        """``incompatible`` counts projects that failed."""
        results = self._make_scan_results(tmp_path)
        report = generate_report(results)
        assert isinstance(report["incompatible"], int)
        assert report["incompatible"] >= 1

    def test_report_compatible_plus_incompatible_equals_total(self, tmp_path):
        """compatible + incompatible == total_projects."""
        results = self._make_scan_results(tmp_path)
        report = generate_report(results)
        assert report["compatible"] + report["incompatible"] == report["total_projects"]

    def test_report_has_field_mapping(self, tmp_path):
        """Report includes a ``field_mapping`` section."""
        results = self._make_scan_results(tmp_path)
        report = generate_report(results)
        assert "field_mapping" in report
        fm = report["field_mapping"]
        # Must document the three mapped-to-new fields
        assert "project_id" in fm
        assert "topic" in fm
        assert "created_at" in fm

    def test_report_has_directory_mapping(self, tmp_path):
        """Report includes a ``directory_mapping`` section."""
        results = self._make_scan_results(tmp_path)
        report = generate_report(results)
        assert "directory_mapping" in report

    def test_report_has_details(self, tmp_path):
        """Report includes a ``details`` list with per-project entries."""
        results = self._make_scan_results(tmp_path)
        report = generate_report(results)
        assert "details" in report
        assert isinstance(report["details"], list)
        assert len(report["details"]) == 2

    def test_report_detail_has_project_id(self, tmp_path):
        """Each detail entry includes a ``project_id``."""
        results = self._make_scan_results(tmp_path)
        report = generate_report(results)
        for detail in report["details"]:
            assert "project_id" in detail

    def test_report_detail_has_compatible(self, tmp_path):
        """Each detail entry includes a ``compatible`` boolean."""
        results = self._make_scan_results(tmp_path)
        report = generate_report(results)
        for detail in report["details"]:
            assert "compatible" in detail
            assert isinstance(detail["compatible"], bool)

    def test_report_all_compatible_projects(self, tmp_path):
        """A report from all-good projects has incompatible == 0."""
        d1 = build_historical_project_dir(tmp_path / "p1", form="a")
        d2 = build_historical_project_dir(tmp_path / "p2", form="a")
        results = scan_all([d1, d2])
        report = generate_report(results)
        assert report["incompatible"] == 0
        assert report["compatible"] == 2
