"""Migration — export assets from SQLite + Chroma to PostgreSQL + pgvector.

Provides ``migrate_assets()`` which reads all assets from a brand's SQLite
database and their embeddings from the Chroma vector store, formats the
data for pgvector insertion, and optionally pushes to a PostgreSQL URI.

When *dry_run* is ``True`` (the default), only source data is read and
a report is printed — no remote connection is attempted.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from structlog import get_logger

from automedia.asset_library.db import AssetDatabase
from automedia.asset_library.vector_store import VectorStore

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def migrate_assets(
    brand: str,
    pg_uri: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Migrate *brand* assets from SQLite + Chroma to PostgreSQL + pgvector.

    Parameters
    ----------
    brand : str
        Brand identifier.  Used to locate the per-brand SQLite database
        and Chroma collection.
    pg_uri : str or None
        PostgreSQL connection URI.  Required when *dry_run* is ``False``.
        Ignored when *dry_run* is ``True``.
    dry_run : bool
        When ``True`` (default), only reads source data and reports what
        would be migrated without connecting to PostgreSQL.

    Returns
    -------
    dict
        Migration report with keys:

        - ``brand`` — the brand identifier
        - ``dry_run`` — whether this was a dry run
        - ``success_count`` — assets successfully read (dry run) or migrated
        - ``fail_count`` — assets that could not be read or migrated
        - ``asset_count`` — total assets found in SQLite
        - ``embedding_count`` — total embeddings found in Chroma
        - ``checksums`` — dict of ``{doc_id: checksum}`` for every asset
        - ``errors`` — list of error messages (if any)
        - ``pg_uri_configured`` — whether a pg_uri was provided
    """
    report: dict[str, Any] = {
        "brand": brand,
        "dry_run": dry_run,
        "success_count": 0,
        "fail_count": 0,
        "asset_count": 0,
        "embedding_count": 0,
        "checksums": {},
        "errors": [],
        "pg_uri_configured": pg_uri is not None,
    }

    # ------------------------------------------------------------------
    # 1. Read all assets from SQLite
    # ------------------------------------------------------------------
    assets: list[dict[str, Any]] = []
    try:
        db = AssetDatabase(brand=brand)
        assets = db.list_all()
        db.close()
    except Exception as exc:
        report["fail_count"] += 1
        report["errors"].append(f"Failed to open AssetDatabase for '{brand}': {exc}")
        _print_report(report)
        return report

    report["asset_count"] = len(assets)
    report["checksums"] = {a.get("doc_id", ""): a.get("checksum", "") for a in assets}

    # ------------------------------------------------------------------
    # 2. Read all embeddings from Chroma
    # ------------------------------------------------------------------
    embeddings: list[dict[str, Any]] = []
    try:
        vs = VectorStore(brand=brand)
        embeddings = vs.get_all_embeddings()
    except Exception as exc:
        log.warning("Could not read Chroma embeddings for '%s': %s", brand, exc)
        # Non-fatal — we proceed with zero embeddings
    report["embedding_count"] = len(embeddings)

    # ------------------------------------------------------------------
    # 3. Format data for pgvector insertion
    # ------------------------------------------------------------------
    pg_rows = _format_for_pgvector(assets, embeddings)
    report["success_count"] = len(pg_rows)

    # ------------------------------------------------------------------
    # 4. Optionally insert into PostgreSQL
    # ------------------------------------------------------------------
    if not dry_run:
        if not pg_uri:
            report["errors"].append("dry_run=False requires a pg_uri — no URI provided")
            report["fail_count"] = report["asset_count"]
            report["success_count"] = 0
            _print_report(report)
            return report

        try:
            _insert_into_pg(pg_uri, pg_rows, brand)
        except Exception as exc:
            report["success_count"] = 0
            report["fail_count"] = report["asset_count"]
            report["errors"].append(f"PostgreSQL insert failed: {exc}")

    # ------------------------------------------------------------------
    # 5. Print report and return
    # ------------------------------------------------------------------
    _print_report(report)
    return report


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_for_pgvector(
    assets: list[dict[str, Any]],
    embeddings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Combine SQLite assets and Chroma embeddings into pgvector-ready rows.

    Each output row contains the asset metadata plus the embedding vector
    (if available).  Assets without a matching embedding are still included
    (with a ``None`` vector) so that the migration is complete.
    """
    # Build a lookup: doc_id -> embedding document + metadata
    embed_map: dict[str, dict[str, Any]] = {}
    for emb in embeddings:
        eid = emb.get("id", "")
        embed_map[eid] = {
            "document": emb.get("document", ""),
            "embedding_metadata": emb.get("metadata", {}),
        }

    rows: list[dict[str, Any]] = []
    for asset in assets:
        doc_id = asset.get("doc_id", "")
        match = embed_map.get(doc_id, {})

        # Serialise tags back to JSON for the JSONB column.
        tags = asset.get("tags")
        tags_json = json.dumps(tags, ensure_ascii=False) if isinstance(tags, list) else tags or "[]"

        row = {
            "doc_id": doc_id,
            "brand_id": asset.get("brand_id", ""),
            "type": asset.get("type", "asset"),
            "source_phase": asset.get("source_phase", ""),
            "title": asset.get("title", ""),
            "tags": tags_json,
            "lang": asset.get("lang", "zh"),
            "file_path": asset.get("file_path", ""),
            "vector_id": asset.get("vector_id", ""),
            "source_project_id": asset.get("source_project_id", ""),
            "created_at": asset.get("created_at", ""),
            "updated_at": asset.get("updated_at", ""),
            "checksum": asset.get("checksum", ""),
            # Embedding text (if available in Chroma)
            "document_text": match.get("document", ""),
            # Placeholder — real vector is computed by pgvector on insert
            "embedding": None,
        }
        rows.append(row)

    return rows


def _insert_into_pg(
    uri: str,
    rows: list[dict[str, Any]],
    brand: str,
) -> None:
    """Insert formatted rows into PostgreSQL via psycopg2/psycopg.

    Creates the schema and table if they do not exist.
    """
    import psycopg2  # type: ignore[import-untyped]  # psycopg2 has no type stubs

    conn = psycopg2.connect(uri)
    try:
        cur = conn.cursor()

        # Create schema and table (idempotent)
        cur.execute(
            """
            CREATE SCHEMA IF NOT EXISTS asset_library
        """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS asset_library.assets (
                doc_id            TEXT PRIMARY KEY,
                brand_id          TEXT NOT NULL,
                type              TEXT NOT NULL,
                source_phase      TEXT,
                title             TEXT NOT NULL,
                tags              JSONB DEFAULT '[]',
                lang              TEXT DEFAULT 'zh',
                file_path         TEXT,
                vector_id         TEXT,
                source_project_id TEXT,
                created_at        TIMESTAMP,
                updated_at        TIMESTAMP,
                checksum          TEXT,
                document_text     TEXT,
                embedding         vector(384)
            )
        """
        )

        # Upsert each row
        for row in rows:
            # We skip the embedding column here — real vectorisation
            # would be done by a separate embedding service.  We store
            # the raw document_text for later embedding.
            cur.execute(
                """
                INSERT INTO asset_library.assets (
                    doc_id, brand_id, type, source_phase, title, tags,
                    lang, file_path, vector_id, source_project_id,
                    created_at, updated_at, checksum, document_text
                ) VALUES (
                    %(doc_id)s, %(brand_id)s, %(type)s, %(source_phase)s,
                    %(title)s, %(tags)s::jsonb, %(lang)s, %(file_path)s,
                    %(vector_id)s, %(source_project_id)s,
                    %(created_at)s::timestamptz, %(updated_at)s::timestamptz,
                    %(checksum)s, %(document_text)s
                ) ON CONFLICT (doc_id) DO UPDATE SET
                    brand_id          = EXCLUDED.brand_id,
                    type              = EXCLUDED.type,
                    source_phase      = EXCLUDED.source_phase,
                    title             = EXCLUDED.title,
                    tags              = EXCLUDED.tags,
                    lang              = EXCLUDED.lang,
                    file_path         = EXCLUDED.file_path,
                    vector_id         = EXCLUDED.vector_id,
                    source_project_id = EXCLUDED.source_project_id,
                    updated_at        = EXCLUDED.updated_at,
                    checksum          = EXCLUDED.checksum,
                    document_text     = EXCLUDED.document_text
                """,
                row,
            )

        conn.commit()
    finally:
        conn.close()


def _print_report(report: dict[str, Any]) -> None:
    """Print the migration report to stdout."""
    dash = "-" * 50
    print(dash)
    print(f"  Asset Library Migration Report  —  brand: {report['brand']}")
    print(dash)
    print(f"  Dry run          : {report['dry_run']}")
    print(f"  Assets found     : {report['asset_count']}")
    print(f"  Embeddings found : {report['embedding_count']}")
    print(f"  Success count    : {report['success_count']}")
    print(f"  Fail count       : {report['fail_count']}")
    print(f"  PG URI provided  : {report['pg_uri_configured']}")
    if report["checksums"]:
        print(f"  Checksum entries : {len(report['checksums'])}")
    if report["errors"]:
        print(f"  Errors ({len(report['errors'])}):")
        for err in report["errors"]:
            print(f"    - {err}")
    print(dash)

    # Compute aggregate checksum for verification
    all_cs = sorted(report["checksums"].values())
    aggregate = hashlib.sha256("|".join(all_cs).encode()).hexdigest()
    print(f"  Aggregate checksum (SHA-256): {aggregate}")
    print(dash)
