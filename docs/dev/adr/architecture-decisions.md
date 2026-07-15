# Architecture Decision Records — AutoMedia

> Last updated: 2026-07-12
> Current version: 1.0.0

---

## ADR-001: Singleton Registry Unification

### Status
Accepted · Effort: Medium (1–2 days)

### Context

Three singleton registries exist in the codebase with different internal mechanics:

| Registry | File | Singleton Mechanism | Registration Style | API Surface |
|----------|------|-------------------|-------------------|-------------|
| `GateRegistry` | `gates/base.py` | `__new__` with `_instance` class var | `__init_subclass__` auto-registration + manual `register()` | `register()`, `get()`, `list()`, `clear()`, `get_all()`, `__contains__`, `__len__`, `__repr__` |
| `AdapterRegistry` | `adapters/registry.py` | `__new__` with `_instance` class var | Manual `register()` | `register()`, `get()`, `list()`, `clear()` — all `@classmethod` |
| `OmniToolRegistry` | `omni/registry.py` | `__new__` with `_instance` class var | Manual `register()` | `register()`, `get()`, `list_tools()`, `list()` (deprecated), `clear()` — all `@classmethod` |

All three share a core pattern (singleton instance, string-keyed dict, CRUD methods) but diverge in details — whether methods are `@classmethod` vs instance methods, naming of `list()` vs `list_tools()`, and presence of extras like `get_all()`, `__contains__`, and validation logic.

### Options Considered

#### Option A: Leave as-is (Do nothing)
- **Pros:** Zero risk, no test changes, no migration effort.
- **Cons:** Perpetuates inconsistency; developers writing a new registry must choose a pattern arbitrarily; `OmniToolRegistry.list()` deprecated alias persists confusingly.

#### Option B: Extract a common `BaseRegistry` mixin class
Introduce a single `BaseRegistry` (or `SingletonRegistry`) in a shared location (e.g. `automedia/core/registry.py`) that codifies:
- Singleton via `__new__` + `_instance`
- `register(key, value)`, `get(key)`, `list()`, `clear()`, `__contains__`, `__len__`, `__repr__`
- Each subclass overrides registration validation.

- **Pros:** DRY; consistent API; one place to fix if the pattern evolves; preserves backward compat via add-only.
- **Cons:** Medium effort; needs a minor version bump; all three registries must be updated in one PR.

#### Option C: Standardize `OmniToolRegistry` and `AdapterRegistry` to match `GateRegistry` interface
Make the two smaller registries match the richer `GateRegistry` interface without extracting a base class.
- **Pros:** Less refactoring than Option B; only two files change.
- **Cons:** Duplication remains; next new registry would need to be nudged manually.

### Recommended Approach

**Option B: Extract a common `BaseRegistry` mixin class.**

Implementation plan:

1. Create `automedia/core/registry.py` with a `BaseRegistry` that:
   - Implements the singleton pattern via `__new__`
   - Provides `register(key, value)`, `get(key)`, `list()`, `clear()`, `__contains__`, `__len__`, `__repr__`
   - Defines `_validate(key, value)` as a no-op hook for subclasses to override
   - Keeps `_registry` as an instance dict (not class-level) to enable clean test isolation via `clear()`

2. Refactor `GateRegistry(gates/base.py:17)` to inherit from `BaseRegistry`:
   - Override `_validate()` to enforce regex and duplicate checks (existing logic moves there)
   - Keep `get_all()` and the module-level `_registry: GateRegistry` singleton

3. Refactor `AdapterRegistry(adapters/registry.py:11)` to inherit from `BaseRegistry`:
   - Override `_validate()` to enforce `platform_name` is non-empty
   - Keep `@classmethod` wrappers for backward compatibility, or migrate all callers

4. Refactor `OmniToolRegistry(omni/registry.py:11)` to inherit from `BaseRegistry`:
   - Keep `list_tools()` as primary, keep `list()` as deprecated alias
   - Override `_validate()` to enforce `name` is non-empty

### Rationale

- The three registries share ≈70% structural code (singleton boilerplate, CRUD, iteration protocol). Extracting a base eliminates that duplication.
- Extending with a new registry becomes trivial — 10 lines instead of 60.
- `__contains__` and `__len__` are standard Python protocol methods that all dict-like registries should support; `GateRegistry` already has them.
- A minor version bump (1.1.0) signals backward-compatible addition — all existing import paths and method signatures remain valid.

