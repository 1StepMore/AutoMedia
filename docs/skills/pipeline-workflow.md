---
name: pipeline-workflow
description: "Run a single AutoMedia production pipeline end to end via MCP: prepare a brand strategy, select or supply a topic, call run_pipeline with the right mode, poll get_pipeline_progress, inspect status and assets, then archive. Triggers: 'run a pipeline', 'produce content', 'create a video', 'write an article', 'make a draft', 'produce a carousel', 'create a thread'."
---

# Pipeline Workflow — run_pipeline

Use this skill when the user wants to produce one finished piece of content through the full AutoMedia pipeline: topic selection, draft writing, video generation, subtitle rendering, and packaging. It is the agent-facing guide to the MCP tools for a single project. For publishing or distributing the finished content, see `distribution-workflow`. For producing several topics at once, see `batch-workflow`.

## When to Use

Use when the user asks for a single piece of content: an article, a video, a carousel, or a social thread. Do NOT use it for multi-topic runs (those belong to `run_batch`) or for rewriting content for other platforms (those belong to `distribute_content`).

## End-to-end Flow

1. Run `run_brand_strategy` (optional) to ground the content in brand positioning and messaging.
2. Pick a topic with `select_topic`, or use the topic the user gave you directly.
3. Start the pipeline with `run_pipeline` and pick a mode.
4. Poll `get_pipeline_progress` until the run finishes.
5. Inspect the result with `get_pipeline_status` and `get_project_assets`.
6. Once the content is published (see `distribution-workflow`), archive the project with `archive_project`.

## Step 1: Brand Strategy (optional)

Call `run_brand_strategy` with the brand name, industry, and target audience. The returned positioning and messaging can feed into the pipeline's strategy. See the `brand-strategy` skill for the full breakdown.

## Step 2: Select a Topic

| Parameter | Required | Description |
|-----------|----------|-------------|
| `category` | No | Filter topics by category (e.g. "tech", "finance") |
| `tenant_id` | No | Tenant or namespace identifier (default `"default"`) |
| `pool_db_path` | No | Explicit path to the topic pool SQLite database |

`select_topic` returns the highest-scored pending topic as `{"selected": {...}, "remaining_count": int}`. If the pool is empty it returns `selected: null` with an error. If the user supplied a topic directly, skip this step and pass it to `run_pipeline`.

## Step 3: Start the Pipeline

| Parameter | Required | Description |
|-----------|----------|-------------|
| `topic` | Yes | Content topic or subject |
| `brand` | Yes | Brand identifier (must be configured) |
| `mode` | No | Pipeline mode (default `"auto"`) |
| `tenant_id` | No | Tenant or namespace identifier (default `"default"`) |
| `resume_from` | No | Gate name to resume from, skips preceding gates |
| `source_path` | No | Path to a source document (`.md`, `.txt`, `.pdf`) loaded into the gates |
| `source_url` | No | URL to fetch source content from |
| `workflow` | No | Named workflow from `workflows.yaml`, merged as a higher-priority config layer |
| `director` | No | When `true`, gates that require approval pause for approve/reject calls |
| `platforms` | No | Comma-separated platforms (e.g. `"xiaohongshu,zhihu"`); only relevant gates run |

Pipeline modes (shared with the CLI and SDK):

| Mode | What it produces |
|------|------------------|
| `auto` | Full pipeline: copy, video, subtitles, packaging |
| `text_only` | Text draft only, no video generation |
| `text_with_cover` | Text draft plus a cover image |
| `video_only` | Video production only |
| `qa_only` | Quality-assurance checks only |
| `image-carousel` | Image carousel format |
| `social-thread` | Social thread format |
| `short-video` | Short video format |
| `repurpose` | Deep repurpose sub-pipelines (P1-P4) at the end |

`run_pipeline` runs in a background thread and returns immediately:

```
{
    "project_id": "abc123def456",   # 12-char hex id, used for all follow-up calls
    "status": "started"
}
```

If the run cannot start, it returns `{"status": "failed", "error": {"code", "message", "resolution"}}`. Unknown modes are rejected before starting. At the concurrency limit the call fails with a message telling you to wait or cancel a running pipeline.

## Step 4: Poll Progress

| Parameter | Required | Description |
|-----------|----------|-------------|
| `project_id` | Yes | The 12-char project id from `run_pipeline` |
| `since_index` | No | Only return gate events at or after this index (default `0`) |

`get_pipeline_progress` returns the current gate, gate counts, and events:

```
{
    "project_id": "abc123def456",
    "current_gate": "G2",
    "gates_done": 5,
    "gates_remaining": 16,
    "total_gates": 21,
    "events": [...],
    "is_running": true,
    "is_failed": false,
    "elapsed_s": 42.3
}
```

Poll this every few seconds until `is_running` is `false`. When finished, the result includes `token_usage` and `estimated_cost_usd`. If `is_failed` is `true`, read the `error` field to find the failing gate, then refer to `docs/dev/gate-failure-modes.md` for remediation.

## Step 5: Inspect Status and Assets

| Tool | Purpose |
|------|---------|
| `get_pipeline_status` | Query project metadata and directory layout by `project_id` (params: `project_id`, `base_dir`) |
| `get_project_assets` | List asset files in a project directory (param: `project_dir`, absolute path) |
| `list_projects` | List all projects under a base directory, optionally filtered by status (params: `base_dir`, `status`) |

## Step 6: Archive

After the content is published (see `distribution-workflow`), archive the project:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `project_id` | Yes | The 12-char hex project identifier |
| `base_dir` | No | Base directory to scan for projects (default `"."`) |
| `force` | No | Force archive even if status is not `"published"` (default `false`) |

`archive_project` enforces Red Line 8: it refuses unless the project status is `"published"` or `force` is `true`. Do NOT call it with `force=true` unless the user explicitly asks. Success returns `{"archived": true, "archive_dir": str}`.

## Error Handling

- **Missing brand profile**: `run_pipeline` fails fast if the brand is not configured. Tell the user to run `init_config` or check brand profiles.
- **Unknown mode**: The tool rejects the mode before starting. Pick one of the nine modes listed above.
- **Concurrency limit**: At the max concurrent pipelines the call fails. Wait for a running pipeline to finish or call `cancel_pipeline`.
- **Empty topic pool**: `select_topic` returns no topic. Suggest `add_pool_topic` or `research_topics` to fill the pool.
- **Gate failure**: Poll progress and read the failing gate from the `error` field. Fix the cause, then resume with `resume_from="<gate_name>"` on a new `run_pipeline` call.
- **Allowlist rejection**: `source_path` and `base_dir` must be inside the MCP path allowlist. If a call returns an allowlist error, ask the user for an allowed path.

If a tool returns an `error` dict, relay the message to the user and do not fabricate results.

## Related Tools

- `run_pipeline_from_strategy` — generate a content strategy via LLM, then run the pipeline in one call
- `run_brand_strategy` — brand positioning and messaging analysis
- `select_topic` / `research_topics` / `add_pool_topic` — topic pool operations
- `distribute_content` / `publish_content` — publishing the finished content (see `distribution-workflow`)
- `run_batch` — run several topics sequentially (see `batch-workflow`)
- `cancel_pipeline` — stop a running pipeline at the next gate boundary
