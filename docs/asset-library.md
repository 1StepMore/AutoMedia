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

After pipeline execution, outputs are ingested back:

```
pipeline.run_full_pipeline(topic, brand)
    → asset_library.ingest_artifacts(project_dir, brand)
```

---

## Migrations

Database schema migrations live in `automedia/asset_library/migrate.py`.
Run migrations with:

```bash
automedia asset migrate --brand EcoBrand
```