### Watch Out For

- **Module-level import order:** `BaseRegistry` must be importable without circular deps. Place it in `automedia/core/registry.py` which has no dependency on gates, adapters, or omni.
- **`GateRegistry.__init_subclass__` auto-registration:** This is unique to gates and should remain in `BaseGate.__init_subclass__`, not in `BaseRegistry`.
- **Test `clear()` isolation:** Ensure `clear()` resets instance state, not class state, so tests don't leak across modules.

---

## ADR-002: HITL ↔ Decision Layer Decoupling

### Status
Implemented · Effort: Medium (1–2 days)

### Context

The `hitl/` and `decision/` packages have a bidirectional import dependency:

| Direction | File | Import | Severity |
|-----------|------|--------|----------|
| `hitl/` → `decision/` | `hitl/config.py:11` | `from automedia.decision import dependency` | **Hard** — module-level, used at import time to build `_BUILTIN_PRESETS` |
| `hitl/` → `decision/` | `hitl/executor.py:29` | `from automedia.decision.base import DecisionArtifact` | **Medium** — type annotation in public API |
| `decision/` → `hitl/` | `decision/orchestrator.py:35` | `from automedia.hitl.executor import NodeExecutor` | **Soft** — wrapped in try/except, optional |
| `decision/` → `hitl/` | `decision/cli/solution.py:344` | `from automedia.hitl.config import HITLConfig` | **Hard** — direct import |

This means:
- Importing `HITLConfig` immediately imports `automedia.decision.dependency`, pulling in the entire decision graph.
- HITL cannot be used or tested without the decision package installed.
- The decision layer optionally depends on HITL, creating a tangled graph.

### Options Considered

#### Option A: Define a `NodeProvider` Protocol in HITL, inject from decision
Create a `NodeProvider` Protocol in `hitl/protocol.py` with a `list_all_nodes() -> list[dict]` method. `HITLConfig` accepts an optional `NodeProvider` instance. The decision layer registers itself as the provider. Move the `_BUILTIN_PRESETS` construction out of module-level into lazy initialization.

- **Pros:** Clean dependency inversion; HITL becomes fully standalone; no runtime imports from decision; testable with mock providers.
- **Cons:** Requires changing the `HITLConfig.__init__` signature (minor breaking change); need lazy preset construction.

#### Option B: Move preset construction entirely into the decision layer
Remove `_BUILTIN_PRESETS` from `hitl/config.py`. Add a `decision/hitl_bridge.py` that constructs presets and injects them into `HITLConfig`.

- **Pros:** Decision owns its node metadata; HITL has zero knowledge of decision.
- **Cons:** Adds boilerplate bridge module; still requires HITL config changes.

#### Option C: Soften with deferred import + type stub
Replace `from automedia.decision import dependency` with a deferred import inside `_load_preset()`. Keep `DecisionArtifact` import but guard with `TYPE_CHECKING`.

- **Pros:** Minimal change; removes import-time coupling.
- **Cons:** Does not truly decouple; still requires decision package to be installed for HITL to function.

### Recommended Approach

**Option A: Define a `NodeProvider` Protocol in HITL, inject from decision.**

Implementation plan:

1. Create `automedia/hitl/protocol.py`:
   ```python
   from __future__ import annotations
   from typing import Protocol, Any

   class NodeProvider(Protocol):
       """Abstract source of decision node metadata."""
       def list_all_nodes(self) -> list[dict[str, Any]]: ...
   ```

2. Refactor `hitl/config.py`:
   - Remove `from automedia.decision import dependency`
   - Add `node_provider: NodeProvider | None = None` parameter to `HITLConfig.__init__`
   - Make `_BUILTIN_PRESETS` lazy (computed on first access, not at module level)
   - When `node_provider` is provided, use it to build auto-generated presets

3. Refactor `hitl/executor.py`:
   - Replace `from automedia.decision.base import DecisionArtifact` with a local `DecisionArtifact` Protocol definition (duck type) or guard with `TYPE_CHECKING`
   - Keep the import for runtime, but make it deferred inside methods

4. Create `automedia/decision/hitl_provider.py`:
   - Expose a function `create_hitl_config(preset_name, overrides_dir) -> HITLConfig` that wires in the decision `dependency` module as `NodeProvider`

5. Refactor `decision/orchestrator.py`:
   - Keep existing try/except fallback, or switch to using the provider

### Rationale

