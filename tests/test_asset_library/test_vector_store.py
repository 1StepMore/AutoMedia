"""Unit tests for the asset_library vector_store module.

Tests _format_results with valid and edge-case data, the available
property based on _chromadb_installed, and graceful degradation when
Chroma is unavailable. No real Chroma instance is needed.
"""

from __future__ import annotations

import builtins
import importlib.util
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.asset_library.vector_store import VectorStore

# ---------------------------------------------------------------------------
# _format_results (static method)
# ---------------------------------------------------------------------------


class TestFormatResults:
    """Verify Chroma query output formatting."""

    def test_valid_full_data(self) -> None:
        raw: dict[str, Any] = {
            "ids": [["doc1", "doc2"]],
            "documents": [["text one", "text two"]],
            "metadatas": [[{"type": "strategy"}, {"type": "content"}]],
            "distances": [[0.1, 0.5]],
        }
        results = VectorStore._format_results(raw)
        assert len(results) == 2
        assert results[0]["id"] == "doc1"
        assert results[0]["document"] == "text one"
        assert results[0]["metadata"] == {"type": "strategy"}
        assert results[0]["distance"] == 0.1
        assert results[1]["id"] == "doc2"
        assert results[1]["distance"] == 0.5

    def test_missing_documents(self) -> None:
        raw: dict[str, Any] = {
            "ids": [["doc1"]],
            "distances": [[0.3]],
        }
        results = VectorStore._format_results(raw)
        assert len(results) == 1
        assert results[0]["document"] == ""  # missing → empty string
        assert results[0]["metadata"] == {}  # missing → empty dict

    def test_none_inner_lists(self) -> None:
        """Empty inner lists (not None) produce results with defaults."""
        raw: dict[str, Any] = {
            "ids": [["doc1"]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        results = VectorStore._format_results(raw)
        assert len(results) == 1
        assert results[0]["document"] == ""
        assert results[0]["metadata"] == {}
        assert results[0]["distance"] == 0.0

    def test_empty_results(self) -> None:
        raw: dict[str, Any] = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        results = VectorStore._format_results(raw)
        assert results == []

    def test_mismatched_lengths(self) -> None:
        """When lists have different lengths, missing entries get defaults."""
        raw: dict[str, Any] = {
            "ids": [["doc1", "doc2", "doc3"]],
            "documents": [["text one"]],  # shorter
            "metadatas": [[{"type": "a"}]],  # shorter
            "distances": [[0.1]],  # shorter
        }
        results = VectorStore._format_results(raw)
        assert len(results) == 3
        assert results[0]["document"] == "text one"
        assert results[1]["document"] == ""  # out of range
        assert results[2]["metadata"] == {}  # out of range
        assert results[2]["distance"] == 0.0  # out of range

    def test_completely_empty_raw(self) -> None:
        raw: dict[str, Any] = {}
        results = VectorStore._format_results(raw)
        assert results == []


# ---------------------------------------------------------------------------
# VectorStore.available property
# ---------------------------------------------------------------------------


class TestVectorStoreAvailable:
    """Verify the available property reflects chromadb installation state."""

    @patch("automedia.asset_library.vector_store._chromadb_installed", True)
    def test_available_true_when_chroma_installed(self) -> None:
        """When _chromadb_installed is True but client init fails, available is False."""
        with patch.object(VectorStore, "_init_client", side_effect=RuntimeError("fail")):
            vs = VectorStore(brand="test")
            # Client init failed → _client is None → available is False
            assert vs.available is False

    @patch("automedia.asset_library.vector_store._chromadb_installed", False)
    def test_available_false_when_chroma_not_installed(self) -> None:
        vs = VectorStore(brand="test")
        assert vs.available is False

    @patch("automedia.asset_library.vector_store._chromadb_installed", True)
    def test_available_true_when_client_and_collection_set(self) -> None:
        mock_client = MagicMock()
        mock_collection = MagicMock()
        with patch.object(VectorStore, "_init_client"):
            vs = VectorStore(brand="test")
            # Simulate successful init
            vs._client = mock_client
            vs._collection = mock_collection
            assert vs.available is True

    @patch("automedia.asset_library.vector_store._chromadb_installed", True)
    def test_available_false_when_collection_is_none(self) -> None:
        mock_client = MagicMock()
        with patch.object(VectorStore, "_init_client"):
            vs = VectorStore(brand="test")
            vs._client = mock_client
            vs._collection = None
            assert vs.available is False


# ---------------------------------------------------------------------------
# Graceful degradation when Chroma is unavailable
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Verify VectorStore operations degrade gracefully without Chroma."""

    @patch("automedia.asset_library.vector_store._chromadb_installed", False)
    def test_add_embedding_returns_empty_string(self) -> None:
        vs = VectorStore(brand="test")
        result = vs.add_embedding(doc_id="doc1", text="hello")
        assert result == ""

    @patch("automedia.asset_library.vector_store._chromadb_installed", False)
    def test_search_returns_empty_list(self) -> None:
        vs = VectorStore(brand="test")
        results = vs.search("query text")
        assert results == []

    @patch("automedia.asset_library.vector_store._chromadb_installed", False)
    def test_count_returns_zero(self) -> None:
        vs = VectorStore(brand="test")
        assert vs.count() == 0

    @patch("automedia.asset_library.vector_store._chromadb_installed", False)
    def test_get_all_embeddings_returns_empty_list(self) -> None:
        vs = VectorStore(brand="test")
        assert vs.get_all_embeddings() == []

    @patch("automedia.asset_library.vector_store._chromadb_installed", False)
    def test_delete_embedding_noop(self) -> None:
        vs = VectorStore(brand="test")
        # Should not raise
        vs.delete_embedding("nonexistent-id")

    @patch("automedia.asset_library.vector_store._chromadb_installed", False)
    def test_reset_noop(self) -> None:
        vs = VectorStore(brand="test")
        # Should not raise
        vs.reset()


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestVectorStoreProperties:
    """Verify VectorStore property accessors."""

    @patch("automedia.asset_library.vector_store._chromadb_installed", False)
    def test_collection_name(self) -> None:
        vs = VectorStore(brand="mybrand")
        assert vs.collection_name == "automedia_mybrand"

    @patch("automedia.asset_library.vector_store._chromadb_installed", False)
    def test_chroma_dir_contains_brand(self) -> None:
        vs = VectorStore(brand="mybrand")
        assert "mybrand" in str(vs.chroma_dir)
        assert "chroma" in str(vs.chroma_dir)


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestVectorStoreContextManager:
    """Verify VectorStore works as a context manager."""

    @patch("automedia.asset_library.vector_store._chromadb_installed", False)
    def test_context_manager_enter_returns_self(self) -> None:
        vs = VectorStore(brand="test")
        with vs as ctx:
            assert ctx is vs


# ---------------------------------------------------------------------------
# add_embedding / search with mocked Chroma collection
# ---------------------------------------------------------------------------


class TestVectorStoreWithMockedCollection:
    """Test add_embedding and search with a mocked Chroma collection."""

    @patch("automedia.asset_library.vector_store._chromadb_installed", True)
    def test_add_embedding_success(self) -> None:
        mock_collection = MagicMock()
        with patch.object(VectorStore, "_init_client"):
            vs = VectorStore(brand="test")
            vs._client = MagicMock()
            vs._collection = mock_collection

        result = vs.add_embedding(
            doc_id="doc1",
            text="some text",
            metadata={"type": "strategy"},
        )
        assert result == "doc1"
        mock_collection.add.assert_called_once_with(
            ids=["doc1"],
            documents=["some text"],
            metadatas=[{"type": "strategy"}],
        )

    @patch("automedia.asset_library.vector_store._chromadb_installed", True)
    def test_add_embedding_failure_returns_empty(self) -> None:
        mock_collection = MagicMock()
        mock_collection.add.side_effect = RuntimeError("add failed")
        with patch.object(VectorStore, "_init_client"):
            vs = VectorStore(brand="test")
            vs._client = MagicMock()
            vs._collection = mock_collection

        result = vs.add_embedding(doc_id="doc1", text="text")
        assert result == ""

    @patch("automedia.asset_library.vector_store._chromadb_installed", True)
    def test_search_returns_formatted_results(self) -> None:
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "ids": [["doc1"]],
            "documents": [["text"]],
            "metadatas": [[{"type": "content"}]],
            "distances": [[0.2]],
        }
        with patch.object(VectorStore, "_init_client"):
            vs = VectorStore(brand="test")
            vs._client = MagicMock()
            vs._collection = mock_collection

        results = vs.search("query", n_results=5)
        assert len(results) == 1
        assert results[0]["id"] == "doc1"
        mock_collection.query.assert_called_once_with(
            query_texts=["query"],
            n_results=5,
        )

    @patch("automedia.asset_library.vector_store._chromadb_installed", True)
    def test_search_failure_returns_empty(self) -> None:
        mock_collection = MagicMock()
        mock_collection.query.side_effect = RuntimeError("query failed")
        with patch.object(VectorStore, "_init_client"):
            vs = VectorStore(brand="test")
            vs._client = MagicMock()
            vs._collection = mock_collection

        results = vs.search("query")
        assert results == []


# ---------------------------------------------------------------------------
# Narrowed exception handling (_CHROMA_ERRORS)
# ---------------------------------------------------------------------------


def _make_available_store() -> tuple[VectorStore, MagicMock]:
    """Build a VectorStore with a mocked, available client and collection."""
    with (
        patch("automedia.asset_library.vector_store._chromadb_installed", True),
        patch.object(VectorStore, "_init_client"),
    ):
        vs = VectorStore(brand="test")
    vs._client = MagicMock()
    vs._collection = MagicMock()
    return vs, vs._collection


class TestNarrowedExceptionHandling:
    """Listed exceptions yield the existing fallback; unlisted ones propagate."""

    def test_init_listed_exception_is_swallowed(self) -> None:
        with (
            patch("automedia.asset_library.vector_store._chromadb_installed", True),
            patch.object(VectorStore, "_init_client", side_effect=ValueError("bad init")),
        ):
            vs = VectorStore(brand="test")
        assert vs.available is False

    def test_init_unlisted_exception_propagates(self) -> None:
        with (
            patch("automedia.asset_library.vector_store._chromadb_installed", True),
            patch.object(VectorStore, "_init_client", side_effect=KeyError("boom")),
            pytest.raises(KeyError),
        ):
            VectorStore(brand="test")

    def test_search_listed_exception_returns_empty(self) -> None:
        vs, collection = _make_available_store()
        collection.query.side_effect = ValueError("query failed")
        assert vs.search("query") == []

    def test_search_unlisted_exception_propagates(self) -> None:
        vs, collection = _make_available_store()
        collection.query.side_effect = KeyError("boom")
        with pytest.raises(KeyError):
            vs.search("query")

    def test_add_embedding_listed_exception_returns_empty(self) -> None:
        vs, collection = _make_available_store()
        collection.add.side_effect = OSError("add failed")
        assert vs.add_embedding(doc_id="doc1", text="text") == ""

    def test_add_embedding_unlisted_exception_propagates(self) -> None:
        vs, collection = _make_available_store()
        collection.add.side_effect = KeyError("boom")
        with pytest.raises(KeyError):
            vs.add_embedding(doc_id="doc1", text="text")

    def test_delete_embedding_listed_exception_is_noop(self) -> None:
        vs, collection = _make_available_store()
        collection.delete.side_effect = RuntimeError("delete failed")
        vs.delete_embedding("doc1")

    def test_delete_embedding_unlisted_exception_propagates(self) -> None:
        vs, collection = _make_available_store()
        collection.delete.side_effect = KeyError("boom")
        with pytest.raises(KeyError):
            vs.delete_embedding("doc1")

    def test_get_all_embeddings_listed_exception_returns_empty(self) -> None:
        vs, collection = _make_available_store()
        collection.get.side_effect = RuntimeError("get failed")
        assert vs.get_all_embeddings() == []

    def test_get_all_embeddings_unlisted_exception_propagates(self) -> None:
        vs, collection = _make_available_store()
        collection.get.side_effect = KeyError("boom")
        with pytest.raises(KeyError):
            vs.get_all_embeddings()

    def test_reset_listed_exception_clears_collection(self) -> None:
        vs, _ = _make_available_store()
        vs._client.create_collection.side_effect = RuntimeError("reset failed")
        vs.reset()
        assert vs._collection is None

    def test_reset_unlisted_exception_propagates(self) -> None:
        vs, _ = _make_available_store()
        vs._client.create_collection.side_effect = KeyError("boom")
        with pytest.raises(KeyError):
            vs.reset()


class TestChromaErrorsTupleShape:
    """_CHROMA_ERRORS references chromadb only when it is installed."""

    def test_installed_shape_prepends_chroma_error(self) -> None:
        import automedia.asset_library.vector_store as vs_module

        if vs_module._chromadb_installed:
            assert vs_module._CHROMA_ERRORS[0] is vs_module.chromadb.errors.ChromaError
        assert vs_module._CHROMA_ERRORS[-3:] == (OSError, ValueError, RuntimeError)

    def test_absent_shape_is_chromadb_free(self) -> None:
        import automedia.asset_library.vector_store as vs_module

        real_import = builtins.__import__

        def _block_chromadb(name: str, *args: object, **kwargs: object) -> object:
            if name == "chromadb" or name.startswith("chromadb."):
                raise ImportError("chromadb blocked for test")
            return real_import(name, *args, **kwargs)

        spec = importlib.util.spec_from_file_location(
            "automedia._vector_store_absent_probe", vs_module.__file__
        )
        assert spec is not None and spec.loader is not None
        probe = importlib.util.module_from_spec(spec)
        with patch.object(builtins, "__import__", side_effect=_block_chromadb):
            spec.loader.exec_module(probe)

        try:
            assert probe._chromadb_installed is False
            expected = (OSError, ValueError, RuntimeError)
            assert expected == probe._CHROMA_ERRORS
        finally:
            sys.modules.pop("automedia._vector_store_absent_probe", None)
