# D3 Gap Analysis — Founder Expectations vs Codebase Reality

> **Purpose**: Identify every gap between the D3 founder expectations document
> (`docs/dev/founder-expectations.md`) and the actual AutoMedia codebase.
>
> **Scope**: All 8 phases, 48 expectations (F01–F48).
>
> **Legend**: ✅ Already implemented · ⚠️ Partial / needs alignment · ❌ Missing / not implemented
>
> **Documentation alignment wave in progress**: The D3 founder expectations doc
> and this gap analysis are being updated together. Gaps in documentation
> alignment (e.g., `_VALID_GATE_NAME_RE` comment, README mode list, gate ranges)
> are being closed in the current wave.

---

## Summary

| Phase | Expectations | ✅ | ⚠️ | ❌ | Mostly… |
|-------|:---:|:---:|:---:|:---:|---------|
| 1 — Setup (F01–F10) | 10 | 5 | 2 | 3 | Partial |
| 2 — Input (F11–F16) | 6 | 4 | 0 | 2 | Partial |
| 3 — Run & Monitor (F17–F22) | 6 | 5 | 1 | 0 | Good |
| 4 — Review (F23–F28) | 6 | 0 | 1 | 5 | ❌ Poor |
| 5 — Publish (F29–F35) | 7 | 3 | 3 | 1 | Partial |
| 6 — Repeat (F36–F39) | 4 | 3 | 1 | 0 | Good |
| 7 — Monitor (F40–F43) | 4 | 3 | 1 | 0 | Good |
| 8 — Iterate (F44–F48) | 5 | 3 | 2 | 0 | Good |
| **Total** | **48** | **26** | **11** | **11** | **~54% aligned** |

---

## Phase 1 — Setup (F01–F10)

### F01 — Installation ✅
Already implemented: `pip install`, `git clone`, Docker, `automedia doctor` for dep checking.

### F02 — First Command ✅
Already implemented: `automedia` shows help, `--json` flag available, MCP tool auto-discovery via protocol.

### F03 — Configuration Initialization ❌
| Aspect | D3 Expectation | Codebase Reality |
|--------|---------------|------------------|
| **What init creates** | Full project skeleton: `config.yaml`, `brand_profile.yaml`, `model_config.yaml`, directory structure (`01_content/`, `02_images/`, `03_video/`, `04_subtitle/`, `05_review/`, `06_publish/`) | Only writes `~/.automedia/model_config.yaml` (LLM provider/model/key). No directory structure, no `config.yaml`, no `brand_profile.yaml`. |
| **Init process** | Interactive wizard asking for brand name, industry, target audience | Interactive wizard asks only for LLM provider, model, API key, base URL |
| **Project skeleton** | Created by `init` | Does NOT exist. Project directory is created by `Project.init()` in `runner.py` when the first pipeline runs. |
| **Re-running init** | Idempotent: creates missing files, never overwrites | ✅ Already idempotent (writes model_config.yaml only) |

**Impact**: First-time user who runs `automedia init` gets only LLM config, not a usable project structure. They must run a pipeline to get directories created. The "5 minutes from install to first command" is achievable only if user already knows to set env vars instead of relying on `init`.

### F04 — API Key Configuration ✅
Already implemented: env var + `model_config.yaml`, `doctor` checks, friendly error on missing key.

### F05 — Brand Configuration ❌ (CRITICAL)
| Aspect | D3 Expectation | Codebase Reality |
|--------|---------------|------------------|
| **Storage model** | Multiple brand profiles in `.automedia/brand_profile.yaml` | Single brand per project stored in `project_dir/brand-profile.yaml` (loaded in `runner.py:390-395`) |
| **`list_brands` MCP tool** | Returns `[{"name": "wechat-tech", "industry": "tech"}]` | ❌ **Does NOT exist.** No tool to discover brands. Agent is blind to available brands. |
| **Multi-brand** | One `.automedia/` stores multiple brands | Impossible — brand is per-project, not per-config |
| **Default brand** | Configurable in `config.yaml` `default_brand` | Not implemented. Brand is always required. |
| **Brand fields** | `brand_name`, `industry`, `target_audience`, `tone`, `personality`, `CTA_rules`, `banned_words` | `BrandProfile` dataclass has: `brand_name`, `aliases`, `cta_principles`, `blocked_words`, `tone_guidelines`, `brand_identity`, `languages`. No `industry`, `target_audience`, or `personality` fields. |

