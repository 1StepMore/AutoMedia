---
title: Production Workflow
description: AutoMedia daily production standard operating procedures — daily production cadence and operations guide.
---

# Daily Production Workflow

This document describes the standard operating procedures for AutoMedia in
daily production.

## Daily Production Cadence

AutoMedia runs on the following daily schedule:

| Time | Operation | Tool |
|------|-----------|------|
| 08:00 | Hot topic collection (4 platforms + Tavily + AIHOT) | `automedia cron run pool-collect` |
| 08:05 | Semantic review + blacklist filtering | `automedia cron run pool-score` |
| 08:30 | Check pending publish content | `automedia cron run publish-check` |
| 09:00 | Operators select topics, start production | `automedia run --topic "..." --brand ...` |
| 09:30 | Full system health check | `automedia cron check-health` |
| 10:00 | Scheduled pipeline run | `automedia cron run-pipeline` |
| All day | Publish confirmation + archive | `automedia archive <project-id>` |

## Pre-Production Checks

### 1. Environment Readiness

```bash
# Check dependencies
automedia doctor

# Check configuration
ls -la .automedia/
cat .automedia/config.yaml

# Check topic pool
automedia pool list --status pending --db .automedia/pool.db
```

### 2. Network Connectivity

```bash
# Confirm LLM API is available
curl -s -o /dev/null -w "%{http_code}" https://api.openai.com/v1/models

# Confirm source URLs are accessible (G0 Gate needs this)
curl -s -o /dev/null -w "%{http_code}" https://example.com
```

### 3. Disk Space

```bash
df -h /var/automedia/projects/
# Ensure at least 10GB free (video projects need this)
```

## Starting Production

### Method A: CLI Manual Run (Recommended)

```bash
automedia run --topic "AI 视频生成工具对比: 2026 年最新格局" --brand my-brand
```

### Method B: Python SDK

```python
from automedia import run_full_pipeline

result = run_full_pipeline(
    topic="AI 视频生成工具对比: 2026 年最新格局",
    brand="my-brand",
    mode="auto",
)

if result.status == "success":
    print(f"Project directory: {result.project_dir}")
    for asset in result.assets:
        print(f"  [{asset.type}] {asset.path}")
else:
    print(f"Failed: {result.error}")
    for log in result.gates_log:
        if log.status != "passed":
            print(f"  Gate {log.gate_name}: {log.status} ({log.error})")
```

### Method C: MCP (AI Agent)

The agent calls `select_topic` to pick a topic, then calls `run_pipeline` to
produce content.

### Method D: Scheduled Pipeline (Cron)

Use `automedia cron run-pipeline` to execute pipeline runs defined in
`cron/jobs.yaml`. Each schedule specifies a topic source, mode, target
platform, and optional cron expression:

```yaml
# cron/jobs.yaml
pipeline_schedules:
  - name: daily-wechat
    topic_source: pool          # Select best topic from pool
    mode: auto
    platform: wechat
    schedule: "0 10 * * *"      # Daily at 10:00
  - name: weekly-video
    topic_source: pool
    mode: short-video
    platform: xiaohongshu
    schedule: "0 9 * * 1"       # Weekly on Monday
```

Run all schedules:
```bash
automedia cron run-pipeline
```

Or run a specific schedule:
```bash
automedia cron run-pipeline --name daily-wechat
```

### Method E: Workflow (SDK / MCP)

Define reusable workflows in `workflows.yaml`:

```yaml
# workflows.yaml
workflows:
  daily-article:
    mode: auto
    platform: wechat
    gates:
      exclude: [V3, V7]
    brand: my-brand
  weekend-video:
    mode: short-video
    platform: xiaohongshu
    extends: daily-article  # Inherit from daily-article
    gates:
      include: [H0]
```

Then reference by name:
```python
result = run_full_pipeline(
    topic="AI tools",
    brand="my-brand",
    workflow="daily-article",
)
```

Workflows support `extends` for inheritance and are merged into the pipeline
config at runtime via `_merge_workflow_config()`.

## Production Monitoring

### Real-Time View

```bash
# Watch project directory changes
watch -n 5 ls -la 20260707_*/

# View pipeline_md5.json
cat 20260707_*/pipeline_md5.json
```

### View Gate Status

When running `automedia run`, the CLI output shows each Gate's status:

