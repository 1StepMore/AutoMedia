"""Asset Library — knowledge base for brand production artifacts.

The Asset Library stores and retrieves brand assets (brand docs, market
research, personas, content, etc.) using SQLite for structured storage
and Chroma for semantic vector search.

Top-level exports
-----------------
* ``AssetLibrary`` — orchestrator combining SQLite + Chroma
* ``AssetDoc`` — schema-aligned dataclass for a single asset
* ``IngestResult`` — summary of an ingestion run
"""

from __future__ import annotations

from structlog import get_logger

from automedia.asset_library.db import ASSET_TYPES, AssetDatabase, AssetDoc
from automedia.asset_library.ingest import IngestResult, ingest_artifacts
from automedia.asset_library.search import AssetLibrary, search_assets
from automedia.asset_library.vector_store import VectorStore

log = get_logger(__name__)

__all__ = [
    "ASSET_TYPES",
    "AssetDatabase",
    "AssetDoc",
    "AssetLibrary",
    "IngestResult",
    "VectorStore",
    "ingest_artifacts",
    "search_assets",
]
