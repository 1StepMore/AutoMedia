---
title: MCP Server Setup
description: Configure the AutoMedia MCP server for AI agents — integration guide for Claude Desktop, OpenCode, Codex CLI, and other clients.
---

# MCP Server Setup

AutoMedia provides an MCP (Model Context Protocol) server that allows any MCP client (Claude Desktop, OpenCode, Cline) to use the AutoMedia pipeline through a standard tool-calling interface.

## Installation

```bash
pip install automedia-pipeline[mcp]
```

## Starting the Server

The MCP server uses stdio transport, communicating with the MCP client through standard input/output:

```bash
python -m automedia.mcp.server
```

View registered tools:

```bash
python -m automedia.mcp.server --show-tools
```

Output:

```
Registered MCP tools:
  - add_cron_schedule
  - add_pool_topic
  - analyze_content
  - archive_project
  - batch_run
  - connect_account
  - disconnect_account
  - distribute_content
  - engine_health
  - evaluate_content_quality
  - extract_brief
  - format_output
  - get_account_health
  - get_config
  - get_cron_health
  - get_pipeline_progress
  - get_pipeline_status
  - get_project_assets
  - health_check
  - health_engine
  - help_mcp
  - list_accounts
  - list_brands
  - list_cron_schedules
  - list_projects
  - list_topic_pool
  - localize_content
  - localize_output
  - mcp_help
  - pool_add_topic
  - publish_content
  - register_platform_adapter
  - remove_cron_schedule
  - research_topics
  - run_batch
  - run_brand_strategy
  - run_pipeline
  - run_pipeline_from_strategy
  - search_assets
  - select_topic
  - test_cron_schedule
  - update_engine_config
```

## Available Tools (52)

| Tool | Description |
|------|------|
| `select_topic` | Select the highest-scored pending topic from the pool |
| `research_topics` | Research trending topics using LLM (requires AUTOMEDIA_TAVILY_API_KEY for real-time data; defaults to simulated results) |
| `run_pipeline` | Execute full production pipeline (background async) |
| `run_pipeline_from_strategy` | Generate content strategy via LLM then execute pipeline |
| `run_brand_strategy` | Generate a brand strategy using LLM analysis |
| `evaluate_content_quality` | Score content quality against criteria |
| `run_batch` | Run pipeline sequentially for multiple topics |
| `batch_run` | ⚠️ Deprecated: use run_batch |
| `cancel_pipeline` | Cancel a running pipeline by project ID |
| `pause_pipeline` | Pause a running pipeline after the current gate completes |
| `resume_pipeline` | Resume a paused pipeline |
| `retry_gate` | Mark a specific gate for retry in a running pipeline |
| `skip_gate` | Mark a specific gate for skipping in a running pipeline |
| `get_pipeline_progress` | Poll gate-by-gate progress of a running pipeline |
| `get_pipeline_status` | Query project status from its info file |
| `list_projects` | List all projects, optionally filtered by status |
| `get_project_assets` | List asset files in a project directory |
| `archive_project` | Archive a project (Red Line 8: refuses unless published or —force) |
| `help_mcp` | Get a categorized listing of all MCP tools with descriptions and parameter schemas |
| `mcp_help` | ⚠️ Deprecated: use help_mcp |
| `health_engine` | Check all engine-related dependencies health |
| `engine_health` | ⚠️ Deprecated: use health_engine |
| `health_check` | Return server health status (version, uptime, tool count) |
| `update_engine_config` | Update an engine configuration setting |
| `extract_brief` | Extract a content brief from a document (OPP) |
| `localize_content` | Translate Markdown content (OL shield pipeline) |
| `localize_output` | Translate all project drafts into multiple languages |
| `format_output` | Convert content format (ORF adapter) |
| `add_pool_topic` | Add a topic to the topic pool |
| `pool_add_topic` | ⚠️ Deprecated: use add_pool_topic |
| `list_topic_pool` | View the topic pool with optional filters |
| `connect_account` | Register a new platform account (returns account_id) |
| `list_accounts` | List all registered accounts with optional filters |
| `get_account_health` | Check an account's health status |
| `disconnect_account` | Disconnect/remove a platform account |
| `publish_content` | Publish a project to a platform |
| `distribute_content` | Distribute pipeline content to platforms via D-gates (WeChat, Twitter/X, Zhihu, Xiaohongshu, Bilibili, YouTube, TikTok) |
| `analyze_content` | Compute content analytics (word count, sentiment, readability, brand mentions, SEO scores) |
| `register_platform_adapter` | Register a platform adapter stub |
| `add_cron_schedule` | Add a cron schedule entry |
| `list_cron_schedules` | List all cron schedules |
| `remove_cron_schedule` | Remove a cron schedule entry |
| `get_cron_health` | Check cron job configuration health |
| `test_cron_schedule` | Validate cron expression and compute next trigger times |
| `search_assets` | Search produced content via keyword + semantic search |
| `list_brands` | Return all configured brands with profile metadata |
| `get_config` | Return merged configuration (secrets redacted) |