```
Pipeline finished: success
  Project ID : abc123def456
  Project dir: /var/automedia/projects/20260707_ai-video-tools
  Duration   : 342.5s

  Gates executed: 21
    ✓ pre-gate (0.32s)
    ✓ CW (8.00s)
    ✓ G0 (12.50s)
    ✓ G1 (8.20s)
    ✓ G2 (5.10s)
    ✓ G3 (3.40s)
    ✓ G4 (2.10s)
    ✓ G5 (1.80s)
    ✓ V0 (0.90s)
    ✓ V1 (45.60s)
    ✓ V2 (30.20s)
    ✓ V3 (15.80s)
    ✓ V4 (10.50s)
    ✓ V5 (2.30s)
    ✓ V6 (60.10s)
    ✓ V7 (5.40s)
    ✓ L1 (0.50s)
    ✓ L2 (1.20s)
    ✓ L3 (0.80s)
    ✓ L4 (1.50s)

  Assets produced: 7
    - [article] 01_content/drafts/wechat/wechat_draft.html
    - [image] 02_images/cover/cover.png
    - [video] 03_video/video_final.mp4
    - [subtitle] 03_subtitle/subtitle.srt
    - [audio] 03_video/tts_audio.mp3
    - [report] 04_review/qa_report.json
    - [log] 05_publish/publish_log.json
```

### Failure Handling

If the Pipeline shows `status="partial"` or `status="failed"`:

1. Check the error message to identify the failing Gate
2. Refer to `docs/dev/gate-failure-modes.md` for remediation steps
3. After fixing the issue, resume from the failed Gate using `--resume-from`:

```bash
automedia run --topic "..." --brand my-brand --resume-from G3
```

## Post-Production Operations

### 1. Review Output

```bash
# Check directories
ls 20260707_*/
ls 20260707_*/01_content/drafts/
ls 20260707_*/02_images/cover/
ls 20260707_*/03_video/
```

### 2. Verify File Integrity

```bash
# Check MD5 records
cat 20260707_*/pipeline_md5.json

# Verify key files
ffprobe 20260707_*/03_video/video_final.mp4
file 20260707_*/02_images/cover/*.png
```

### 3. Publish

Publishing is done automatically or manually through platform adapters. If
auto-publish is configured:

```bash
# Check publish log
cat 20260707_*/05_publish/publish_log.json
```

### 4. Distribute to Platforms

After the pipeline completes, use the distribute command to rewrite content for specific platforms via D1-D7 distribution gates:

```bash
# Distribute to WeChat and Twitter
automedia distribute <project-id> --platforms wechat,twitter

# Distribute to all configured platforms
automedia distribute <project-id> --all

# Preview what would be distributed
automedia distribute <project-id> --all --dry-run
```

Distribution gates are standalone LLM rewrites that adapt content to each platform's format and tone. They run independently from the main pipeline and can be invoked any number of times.

For programmatic distribution, use the MCP tool:
```
distribute_content(project_id="<id>", platforms=["wechat", "twitter"])
```

### 5. View Content Analytics

Get content metrics for a project:

```bash
automedia effects <project-id>
```

Returns: word count, sentiment score, readability score, brand mentions, and SEO scores across 5 dimensions.

### 6. Archive

After confirming the content has been successfully published:

```bash
# Archive (requires status to be published)
automedia archive <project-id>

# Or force archive
automedia archive <project-id> --force
```

After archiving, the project directory gets the `_archived` suffix.

## Weekly Maintenance

### Clean Topic Pool

Clean expired topics weekly:

```bash
automedia pool prune --days 14 --db .automedia/pool.db
```

### Check Disk Usage

```bash
du -sh /var/automedia/projects/*_archived/
# Archived projects can be moved to cold storage
```

### Update Brand Configuration

Modify `~/.automedia/brand-profile.yaml` as needed:

- Adjust CTA strategy
- Update the blocked words list
- Change brand name or tone

### Check Cron Logs

```bash
tail -100 /var/log/automedia/cron.log
```

Confirm all jobs have run normally over the past week.

## Exception Handling

### Gate Repeatedly Fails

If a Gate repeatedly fails, refer to `gate-failure-modes.md` for diagnosis.
If it still fails after remediation:

1. Check if the LLM provider is working (G0, G1 and other LLM-related Gates)
2. Check if external dependencies are working (V1 depends on ComfyUI,
   V2 depends on Whisper)
3. Temporarily switch to lower gate thresholds (via overrides/rules)

### Insufficient Disk Space

```bash
# Find large files
find . -type f -size +100M
# Clean temp files from archived projects (keep 00_project_info.json only)
```

### API Rate Limiting

If you encounter LLM API rate limiting:

1. Check the `rate_limit` configuration in `model_config.yaml`
2. Vision QA will automatically degrade to pixel luminance analysis
   (noted as "degraded" in output)
3. Consider switching providers or increasing the rate limit window

### Pipeline Interrupted Midway

```bash
# View completed Gates
cat 20260707_*/pipeline_md5.json | python -m json.tool

# Resume from the interruption point
automedia run --topic "..." --brand my-brand --resume-from G3
```
