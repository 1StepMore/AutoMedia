# SOP Runner

The SOP Runner generates operational playbooks and daily task lists from
Decision Layer outputs. It transforms strategic plans into actionable
execution guides for content operations teams.

---

## Overview

After the Decision Layer completes (Phase 4), the SOP Runner produces:

1. **Execution Handbook** — comprehensive brand operations manual
2. **Daily Task YAML** — machine-readable daily task list for automation
3. **Progress Report** — KPI tracking and optimisation recommendations

### Architecture

```
Decision Layer output
    │
    ▼
┌──────────────────────┐
│    SOP Runner         │
│                       │
│  ┌─────────────────┐  │
│  │ Jinja2 Templates│  │
│  │  handbook.md.j2 │  │
│  │  daily_task.yaml│  │
│  │  .j2            │  │
│  │  progress_      │  │
│  │  report.md.j2   │  │
│  └─────────────────┘  │
│                       │
│  Outputs:              │
│  │ execution_handbook  │
│  │   .md              │
│  │ daily_task.yaml    │
│  │ progress_report.md │
└──────────────────────┘
```

---

## Execution Handbook Generation

The handbook is a Markdown document that serves as the day-to-day operations
manual for the brand's content team.

```bash
automedia sop generate-handbook --brand EcoBrand
```

Output: `output/EcoBrand/execution_handbook.md`

Contents:
- Brand overview and positioning summary
- Daily and weekly task checklists
- A/B testing configuration with sample sizes and confidence thresholds
- Review templates for content quality, brand consistency, and CTA alignment
- Optional overrides section for custom instructions

---

## Daily Task YAML Format

```yaml
# Daily tasks for EcoBrand — 2025-07-09
date: "2025-07-09"
brand: EcoBrand
tasks:
  - "Review and approve pending content items"
  - "Monitor engagement metrics for yesterday's posts"
  - "Schedule 3 social media posts for tomorrow"
overrides:
  ab_test_sample_size: 1000
  ab_confidence_level: 0.95
```

Tasks flow from the content calendar generated in Phase 3 plus any standing
operational tasks defined in the brand profile.

```bash
automedia sop generate-daily-tasks --brand EcoBrand --date 2025-07-09
```

---

## Progress Report Generation

After a content cycle completes, the progress report summarises performance:

```bash
automedia sop generate-progress-report --brand EcoBrand
```

Output: `output/EcoBrand/progress_report.md`

Contents:
- KPI metrics: content produced, total engagement, platform distribution
- Top-performing content (ranked by engagement metric)
- Optimisation recommendations for the next cycle
- Overrides section for custom metrics or notes

### Report Sections

```
┌─────────────────────────────────────┐
│  Brand Name — Progress Report       │
│                                     │
│  ## KPI Metrics                     │
│  - Content pieces produced: 24      │
│  - Total engagement: 45,320         │
│  - Platform distribution:           │
│      WeChat: 12, Instagram: 8, ...  │
│                                     │
│  ## Top Performing Content          │
│  1. "Eco Tips" — 5,200 engagements │
│  2. "New Product" — 3,800 eng.     │
│                                     │
│  ## Optimisation Recommendations    │
│  - Increase video content by 20%    │
│  - Test CTA variants                │
└─────────────────────────────────────┘
```

---

## Customization via Overrides

Templates can be customised with override values:

```yaml
# ~/.automedia/sop/overrides.yaml
ab_test_sample_size: 2000
ab_confidence_level: 0.99
additional_task_categories:
  - "Community management"
  - "Influencer outreach"
```

These overrides are merged into the Jinja2 template context and appear in the
`overrides` section of generated documents. Users can also provide custom
Jinja2 templates at `~/.automedia/sop/templates/` to override the built-in ones.

---

## CLI Reference

```bash
# Generate execution handbook
automedia sop generate-handbook --brand EcoBrand [--output ./my-handbook.md]

# Generate daily task list
automedia sop generate-daily-tasks --brand EcoBrand --date 2025-07-09

# Generate progress report
automedia sop generate-progress-report --brand EcoBrand [--from 2025-06-01 --to 2025-07-01]
```
