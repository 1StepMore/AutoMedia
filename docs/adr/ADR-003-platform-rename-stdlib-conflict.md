# ADR-003: Rename `platform/` to Avoid stdlib Conflict

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
