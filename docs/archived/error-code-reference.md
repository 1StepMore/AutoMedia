---
title: MCP Error Code Reference
description: Complete reference of all error codes returned by MCP tools, including error shape, code descriptions, and resolution guidance.
---

# MCP Error Code Reference

## Error Response Shape

Every MCP tool returns errors in a consistent structure.  The shape is
produced by `error_response()` in `src/automedia/mcp/mcp_error.py`:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description of what went wrong.",
    "resolution": "Steps the agent can take to resolve the issue."
  },
  "error_message": "Same as error.message (deprecated, scheduled for removal)"
}
```

The `error` block is the canonical payload.  The top-level `error_message`
key is a duplicate kept for backward compatibility and will be removed in
a future release.

Some tools wrap the error inside a result dict with partial fallback data:

```json
{
  "selected": null,
  "remaining_count": 0,
  "success": false,
  "error": { "code": "NOT_FOUND", "message": "...", "resolution": "..." }
}
```

Always check `success` or the presence of an `error` key before reading
tool-specific fields.

---

## Error Code Categories

### Enum: `MCPErrorCode` (defined in `mcp_error.py`)

All codes belong to the `MCPErrorCode` string enum.

| Code | Meaning | Used In |
|------|---------|---------|
| `INVALID_PARAM` | One or more input parameters failed validation | ~20 call sites |
| `NOT_FOUND` | A requested resource does not exist | ~15 call sites |
| `PIPELINE_ERROR` | Pipeline execution failure | Reserved, not yet emitted |
| `ENGINE_ERROR` | Engine dependency or configuration failure | Reserved, not yet emitted |
| `ALLOWLIST_DENIED` | Access to a path or config key blocked by allowlist | `get_config` |
| `UNKNOWN` | Unexpected exception caught at the MCP boundary | ~30 catch-all call sites |

---

## Error Code Reference

### `INVALID_PARAM`

One or more input parameters failed validation.

| Tool | Condition | Resolution |
|------|-----------|------------|
| `run_pipeline` | Mode not in `VALID_MODES` | Pass a valid mode: `auto`, `text_only`, `text_with_cover`, `video_only`, `qa_only`, `image-carousel`, `social-thread`, `short-video` |
| `run_pipeline` | Workflow name not found | Check workflow name with `list_workflows()` |
| `run_pipeline_from_strategy` | Workflow name not found | Check workflow name with `list_workflows()` |
| `archive_project` | Project status is not `published` and `force` is False | Either publish the project first, or pass `force=True` |
| `archive_project` | Archive target directory already exists | Remove or rename the existing archive directory |
| `add_cron_schedule` | Cron expression does not have exactly 5 fields | Use the standard 5-field cron format (`min hour dom mon dow`) |
| `add_cron_schedule` | Platform name not in `AdapterRegistry` | Use `register_platform_adapter` first or pick a known platform |
| `add_cron_schedule` | Pipeline mode not in `VALID_MODES` | Pass a valid mode (same list as `run_pipeline`) |
| `add_cron_schedule` | Schedule name already exists | Use a different name or remove the existing schedule |
| `test_cron_schedule` | Cron expression does not have exactly 5 fields | Use the standard 5-field cron format |
| `approve_gate` | Gate name not found or gate is not paused for approval | Check `get_pending_approvals()` for the correct gate name |
| `reject_gate` | Gate name not found or gate is not paused for approval | Check `get_pending_approvals()` for the correct gate name |
| `register_platform_adapter` | `platform_name` is empty or not a string | Provide a non-empty platform name |
| `register_platform_adapter` | `platform_name` contains invalid characters | Use only letters, digits, underscores, and hyphens |
| `register_platform_adapter` | `adapter_class` is not a valid dotted path | Use the `package.module.ClassName` format |
| `register_platform_adapter` | `adapter_class` is not under `automedia.adapters.*` | Adapter classes must live in the `automedia.adapters` namespace |
| `register_platform_adapter` | Class name does not match `[A-Za-z_][A-Za-z0-9_]*` | Use a valid Python class name |
| `format_output` | Format string contains path separators | Remove `/`, `\`, or `..` from the format identifier |
| `format_output` | Unsupported output format | Use one of the allowed formats (e.g. `html`, `pdf`) |
| `update_engine_config` | Invalid modality | Valid: `tts`, `asr`, `image`, `video` |
| `connect_account` | Credentials not provided | Pass a non-empty `credentials` dict |
| `connect_account` | Credential validation failed | Check credential key names and values |

### `NOT_FOUND`

A requested resource does not exist.

| Tool | Condition | Resolution |
|------|-----------|------------|
| `select_topic` | No pending topics in the pool | Add topics via `add_pool_topic` or `research_topics` |
| `get_pipeline_progress` | Project ID not in active pipeline tracker | Check the project ID from `run_pipeline` output, or query `list_projects()` |
| `get_pipeline_status` | Project not found on disk | Verify the project ID and base directory |
| `archive_project` | Project not found on disk | Verify the project ID and base directory |
| `publish_content` | Project not found on disk | Verify the project ID and base directory |
| `cancel_pipeline` | No active pipeline for project ID | Start a pipeline with `run_pipeline` first |
| `pause_pipeline` | No active pipeline for project ID | Start a pipeline with `run_pipeline` first |
| `resume_pipeline` | No active pipeline for project ID | Start a pipeline with `run_pipeline` first |
| `retry_gate` | No active pipeline for project ID | Start a pipeline with `run_pipeline` first |
| `skip_gate` | No active pipeline for project ID | Start a pipeline with `run_pipeline` first |
| `approve_gate` | No active engine for project ID | Check project ID or start a pipeline first |
| `reject_gate` | No active engine for project ID | Check project ID or start a pipeline first |
| `get_config` | Config key not found (deep get returned `None`) | Check the key name and use dot notation |
| `get_account_health` | Account ID not found | Verify the account ID from `list_accounts()` |
| `disconnect_account` | Account ID not found | Verify the account ID from `list_accounts()` |

### `ALLOWLIST_DENIED`

Access blocked by the MCP path or key allowlist.

| Tool | Condition | Resolution |
|------|-----------|------------|
| `get_config` | The requested config key contains a secret keyword (`key`, `secret`, `password`, `token`) | Use a non-secret key or access the value through other means |
| Various file tools | File path not in `mcp_allowlist.yaml` | Have the user add the path to the allowlist |

### `UNKNOWN`

Catch-all error for unexpected exceptions at the MCP boundary.  Any MCP
tool can return this when an unhandled exception escapes.  The `message`
field contains the exception string representation.

| Tool | Typical Causes |
|------|---------------|
| All tools | Database connection failures, file I/O errors, import errors, unexpected `None` values, network timeouts, API authentication failures |

When an `UNKNOWN` error is returned:
1. Check the `message` for the specific exception text.
2. Retry the operation.
3. If the error persists, check server logs for the full traceback.

---

## Unused Codes

The following codes are defined in `MCPErrorCode` but are not currently
emitted by any MCP tool.  They are reserved for future use.

| Code | Intended Purpose |
|------|-----------------|
| `PIPELINE_ERROR` | Pipeline execution failure (gate failure, runner crash) |
| `ENGINE_ERROR` | Engine dependency failure (TTS, ASR, image, video engine errors) |

---

## Source Files

| File | Role |
|------|------|
| `src/automedia/mcp/mcp_error.py` | `MCPErrorCode` enum + `error_response()` / `success_response()` helpers |
| `src/automedia/mcp/tools.py` | All MCP tool implementations with `error_response()` call sites |
| `src/automedia/mcp/accounts.py` | Account management tools with `error_response()` call sites |
