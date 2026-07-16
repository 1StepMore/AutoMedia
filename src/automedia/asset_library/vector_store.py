"""Vector Store — Chroma-based semantic search for brand assets.

Each brand gets an isolated Chroma collection named ``automedia_{brand}``
with persistent storage at::

    ~/.automedia/asset-library/{brand}/chroma/

If Chroma is not installed or fails to initialise, the module degrades
gracefully by returning empty results from search operations.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import chromadb

from structlog import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Chroma availability check
# ---------------------------------------------------------------------------

_chromadb_installed = False
try:
    import chromadb  # noqa: F401

    _chromadb_installed = True
except ImportError:
    from automedia.core._import_helpers import warn_missing_optional

    warn_missing_optional("chromadb", feature="vector search disabled")

# ---------------------------------------------------------------------------
# Default embedding function name
# ---------------------------------------------------------------------------

_DEFAULT_EMBEDDING_FN = "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------


class VectorStore:
    """Per-brand Chroma vector store for semantic search.

    Parameters
    ----------
    brand : str
        Brand identifier.  The Chroma collection is named
        ``automedia_{brand}`` and data is persisted under
        ``~/.automedia/asset-library/{brand}/chroma/``.
    """

    def __init__(self, brand: str) -> None:
        self._brand = brand
        self._collection_name = f"automedia_{brand}"
        self._client: chromadb.PersistentClient | None = None
        self._collection: chromadb.Collection | None = None
        self._chroma_dir = (
            Path(os.path.expanduser("~/.automedia/asset-library/")) / brand / "chroma"
        )

        if _chromadb_installed:
            try:
                self._init_client()
            except Exception as exc:
                log.warning(
                    "Failed to initialise Chroma client for brand '%s': %s",
                    brand,
                    exc,
                )

    # -- Properties -----------------------------------------------------------

    @property
    def collection_name(self) -> str:
        """Return the Chroma collection name for this brand."""
        return self._collection_name

    @property
    def chroma_dir(self) -> Path:
        """Return the Chroma persistent directory path."""
        return self._chroma_dir

    @property
    def available(self) -> bool:
        """``True`` when Chroma is available and the client initialised."""
        return self._client is not None and self._collection is not None

    # -- Initialisation -------------------------------------------------------

    def _init_client(self) -> None:
        """Initialise the Chroma PersistentClient and collection."""
        import chromadb

        self._chroma_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._chroma_dir))

        # Get or create the collection
        try:
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
            )
        except (ValueError, RuntimeError):
            # Fallback: try creating it fresh
            with contextlib.suppress(Exception):
                self._client.delete_collection(self._collection_name)
            self._collection = self._client.create_collection(
                name=self._collection_name,
            )

    # -- CRUD -----------------------------------------------------------------

    def add_embedding(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Compute and store an embedding for *text*.

        Parameters
        ----------
        doc_id : str
            Unique identifier (typically the asset's ``doc_id``).
        text : str
            Text content to embed.
        metadata : dict or None
            Optional metadata attached to the embedding (e.g. type,
            title, brand_id).

        Returns
        -------
        str
            The Chroma internal ID (``vector_id``).  When Chroma is not
            available returns an empty string.
        """
        if not self.available:
            log.debug("Chroma unavailable — skipping embedding for %s", doc_id)
            return ""

        vec_id = str(doc_id)
        meta = dict(metadata) if metadata else {}

        try:
            self._collection.add(
                ids=[vec_id],
                documents=[text],
                metadatas=[meta],
            )
        except Exception as exc:
            log.error("Failed to add embedding for %s: %s", doc_id, exc)
            return ""

        return vec_id

    def search(
        self,
        query: str,
        n_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Perform semantic search against the vector store.

        Parameters
        ----------
        query : str
            Natural-language query string.
        n_results : int
            Maximum number of results to return (default 10).

        Returns
        -------
        list[dict]
            Each result dict contains ``id``, ``document``, ``metadata``,
            and ``distance`` keys.  Returns an empty list when Chroma is
            not available or the search fails.
        """
        if not self.available:
            log.debug("Chroma unavailable — returning empty search results")
            return []

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=n_results,
            )
        except Exception as exc:
            log.error("Vector search failed: %s", exc)
            return []

        return self._format_results(results)

    @staticmethod
    def _format_results(raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert Chroma query output to a list of result dicts."""
        formatted: list[dict[str, Any]] = []
        ids = raw.get("ids", [[]])[0]
        documents = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        for i, doc_id in enumerate(ids):
            formatted.append(
                {
                    "id": doc_id,
                    "document": documents[i] if i < len(documents) else "",
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "distance": distances[i] if i < len(distances) else 0.0,
                }
            )

        return formatted

    def delete_embedding(self, vector_id: str) -> None:
        """Remove an embedding by its Chroma ID.

        Parameters
        ----------
        vector_id : str
            The Chroma internal ID (returned by ``add_embedding``).
        """
        if not self.available:
            return

        try:
            self._collection.delete(ids=[vector_id])
        except Exception as exc:
            log.error("Failed to delete embedding %s: %s", vector_id, exc)

    # -- Bulk operations ------------------------------------------------------

    def get_all_embeddings(self) -> list[dict[str, Any]]:
        """Retrieve all embeddings from the Chroma collection.

        Returns a list of dicts, each containing ``id``, ``document``,
        and ``metadata`` keys.  Returns an empty list when Chroma is
        not available or the collection is empty.

        This is used primarily by the migration script to read source
        data from Chroma before migrating to pgvector.
        """
        if not self.available:
            log.debug("Chroma unavailable — returning empty embedding list")
            return []

        try:
            raw = self._collection.get(limit=None)  # noqa: E501  # type: ignore[arg-type]  # chromadb.Collection.get() expects int for limit, None is valid at runtime but typing doesn't allow it
        except Exception as exc:
            log.error("Failed to get all embeddings: %s", exc)
            return []

        formatted: list[dict[str, Any]] = []
        ids = raw.get("ids", [])
        documents = raw.get("documents", [])
        metadatas = raw.get("metadatas", [])

        for i, doc_id in enumerate(ids):
            formatted.append(
                {
                    "id": doc_id,
                    "document": documents[i] if i < len(documents) else "",
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                }
            )

        return formatted

    def count(self) -> int:
        """Return the number of embeddings in the collection."""
        if not self.available:
            return 0
        try:
            return self._collection.count()
        except (ValueError, RuntimeError):
            log.debug("VectorStore.count() failed, returning 0")
            return 0

    def reset(self) -> None:
        """Delete the entire collection and recreate it."""
        if not self.available:
            return
        with contextlib.suppress(Exception):
            self._client.delete_collection(self._collection_name)
        try:
            self._collection = self._client.create_collection(
                name=self._collection_name,
            )
        except Exception as exc:
            log.error("Failed to reset collection: %s", exc)
            self._collection = None

    # -- Context manager ------------------------------------------------------

    def __enter__(self) -> VectorStore:
        return self

    def __exit__(self, *exc: object) -> None:
        pass  # Chroma client doesn't require explicit close
