---
name: distribution-workflow
version: 1.0.0
description: "Distribute or publish a finished AutoMedia project to one or more platforms via MCP: connect and verify platform accounts first, then call distribute_content (or publish_content) with platforms, all, and dry_run options. Triggers: 'distribute content', 'publish to platforms', 'post to wechat', 'push to twitter', 'publish this project', 'share on xiaohongshu'."
---

# Distribution Workflow — distribute_content

Use this skill when a pipeline project has finished and the user wants its content rewritten for, or published to, one or more platforms. AutoMedia distributes content through the standalone D-gates (D1-D7), which are platform-specific LLM rewrites that run independently of the main pipeline and can be invoked any number of times.

## When to Use

Use when the user asks to publish, post, push, or share a finished project to platforms like WeChat, Twitter/X, Zhihu, Xiaohongshu, Bilibili, YouTube, or TikTok. Do NOT use it to produce the content itself (that is `pipeline-workflow`). Do NOT archive a project here unless it is already published.

## End-to-end Flow

1. Make sure the pipeline finished: check `get_pipeline_status` for the `project_id`.
2. Connect and verify platform accounts with `connect_account`, `list_accounts`, and `get_account_health`.
3. Preview what would be sent with `distribute_content(..., dry_run=True)`.
4. Distribute with `distribute_content` (platform-specific rewrites via D-gates), or publish directly with `publish_content`.
5. After successful publishing, the project can be archived via `archive_project` (see `pipeline-workflow`).

## Step 1: Account Readiness

Distribution publishes through registered platform accounts. Set these up first.

| Tool | Parameters | Purpose |
|------|------------|---------|
| `connect_account` | `platform`, `auth_type` (default `"api_key"`), `credentials` (dict), `label` | Register a new platform account, returns an `account_id` |
| `list_accounts` | `platform` (optional filter), `status` (optional: active, inactive, stale) | List registered accounts and their metadata |
| `get_account_health` | `account_id` | Check an account's health status |
| `disconnect_account` | `account_id` | Remove a platform account |

Authenticate each platform you plan to target before distributing. If `get_account_health` reports a problem, fix the account before publishing, otherwise the platform's publish step will fail.

## Step 2: Preview With dry_run

| Parameter | Required | Description |
|-----------|----------|-------------|
| `project_id` | Yes | The 12-char hex project id returned by `run_pipeline` |
| `platforms` | No | Comma-separated target platforms (e.g. `"wechat,zhihu"`); ignored when `all` is true |
| `all` | No | When `true`, distribute to every registered platform (overrides `platforms`) |
| `dry_run` | No | When `true`, validate pre-conditions without actually publishing |
| `base_dir` | No | Root directory containing project directories (defaults to the projects dir) |

Call `distribute_content(project_id="<id>", platforms=["wechat", "twitter"], dry_run=True)` first to validate pre-conditions per platform without publishing anything.

## Step 3: Distribute

Run the real distribution once the dry run passes:

```
MCP call: distribute_content(
    project_id="abc123def456",
    platforms="wechat,twitter",
    all=False,
    dry_run=False
)
```

Expected output:

```
{
    "platforms": {"wechat": "success", "twitter": "failed", ...},
    "summary": "2/3 platforms succeeded",
    "dry_run": false
}
```

Each platform key holds that platform's distribution result. `summary` gives the pass/fail count. With `dry_run=true` the same shape is returned with `"dry_run": true`.

To target every registered platform in one call, pass `all=true` and omit `platforms`.

## Alternative: Publish Directly

`publish_content` publishes a project to a single platform through the publish engine, bypassing the D-gate rewrites.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `project_id` | Yes | Project identifier |
| `platform` | Yes | Target platform name (e.g. `"xiaohongshu"`, `"zhihu"`) |
| `account_id` | No | Account identifier for account-aware publishing |
| `base_dir` | No | Root directory containing project directories |
| `mode` | No | `"auto"` (default) respects the brand profile's automation level; `"publish"` forces full publish |

Returns `{"published": bool, "platform": str, "url": str, ...}`. When the brand's automation level for that platform is `"review"` and mode is `"auto"`, the result instead contains `status: "draft_created"` and a `draft_url` for human review.

## Error Handling

- **Project not found**: `distribute_content` and `publish_content` return a `NOT_FOUND` error when the `project_id` is wrong. Verify the id with `get_pipeline_status` or `list_projects`.
- **Missing account**: If the target platform has no registered account, distribution fails. Run `connect_account` for that platform first.
- **dry_run failures**: When a dry run reports a platform as failed, it means pre-conditions are not met. Check account health and platform configuration before the real run.
- **Automation level is "review"**: `publish_content` with mode `"auto"` creates a draft instead of publishing. Tell the user to review the draft URL, or pass `mode="publish"` to force the publish.
- **Allowlist rejection**: `base_dir` and `project_dir` must be inside the MCP path allowlist. Ask the user for an allowed path.

If a tool returns an `error` dict, relay the message to the user and do not fabricate publish results.

## Related Tools

- `publish_content` — single-platform publish through the publish engine
- `connect_account` / `list_accounts` / `get_account_health` / `disconnect_account` — account management
- `list_platforms` — list all platforms with registered adapters
- `register_platform_adapter` — register a publish adapter for a platform
- `get_pipeline_status` — confirm the project exists and its status before distributing
- `archive_project` — archive a published project (Red Line 8 enforced)
- `run_pipeline` — produce the content before distributing (see `pipeline-workflow`)
