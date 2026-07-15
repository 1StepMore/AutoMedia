---
title: Asset Library
description: Persistent searchable storage for brand production artifacts — SQLite metadata with Chroma vector search.
---

# Asset Library

The Asset Library provides persistent, searchable storage for brand production
artifacts. It combines **SQLite** for structured metadata with **Chroma** for
semantic vector search.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Asset Library                        │
│                                                      │
│  ┌─────────────────────┐  ┌──────────────────────┐  │
│  │   SQLite (metadata)  │  │   Chroma (vectors)   │  │
│  │                      │  │                      │  │
│  │  assets table        │  │  embeddings index    │  │
│  │  doc_id (PK)         │  │  doc_id → vector     │  │
│  │  brand_id            │  │  text → embedding    │  │
│  │  type                │  │                      │  │
│  │  tags (JSON array)   │  │                      │  │
│  │  checksum            │  │                      │  │
│  │  vector_id → Chroma  │  │                      │  │
│  └─────────────────────┘  └──────────────────────┘  │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │              Search Pipeline                   │   │
│  │  SQLite keyword → Chroma semantic → merge     │   │
│  │  → deduplicate → filter → sort by score      │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### Storage Layout

```
~/.automedia/asset-library/
  └── <brand>/
      ├── index.sqlite        # SQLite database
      └── chroma/             # Chroma persistent index
```

---

## AssetDoc Schema

```python
@dataclass
class AssetDoc:
    doc_id: str               # UUID (auto-generated if empty)
    brand_id: str             # Brand identifier
    type: str                 # One of built-in taxonomy
    source_phase: str         # e.g. "1b", "2", "3"
    title: str                # Extracted from content or filename
    tags: list[str]           # Custom user-defined tags
    lang: str                 # Language code (default: "zh")
    file_path: str            # Absolute path to source file
    vector_id: str            # Chroma embedding reference
    source_project_id: str    # Project directory name
    created_at: str           # ISO timestamp
    updated_at: str           # ISO timestamp
    checksum: str             # MD5 of file content
    content_stage: str        # Lifecycle stage: raw, draft, wiki, archived
    previous_stage: str       # Previous stage before archiving (for restore)
    source_url: str           # Original source URL
    source_platform: str      # Original source platform
    author: str               # Content author
    publish_date: str         # Original publish date
    priority: int             # Content priority score
```

### Type Taxonomy

| Type | Description |
|------|-------------|
| `strategy` | Briefs, brand DNA, market reports, competitor matrices |
| `persona` | Audience personas and segmentation maps |
| `product` | Product specs, blueprints, feature docs |
| `content` | Published content, calendars, scripts |
| `kol_brief` | KOL/influencer collaboration briefs |
| `asset` | Media assets (images, videos, audio) |

---

## APIs

### `ingest_artifacts()`

```python
from automedia.asset_library import ingest_artifacts

result = ingest_artifacts(
    project_dir="/path/to/project",
    brand="EcoBrand",
)
# => IngestResult(success=12, fail=0, errors=[])
```

Scans the project directory for markdown, YAML, JSON, and CSV files, extracts
metadata, computes MD5 checksums, and writes to both SQLite and Chroma.
Duplicates (same checksum) are silently skipped.

### `search()`

```python
from automedia.asset_library import search_assets, AssetLibrary

# Standalone search
results = search_assets(
    query="eco-friendly packaging",
    brand="EcoBrand",
    filters={"type": "strategy", "lang": "zh"},
)

# Via AssetLibrary instance
with AssetLibrary(brand="EcoBrand") as lib:
    results = lib.search(
        query="market trends 2025",
        filters={"tags": ["competitive-analysis"]},
    )

# Each result includes a `_score` key (higher = better)
```

### Filter Options

| Key | Type | Description |
|-----|------|-------------|
| `type` | str | Filter by built-in asset type |
| `tags` | list[str] | Match any of the given custom tags |
| `lang` | str | Language code (e.g. `"zh"`, `"en"`) |
| `phase` | str | Source phase (e.g. `"1b"`, `"2"`) |

---

## CLI Commands

The following CLI commands are available for Asset Library management:

```bash
# Ingest project artifacts into the Asset Library
automedia asset ingest --project-dir ./my-project --brand EcoBrand

# Search the Asset Library
automedia asset search --brand EcoBrand --query "packaging design"

# List all assets for a brand
automedia asset list --brand EcoBrand

# Delete an asset
automedia asset delete --doc-id <uuid>
```

These commands are fully implemented and registered under ``automedia asset``.
Note that ``automedia run`` also automatically ingests artifacts as part of the
pipeline — you only need the explicit ``asset ingest`` command for standalone
ingestion outside a pipeline run.

---

## Post-Pipeline Auto-Ingest

Every call to ``run_full_pipeline()`` automatically ingests project artifacts
into the Asset Library after all gates complete. This happens as a **non-blocking
best-effort** operation — ingestion failures are logged as warnings and never
block pipeline completion or alter the ``PipelineResult``.

