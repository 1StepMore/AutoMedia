# ADR-001: Singleton Registry Unification

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
