---
title: CLI Reference
description: AutoMedia CLI command reference — usage and parameter descriptions for 15 subcommands.
---

# CLI Reference

## Global

```bash
automedia --help
automedia --version
```

## `automedia run`

Execute the full content production pipeline.

```bash
automedia run --topic "AI Video Generation Tool Comparison" --brand my-brand

# Text-only mode
automedia run --topic "..." --brand my-brand --mode text_only

# Resume from a specific Gate
automedia run --topic "..." --brand my-brand --resume-from G3

```

### Flags

| Flag | Short | Type | Default | Description |
|------|------|------|--------|------|
| `--topic` | `-t` | `str` | required | Content topic |
| `--brand` | `-b` | `str` | required | Brand identifier |
| `--mode` | `-m` | `str` | `auto` | Mode: auto, text_only, video_only, qa_only |
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

1. Python >= 3.11
2. ffmpeg available
3. `.automedia/` config directory exists
4. `pool.db` accessible

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
automedia hitl preset list
```

## `automedia license`

License management.

```bash
# Check license status
automedia license check

# View available features
automedia license features
```

## `automedia sop`

SOP (Standard Operating Procedure) execution.

```bash
# Generate SOP report
automedia sop generate --project-dir ./project
```

## `automedia tenant`

Multi-tenant management.

```bash
# List tenants
automedia tenant list

# Create tenant
automedia tenant create --name my-tenant

# Invite member
automedia tenant invite --tenant-id <id> --email user@example.com
```

## `automedia solution`

Decision layer solution management.

```bash
# View next node
automedia solution next-node --solution-id <id>

# Approve node
automedia solution approve-node --node-id <id>

# Preflight check
automedia solution preflight-check --solution-id <id>
```

## `automedia onboard`

Guided configuration wizard.

```bash
# Launch configuration wizard
automedia onboard

# List available wizards
automedia onboard list
```
