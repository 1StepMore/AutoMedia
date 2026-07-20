---
title: API Gotchas
description: Common pitfalls when using the AutoMedia API — drawn from the original SKILL.md and day-to-day development lessons.
---

# Common API Pitfalls

This document records common pitfalls when using the AutoMedia API, drawn from
the original SKILL.md and day-to-day development experience.

## Paths and Directories

### `Project.init()` slugifies the topic parameter

```python
# topic is slugified: lowercased, non-ASCII removed, hyphenated
p = Project.init("Hello World 项目启动")  # directory name: 20260707_hello-world
```

Chinese characters are completely removed, so the directory name may be shorter
than expected. If the slug result is empty, a `ValueError` is raised.

**Gotcha:** Do not assume the original Chinese topic content is preserved in
`project_dir`.

### `sanitize_path()` rejects path traversal

```python
from automedia.core.project import sanitize_path

sanitize_path("../etc")   # ValueError: Path must not contain '..'
sanitize_path("~/config") # ValueError: Path must not contain '~'
sanitize_path("a//b")     # ValueError: Path must not contain '//'
```

This is a security measure to prevent the topic parameter from being used for
path traversal attacks.

## Configuration Loading

### Config merge is shallow + recursive hybrid

`deep_merge()` recursively merges dict values but directly overwrites lists.
This means:

```yaml
# defaults.yaml
blocked_words:
  - investment
  - finance

# brand-profile.yaml
blocked_words:
  - politics
```

Result: `blocked_words` only contains `["politics"]`, it does not merge with
the defaults.

**Solution:** To append list items, write the complete list in overrides.

### Environment variable override rules

`AUTOMEDIA_LLM_API_KEY=sk-xxx` resolves to:

```python
{"llm": {"api": {"key": "sk-xxx"}}}
```

That is, each underscore-delimited segment becomes a nesting level. This can
lead to unexpected nesting depth:

```
AUTOMEDIA_FOO_BAR_BAZ=val  →  {"foo": {"bar": {"baz": "val"}}}
```

**Gotcha:** Do not use extra underscores in variable names, or they will
produce unexpected nested structures.

## Pipeline Execution

### `run_full_pipeline()` does not throw exceptions

All exceptions are caught and placed into the `PipelineResult.error` field,
with status set to `"failed"`. This is by design, so callers check
`result.status` uniformly instead of using try/except.

```python
result = run_full_pipeline(topic, brand)
if result.status == "failed":
    print(f"Error: {result.error}")  # do not try/except
```

**Gotcha:** If you forget to check `result.status`, you might mistakenly
assume the Pipeline completed successfully.

### `resume_from` uses Gate names, not numbers

```python
# Correct
run_full_pipeline(topic, brand, resume_from="G3")

# Wrong (won't error but won't work as expected)
run_full_pipeline(topic, brand, resume_from="3")
```

The `resume_from` value must exist in the current mode's gate list, otherwise
a `ValueError` is raised.

### mode affects the gate list

Different modes execute different Gate subsets:

| mode | Gates Included |
|------|----------------|
| `auto` | pre-gate → CW → G0-G6 → V0-V7 → H0 → L1-L4 |
| `text_only` | CW → G0-G6 → H0 → L1-L4 |
| `text_with_cover` | CW → G0-G6 → H0 → L1-L4 (+ cover image) |
| `video_only` | V0-V7 → H0 → L1-L4 |
| `image-carousel` | CW → G0-G6 → L1-L4 (+ carousel images) |
| `social-thread` | CW → G0-G6 → L1-L4 (thread format) |
| `short-video` | pre-gate → CW → G0-G6 → V0-V7 → H0 → L1-L4 |
| `qa_only` | G0 → G2 → G3 → V1 → V6 |
| `repurpose` | CW → G0-G6 → V0-V7 → H0 → L1-L4 → P1-P4 |

