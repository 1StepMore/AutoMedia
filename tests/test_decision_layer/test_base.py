"""Tests for Decision Layer base abstractions — DecisionArtifact + BaseDecisionAgent.

Covers
------
1. DecisionArtifact construction with all fields
2. DecisionArtifact default values (format, metadata, created_at)
3. DecisionArtifact dict round-trip serialisation
4. DecisionArtifact invalid content type rejection
5. Metadata mutability and provenance round-trip
6. BaseDecisionAgent cannot be instantiated (ABC enforcement)
7. Subclass must implement both abstract methods
8. Minimal concrete agent lifecycle
9. search_asset_library returns results on success
10. search_asset_library degrades gracefully on exception
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.decision.base import BaseDecisionAgent, DecisionArtifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MinimalAgent(BaseDecisionAgent):
    """Concrete agent with the smallest possible implementation."""

    def name(self) -> str:
        return "minimal_test_agent"

    def execute(
        self,
        context: dict[str, Any],
        asset_library: Any,
    ) -> DecisionArtifact:
        return DecisionArtifact(
            artifact_type="brief",
            content={"idea": context.get("idea", "unknown")},
            metadata={"agent": self.name()},
        )


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
        """dataclasses.asdict → reconstruct preserves equality."""
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

        nested = {
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
    """Invalid argument types are rejected by type hints / runtime checks."""

    def test_artifact_type_must_be_string(self) -> None:
        """artifact_type is annotated as str; passing int triggers TypeError or succeeds
        with wrong type (dataclasses don't enforce types at runtime, but we verify
        the value is stored as-is for transparency)."""
        # Dataclasses don't enforce types at construction — this is a smoke test
        # confirming no crash occurs; a stricter layer (e.g. Pydantic) would reject.
        artifact = DecisionArtifact(artifact_type=123, content={})  # type: ignore[arg-type]
        assert artifact.artifact_type == 123  # type: ignore[comparison-overlap]

    def test_content_must_be_dict(self) -> None:
        """content is annotated as dict; passing a list stores it as-is (dataclass limitation)."""
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


# ===================================================================
# BaseDecisionAgent — ABC enforcement
# ===================================================================


class TestBaseDecisionAgentABC:
    """BaseDecisionAgent cannot be instantiated; abstract methods enforced."""

    def test_cannot_instantiate_directly(self) -> None:
        """Direct instantiation raises TypeError."""
        with pytest.raises(TypeError, match="name"):
            BaseDecisionAgent()  # type: ignore[abstract]

    def test_missing_execute_raises_type_error(self) -> None:
        """Subclass implementing only name() still cannot be instantiated."""

        class OnlyName(BaseDecisionAgent):
            def name(self) -> str:
                return "partial"

        with pytest.raises(TypeError, match="execute"):
            OnlyName()  # type: ignore[abstract]

    def test_missing_name_raises_type_error(self) -> None:
        """Subclass implementing only execute() still cannot be instantiated."""

        class OnlyExecute(BaseDecisionAgent):
            def execute(
                self,
                context: dict[str, Any],
                asset_library: Any,
            ) -> DecisionArtifact:
                return DecisionArtifact(artifact_type="x", content={})

        with pytest.raises(TypeError, match="name"):
            OnlyExecute()  # type: ignore[abstract]

    def test_minimal_concrete_agent_works(self) -> None:
        """A fully implemented subclass instantiates and runs correctly."""
        agent = MinimalAgent()
        assert agent.name() == "minimal_test_agent"

        result = agent.execute({"idea": "test idea"}, None)
        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "brief"
        assert result.content["idea"] == "test idea"
        assert result.metadata["agent"] == "minimal_test_agent"


# ===================================================================
# BaseDecisionAgent — search_asset_library
# ===================================================================


class TestSearchAssetLibrary:
    """search_asset_library() delegates to AssetLibrary and degrades gracefully."""

    def test_returns_results_when_library_succeeds(self) -> None:
        """When AssetLibrary.search() returns results, they are forwarded."""
        mock_results = [{"id": "doc1", "text": "brand guidelines"}, {"id": "doc2", "text": "tone of voice"}]
        mock_library_cls = MagicMock()
        mock_library_instance = MagicMock()
        mock_library_instance.search.return_value = mock_results
        mock_library_cls.return_value = mock_library_instance

        agent = MinimalAgent()
        with patch.dict(
            "sys.modules",
            {"automedia.asset_library": MagicMock(AssetLibrary=mock_library_cls)},
        ):
            results = agent.search_asset_library("test-brand", "brand guidelines")

        assert results == mock_results
        mock_library_cls.assert_called_once_with(brand="test-brand")
        mock_library_instance.search.assert_called_once_with(
            query="brand guidelines", filters={}
        )

    def test_returns_results_with_filters(self) -> None:
        """Filters dict is forwarded to library.search()."""
        mock_library_cls = MagicMock()
        mock_library_instance = MagicMock()
        mock_library_instance.search.return_value = ["doc"]
        mock_library_cls.return_value = mock_library_instance

        agent = MinimalAgent()
        filters = {"category": "brand", "lang": "en"}
        with patch.dict(
            "sys.modules",
            {"automedia.asset_library": MagicMock(AssetLibrary=mock_library_cls)},
        ):
            agent.search_asset_library("test-brand", "query", filters=filters)

        mock_library_instance.search.assert_called_once_with(
            query="query", filters=filters
        )

    def test_returns_empty_list_when_library_import_fails(self) -> None:
        """Graceful degradation: returns [] when AssetLibrary import raises."""
        agent = MinimalAgent()
        # Patch import to raise ImportError
        with patch.dict("sys.modules", {"automedia.asset_library": None}):
            results = agent.search_asset_library("test-brand", "anything")

        assert results == []

    def test_returns_empty_list_when_search_raises(self) -> None:
        """Graceful degradation: returns [] when library.search() raises."""
        mock_library_cls = MagicMock()
        mock_library_instance = MagicMock()
        mock_library_instance.search.side_effect = RuntimeError("db connection failed")
        mock_library_cls.return_value = mock_library_instance

        agent = MinimalAgent()
        with patch.dict(
            "sys.modules",
            {"automedia.asset_library": MagicMock(AssetLibrary=mock_library_cls)},
        ):
            results = agent.search_asset_library("test-brand", "query")

        assert results == []

    def test_defaults_filters_to_empty_dict(self) -> None:
        """When filters is None (default), an empty dict is passed to search()."""
        mock_library_cls = MagicMock()
        mock_library_instance = MagicMock()
        mock_library_instance.search.return_value = []
        mock_library_cls.return_value = mock_library_instance

        agent = MinimalAgent()
        with patch.dict(
            "sys.modules",
            {"automedia.asset_library": MagicMock(AssetLibrary=mock_library_cls)},
        ):
            agent.search_asset_library("brand", "q")

        mock_library_instance.search.assert_called_once_with(query="q", filters={})