**Impact**: Foundational architecture difference. Agent workflow "call `list_brands` → pick best brand → pass to `run_pipeline`" is impossible. Every brand change requires either a different project or manually editing `brand-profile.yaml`.

### F06 — Setup Verification ✅
Already implemented: `automedia doctor` + `health_check` MCP tool.

### F07 — Pipeline Mode Default ⚠️
`_MODE_MAP` in runner.py defines 8 modes, but `run_pipeline` MCP tool (tools.py:481) only validates 4 (`auto`, `text_only`, `video_only`, `qa_only`). MCP tool validation is out of sync with runner. D3 doc mentions only 4 modes. **Need to align on which set is canonical.**

### F08 — Runtime Output ✅
Already implemented: MCP `run_pipeline` returns `{project_id, status: "started"}` in background thread, `get_pipeline_progress` polls `PipelineProgress` events. Human CLI gets line-by-line output.

### F09 — Failure & Error Display ⚠️
D3 specifies structured error schema: `{check_name, actual_value, threshold, detail, suggestion}`. GateEngine captures errors but each gate's error format varies — no enforced schema. MCP returns JSON error dicts consistently.

### F10 — Project Output Location ✅
Already implemented: auto-named `{YYYYMMDD}_{slugified_topic}/` with standard subdirectory layout.

---

## Phase 2 — Input (F11–F16)

### F11 — Topic Input ✅
Already implemented: `automedia run --topic "X"`, `run_pipeline(topic="X")`, `select_topic`, pool, trending.

### F12 — Input Source Material ❌
| Aspect | D3 Expectation | Codebase Reality |
|--------|---------------|------------------|
| **`source_path` parameter** | `run_pipeline(topic="X", source_path="/path/to/doc.md")` | ❌ **Does NOT exist.** MCP `run_pipeline` (tools.py:441-449) has no `source_path` or `source_url` parameter. |
| **`--source` CLI** | `automedia run --topic "X" --source /path/to/article.md` | ❌ Not implemented |
| **`--source-url` CLI** | `automedia run --topic "X" --source-url "https://..."` | ❌ Not implemented |
| **Material auto-detect** | Given path → directory scan / file read / URL fetch / LLM-only | ❌ Not implemented |
| **`extract_brief` as workaround** | Agent can call `extract_brief` then pass result to `run_pipeline` | ⚠️ Possible but there's no `source_path` parameter to receive it |

**Impact**: The core promise "give a topic, optionally with source material" is partially broken — topic-only works, but material-augmented generation isn't supported through the standard path.

### F13 — Omni Triad ✅
All three Omni tools implemented: `extract_brief` (OPP), `localize_content` (OL), `format_output` (ORF). Plus `localize_output` for batch translation.

### F14 — Topic Pool ✅
SQLite-backed pool with `pool_add_topic`, `list_topic_pool`, `select_topic`, scoring, dedup.

### F15 — Trending ✅
`research_topics` MCP tool with LLM-driven topic research.

### F16 — Brand Selection ❌ (depends on F05)
`run_pipeline(brand="X")` works but `list_brands` doesn't exist, so agent can't discover available brands. Single-brand-per-project limitation.

---

## Phase 3 — Run & Monitor (F17–F22)

### F17 — One-Command Run ✅
`automedia run --topic "X" --brand Y` after setup. `run_pipeline(topic="X", brand="Y")` for agents.

### F18 — Progress Visibility ✅
`PipelineProgress` tracker with thread-safe events. MCP `get_pipeline_progress` polls gate-by-gate. Human CLI gets per-gate streaming. V-stage gates run in parallel (max_workers=3).

### F19 — Gate Failure Detail ⚠️
D3 specifies consistent error schema: `{check_name, actual_value, threshold, detail, suggestion}`. Not enforced across gates — each gate returns its own dict shape. GateEngine wraps exceptions with `{passed, gate, error, duration_s}`.

