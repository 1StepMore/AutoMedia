# ADR-002: HITL ↔ Decision Layer Decoupling

### Status
Implemented · Effort: Medium (1–2 days)

> **Note:** This ADR was rendered moot by the D3 cleanup, which removed the entire `automedia/decision/` package. The HITL framework now has no dependency on the decision layer.

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
