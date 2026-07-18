"""Tests for automedia.decision.schema_validator — JSON Schema validation.

All tests use a synthetic schema file via monkeypatch to avoid reading
the real ``solution-wise/schemas/`` directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _patch_schema_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temp schema dir with a test schema and patch ``_SCHEMA_DIR``."""
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()

    # Minimal test schema
    test_schema = {
        "required": ["name", "values"],
        "properties": {
            "name": "string",
            "values": "array",
            "description": "string",
            "metadata": "object",
        },
    }
    (schema_dir / "test_schema.json").write_text(json.dumps(test_schema), encoding="utf-8")

    # Broken (invalid JSON) schema
    (schema_dir / "broken.json").write_text("not valid json {{{", encoding="utf-8")

    import automedia.decision.schema_validator as sv_mod

    monkeypatch.setattr(sv_mod, "_SCHEMA_DIR", schema_dir)
    return schema_dir


# ===================================================================
# validate_artifact()
# ===================================================================


class TestValidateArtifact:
    """validate_artifact() validates data against JSON schemas."""

    def test_valid_data_returns_true(self) -> None:
        from automedia.decision.schema_validator import validate_artifact

        result = validate_artifact("test_schema", {"name": "foo", "values": [1, 2]})
        assert result["valid"] is True
        assert result["errors"] == []

    def test_missing_required_field_returns_errors(self) -> None:
        from automedia.decision.schema_validator import validate_artifact

        result = validate_artifact("test_schema", {"name": "foo"})
        assert result["valid"] is False
        assert any("values" in e for e in result["errors"])

    def test_wrong_type_returns_errors(self) -> None:
        from automedia.decision.schema_validator import validate_artifact

        result = validate_artifact("test_schema", {"name": "foo", "values": "not_a_list"})
        assert result["valid"] is False
        assert any("list" in e.lower() for e in result["errors"])

    def test_schema_not_found_returns_error(self) -> None:
        from automedia.decision.schema_validator import validate_artifact

        result = validate_artifact("nonexistent_schema", {"name": "x", "values": []})
        assert result["valid"] is False
        assert any("not found" in e.lower() for e in result["errors"])

    def test_broken_schema_file_returns_error(self) -> None:
        from automedia.decision.schema_validator import validate_artifact

        result = validate_artifact("broken", {"name": "x", "values": []})
        assert result["valid"] is False
        assert any("cannot load" in e.lower() for e in result["errors"])

    def test_string_field_wrong_type(self) -> None:
        from automedia.decision.schema_validator import validate_artifact

        result = validate_artifact("test_schema", {"name": 123, "values": [1]})
        assert result["valid"] is False
        assert any("string" in e.lower() for e in result["errors"])

    def test_object_field_wrong_type(self) -> None:
        from automedia.decision.schema_validator import validate_artifact

        result = validate_artifact(
            "test_schema",
            {"name": "ok", "values": [], "metadata": "not_an_object"},
        )
        assert result["valid"] is False
        assert any("object" in e.lower() for e in result["errors"])

    def test_extra_fields_pass_validation(self) -> None:
        from automedia.decision.schema_validator import validate_artifact

        result = validate_artifact(
            "test_schema",
            {"name": "ok", "values": [], "extra_field": "allowed"},
        )
        assert result["valid"] is True