```python
from automedia import run_full_pipeline

result = run_full_pipeline(topic="AI trends", brand="EcoBrand")
# → Artifacts ingested automatically into ~/.automedia/asset-library/EcoBrand/
# → result.status unaffected by ingest failure
```

Implementation (in ``automedia/pipelines/runner.py``):

```python
# Auto-ingest artifacts into asset library
try:
    from automedia.asset_library import ingest_artifacts
    ingest_result = ingest_artifacts(project.project_dir, brand)
    if ingest_result.success_count > 0:
        log.info("pipeline.asset_library.ingest", count=ingest_result.success_count)
except Exception as exc:
    log.warning("pipeline.asset_library.ingest_failed", error=str(exc))
```

---

## Decision Layer Integration

Decision agents automatically query the Asset Library before inference to avoid
redundant analysis:

```python
class BrandPositioningAgent(BaseDecisionAgent):
    def execute(self, context, asset_library=None):
        # Auto-retrieve relevant brand docs
        docs = self.search_asset_library("EcoBrand", query="brand positioning")
        # ... use retrieved docs in prompt context
```

The HITL ``NodeExecutor`` now constructs and passes a real ``AssetLibrary``
instance to every agent when the execution context contains a ``brand`` key:

```python
executor.execute("brand_positioning", agent, {"brand": "EcoBrand", ...})
# → agent receives AssetLibrary(brand="EcoBrand") instead of None
```

The library is automatically closed after the agent finishes executing.

---

## Promotion Lifecycle

Assets progress through the following content lifecycle:

```
raw -> draft -> wiki -> archived
```

Each promotion step validates the current stage and rejects invalid transitions
(e.g. skipping ``draft`` to go directly from ``raw`` to ``wiki``).

| Stage | Description |
|-------|-------------|
| `raw` | Freshly ingested, unprocessed asset |
| `draft` | In-progress or draft content |
| `wiki` | Reviewed and ready for publication |
| `archived` | Compliance-retained, no longer active |

### API

```python
from automedia.asset_library import promote_to_draft, promote_to_wiki

promote_to_draft(db, doc_id)       # raw -> draft
promote_to_wiki(db, doc_id)        # draft -> wiki
list_assets_by_stage(db, "wiki")   # list all assets at a given stage
```

---

## Compliance (Archive / Restore)

The Asset Library supports compliance-driven archiving. When a project is
completed or retired, its assets can be bulk-archived.  Archived assets
can later be restored to their previous stage.

### Archive

```python
from automedia.asset_library import archive_project_assets, restore_archived

# Archive all assets for a project
result = archive_project_assets(db, project_id="proj-123")
# => {"status": "ok", "count": 5} or {"status": "no_assets"}

# Restore archived assets
result = restore_archived(db, project_id="proj-123")
# => {"status": "ok", "count": 5} or {"status": "no_archived"}
```

Archive rules:

1. Only assets at ``wiki`` or ``draft`` stage can be archived
2. The current stage is saved in ``previous_stage`` before archiving
3. Already-archived assets are skipped with a log warning
4. Restore returns assets to their ``previous_stage`` and clears the field

### Enforcement

- The **L3 Platform Integrity Gate** can optionally verify that all project
  assets are at ``published`` (or another expected) stage before allowing
  publish operations.
- The L3 gate also checks that asset references (images, files) in the
  content body actually exist in the asset library.

---

## L3 Gate Integration

The L3 Platform Integrity Gate (``platform_integrity.py``) has been extended
with two asset-library-aware checks:

### Asset Reference Verification (``verify_asset_references``)

Before the gate's standard platform-integrity checks run, content is scanned
for markdown image references (``![alt](path)``).  Each referenced path is
checked against the Asset Library:

- **Found**: reference is valid — passes
- **Not found**: reference is reported as missing — gate may fail with
  ``failure_mode="stop"``
- **No asset database available**: references are reported as unchecked
  (soft pass)

### Asset Stage Verification (``verify_asset_stage``)

Checks that all assets associated with the current ``project_id`` are at the
expected content stage (default: ``published``).  This ensures assets are
fully promoted before publish operations proceed.

```python
# Gate context keys for asset verification
context = {
    "asset_database": AssetDatabase(brand="EcoBrand"),
    "project_id": "proj-abc",
    "expected_asset_stage": "published",
}
```

When ``asset_database`` is absent from the context, both checks are skipped
(soft pass), preserving backward compatibility.

---

## Migrations

Database schema migrations live in ``automedia/asset_library/schema.py``.
Run migrations with:

```bash
automedia asset migrate --brand EcoBrand
```

Current migration versions:

| Version | Description |
|---------|-------------|
| 1 | Content stages, source metadata, FTS5 index |
| 2 | Content versioning history table |
| 3 | Ingestion sources table |
| 4 | Archive/restore support — ``previous_stage`` column |

Migrations run automatically when ``AssetDatabase`` opens an existing
database.  Fresh databases are created at the latest schema version.

