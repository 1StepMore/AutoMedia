---
name: batch-workflow
description: "Produce several AutoMedia projects in one call with run_batch: pass a list of topics and a brand, get per-topic results with a pass/fail summary, then track each project and cancel or resume individual runs. Triggers: 'run these topics', 'batch of topics', 'produce several articles', 'run multiple pipelines', 'batch production'."
---

# Batch Workflow — run_batch

Use this skill when the user wants to produce content for several topics in one go. `run_batch` runs the pipeline for each topic sequentially, so one failing topic does not stop the rest of the batch.

## When to Use

Use when the user gives you two or more topics for the same brand and asks to produce them all. Do NOT use it for a single topic (that is `pipeline-workflow`) or for distributing the results (that is `distribution-workflow`).

## Input Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `topics` | Yes | List of content topics or subjects |
| `brand` | Yes | Brand identifier (must be configured) |
| `mode` | No | Pipeline mode (default `"auto"`); the same mode applies to every topic in the batch |

Modes are shared with `run_pipeline`: `"auto"`, `"text_only"`, `"text_with_cover"`, `"video_only"`, `"qa_only"`, `"image-carousel"`, `"social-thread"`, `"short-video"`, `"repurpose"`. See `pipeline-workflow` for what each produces.

## Execution Semantics

`run_batch` is synchronous and sequential:

- Topics are processed one at a time in the order given.
- A single topic failure does NOT stop the batch. Errors are collected and all remaining topics still run.
- The call returns only when every topic has been processed, so long batches can take a while.

```
MCP call: run_batch(
    topics=["AI video tools comparison", "Prompt engineering for beginners", "LLM cost optimization"],
    brand="my-brand",
    mode="text_only"
)
```

## Expected Output Structure

```
{
    "results": [
        {
            "topic": "AI video tools comparison",
            "status": "success",
            "project_id": "abc123def456",
            "error": null
        },
        {
            "topic": "LLM cost optimization",
            "status": "failed",
            "project_id": "",
            "error": "gate G0 failed: ..."
        }
    ],
    "total": 3,
    "passed": 2,
    "failed": 1
}
```

Each result entry has the topic, its final pipeline status, the `project_id` for successful runs (empty on failure), and the error when it failed. `passed` counts `status == "success"` results; `failed` is the rest.

## Per-Project Progress and Cancellation

`run_batch` blocks until it finishes, so you cannot poll inside the call. Track the individual projects after the batch returns:

| Tool | Parameters | Purpose |
|------|------------|---------|
| `get_pipeline_progress` | `project_id`, `since_index` | Gate-by-gate progress of one project (useful for runs started separately with `run_pipeline`) |
| `get_pipeline_status` | `project_id`, `base_dir` | Project metadata and directory layout |
| `get_project_assets` | `project_dir` | Asset files produced for a project |
| `list_projects` | `base_dir`, `status` | List projects, optionally filtered by status |
| `cancel_pipeline` | `project_id` | Cancel a running pipeline at the next gate boundary |

`cancel_pipeline` only helps for pipelines that are still running, such as individual `run_pipeline` calls. It sets a cancellation flag so the pipeline exits at the next gate boundary. It cannot interrupt an in-flight `run_batch` call mid-topic; if you need to stop a whole batch, cancel the MCP request itself and then cancel any started projects by id.

## Error Handling

- **Unknown mode**: The mode is validated against the shared mode list. Use one of the nine modes above.
- **Missing brand**: The batch fails per-topic if the brand is not configured. Configure the brand first.
- **One topic fails**: Read that topic's `error` field. The others still completed, so report the failed topic separately and fix it with a single `run_pipeline` run using `resume_from` if needed.
- **Long-running batch**: Since the call is sequential, a heavy batch (especially in video modes) can take a long time. Warn the user before starting, and prefer `text_only` or `text_with_cover` for large batches.
- **Allowlist rejection**: Project directory reads via `get_project_assets` and `get_pipeline_status` require paths inside the MCP allowlist.

If a result carries an `error` dict, relay it to the user and do not fabricate the outcome for that topic.

## Related Tools

- `run_pipeline` — run a single topic, with progress polling and `resume_from` (see `pipeline-workflow`)
- `batch_run` — deprecated alias of `run_batch`; use `run_batch` instead
- `get_pipeline_progress` / `get_pipeline_status` / `get_project_assets` — per-project tracking
- `cancel_pipeline` — stop a running pipeline
- `distribute_content` / `publish_content` — distribute the batch results (see `distribution-workflow`)