- **Standalone HITL:** The framework can be imported and tested without decision. Unit tests for `HITLConfig` can use a mock `NodeProvider` returning 2–3 test nodes.
- **Clean dependency direction:** `decision/` → `hitl/` (one-way), not bidirectional.
- **Lazy presets:** Moving `_BUILTIN_PRESETS` out of module-level avoids import-time coupling entirely.
- **Backward compatible:** `HITLConfig()` (no args) still works — it just won't have auto-generated presets unless a provider is wired. Decision layer's `create_hitl_config()` wires it automatically.

### Watch Out For

- **`DecisionArtifact`** is used as a return type in `NodeExecutor`. Abstract it behind a Protocol or use `Any` with documentation, avoiding a hard import from `decision.base`.
- **The docstring example** in `executor.py` references `DiagnosticAgent` — update to use the Protocol pattern.

---

## ADR-003: Rename `platform/` to Avoid stdlib Conflict

### Status
Accepted · Effort: Quick (< 1 hour)

### Context

The directory `src/automedia/platform/` contains two modules:
- `xiaohongshu.py` — exports `XiaohongshuAdapter`
- `zhihu_draft.py` — exports `ZhihuDraftAdapter`

Python 3 has a stdlib module called `platform` (https://docs.python.org/3/library/platform.html). When any file inside the `automedia` package does `import platform`, Python's import system may resolve to the local `automedia.platform` package instead of the stdlib — depending on `sys.path` order. Currently no file inside `automedia/` uses `import platform`, but:

1. Any future or third-party code that does will be silently broken.
2. The two modules in `platform/` are conceptually "platform-specific draft formatting" — they belong more naturally under `automedia/adapters/platforms/`, which already exists with similar purpose (XiaohongshuPublisher, ZhihuPublisher are the publish-tier counterparts).

### Options Considered

#### Option A: Rename to `platform_drafts/`
Rename directory and update imports.
- **Pros:** Simple, avoids conflict, clear name.
- **Cons:** Breaks any external imports of `automedia.platform`.

#### Option B: Merge into `adapters/platforms/`
Move `xiaohongshu.py` → `adapters/platforms/xiaohongshu_draft.py` and `zhihu_draft.py` → `adapters/platforms/zhihu_draft.py`. Update the `platform/__init__.py` to re-export from the new locations for backward compat.
- **Pros:** Eliminates the namespace entirely; consolidates all platform adapters in one place; `adapters/platforms/` already exists.
- **Cons:** Content is slightly different from publish adapters (draft formatting vs. publishing); requires careful merge to avoid naming collision with existing `XiaohongshuPublisher`.

#### Option C: Keep but add `# type: ignore` and absolute imports
Keep as-is and document that imports of stdlib `platform` must use `import platform as _stdlib_platform`.
- **Pros:** Zero work.
- **Cons:** Fragile; everyone must remember the workaround; breaks silently.

### Recommended Approach

**Option A: Rename to `platform_drafts/`** (with backward-compat shim).

Implementation plan:

1. `git mv src/automedia/platform/ src/automedia/platform_drafts/`
2. Update `platform_drafts/__init__.py`:
   - Change imports to `from automedia.platform_drafts.xiaohongshu import ...`
3. Create `src/automedia/platform/__init__.py` as a backward-compat shim:
   ```python
   from automedia.platform_drafts import XiaohongshuAdapter, ZhihuDraftAdapter
   __all__ = ["XiaohongshuAdapter", "ZhihuDraftAdapter"]
   ```
4. Update any existing import of `automedia.platform` across the codebase.
5. Add a deprecation warning in the shim (via `warnings.warn`).
6. Schedule removal of the shim for v2.0.

### Rationale

- **Minimizes risk:** A rename is fast, localized, and doesn't touch business logic.
- **Backward compat:** The shim `__init__.py` in the old location ensures existing imports keep working with a deprecation warning.
- **No merge complexity:** Unlike Option B, there's no risk of class-name collisions with `adapters/platforms/`.
- **Quick & safe:** The change touches only 4 files (rename, shim, and two internal consumers).

### Watch Out For

- **Git rename tracking:** Use `git mv` to preserve file history.
- **Deprecation timeline:** Announce in CHANGELOG under a "Deprecations" section for v1.x, remove the shim in v2.0.

---

## ADR-004: Decompose `mcp/server.py` Monolith

### Status
Accepted · Effort: Medium (1–2 days)

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