## MCP Client Configuration

### Claude Desktop

Edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "automedia": {
      "command": "python",
      "args": ["-m", "automedia.mcp.server"],
      "env": {
        "AUTOMEDIA_LLM_API_KEY": "sk-xxx"
      }
    }
  }
}
```

### OpenCode

Edit `.opencode/package.json` or the project-level config file:

```json
{
  "mcpServers": {
    "automedia": {
      "command": "python",
      "args": ["-m", "automedia.mcp.server"]
    }
  }
}
```

Or through `~/.config/opencode/mcp.json`:

```json
{
  "servers": {
    "automedia": {
      "command": "python",
      "args": ["-m", "automedia.mcp.server"],
      "env": {
        "AUTOMEDIA_LLM_API_KEY": "sk-xxx"
      }
    }
  }
}
```

### Cline

Edit the VSCode extension config or `~/.config/cline/mcp.json`:

```json
{
  "mcpServers": {
    "automedia": {
      "command": "python",
      "args": ["-m", "automedia.mcp.server"]
    }
  }
}
```

## Path Allowlist

MCP server file access is restricted by an allowlist. The config file is located at:

```
~/.automedia/mcp_allowlist.yaml
```

The default allowlist (shipped at `automedia/mcp/mcp_allowlist.yaml`)
only includes `/tmp/automedia/`. Additional paths must be uncommented or
added as needed:

```yaml
allowed_directories:
  - /tmp/automedia/
  # - /app/data/
  # - /app/output/
  # - /app/projects/
  # - /opt/automedia/
```

If the allowlist is empty, all paths are blocked (fail‑closed). It is recommended to configure a specific allowlist for production environments. The path allowlist can also be overridden via the `AUTOMEDIA_MCP_ALLOWLIST_PATH` environment variable (see [Environment Variables](#environment-variables)).

## Environment Variables

The MCP server supports the following environment variables:

| Variable | Description |
|------|------|
| `AUTOMEDIA_LLM_API_KEY` | LLM API key |
| `AUTOMEDIA_LLM_BASE_URL` | Custom API endpoint |
| `AUTOMEDIA_LLM_PROVIDER` | LLM provider name |
| `AUTOMEDIA_LLM_MODEL` | Model identifier |
| `AUTOMEDIA_PROJECTS_DIR` | Projects root directory override |
| `AUTOMEDIA_MCP_ALLOWLIST_PATH` | Custom allowlist path override |
| `AUTOMEDIA_MASTER_KEY` | Master key for credential encryption |
| `AUTOMEDIA_LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `AUTOMEDIA_FAKE_LLM` | Set to `1` to use deterministic mock LLM responses (no real API calls) |
| `FEISHU_WEBHOOK_URL` | Feishu notification webhook |
| `WX_APPID` | WeChat Official Account AppID |
| `WX_APPSECRET` | WeChat Official Account AppSecret |

## Security Notes

- The `archive_project` tool follows Red Line 8: archiving is only allowed when project status is `published` or `force=True`
- The path allowlist prevents malicious agents from reading files outside the project directory
- It is recommended to use dedicated API keys and environment variables for the MCP server
- All file operations are gated by the path allowlist — files outside allowed directories return `PermissionError`. Some tools (e.g. `archive_project`, `publish_content`, `format_output`) perform write operations within allowed directories.

## Example: Calling MCP Tools Directly in Python

