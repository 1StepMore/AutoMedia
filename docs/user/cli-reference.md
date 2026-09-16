---
title: CLI Reference
description: AutoMedia CLI command reference — usage and parameter descriptions for 19 subcommands.
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
| `automedia distribute` | Distribute pipeline content to platforms (D-gates with `--platforms`, `--all`, `--dry-run`) |
| `automedia effects` | Compute content analytics stats (word count, sentiment, readability, brand mentions, SEO) |
| `automedia adapter` | Platform adapter audit + templates (`list` with `--real`/`--stub`/`--json`, `create`) |
| `automedia cron` | Execute scheduled cron jobs and pipeline runs |
| `automedia account` | Platform account management |
| `automedia archive` | Archive a project |
| `automedia init` | Initialize AutoMedia configuration |
| `automedia doctor` | Check system dependencies |
| `automedia omni` | Omni Triad operations (extract, translate, convert) |
| `automedia pipeline` | Pipeline DAG export and state inspection (export-dag, state) |
| `automedia hitl` | Human-in-the-loop review operations |
| `automedia mcp` | Generate MCP client configuration for various IDEs |
| `automedia onboard` | Onboarding wizard |
| `automedia history` | Show pipeline execution history for a project |
| `automedia rollback` | Roll back a project: archive it and revert status to draft |
| `automedia validate` | Run the agent-tester validation suite (list, run, report, diff, coverage, matrix) |


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

# Tolerate a gate-blocked run in unattended automation (exit 0 on `partial`)
automedia run --topic "..." --brand my-brand --allow-partial

```

### Flags

| Flag | Short | Type | Default | Description |
|------|------|------|--------|------|
| `--topic` | `-t` | `str` | required | Content topic |
| `--topics` | | `str` | `None` | Comma-separated topics for batch mode (overrides `--topic`) |
| `--brand` | `-b` | `str` | required | Brand identifier |
| `--mode` | `-m` | `str` | `auto` | Mode: auto, text_only, text_with_cover, video_only, qa_only, image-carousel, social-thread, short-video, repurpose |
| `--resume-from` | | `str \| None` | `None` | Resume from a specific Gate (skip preceding gates) |
| `--auto-resume` | | `bool` | `False` | Resume from the last passed gate (reads history.db) |
| `--allow-partial` | | `bool` | `False` | Exit 0 when the pipeline stops at a gate (`partial`). A `failed` pipeline still exits non-zero |
| `--decision-mode` | | `str` | `build` | (DEPRECATED) Decision mode for pipeline execution — no longer functional |
| `--verbose` | `-v` | `bool` | `False` | Show full error traceback for debugging |
| `--source-path` | | `str \| None` | `None` | Path to a source document (`.md`, `.txt`, `.pdf`). Content is loaded into the pipeline |
| `--source-url` | | `str \| None` | `None` | URL to fetch source content from. Content is loaded into the pipeline |

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

## `automedia distribute`

Distribute pipeline content to platforms via D1-D7 distribution gates.

```bash
# Distribute to specific platforms
automedia distribute <project-id> --platforms wechat,twitter

# Distribute to all platforms
automedia distribute <project-id> --all

# Dry run (preview without executing)
automedia distribute <project-id> --platforms wechat --dry-run

# Distribute via cron schedule
automedia distribute <project-id> --all --cron
```

### Arguments

| Argument | Type | Description |
|------|------|------|
| `project_id` | `str` | Project ID (required) |

### Flags

| Flag | Short | Type | Default | Description |
|------|------|------|--------|------|
| `--platforms` | `-p` | `str` | `""` | Comma-separated list of target platforms |
| `--all` | `-a` | `bool` | `False` | Distribute to all configured platforms |
| `--dry-run` | `-d` | `bool` | `False` | Preview distribution without executing |
| `--cron` | | `bool` | `False` | Run as cron job (suppresses interactive output) |

## `automedia effects`

Compute content analytics for a project.

```bash
# Compute all analytics for a project
automedia effects <project-id>

