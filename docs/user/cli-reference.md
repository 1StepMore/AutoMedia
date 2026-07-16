---
title: CLI Reference
description: AutoMedia CLI command reference — usage and parameter descriptions for 12 subcommands.
---

# CLI Reference

## MCP-CLI Naming Equivalences

AutoMedia exposes the same functionality through both CLI commands and MCP
tools. Some operations use different names depending on the interface:

| Function | CLI Command | MCP Tool |
|----------|-------------|----------|
| Document extraction | `automedia omni ingest` | `extract_brief` |
| Content translation | `automedia omni localize` | `localize_content` |
| Format conversion | `automedia omni format-output` | `format_output` |

These pairs are **semantically equivalent** — they call the same underlying
implementation (:func:`automedia.pipelines.runner.run_full_pipeline` for
pipeline operations; the Omni adapter layer for extract/translate/convert).

## Commands Overview

| Command | Description |
|---------|-------------|
| `automedia run` | Execute production pipeline (single topic or batch via `--topics`) |
| `automedia pool` | Topic pool management (list, add, score) |
| `automedia projects` | List and manage production projects |
| `automedia adapter` | Platform adapter management |
| `automedia cron` | Execute scheduled cron jobs |
| `automedia account` | Platform account management |
| `automedia archive` | Archive a project |
| `automedia init` | Initialize AutoMedia configuration |
| `automedia doctor` | Check system dependencies |
| `automedia omni` | Omni Triad operations (extract, translate, convert) |
| `automedia hitl` | Human-in-the-loop review operations |
| `automedia onboard` | Onboarding wizard |


## Global

```bash
automedia --help
automedia --version
```

## `automedia account`

Manage platform accounts for publishing.

```bash
# Connect a new account
automedia account connect wechat --auth-type cookie --label "Main WeChat"

# List all accounts
automedia account list

# List accounts filtered by platform
automedia account list --platform wechat

# Check account health
automedia account health acc_wechat_a1b2c3d4

# Disconnect an account
automedia account disconnect acc_wechat_a1b2c3d4

# Force disconnect without confirmation
automedia account disconnect acc_wechat_a1b2c3d4 --yes


```

### Subcommands

| Subcommand | Description |
|--------|------|
| `connect` | Register a new platform account (prompts for credentials) |
| `list` | List registered accounts, supports `--platform` and `--status` filtering |
| `health` | Check an account's health status and last check time |
| `disconnect` | Remove a platform account (requires confirmation unless `--yes`) |


### account connect Arguments

| Argument | Type | Default | Description |
|------|------|--------|------|
| `platform` | `str` | required | Platform name (e.g. wechat, zhihu, xiaohongshu) |

### account connect Flags

| Flag | Type | Default | Description |
|------|------|--------|------|
| `--auth-type` | `str` | `api_key` | Authentication type (api_key, cookie, oauth2_client_cred) |
| `--label` | `str` | `""` | Human-readable label for the account |

After running the command, enter credentials as `key=value` pairs (one per line, empty line to finish):

```
  cookie=sessionid=abc123; token=xyz789
  user_agent=Mozilla/5.0...
```

### account list Flags

| Flag | Short | Type | Default | Description |
|------|------|------|--------|------|
| `--platform` | `-p` | `str \| None` | `None` | Filter by platform |
| `--status` | `-s` | `str \| None` | `None` | Filter by status (active, inactive, stale) |

### account health Arguments

| Argument | Type | Description |
|------|------|------|
| `account_id` | `str` | Account ID (required) |

### account disconnect Arguments

| Argument | Type | Description |
|------|------|------|
| `account_id` | `str` | Account ID (required) |

### account disconnect Flags

| Flag | Short | Type | Default | Description |
|------|------|------|--------|------|
| `--yes` | `-y` | `bool` | `False` | Skip confirmation prompt |

## `automedia run`

Execute the full content production pipeline.

```bash
automedia run --topic "AI Video Generation Tool Comparison" --brand my-brand

# Text-only mode
automedia run --topic "..." --brand my-brand --mode text_only

# Image carousel mode
automedia run --topic "..." --brand my-brand --mode image-carousel

# Short video mode
automedia run --topic "..." --brand my-brand --mode short-video

# Resume from a specific Gate
automedia run --topic "..." --brand my-brand --resume-from G3

```

### Flags

| Flag | Short | Type | Default | Description |
|------|------|------|--------|------|
| `--topic` | `-t` | `str` | required | Content topic |
| `--brand` | `-b` | `str` | required | Brand identifier |
| `--mode` | `-m` | `str` | `auto` | Mode: auto, text_only, text_with_cover, video_only, qa_only, image-carousel, social-thread, short-video |
| `--resume-from` | | `str \| None` | `None` | Resume from a specific Gate |

## `automedia pool`

Manage the topic pool.

```bash
# List topics (filterable by status)
automedia pool list
automedia pool list --status pending

# Add a topic
automedia pool add --topic "AI Trends 2026" --url "https://..." --source weibo

# Clean up expired topics
automedia pool prune --days 7
```

### Subcommands

| Subcommand | Description |
|--------|------|
| `list` | List topics, supports `--status` filtering |
| `add` | Add a new topic, requires `--topic` |
| `attach-brief` | Attach a content brief to a topic |
| `prune` | Clean up expired topics from N days ago, defaults to 7 days |

### pool list Flags