**Gotcha:** `qa_only` only runs 5 gates, far fewer than the full pipeline's
33 gates. Do not use `qa_only` results to judge whether the entire pipeline
is working correctly. `text_with_cover` gate list is identical to `text_only`
but additionally generates a cover image.

## Gate Development

### Gate must define `_gate_name` and `_failure_mode`

Missing either attribute raises `NotImplementedError` at runtime:

```python
class MyGate(BaseGate):
    # Missing _gate_name → NotImplementedError
    # Missing _failure_mode → NotImplementedError
    pass
```

Gates are automatically registered via `__init_subclass__`, so these two
attributes are class-level and do not need `__init__`.

### Gate names cannot be duplicated

If two Gate classes define the same `_gate_name`, registration raises a
`KeyError`:

```
KeyError: "Gate 'G0' is already registered by <class '...'>"
```

### `failure_mode` has two values

- `"stop"`: Gate failure stops the Pipeline immediately, returns
  `status="partial"`
- `"retry"`: Gate failure allows the Pipeline to continue (used for
  retryable gates)

### `execute()` must return a dict

The returned dict is appended to `gate_context` and passed to downstream
Gates. At minimum, it should include:

```python
return {"passed": True, "gate": self._gate_name}
```

If the return value lacks a `"gate"` key, the Gate name in logs will show
as `"unknown"`.

## GateHook

### Hooks cannot modify anything

`GateHook` is a `Protocol`, and all three methods have a return type of
`None`. If a hook tries to modify `context` or `result`, the modifications
will not propagate between Gates (context is a plain dict, so modifications
are visible to Gates, but this violates the contract).

```python
class BadHook:
    def before_gate(self, gate_name, context):
        context["topic"] = "hacked"  # Technically works, but violates contract
```

**Design principle:** Hooks are observers, not interceptors. If you need
custom blocking logic, use overrides/rules instead of hooks.

### Files recorded by MD5 must be readable

`record_md5()` computes the MD5 of a file. If the file does not exist or is
not readable, it is silently ignored (OSError is caught). But you will not
receive a warning, so manually confirm that `pipeline_md5.json` has the
expected records.

## MCP Server

### `run_pipeline`'s `resume_from`: empty string and None differ

The MCP server converts empty strings to `None`:

```python
resume_from = resume_from or None  # "" → None
```

So if you pass an empty string from MCP, it is equivalent to starting from
scratch.

### An empty allowlist allows all paths

```yaml
# mcp_allowlist.yaml does not exist or is empty
```

In this case, `check_path_allowed()` returns `True`, and all paths pass
through. This is not a secure configuration. Configure the allowlist in
production.

### Archive operation and Red Line 8

`archive_project()` checks whether the project status is `"published"`. If
not and `force=True` is not set, it returns
`{"archived": False, "error": "..."}`. This is not an exception, it is
expected behavior. Do not treat this return value as a bug.

## Testing

### Gate registration order in tests

Gates are automatically registered via `__init_subclass__` on module import.
If gate modules are imported multiple times during testing, already-registered
gates with the same name will raise a `KeyError`.

**Solution:** Call `_registry._gates.clear()` (note the private attribute)
between tests, or use an isolated registry instance.

### Use `run_with_results()` for full results

`run()` returns early when a stop-mode Gate fails. If you need the complete
Gate execution list (including Gates that were not executed due to failure),
use `run_with_results()`.

## Other

### `automedia doctor` does not block execution

Missing dependencies are marked in red but do not cause an exit. This can
lead to pipeline failures mid-execution. For example, if ComfyUI is
unavailable, V1 Vision QA will fail.

### pool.db uses an in-memory database by default

If the `--db` parameter is not specified, the topic pool is created in
`:memory:` by default. This means the data only lives as long as the current
process and is lost on restart. Always specify `--db` in production:

```bash
automedia pool list --db /path/to/pool.db
```

### Project directories include a date prefix

`Project.init()` creates directories with the format `{YYYYMMDD}_{slug}`.
Running multiple times on the same day with the same topic produces the same
directory name, causing conflicts. Ensure topics are distinguishable.