# Get analytics with summary
automedia effects <project-id> --summary
```

### Arguments

| Argument | Type | Description |
|------|------|------|
| `project_id` | `str` | Project ID (required) |

### Flags

| Flag | Short | Type | Default | Description |
|------|------|------|--------|------|
| `--summary` | `-s` | `bool` | `False` | Print a human-readable summary |

Analytics computed: word count, sentiment score, readability score, brand mention count, SEO scores (5 dimensions).

## `automedia adapter`

Manage platform adapters.

The `adapter` command family is **deprecated** for account and publish flows.
Those moved to `automedia account`. `adapter list` remains the sanctioned
platform-audit surface: every row carries its automation status derived from
the adapter's `is_stub` attribute.

```bash
# List all registered platform adapters with a real/stub status column
automedia adapter list

# Platform-audit filters (plan P1-1): only real-API automation, only manual stubs
automedia adapter list --real
automedia adapter list --stub

# Machine-readable audit output
automedia adapter list --json
automedia adapter list --json --real

# Create new adapter template
automedia adapter create --name youtube
```

Plain `automedia adapter list` prints one line per platform with its status:
20 registered adapters, 12 `real` (is_stub=False; 11 publish APIs plus the
feishu notifier) and 8 `stub` (is_stub=True; intentional manual-publish
stubs). `--real` filters to the 12 real-automation adapters, `--stub` to the 8
manual-publish stubs. `--json` emits the machine-readable payload instead:
`{"status", "adapters": [{name, is_stub}], "count", "filters"}`.

### Subcommands

| Subcommand | Description |
|--------|------|
| `list` | List registered platform adapters with a real/stub audit status column |
| `create` | Generate a new adapter template file |

### adapter list Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--real` | `bool` | `False` | Only platforms with real API automation (is_stub=False — 11 publish APIs + feishu notifier) |
| `--stub` | `bool` | `False` | Only intentional manual-publish stub platforms (is_stub=True — 8) |
| `--json` | `bool` | `False` | Machine-readable JSON output (also accepted app-level as `automedia --json adapter list`) |

`--real` and `--stub` are mutually exclusive: passing both together is an
error and the command exits with status 1.

### adapter create Flags

| Flag | Short | Type | Default | Description |
|------|------|------|--------|------|
| `--name` | `-n` | `str` | required | Platform name (e.g. youtube) |
| `--output-dir` | `-o` | `str` | `src/automedia/adapters/platforms` | Output directory |

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
| `run-pipeline` | Execute scheduled pipeline runs from cron/jobs.yaml |

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

### cron run-pipeline

Execute scheduled pipeline runs defined in `cron/jobs.yaml`.

```bash
# Run all pipeline schedules
automedia cron run-pipeline

# Run a specific schedule by name
automedia cron run-pipeline --name daily-wechat

# Run with explicit pool database path
automedia cron run-pipeline --pool-db /path/to/pool.db
```

#### cron run-pipeline Flags

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--name` | `-n` | `str` | `""` | Schedule name (empty = run all schedules) |
| `--pool-db` | | `str` | `""` | Explicit path to topic pool SQLite database |

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

Reconfiguring preserves an existing LLM fallback chain in `model_config.yaml`; only the fields you change are updated.

## `automedia doctor`

System dependency and runtime environment health check.

```bash
automedia doctor
```

Checks: python, bun, ffmpeg, whisper, edge-tts, comfyui, chrome. Missing items are marked in red, but this does not block execution; the corresponding Gate will report an error at runtime.

When a model_config.yaml exists, doctor also reports advisory LLM configuration warnings (missing or incomplete fallback chain, primary model/endpoint mismatches) as yellow warnings; in --json mode these appear in the `llm` field. These warnings are advisory and do not affect the exit code.

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

## `automedia pipeline`

Pipeline DAG export and per-gate state inspection (read-only views over the
canonical gate DAG in `automedia.pipelines.dag` and the project's
`history.db` / `pipeline_md5.json`).

### pipeline export-dag

Export pipeline-mode gate DAGs as Markdown gate tables and Graphviz DOT graphs.

```bash
# Render one mode (writes <mode>.md and <mode>.dot to the output directory)
automedia pipeline export-dag --mode auto --out ./dag

# Render every pipeline mode (one .md/.dot pair per mode)
automedia pipeline export-dag --all --out ./dag