### F20 — Pipeline Resilience ✅
`failure_mode="stop"` halts, `failure_mode="retry"` triggers automatic retry (tenacity for transient exceptions). Pipeline never crashes — top-level try/except catches everything.

### F21 — Pipeline Resume ✅
`resume_from` parameter supported in both CLI and MCP. MD5 integrity verification before resume. `_VERIFY_RESUME_INTEGRITY` checks prior gate outputs.

### F22 — Performance Expectation ✅
No hard time target. Progress feedback as perf proxy.

---

## Phase 4 — Review (F23–F28)
**This is where the biggest architectural gaps exist.**

### F23 — Output Summary ⚠️
The D3 expectation is that agent presents a natural language summary to the human. The tooling exists (`get_pipeline_status`, `get_project_assets`) but the "agent presenting a summary" is agent-side behavior, not a codebase feature. The CLI prints a summary at pipeline end.

### F24 — Article Quality Auto-Recovery ❌ (CRITICAL)
| Aspect | D3 Expectation | Codebase Reality |
|--------|---------------|------------------|
| **Auto-recovery model** | Escalating: (1) retry same content → if fail, (2) regenerate with modified prompt → re-run gate → if still fail, (3) escalate to human with summary | ❌ **NOT IMPLEMENTED.** Gate engine retries only on **transient exceptions** (ConnectionError, TimeoutError). No "gate failed due to quality → regenerate content → re-run" logic. |
| **Content regeneration** | Modified prompt with feedback from failed gate | ❌ Not implemented. No feedback loop from gate results back to content generation. |
| **Human escalation** | Human receives summary of what was tried | ❌ Not implemented. No escalation path. |
| **Supervisor model** | Agent runs gates, attempts self-recovery, human supervises | ❌ The entire supervisor model is absent. Agent calls `run_pipeline` once and gets a binary pass/fail. |

### F25 — Factual Accuracy Auto-Recovery ❌
Same auto-recovery architecture gap as F24.

### F26 — Brand Compliance Auto-Recovery ❌
Same auto-recovery architecture gap as F24.

### F27 — Video & Subtitle Quality ❌
Same auto-recovery architecture gap as F24. V0-V7 gates exist and run (parallel V-stage) but no auto-recovery beyond transient exception retry.

### F28 — Human Content Review Before Publish ❌
| Aspect | D3 Expectation | Codebase Reality |
|--------|---------------|------------------|
| **Review trigger** | After pipeline completes, agent presents content for human review | ❌ HITL framework exists in `automedia/hitl/` as an independent module but is **NOT integrated into the pipeline or gate engine**. No `before_publish` gate or hook. |
| **HITL in gates** | "HITL is not integrated into every gate" — single review point before publish | ✅ The framework is NOT integrated into gates (correct per D3), but it's also NOT integrated anywhere in the pipeline flow. |
| **Agent approval flow** | Human says "publish" → agent calls `publish_content` | ⚠️ `publish_content` exists but the workflow is manual — no prompt-and-confirm flow. |

**Impact**: The entire Phase 4 supervisor model is **not implemented**. The codebase has a retry mechanism for transient errors but no content-quality self-recovery. The D3 vision of "agent as primary operator, human as 监工" requires significant architectural work.

---

## Phase 5 — Publish (F29–F35)

### F29 — Publish Automation Model ❌
| Aspect | D3 Expectation | Codebase Reality |
|--------|---------------|------------------|
| **Automation levels** | `auto` (publish immediately), `review` (create draft), `manual` (no attempt) per platform | ❌ **NOT IMPLEMENTED.** `PublishEngine.publish_all()` iterates ALL adapters with `enabled=True` — no per-platform automation level filter. |
| **Configuration** | Per-platform in brand config: `brands.wechat.automation: auto` | ❌ No automation field in `BrandProfile` dataclass or brand config |
| **Draft creation for review mode** | Agent gets `{status: "draft_created", draft_url: "..."}` | ❌ No draft flow |

### F30 — WeChat Official Account ✅
Implemented (`wechat_publisher.py`, 529 lines). Uses real WeChat API.

