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
  - archive_project
  - connect_account
  - disconnect_account
  - evaluate_content_quality
  - extract_brief
  - format_output
  - get_account_health
  - get_pipeline_progress
  - get_pipeline_status
  - get_project_assets
  - health_check
  - list_accounts
  - list_projects
  - list_topic_pool
  - localize_content
  - localize_output
  - pool_add_topic
  - publish_content
  - register_platform_adapter
  - research_topics
  - run_brand_strategy
  - run_pipeline
  - run_pipeline_from_strategy
  - select_topic
```

## Available Tools (24)

| Tool | Description |
|------|------|
| `select_topic` | Select the highest-scored topic from the topic pool |
| `research_topics` | Research trending topics using LLM |
| `run_pipeline` | Execute full production pipeline (background async) |
| `run_pipeline_from_strategy` | Generate content strategy via LLM then execute pipeline |
| `run_brand_strategy` | Generate a brand strategy using LLM analysis |
| `get_pipeline_progress` | Pull gate-by-gate progress of a running pipeline |
| `get_pipeline_status` | Query project status |
| `list_projects` | List all projects |
| `get_project_assets` | Get project asset list |
| `archive_project` | Archive a project (Red Line 8 constraint) |
| `list_topic_pool` | View the topic pool |
| `pool_add_topic` | Add a topic to the topic pool |
| `publish_content` | Publish a project to a platform |
| `register_platform_adapter` | Register a platform adapter |
| `extract_brief` | Extract a content brief from a document (OPP) |
| `localize_content` | Translate Markdown content (OL shield pipeline) |
| `localize_output` | Translate all project drafts into multiple languages |
| `format_output` | Convert content format (ORF adapter) |
| `evaluate_content_quality` | Score content quality against criteria |
| `health_check` | Return server health status |
| `connect_account` | Register a new platform account |
| `list_accounts` | List all registered accounts |
| `get_account_health` | Check an account's health status |
| `disconnect_account` | Disconnect/remove a platform account |

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

Edit `opencode.json` or the project-level config file:

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
      "env": {}
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

The default allowlist (shipped at `src/automedia/mcp/mcp_allowlist.yaml`)
includes paths for development, production, and Docker deployments:

```yaml
allowed_directories:
  - /tmp/automedia/
  - /app/data/
  - /app/output/
  - /app/projects/
  - /opt/automedia/
```

- `/tmp/automedia/` — Temporary test data (always safe)
- `/app/data/`, `/app/output/`, `/app/projects/` — Docker volume mount paths
- `/opt/automedia/` — systemd service default `WorkingDirectory`

If the allowlist is empty, all paths are blocked (fail‑closed). It is recommended to configure a specific allowlist for production environments. The path allowlist can also be overridden via the `AUTOMEDIA_MCP_ALLOWLIST_PATH` environment variable.

## Environment Variables

The MCP server supports the following environment variables:

| Variable | Description |
|------|------|
| `AUTOMEDIA_LLM_API_KEY` | LLM API key |
| `AUTOMEDIA_LLM_BASE_URL` | Custom API endpoint |
| `FEISHU_WEBHOOK_URL` | Feishu notification webhook |
| `WX_APPID` | WeChat Official Account AppID |
| `WX_APPSECRET` | WeChat Official Account AppSecret |

## Security Notes

- The `archive_project` tool follows Red Line 8: archiving is only allowed when project status is `published` or `force=True`
- The path allowlist prevents malicious agents from reading files outside the project directory
- It is recommended to use dedicated API keys and environment variables for the MCP server
- All file operations are read-only by default (path check without modification)

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
