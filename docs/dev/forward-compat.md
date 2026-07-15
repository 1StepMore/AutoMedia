---
title: Forward Compatibility Policy
description: v1=readable, v2=re-runnable, v3=auto-migration. Schema stability guarantees and deprecation policy for project metadata files.
---

# Forward Compatibility Policy

## Why This Matters

AutoMedia produces project directories that live on disk indefinitely. A
project created with v0.4.2 should still open, read, and report useful
information when the codebase is at v2.0.0. This policy defines exactly what
"still works" means and what guarantees users and agents can rely on.

This document is referenced by [F48](founder-expectations.md#f48--forward-compatibility)
in the Founder's Expectations. F48 states the priority: readable comes first,
re-runnable comes second, auto-migration comes third.

---

## 1. Compatibility Tiers

Forward compatibility is defined in three tiers. Each tier is a superset of the
one before it. The current codebase targets **v1 (Readable)** as the stable
contract. v2 and v3 are future milestones.

### v1: Readable (Current Stable)

**Guarantee**: New code can open any old project directory and extract
meaningful information from it.

What this means in practice:

- All metadata files (`00_project_info.json`, `pipeline_md5.json`) parse
  correctly under the current schema reader.
- Unknown or future fields are silently ignored (never crash on unexpected
  keys).
- The directory layout (`01_content/`, `02_images/`, etc.) is recognized and
  assets can be enumerated.
- If a file format changes, the old format remains readable for at least one
  major version cycle.

**What is NOT guaranteed at v1**:

- Old topics cannot be re-processed with the new pipeline (that is v2).
- Old projects cannot be auto-upgraded to a new schema (that is v3).

### v2: Re-runnable (Future Goal)

**Guarantee**: Topics from old projects can be re-processed by the current
pipeline without manual re-entry.

What this adds over v1:

- `00_project_info.json` contains enough information to seed a new
  `run_pipeline()` call: `topic`, `brand`, `tenant_id` are all present.
- Old `pipeline_md5.json` checksums do not block a new run (the file is
  overwritten, not merged).
- Pipeline `--resume` works across minor version bumps for the same project.

**Adoption criteria**: v2 is achieved when `automedia run --resume-from
<old-project-dir>` works for projects created under the previous major version.

### v3: Auto-migration (Future Goal)

**Guarantee**: An optional upgrade tool can convert old project directories to
the latest schema, directory layout, and file format in one shot.

What this adds over v2:

- A CLI command `automedia project migrate <project-dir>` upgrades the project
  in place.
- Migration is idempotent: running it twice produces the same result as
  running it once.
- The original project directory is backed up before migration (copy to
  `{project-dir}.bak_{timestamp}`).
- Migration covers: `00_project_info.json` field changes, `pipeline_md5.json`
  schema changes, directory restructuring, and output file format updates.

**Adoption criteria**: v3 is achieved when the migration command exists and
has tests covering every breaking change introduced in the current major
version.

---

## 2. Schema Stability Guarantees

### 2.1 `00_project_info.json`

**Purpose**: Project identity and metadata. Written once at project creation,
never modified afterward.

**Current schema** (v1):

```json
{
  "project_id": "010d36582aa2",
  "topic": "AI video tools comparison",
  "brand": "my-brand",
  "tenant_id": "default",
  "created_at": "2026-07-15T08:07:20.342725+00:00"
}
```

**Stability guarantees**:

| Field | Stability | Can Add? | Can Remove? | Can Change Type? |
|-------|-----------|----------|-------------|------------------|
| `project_id` | **Stable** | No | No | No |
| `topic` | **Stable** | No | No | No |
| `brand` | **Stable** | No | No | No |
| `tenant_id` | **Stable** | No | No | No |
| `created_at` | **Stable** | No | No | No |

**Adding new fields**: Allowed, but every new field MUST be optional in the
reader. Old projects without the field must not error. The reader must supply
a sensible default (`null`, `""`, or `0` as appropriate).

**Removing fields**: Prohibited without a 2-version deprecation cycle (see
§3 Deprecation Policy).

**Changing field types**: Prohibited. If a wider type is needed, add a new
field with a distinct name and deprecate the old one.

**Reader contract**: Code that reads `00_project_info.json` MUST use a lenient
parser. Unknown keys are ignored. Missing optional keys use defaults. The only
hard error is unparseable JSON (malformed file).

### 2.2 `pipeline_md5.json`

**Purpose**: Per-gate file integrity checksums. Written incrementally as each
gate completes. Two subsystems write to this file:

1. **Gate MD5 tracker** (`automedia/hooks/md5_tracker.py`): writes per-gate
   checksums under `gates.<gate_name>`.
2. **Omni MD5 tracker** (`automedia/omni/md5_integration.py`): writes Omni
   pipeline checksums under `omni_*` sections.

**Current schema** (v1):

```json
{
  "gates": {
    "CW": {
      "file_path": "/abs/path/to/project/01_content/drafts/draft.md",
      "md5": "abc123def456",
      "recorded_at": "2026-07-15T08:07:20.342725+00:00"
    },
    "G0": {
      "file_path": "/abs/path/to/project/01_content/drafts/draft.md",
      "md5": "abc123def456",
      "recorded_at": "2026-07-15T08:07:21.102345+00:00"
    }
  },
  "omni_inputs": {},
  "omni_extraction": {
    "/abs/path/to/source.pdf": {
      "md5": "789ghi012jkl"
    }
  },
  "omni_translation": {},
  "omni_orf_outputs": {}
}
```

**Stability guarantees**:

| Section / Field | Stability | Can Add? | Can Remove? | Can Change Type? |
|-----------------|-----------|----------|-------------|------------------|
| `gates` (top-level key) | **Stable** | No | No | No |
| `gates.<name>.file_path` | **Stable** | No | No | No |
| `gates.<name>.md5` | **Stable** | No | No | No |
| `gates.<name>.recorded_at` | **Stable** | No | No | No |
| `omni_inputs` (top-level key) | **Stable** | No | No | No |
| `omni_extraction` (top-level key) | **Stable** | No | No | No |
| `omni_translation` (top-level key) | **Stable** | No | No | No |
| `omni_orf_outputs` (top-level key) | **Stable** | No | No | No |
| New per-entry fields (e.g. `gates.<name>.duration_s`) | **Allowed** | Yes | N/A | N/A |

**Adding new per-gate fields**: Allowed. New fields MUST be optional. Readers
that extract per-gate data MUST tolerate missing keys.

**Adding new top-level sections**: Allowed (e.g. `artifact_links`). Old readers
will ignore them per the lenient parser contract.

**Removing sections**: Prohibited without 2-version deprecation cycle.

**Reader contract**: Same as `00_project_info.json` -- lenient parser, unknown
keys ignored, missing optional keys use defaults. Malformed JSON is the only
hard error.

### 2.3 Directory Structure

**Purpose**: Standard subdirectory layout inside every project directory.

**Current layout** (v1):

```
{project_dir}/
  00_project_info.json
  pipeline_md5.json
  01_content/
    drafts/
  02_images/
    cover/
  03_video/
  04_subtitle/
  05_review/
  06_publish/
```

**Stability guarantees**:

| Directory | Stability | Notes |
|-----------|-----------|-------|
| `01_content/drafts/` | **Stable** | Draft output location |
| `02_images/cover/` | **Stable** | Cover images |
| `03_video/` | **Stable** | Video output |
| `04_subtitle/` | **Stable** | Subtitle files |
| `05_review/` | **Stable** | Review artifacts |
| `06_publish/` | **Stable** | Publish artifacts |
| `00_project_info.json` | **Stable** | At root of project dir |
| `pipeline_md5.json` | **Stable** | At root of project dir |

**Adding new subdirectories**: Allowed. New content types get new numbers
(e.g. `07_audio/`). Old readers will not look for them, which is acceptable.

**Renaming or removing directories**: Prohibited without 2-version deprecation
cycle.

---

## 3. Deprecation Policy

### 3.1 Principles

1. **No silent breakage**. Every breaking change goes through a formal
   deprecation process. Users and agents receive advance notice.
2. **Backward compatibility during deprecation**. Both old and new formats
   are supported concurrently for at least one minor version.
3. **Migration tool for every break**. When the old format is finally removed,
   a migration command is available.

### 3.2 Deprecation Lifecycle

A breaking change goes through four stages:

```
Stage 0:  Announce  ──  CHANGELOG entry: "FIELD_X will be removed in vN+2"
Stage 1:  Deprecate ──  Both old and new formats supported. Reader warns
                        on old format: "FIELD_X is deprecated, see migration guide."
Stage 2:  Remove    ──  Old format no longer read. Migration tool converts.
Stage 3:  Cleanup   ──  Migration tool may be archived. Old format fully unsupported.
```

Each stage lasts at minimum one minor version (X.Y.0). A full deprecation
cycle is therefore at least two minor versions.

### 3.3 What Qualifies as a Breaking Change

Any change that causes old project directories to fail under new code:

- Removing a field from `00_project_info.json` or `pipeline_md5.json`.
- Changing the type or format of an existing field.
- Removing or renaming a standard subdirectory.
- Changing the `pipeline_md5.json` top-level key structure.
- Requiring a field that old projects do not have.

Changes that are NOT breaking:

- Adding a new optional field.
- Adding a new subdirectory.
- Adding a new top-level section to `pipeline_md5.json`.
- Changing internal code that does not affect serialized output.

### 3.4 Version Numbering and Compatibility

AutoMedia follows [Semantic Versioning 2.0.0](https://semver.org/):

| Bump | Meaning for Forward Compat |
|------|---------------------------|
| **PATCH** (0.4.1 -> 0.4.2) | Fully backward and forward compatible. No schema changes. |
| **MINOR** (0.4.0 -> 0.5.0) | New features added. Schema MAY gain new optional fields. Old projects remain readable. Deprecation warnings MAY begin. |
| **MAJOR** (1.0.0 -> 2.0.0) | Breaking changes allowed, but only after a deprecation cycle. Migration tool MUST exist for every documented breaking change. |

### 3.5 Migration Tool Contract

When a migration tool ships (target: v3 tier), it must:

1. Accept a project directory path.
2. Detect the current schema version of that project.
3. If migration is needed, create a backup (`{project-dir}.bak_{timestamp}`).
4. Perform all upgrades in a single pass.
5. Print a detailed log of what changed.
6. Return exit code 0 on success, non-zero on failure.
7. Be idempotent: running on an already-migrated project is a no-op (exit 0).

---

## 4. Agent-Facing Guarantees

Agents (OpenCode, Claude Code, etc.) interact with old projects through MCP
tools. The forward compatibility policy applies to these tools as well:

- `get_pipeline_status(project_id)` must return valid data for old projects
  (v1 guarantee).
- `get_project_assets(project_dir)` must list all files in old project
  directories (v1 guarantee).
- `run_pipeline(topic=old_project.topic, brand=old_project.brand)` must
  accept identity data from `00_project_info.json` (v2 guarantee).
- `archive_project(project_id)` must work regardless of project age.

Agent-facing behavior when opening an old project:

> "This project was produced with AutoMedia v0.4.2. Content is accessible.
> Re-running with current pipeline is available on request."

---

## 5. Summary Table

| Aspect | v1 (Current) | v2 (Future) | v3 (Future) |
|--------|-------------|-------------|-------------|
| Read old metadata files | Yes | Yes | Yes |
| List old project assets | Yes | Yes | Yes |
| Parse old `00_project_info.json` | Yes | Yes | Yes |
| Parse old `pipeline_md5.json` | Yes | Yes | Yes |
| Re-run old topic in new pipeline | No | Yes | Yes |
| Resume old project after upgrade | No | Yes (minor) | Yes |
| Auto-upgrade old project schema | No | No | Yes |
| Migration CLI tool | Not needed | Not needed | Exists |
| Backup before upgrade | N/A | N/A | Yes |
| Idempotent migration | N/A | N/A | Yes |

---

## 6. Related Documents

- [F48: Forward Compatibility](founder-expectations.md#f48--forward-compatibility) -
  Founder's expectation that old projects remain readable.
- [F43: Pipeline Integrity Verification](founder-expectations.md#f43--pipeline-integrity-verification) -
  MD5 checksum tracking and verification.
- [F39: Run Isolation](founder-expectations.md#f39--run-isolation) -
  Shared-nothing project isolation model.
- `src/automedia/hooks/md5_tracker.py` - Gate MD5 tracker implementation.
- `src/automedia/omni/md5_integration.py` - Omni MD5 tracker implementation.
- `src/automedia/core/project.py` - Project creation and `00_project_info.json`
  writer.
