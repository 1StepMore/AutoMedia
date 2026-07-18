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
  - archive_project
  - batch_run
  - connect_account
  - disconnect_account
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

## Available Tools (50)

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
print(f"Status: {result['status']}")

# List projects
projects = list_projects(base_dir=".")
print(f"Found {projects['count']} projects")

# Archive (requires user confirmation)
result = archive_project(project_id="abc123def456", force=True)
```