### F31 — Zhihu ✅
Implemented (`zhihu_publisher.py`).

### F32 — Platform Notifications ✅
Feishu notifier, Discord publisher exist.

### F33 — Platform-Specific Formatting ⚠️
Adapters handle format internally. AssetSelector (`publish_engine.py:182-276`) selects assets by platform category (text-first/image-first/video-first/mixed-social). Per-platform format adaptation exists but per-platform content adaptation (title tweaks, CTA adjustment) is not implemented.

### F34 — Multi-Platform Routing ⚠️
| Aspect | D3 Expectation | Codebase Reality |
|--------|---------------|------------------|
| **Platform binding** | Brand config declares `platforms: [wechat, zhihu]` → content type auto-determined | ❌ No platform binding in brand config. Content mode is explicit `--mode` parameter, not derived from platform list. |
| **Content type from platforms** | `[text-first, mixed-social]` → text mode; `[video-first]` → video mode | ❌ Not implemented |
| **Partial failure** | One platform failure doesn't block others | ✅ Already implemented |

### F35 — Publish Error Handling ⚠️
| Aspect | D3 Expectation | Codebase Reality |
|--------|---------------|------------------|
| **Self-recovery** | Retry → credential refresh → retry → escalate to human | ⚠️ Partial: tenacity retry on transient exceptions only. No credential refresh or human escalation. |
| **Common failures handled** | Credential expiry, rate limit, network error, format rejection | ⚠️ Network error retry done. Credential expiry, rate limit, format rejection NOT handled. |
| **Structured errors** | `{platform, error, action, retryable}` | ⚠️ Errors are `{"status": "error", "reason": str(exc)}` — not structured per D3 spec |

---

## Phase 6 — Repeat (F36–F39)

### F36 — Batch Production ✅
D3 acknowledges batch is orchestration pattern, not pipeline mode. Agent loops over topics. Each topic gets its own `run_pipeline` call.

### F37 — Scheduled Production ⚠️
D3 says config-driven cron with `cron.schedules` in `config.yaml`. The cron module exists (`automedia/cron/`) but default config has no `cron.schedules`. Need to verify cron config format.

### F38 — Customizable Topic Pipeline ✅
Override system (`~/.automedia/overrides/rules/` and `prompts/`) exists for customization.

### F39 — Run Isolation ✅
Per-project directories, independent `pipeline_md5.json`, shared-nothing design.

---

## Phase 7 — Monitor (F40–F43)

### F40 — Project Overview ✅
`list_projects` MCP tool, `automedia projects list` CLI, status categories.

### F41 — Asset Inspection ✅
`get_project_assets` MCP tool, `automedia projects assets` CLI.

### F42 — Asset Library Search ✅
Combined FTS5 + Chroma semantic search implemented in `asset_library/search.py`.

### F43 — System Health & Integrity ⚠️
`automedia doctor` checks system state. MD5 tracking in `pipeline_md5.json`. Auto-repair is agent-side — not a codebase feature.

---

## Phase 8 — Iterate (F44–F48)

### F44 — Gate & Brand Isolation ✅
Gate registry per pipeline run. Brand profile per project (but single-brand limitation noted in F05).

### F45 — Override System ✅
6-layer config hierarchy with `overrides/rules/` and `overrides/prompts/`.

### F46 — Test Coverage ⚠️
2,047 tests passing. D3 doc mentions this number. Tests cover gates, pipelines, CLI, MCP, Omni, hooks, accounts. Gate naming convention (`G\d+`, `V\d+`, `L\d+`, `CW`, `pre-gate`) is enforced by `_VALID_GATE_NAME_RE` — broad enough to cover all current and future gates.

### F47 — Forward Compatibility ⚠️
`deprecated` warnings for `decision_mode` and `force_provenance`. Runner loads gates module dynamically (`import automedia.gates`). `rewrite` → `retry` mapping. Good but no formal deprecation policy document.

### F48 — Documentation Fidelity ✅
AGENTS.md, README.md, docs/, changelog all maintained.

---

## Cross-Cutting Issues