| Flag | Short | Type | Default | Description |
|------|------|------|--------|------|
| `--status` | `-s` | `str \| None` | `None` | Filter by status (pending, selected, published) |
| `--db` | | `str \| None` | `None` | Pool SQLite file path |

### pool add Flags

| Flag | Short | Type | Default | Description |
|------|------|------|--------|------|
| `--topic` | `-t` | `str` | required | Topic title |
| `--url` | `-u` | `str` | `""` | Source URL |
| `--source` | `-s` | `str` | `""` | Source platform |
| `--db` | | `str \| None` | `None` | Pool SQLite file path |

### pool prune Flags

| Flag | Short | Type | Default | Description |
|------|------|------|--------|------|
| `--days` | `-d` | `int` | `7` | Delete pending topics older than N days |
| `--db` | | `str \| None` | `None` | Pool SQLite file path |

## `automedia projects`

View and manage projects.

```bash
# List all projects
automedia projects list

# Filter by status
automedia projects list --status published

# View specific project details
automedia projects get <project-id>
```

### Subcommands

| Subcommand | Description |
|--------|------|
| `list` | List projects |
| `get` | View project details (JSON) |
| `get-assets` | Get project asset list |

### projects list Flags

| Flag | Short | Type | Default | Description |
|------|------|------|--------|------|
| `--status` | `-s` | `str \| None` | `None` | Filter by status |
| `--base-dir` | `-d` | `str` | `.` | Root directory to scan for projects |

### projects get Arguments

| Argument | Type | Description |
|------|------|------|
| `project_id` | `str` | Project ID (required) |

## `automedia archive`

Archive a project (Red Line 8 mandatory constraint).

```bash
# Normal archive (status must be published)
automedia archive <project-id>

# Force archive (skip published check)
automedia archive <project-id> --force
```

### Arguments

| Argument | Type | Description |
|------|------|------|
| `project_id` | `str` | Project ID (required) |

### Flags

| Flag | Short | Type | Default | Description |
|------|------|------|--------|------|
| `--force` | `-f` | `bool` | `False` | Force archive, skip published status check |
| `--base-dir` | `-d` | `str` | `.` | Project root directory |

## `automedia adapter`

Manage platform adapters.

```bash
# List registered adapters
automedia adapter list

# Create new adapter template
automedia adapter create --name youtube
```

### Subcommands

| Subcommand | Description |
|--------|------|
| `list` | List all registered platform adapters |
| `create` | Generate a new adapter template file |

### adapter create Flags

| Flag | Short | Type | Default | Description |
|------|------|------|--------|------|
| `--name` | `-n` | `str` | required | Platform name (e.g. youtube) |
| `--output-dir` | `-o` | `str` | `automedia/adapters/platforms` | Output directory |

## `automedia cron`

Run scheduled jobs and health checks.

```bash
# Run a specific job
automedia cron run <job-name>

# Full system health check
automedia cron check-health
```

### Known Jobs

| Job Name | Description |
|----------|------|
| `pool-collect` | Collect new topics into the pool |
| `pool-score` | Score and rank topics |
| `pool-prune` | Clean up expired topics |
| `publish-check` | Check pending publish content |

### cron run Arguments

| Argument | Type | Description |
|------|------|------|
| `job_name` | `str` | Job name (required) |

### cron run Flags

| Flag | Type | Default | Description |
|------|------|--------|------|
| `--timeout` | `int` | `120` | Job timeout in seconds |

### cron check-health

Run a 4-step health check:

1. `.automedia/` config directory exists
2. `pool.db` accessible
3. Core dependencies: Python >= 3.11, ffmpeg available
4. `jobs.yaml` valid

## `automedia init`

Initialize AutoMedia configuration.

```bash
# Interactive wizard
automedia init

# Minimal config (non-interactive)
automedia init --template minimal
```

### Flags

| Flag | Type | Default | Description |
|------|------|--------|------|
| `--template` | `str \| None` | `None` | Template mode: `minimal` |

The interactive wizard prompts for the following:

- LLM provider (`openai` / `anthropic`)
- API base URL
- API key (hidden input)

## `automedia doctor`

System dependency and runtime environment health check.

```bash
automedia doctor
```

Checks: python, bun, ffmpeg, whisper, edge-tts, comfyui, chrome. Missing items are marked in red, but this does not block execution; the corresponding Gate will report an error at runtime.

## `automedia omni`

Omni Triad operations: content extraction (OPP), localization translation (OL), format conversion (ORF).

Each CLI subcommand has a corresponding MCP tool with a different name (see the
[MCP-CLI Naming Equivalences](#mcp-cli-naming-equivalences) table at the top of this page):

| CLI Subcommand | MCP Equivalent |
|----------------|----------------|
| `automedia omni ingest` | ``extract_brief`` |
| `automedia omni localize` | ``localize_content`` |
| `automedia omni format-output` | ``format_output`` |

```bash
# Extract content brief
automedia omni ingest --file document.md

# Localization translation
automedia omni localize --content "Hello world" --source-lang en --target-lang zh

# Format conversion
automedia omni format-output --content "# Title" --target-format html
```

## `automedia hitl`

Human-in-the-loop review management.

```bash
# View review configuration
automedia hitl config

# List presets
automedia hitl preset --list
```

## `automedia onboard`

Guided configuration wizard.

```bash
# Launch configuration wizard
automedia onboard

# List available wizards
automedia onboard list
```