```python
from automedia.mcp import (
    select_topic,
    run_pipeline,
    get_pipeline_progress,
    get_pipeline_status,
    list_projects,
    get_project_assets,
    archive_project,
    list_topic_pool,
    register_platform_adapter,
    extract_brief,
    localize_content,
    localize_output,
    format_output,
)

# Select topic
topic = select_topic(category="tech")
if topic.get("selected"):
    print(f"Selected: {topic['selected']['title']}")

# Run pipeline
result = run_pipeline(topic=topic, brand="my-brand")
print(f"Project ID: {result['project_id']}")

# List projects
projects = list_projects(base_dir=".")
print(f"Found {projects['count']} projects")

# Archive (requires user confirmation)
result = archive_project(project_id="abc123def456", force=True)

<!-- Merged from: docs/dev/error-code-reference.md -->

## Error Code Reference

### Error Response Shape

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

### Error Code Categories

#### Enum: `MCPErrorCode` (defined in `mcp_error.py`)

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

### INVALID_PARAM

One or more input parameters failed validation.

| Tool | Condition | Resolution |
|------|-----------|------------|
| `run_pipeline` | Mode not in `VALID_MODES` | Pass a valid mode: `auto`, `text_only`, `text_with_cover`, `video_only`, `qa_only`, `image-carousel`, `social-thread`, `short-video`, `repurpose` |
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

### NOT_FOUND

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

### ALLOWLIST_DENIED

Access blocked by the MCP path or key allowlist.

| Tool | Condition | Resolution |
|------|-----------|------------|
| `get_config` | The requested config key contains a secret keyword (`key`, `secret`, `password`, `token`) | Use a non-secret key or access the value through other means |
| Various file tools | File path not in `mcp_allowlist.yaml` | Have the user add the path to the allowlist |

### UNKNOWN

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

### Unused Codes

The following codes are defined in `MCPErrorCode` but are not currently
emitted by any MCP tool.  They are reserved for future use.

| Code | Intended Purpose |
|------|-----------------|
| `PIPELINE_ERROR` | Pipeline execution failure (gate failure, runner crash) |
| `ENGINE_ERROR` | Engine dependency failure (TTS, ASR, image, video engine errors) |

---

### Source Files

| File | Role |
|------|------|
| `src/automedia/mcp/mcp_error.py` | `MCPErrorCode` enum + `error_response()` / `success_response()` helpers |
| `src/automedia/mcp/tools.py` | All MCP tool implementations with `error_response()` call sites |
| `src/automedia/mcp/accounts.py` | Account management tools with `error_response()` call sites |

---

<!-- Merged from: docs/user/mcp-systemd-setup.md -->

## Production Deployment (systemd)

Run the AutoMedia MCP server as a persistent systemd service so it stays
alive across reboots and restarts automatically on failure.

### Prerequisites

- AutoMedia installed in a Python environment reachable by the systemd unit.
- `sudo` access on the host where the service will run.

### Files

| File | Purpose |
|------|---------|
| `deploy/systemd/automedia-mcp.service` | systemd unit definition |
| `deploy/systemd/automedia-mcp.env` | Environment variable template |
| `docs/user/mcp-setup.md#production-deployment-systemd` | This guide |

### Installation

#### 1. Copy the service unit

```bash
sudo cp deploy/systemd/automedia-mcp.service /etc/systemd/system/
```

#### 2. Create the env directory and copy the env file

```bash
sudo mkdir -p /etc/automedia
sudo cp deploy/systemd/automedia-mcp.env /etc/automedia/automedia-mcp.env
sudo chmod 600 /etc/automedia/automedia-mcp.env
```

#### 3. Edit the env file

```bash
sudo vim /etc/automedia/automedia-mcp.env
```

At minimum, set `AUTOMEDIA_LLM_API_KEY`. Uncomment and adjust other
variables as needed.

#### 4. Review the service unit

If your Python environment is not the system default (e.g. you use a
virtualenv), edit the `ExecStart` path in the service file:

```bash
sudo vim /etc/systemd/system/automedia-mcp.service
```

Change:

```
ExecStart=python -m automedia.mcp.server
```

to:

```
ExecStart=/home/automedia/.venv/bin/python -m automedia.mcp.server
```

Also adjust `WorkingDirectory` to match your deployment layout.

#### 5. Reload systemd and enable the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable automedia-mcp
```

#### 6. Start the service

```bash
sudo systemctl start automedia-mcp
```

#### 7. Verify the service is running

```bash
sudo systemctl status automedia-mcp
```

Expected output includes `Active: active (running)`.

#### 8. Security hardening note

The service files ship with `ProtectHome=read-only` enabled. Since
AutoMedia reads user configuration from `~/.automedia/`, the service
files also include `ReadWritePaths=/home/*/.automedia` to grant the
service access to user-level config while keeping the rest of `/home/`
protected.

If you deploy with a non-standard home directory layout, adjust
`ReadWritePaths` accordingly — for example:

```ini
ReadWritePaths=/opt/automedia/.automedia
```

#### 9. View logs

```bash
# Follow new log entries
sudo journalctl -u automedia-mcp -f

# View the last 100 lines
sudo journalctl -u automedia-mcp -n 100

# View all logs since the service started
sudo journalctl -u automedia-mcp --since "5 minutes ago"
```

### Management

| Action | Command |
|--------|---------|
| Start | `sudo systemctl start automedia-mcp` |
| Stop | `sudo systemctl stop automedia-mcp` |
| Restart | `sudo systemctl restart automedia-mcp` |
| Status | `sudo systemctl status automedia-mcp` |
| Enable on boot | `sudo systemctl enable automedia-mcp` |
| Disable on boot | `sudo systemctl disable automedia-mcp` |
| View logs | `sudo journalctl -u automedia-mcp` |
| Follow logs | `sudo journalctl -u automedia-mcp -f` |

### Verification

Check that the MCP server registers its tools correctly:

```bash
python -m automedia.mcp.server --show-tools
```

If using stdio transport, test connectivity from the CLI:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | sudo -u automedia python -m automedia.mcp.server
```

### Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `python: command not found` | Python not on systemd `PATH` | Use absolute path to Python in `ExecStart` |
| Permission denied on env file | Wrong ownership or mode | `sudo chmod 600 /etc/automedia/automedia-mcp.env` |
| Service starts then immediately exits | Missing API key or import error | Check logs with `journalctl -u automedia-mcp -n 50` |
| `WorkingDirectory` does not exist | Path mismatch | Create the directory or update `WorkingDirectory` in the unit file |
```