### 1. Gate Naming Regex (Resolved)
```python
_VALID_GATE_NAME_RE = re.compile(r"^(D\d+|G\d+|V\d+|L\d+|CW|pre-gate)$")
```
✅ **Resolved**: Comment updated to reflect V0–V8, L1–L11. The regex itself (`\d+`) was always broad enough. Now aligned with documentation.

### 2. Pipeline Mode Mismatch (Partial)
| Source | Modes Listed |
|--------|-------------|
| D3 doc (F07) | ✅ 8 modes (updated) |
| `runner.py:_MODE_MAP` | 8 modes (canonical) |
| MCP `run_pipeline` validation | ⚠️ Still only 4 modes (`auto`, `text_only`, `video_only`, `qa_only`) |
| README.md | ✅ 8 modes (updated) |

**Remaining issue**: MCP tool validation still rejects 4 valid pipeline modes (`image-carousel`, `text-with-cover`, `short-video`, `social-thread`). D3 doc and README are now aligned.

### 3. HITL Framework Orphaned
The `automedia/hitl/` module exists with `config.py`, `executor.py`, `protocol.py`, `presets/`, `templates/` — but **zero integration** with the pipeline, gate engine, or any tool. The CLI has `automedia hitl` commands. It's a framework waiting for a consumer.

### 4. Agent → Human Communication Gap
D3 assumes the agent presents summaries, asks for approval, and reports results to the human in natural language. This is **inherently agent-side behavior** (OpenCode, Claude Code, etc.) and not something AutoMedia implements. AutoMedia provides the tools (`get_pipeline_status`, `get_project_assets`, `publish_content`) but the agent framework must handle the human interaction layer.

### 5. run_pipeline MCP Mode Validation
The MCP tool validation (tools.py:481) is **stricter** than the runner:
```python
valid_modes = ("auto", "text_only", "video_only", "qa_only")
```
This rejects `image-carousel`, `text-with-cover`, `short-video`, `social-thread` — all valid modes in `runner.py`. Fix: either remove the validation (let runner validate) or sync the list.

---

## Prioritized Fix List

### P0 — Blocking (breaks agent workflow)
1. **Create `list_brands` MCP tool** (F05) — agent cannot discover brands without it
2. **Either implement multi-brand or update D3 doc** (F05) — foundational architecture decision
3. **Add `source_path` to `run_pipeline`** (F12) — breaks material-augmented content generation

### P1 — Supervisor Model (Phase 4 architecture)
4. **Implement auto-recovery for content gates** (F24–F26) — retry → regenerate → escalate
5. **Integrate HITL into pre-publish flow** (F28) — connect `automedia/hitl/` to pipeline

### P2 — Publish Architecture
6. **Implement per-platform automation levels** (F29) — auto/review/manual in publish engine
7. **Implement brand-to-platform binding** (F34) — platform list in brand config
8. **Structured publish errors** (F35) — `{platform, error, action, retryable}` format

### P3 — Init & Brand
9. **Expand `automedia init` to create project skeleton** (F03)
10. **Add `industry`/`target_audience` to `BrandProfile`** (F05)
11. **Implement default brand** (F05) — `default_brand` in config

### P4 — Documentation & Alignment
12. ✅ **Update `_VALID_GATE_NAME_RE` comment** — reflect V0-V8, L1-L11 (done)
13. ⚠️ **Sync MCP mode validation to 8 modes** — still rejects 4 valid modes
14. ✅ **Update D3 doc mode list** — F07 now lists all 8 modes (done)
15. ✅ **Update README pipeline mode documentation** — 8 modes listed with table (done)

### P5 — Nice to Have
16. **Unified gate error schema** — enforce `{check_name, actual_value, threshold, detail, suggestion}`
17. **Cron config format alignment** — verify `cron.schedules` in default config
18. **Publish error credential refresh** — extend beyond tenacity retry

---

## How to Use This Document

1. **Before implementing**: Check if the expectation is ✅ — don't re-implement existing work
2. **For design decisions**: Use the gap tables to understand what D3 expects vs what exists
3. **Prioritization**: P0 items should be addressed before P1, etc.
4. **Ongoing maintenance**: Update this document when gaps are closed or new gaps discovered
