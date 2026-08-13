# ADR-004: Decompose `mcp/server.py` Monolith

### Status
Accepted · Effort: Medium (1–2 days)

> **Note:** This ADR was partially implemented. The tools extraction (`mcp/tools.py`) was completed, but the full 4-module split (allowlist, tools, resources, server) was not fully carried out.

### Context

`src/automedia/mcp/server.py` is 1,228 lines with a single public API surface (`create_server()` + tool functions). The file contains 5 distinct logical sections:

| Section | Lines | Contents |
|---------|-------|----------|
| Allowlist helpers | 50–145 | `_load_allowlist`, `_reset_allowlist_cache`, `check_path_allowed`, `_require_allowed` |
| Helper utilities | 148–220 | `_resolve_projects_dir`, `_discover_projects`, `_project_assets`, `_pipeline_result_to_dict` |
| Pipeline tracker | 226–233 | Global `_pipeline_tracker` dict, `_lock`, `_SERVER_START` |
| Tool handlers (14) | 237–941 | All tool functions (module-level, each 30–120 lines) |
| Server factory + resources | 971–1189 | `create_server()`, 3 resource functions |
| CLI entry point | 1197–1228 | `main()` |

The file is imported from:
- `automedia/mcp/__init__.py` — re-exports 9 tool functions + `create_server`
- **50 import sites across 7 test files** — tests directly import individual tool functions for unit testing

This means any decomposition must preserve backward-compatible import paths.

### Options Considered

#### Option A: Split into 4 modules with backward-compat re-exports
Extract allowlist, tools, and resources into separate files. Keep `server.py` as a thin orchestration module with re-exports.

Proposed modules:
- `mcp/allowlist.py` — allowlist helpers
- `mcp/tools.py` — all 14 tool handler functions
- `mcp/resources.py` — 3 MCP resource functions + pipeline tracker
- `mcp/server.py` — `create_server()` + `main()` + from-module imports + backward-compat re-exports

- **Pros:** Clean separation; single-responsibility; each module ~300–400 lines; backward compat via re-exports.
- **Cons:** 50 test import sites need updating (can be mitigated by re-exports).

#### Option B: Extract tools only
Move only the 14 tool handlers to `mcp/tools.py`. Leave everything else in `server.py`.
- **Pros:** Minimal diff; addresses the largest section.
- **Cons:** Leaves 600+ lines in server.py; partial fix.

#### Option C: Keep monolithic
- **Pros:** Zero risk.
- **Cons:** File continues to grow (new tools added regularly); violates single-responsibility; hard to navigate.

### Recommended Approach

**Option A: Split into 4 modules with backward-compat re-exports.**

Implementation plan:

1. Create `mcp/allowlist.py`:
   - Move `_ALLOWLIST_FILE`, `_ALLOWED_OUTPUT_FORMATS`, `_cached_allowlist`
   - Move `_load_allowlist()`, `_reset_allowlist_cache()`, `check_path_allowed()`, `_require_allowed()`

2. Create `mcp/tools.py`:
   - Move all 14 tool handler functions (`select_topic` through `health_check`)
   - Import allowlist helpers from `mcp/allowlist.py`
   - Import `_pipeline_tracker`, `_lock`, `_SERVER_START` from `mcp/resources.py` (or a shared state module)

3. Create `mcp/resources.py`:
   - Move `_resolve_projects_dir()`, `_discover_projects()`, `_project_assets()`, `_pipeline_result_to_dict()`
   - Move `_pipeline_tracker`, `_lock`, `_SERVER_START`
   - Move the 3 resource functions (they are defined inline inside `create_server()` as closures — refactor to module-level functions)

4. Update `mcp/server.py`:
   - Keep `create_server()` — import tool functions from `mcp/tools.py` and register them
   - Keep `main()` — CLI entry point
   - Add backward-compat re-exports:
     ```python
     # Backward-compatible imports (deprecated — import from submodules directly)
     from automedia.mcp.tools import (
         select_topic, run_pipeline, archive_project, ...
     )
     from automedia.mcp.allowlist import check_path_allowed, _require_allowed
     ```
   - Add `__all__` matching the current public API

5. Update `mcp/__init__.py`:
   - Update imports to point to `mcp/tools.py` instead of `mcp/server.py` for individual tools
   - Import `create_server` from `mcp/server.py` as before

### Rationale

- **Backward compat guaranteed:** Re-exports in `server.py` mean zero changes to the 50 test import sites and 1 package `__init__.py` import.
- **Clear ownership:** Each module has a single responsibility. `tools.py` is the longest at ~700 lines but that's manageable for a file of standalone handler functions.
- **Incremental adoption:** The decomp can be done file-by-file in separate commits, each preserving tests.
- **Resource closure refactor:** The 3 resources currently defined as closures inside `create_server()` need to become module-level functions. This is a straightforward refactor since they only depend on `_resolve_projects_dir()` and `_discover_projects()`.

### Watch Out For

- **`_pipeline_tracker` access:** It's accessed by `run_pipeline()`, `get_pipeline_progress()`, and `health_check()`. Use a shared `_state` module or pass the tracker explicitly. A simple shared-state module (`mcp/_state.py`) is cleanest.
- **`_ALLOWED_OUTPUT_FORMATS`** is used by `format_output` — ensure it's accessible from `tools.py` via import from `allowlist.py`.
- **Test path imports:** Even with re-exports, some test files import from `automedia.mcp.server` directly. Those will continue to work via re-exports. No test changes needed.
- **`create_server()` length:** After extraction, `create_server()` will still be ~200 lines (14 tool registrations + 3 resource registrations + instructions). This is fine — it's intentionally declarative boilerplate that maps names ↔ handlers ↔ descriptions.