# Overlay gates recorded in a project's history.db with a run marker
automedia pipeline export-dag --mode auto --project ./projects/<id> --out ./dag
```

#### pipeline export-dag Flags

| Flag | Description |
|------|-------------|
| `--mode, -m` | Pipeline mode to render (see `--all` for the full list) |
| `--all` | Render all pipeline modes |
| `--project, -p` | Project directory; overlays gates recorded in its history.db |
| `--out, -o` | Output directory for the rendered files (default: `.`) |

### pipeline state

Show the per-gate state (passed/failed/pending + asset md5) for a project,
aggregated from its `history.db` and `pipeline_md5.json`. Rows are grouped by
track (copy, video, qa, lifecycle). A project without history prints an
all-pending note instead of an error.

```bash
# Plain-text track-grouped table
automedia pipeline state <project_id> --base-dir ./projects

# JSON payload: {"project_id": ..., "gates": [gate, status, track, md5, recorded_at]}
automedia pipeline state <project_id> --base-dir ./projects --json
```

#### pipeline state Arguments and Flags

| Argument / Flag | Description |
|------|-------------|
| `project_id` | Project ID (12-char hex) |
| `--base-dir, -d` | Base directory to scan for projects (default: `.`) |
| `--json` | Output JSON instead of the plain-text table |

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

The LLM step preserves an existing fallback chain in `model_config.yaml` and offers fallback guidance during the flow.

## `automedia history`

Show pipeline execution history for a project.

Displays a table of Timestamp, Action, and Details columns from the per-project
history database recorded by `PipelineHistoryHook`.

```bash
# Show the history for a project
automedia history <project_id> --base-dir ./projects

# Machine-readable JSON output
automedia history <project_id> --base-dir ./projects --json
```

### Arguments and Flags

| Argument / Flag | Description |
|------|-------------|
| `project_id` | Project ID to query history for |
| `--base-dir, -d` | Base directory to scan for projects (default: `.`) |
| `--json` | Output JSON instead of the plain-text table |

## `automedia rollback`

Roll back a project: archive it and revert its status to draft.

The project directory is renamed to `{name}_archived`, its status is set to
`"draft"`, and a `rolled_back` entry is appended to the project's pipeline
history database.

```bash
# Roll back a project (requires confirmation)
automedia rollback <project_id> --base-dir ./projects
```

Refuses to roll back a project that has no pipeline history or is already
archived.

### Arguments and Flags

| Argument / Flag | Description |
|------|-------------|
| `project_id` | Project ID to roll back |
| `--base-dir, -d` | Base directory to scan for projects (default: `.`) |

## `automedia validate`

Run the agent-tester validation suite: an agent runs real calls against the
live surface, grades each response against a declared expect block, and writes
an immutable run record for director sign-off.

```bash
# List the scenario library (load only, no engine run)
automedia validate list

# Run ONE named scenario (recursion bound: scenario_name is required)
automedia validate run --scenario <name>

# Render a run record (defaults to the latest run)
automedia validate report

# Diff the latest two runs, or against an explicit baseline
automedia validate diff [--baseline <path>]

# Static coverage audit (declared/used/covered/missing/phantom per surface)
automedia validate coverage

# Per-scenario surface coverage + status matrix
automedia validate matrix
```

### Subcommands

| Subcommand | Description |
|--------|------|
| `list` | Load and list the scenario library (load only, no engine run) |
| `run` | Run ONE named scenario via the engine; `--scenario` is required (the recursion bound); exits 1 on failed or hard-safety violations |
| `report` | Render a run record (verdicts table + per-scenario status lines) |
| `diff` | Diff the latest two runs, or against an explicit baseline |
| `coverage` | Run the coverage audit over the scenario library; exits 1 when `missing` is non-empty on any surface |
| `matrix` | Render the validation matrix: coverage grid + run-record assertion cards + diff classification |

### validate run Flags

| Flag | Type | Default | Description |
|------|------|--------|------|
| `--scenario` | `str` | required | Scenario name to run (required — the recursion bound) |
| `--env-gate` | `str` | `report` | `report` (default) shows unconfigured when required env vars are missing; `skip` runs the scenario even when env vars are missing |
| `--runs-root` | `str` | `validation-runs` | Directory for immutable run records (gitignored) |
