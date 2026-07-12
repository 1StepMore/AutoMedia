"""Tests for DecisionArtifact dataclass.

Covers
------
1. DecisionArtifact construction with all fields
2. DecisionArtifact default values (format, metadata, created_at)
3. DecisionArtifact dict round-trip serialisation
4. DecisionArtifact invalid content type rejection
5. Metadata mutability and provenance round-trip
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from automedia.decision.base import DecisionArtifact


# ===================================================================
# DecisionArtifact — construction & defaults
# ===================================================================


class TestDecisionArtifactConstruction:
    """DecisionArtifact dataclass basic construction."""

    def test_construction_with_all_fields(self) -> None:
        """All explicit fields are stored correctly."""
        ts = datetime(2025, 1, 15, 10, 30, 0)
        artifact = DecisionArtifact(
            artifact_type="brand_dna",
            content={"brand_name": "Acme"},
            format="markdown",
            metadata={"agent": "test", "version": 2},
            created_at=ts,
        )
        assert artifact.artifact_type == "brand_dna"
        assert artifact.content == {"brand_name": "Acme"}
        assert artifact.format == "markdown"
        assert artifact.metadata == {"agent": "test", "version": 2}
        assert artifact.created_at == ts

    def test_defaults_format_is_yaml(self) -> None:
        """format defaults to 'yaml' when omitted."""
        artifact = DecisionArtifact(artifact_type="brief", content={})
        assert artifact.format == "yaml"

    def test_defaults_metadata_is_empty_dict(self) -> None:
        """metadata defaults to an empty dict (not shared across instances)."""
        a1 = DecisionArtifact(artifact_type="brief", content={})
        a2 = DecisionArtifact(artifact_type="brief", content={})
        assert a1.metadata == {}
        assert a2.metadata == {}
        # Must be independent instances — no shared mutable default
        a1.metadata["key"] = "val"
        assert "key" not in a2.metadata

    def test_defaults_created_at_is_auto_populated(self) -> None:
        """created_at is auto-set to a datetime when omitted."""
        before = datetime.now(UTC).replace(tzinfo=None)
        artifact = DecisionArtifact(artifact_type="brief", content={})
        after = datetime.now(UTC).replace(tzinfo=None)
        assert isinstance(artifact.created_at, datetime)
        assert before <= artifact.created_at <= after
        # Must be tz-naive (tzinfo stripped per source)
        assert artifact.created_at.tzinfo is None


# ===================================================================
# DecisionArtifact — serialisation round-trip
# ===================================================================


class TestDecisionArtifactSerialization:
    """Dict round-trip preserves all data."""

    def test_roundtrip_via_dict(self) -> None:
        """dataclasses.asdict -> reconstruct preserves equality."""
        from dataclasses import asdict

        original = DecisionArtifact(
            artifact_type="market_report",
            content={"market_size": "$5B", "segments": ["a", "b"]},
            format="csv",
            metadata={"agent": "market_research", "phase": 4},
        )
        d = asdict(original)
        restored = DecisionArtifact(**d)
        assert restored == original

    def test_content_nested_dict_survives_roundtrip(self) -> None:
        """Nested dicts inside content survive serialisation."""
        from dataclasses import asdict

        nested: dict[str, Any] = {
            "consumer_profile": {
                "age_range": "18-35",
                "values": ["sustainability", "innovation"],
            },
            "cultural_taboos": ["avoid red"],
        }
        original = DecisionArtifact(
            artifact_type="market_report",
            content=nested,
            metadata={"depth": 2},
        )
        d = asdict(original)
        restored = DecisionArtifact(**d)
        assert restored.content["consumer_profile"]["values"] == [
            "sustainability",
            "innovation",
        ]


# ===================================================================
# DecisionArtifact — invalid types
# ===================================================================


class TestDecisionArtifactValidation:
    """Invalid argument types are accepted (dataclasses don't enforce)."""

    def test_artifact_type_can_be_non_string(self) -> None:
        """artifact_type stores whatever is passed (dataclasses don't enforce types)."""
        artifact = DecisionArtifact(artifact_type=123, content={})  # type: ignore[arg-type]
        assert artifact.artifact_type == 123  # type: ignore[comparison-overlap]

    def test_content_can_be_non_dict(self) -> None:
        """content stores whatever is passed (dataclasses don't enforce types)."""
        artifact = DecisionArtifact(
            artifact_type="brief", content=["not", "a", "dict"]  # type: ignore[arg-type]
        )
        assert isinstance(artifact.content, list)  # type: ignore[assert-type]


# ===================================================================
# DecisionArtifact — metadata provenance
# ===================================================================


class TestMetadataProvenance:
    """Metadata dict is mutable and survives round-trip."""

    def test_metadata_mutable_after_creation(self) -> None:
        """Fields can be added to metadata after construction."""
        artifact = DecisionArtifact(artifact_type="brief", content={})
        artifact.metadata["agent"] = "test_agent"
        artifact.metadata["phase"] = 1
        artifact.metadata["timestamp"] = "2025-01-15T00:00:00"
        assert artifact.metadata["agent"] == "test_agent"
        assert artifact.metadata["phase"] == 1

    def test_metadata_survives_roundtrip(self) -> None:
        """Metadata populated after construction survives asdict round-trip."""
        from dataclasses import asdict

        artifact = DecisionArtifact(artifact_type="brief", content={})
        artifact.metadata["source"] = "diagnostic"
        artifact.metadata["nested"] = {"deep": True}

        d = asdict(artifact)
        restored = DecisionArtifact(**d)
        assert restored.metadata["source"] == "diagnostic"
        assert restored.metadata["nested"]["deep"] is True
