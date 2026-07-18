# Founder's Expectations

> Acceptance from the founder's perspective: does the project actually deliver on the original vision?
> Dimension 3 of the multi-dimension verification system.

---

## 1. Why Founder's Expectations?

AutoMedia has 2,955 test functions, 20 quality gates, and three entry points. Tests prove the code is correct. But there's a harder question:

**Does this project actually solve the problem I created it to solve?**

D1 (Pipeline Output Acceptance) answers "was this run's output acceptable?"
D2 (Behavioral Acceptance) answers "does the system behave correctly?"
D3 answers **"does this project deliver value the way I intended?"**

This is the dimension that matters most. If D3 fails, D1 and D2 don't matter.

### 1.1 The Project's Promise

From `docs/user-introduction.md`:

> **AutoMedia 是一个自动化内容生产系统。你给一个选题，它自己完成写稿、核验、配音、做视频、生成字幕、分发到多个平台的全流程。**
>
> AutoMedia 是你内容生产团队的"自动驾驶系统"——它不是帮你写一篇更好的文章，而是把从选题到发布的全流程工业化、自动化、质量可控。你给它方向和选题，它完成剩下的所有体力活。

This is the contract. D3 verifies whether this contract is fulfilled.

### 1.2 Design Principles

| Principle | Meaning |
|-----------|---------|
| **Value-first** | Criteria measure whether the project delivers value, not whether code is structured well |
| **Founder's truth** | The founder's experience is the source of truth — if it doesn't work for the founder, it doesn't work |
| **Honest about gaps** | This document must candidly acknowledge what doesn't work yet |
| **Drives prioritization** | Failed expectations → highest-priority fixes |
| **Living document** | Expectations evolve as the project matures |

### 1.3 Three User Types

The system serves three distinct user roles:

| Role | Description | Interface | Example |
|------|-------------|-----------|---------|
| **End-user** (最终消费者) | Consumes the produced content — reads articles, watches videos. The entire system exists to serve them. | Published content (web pages, videos, social posts) | A WeChat follower reading an article produced by AutoMedia |
| **Direct-user** (直接执行者) | Directly operates the automation system. **Agent-first**: all capabilities are designed as MCP tools for AI agents. Human-direct access via CLI/SDK is preserved as a fallback for ad-hoc operations. | MCP tools (primary), CLI & SDK (secondary) | An AI agent calling `run_pipeline()`; a human running `automedia run` |
| **Director-user** (人类指挥者) | Gives high-level direction to the direct-user. Does not touch AutoMedia directly — communicates intent to the agent, who translates it into tool calls. The agent is the interface between the director and the system. | Natural language conversation with the agent | "帮我产一篇 AI 工具对比的文章，发到微信和知乎" — the agent plans and executes |

**Design principle**: Agent-oriented by default, human-capable by design. All system capabilities are exposed as structured MCP tools first (for agent direct-users), with CLI and SDK as accessible alternatives (for human direct-users). The director-user communicates intent through the agent, not through AutoMedia directly. This document's expectations are written with the **direct-user** as the primary audience — every expectation covers both agent and human modes where they differ, with agent as the default path.

### 1.4 How This Dimension Is Different

| | D1 (Output) | D2 (Behavioral) | D3 (Founder) |
|---|---|---|---|
| **Asks** | Was this run's output acceptable? | Does the system behave correctly? | Does the project deliver value? |
| **Audience** | Pipeline operator (agent or human direct-user) | Developer | Founder / first user |
| **Scope** | Single pipeline run | All system surfaces | Entire project purpose |
| **Failure means** | Re-run the pipeline | Fix the code | Rethink the approach |
| **Frequency** | Every run | Before releases | Quarterly / milestone |
| **Tone** | Technical pass/fail | Technical pass/fail | Product-ish pass/fail |

---

## 2. Founder's User Journey

The founder's complete workflow — from having an idea to seeing it published.

```
┌─────────────────────────────────────────────────────────────────┐
│                  FOUNDER'S USER JOURNEY                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐  │
│  │ 1. SETUP  │ → │ 2. INPUT │ → │ 3. RUN   │ → │ 4. REVIEW    │  │
│  │          │   │          │   │          │   │              │  │
│  │ Install  │   │ Pick     │   │ Run      │   │ Check gates  │  │
│  │ Config   │   │ topic    │   │ pipeline │   │ View output  │  │
│  │ Brand    │   │ Set mode │   │ Monitor  │   │ Fix if fail  │  │
│  │ Keys     │   │          │   │ progress │   │              │  │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘   └──────┬───────┘  │
│       │              │              │                │          │
│       ▼              ▼              ▼                ▼          │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐  │
│  │ 5. PUBLISH│   │ 6. REPEAT│   │ 7. MONITOR│  │ 8. ITERATE  │  │
│  │          │   │          │   │          │   │              │  │
│  │ Deploy   │   │ Batch    │   │ Track    │   │ Add gates   │  │
│  │ Publish  │   │ Cron     │   │ Analytics│   │ Fix gaps    │  │
│  │ Multi-   │   │ Pool     │   │ Health   │   │ Improve     │  │
│  │ platform │   │          │   │          │   │              │  │
│  └──────────┘   └──────────┘   └──────────┘   └──────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

The journey has 9 phases. Each phase has specific expectations.

---

## 3. Expectation Catalog

Each expectation is a statement of what the founder expects the project to do.
Expectations are grouped by journey phase.

### 3.1 Phase 1: Setup

> "I should be able to install and configure AutoMedia in minutes."

#### F01 — Installation

| UX Detail | Specification |
|-----------|---------------|
| **Installation methods** | Multiple paths supported: `pip install automedia-pipeline` (PyPI), `git clone + pip install -e .` (source/dev), or `docker pull` (Docker). README recommends ONE primary path. |
| **Expected dependency handling** | `automedia doctor` detects missing system dependencies (FFmpeg, Bun, edge-tts, Whisper, Chrome) and reports them with install guidance. User installs missing deps independently. |
| **Expected UX on first install** | Install to first successful command under 5 minutes for a new user who can `pip install`. |
| **Agent perspective** | Agent does not install AutoMedia. Agent connects to a running MCP server (`python -m automedia.mcp.server`). The MCP server must be started by the human or systemd. Agent's "install" is: MCP server is reachable and `health_check` returns OK. |

#### F02 — First Command

| UX Detail | Specification |
|-----------|---------------|
| **Human: `automedia` with no arguments** | Shows standard typer help text listing commands. No splash screen, no branding display. |
| **Agent: MCP server connection** | Agent connects to MCP server via stdio or SSE. Calls `health_check` tool to verify connectivity. Tool manifest is auto-discovered via MCP protocol — no manual configuration needed beyond pointing to the server. |
| **Output format — human** | Plain text help. `--json` flag available globally for machine-readable output. |
| **Output format — agent** | JSON-RPC over stdio. All tools return structured dicts. Tool descriptions are self-documenting via MCP protocol. |
| **Key info visible** | Human: commands, config location, version. Agent: tool list, resource list, server instructions. |

#### F03 — Configuration Initialization

| UX Detail | Specification |
|-----------|---------------|
| **Config file location** | Two-tier: project `.automedia/` takes priority; `~/.automedia/` is fallback. If neither exists, `init` creates `.automedia/` in current directory. |
| **Init process — human** | Interactive wizard: asks user for brand name, industry, target audience, then generates full config skeleton. Not silent — user provides input. |
| **Init process — agent** | Agent does not run `init`. Agent expects `.automedia/` to already exist with valid config. If missing, MCP tools return appropriate error. |
| **Re-running init** | Idempotent: creates any missing files but never overwrites existing config. To reset fully, delete `.automedia/` and re-run init. |
| **What init creates** | Full project skeleton: `config.yaml` + `brand_profile.yaml` + `model_config.yaml` + directory structure (`01_content/`, `02_images/`, `03_video/`, `04_subtitle/`, `05_review/`, `06_publish/`). |

#### F04 — API Key Configuration

| UX Detail | Specification |
|-----------|---------------|
| **Supported methods — human** | Both: `export AUTOMEDIA_LLM_API_KEY="sk-..."` (env var, higher priority) OR write into `model_config.yaml` (lower priority). |
| **Supported methods — agent** | Agent does not set API key. MCP server process has `AUTOMEDIA_LLM_API_KEY` in its environment (configured by human in MCP client config or systemd unit). Agent inherits server's key. |
| **Key verification** | Two routes: `automedia doctor` can check LLM connectivity on demand; pipeline run also gives friendly error if key is invalid. MCP `health_check` does not verify LLM key — agent should call `run_pipeline` and handle key errors gracefully. |
| **Missing key at pipeline start** | Clean error: "AUTOMEDIA_LLM_API_KEY 未设置。设置方法：export AUTOMEDIA_LLM_API_KEY="sk-..." 或写入 model_config.yaml"。Pipeline not started. For agent: `{"error": "LLM API key not configured"}`. |
| **Minimum friction — human** | Single env var is sufficient. User can `export AUTOMEDIA_LLM_API_KEY="..."` and immediately run a pipeline. No need for init wizard if env var is set. |
| **Minimum friction — agent** | Agent assumes MCP server has key configured. If not, agent reports back to human: "AutoMedia MCP server needs AUTOMEDIA_LLM_API_KEY configured." |

#### F05 — Brand Configuration

| UX Detail | Specification |
|-----------|---------------|
| **Minimum required fields** | `brand_name` + `industry` + `target_audience`. Beyond these, any extra data the user provides that AutoMedia can meaningfully use is accepted and applied. |
| **Validation** | `init` validates brand configuration at creation time. Errors reported immediately with clear messaging. |
| **Multi-brand config** | One `.automedia/` directory stores multiple brand profiles in `brand_profile.yaml`. Each profile has a unique `brand_name` and its own `industry`, `target_audience`, `tone`, `personality`, `CTA_rules`, `banned_words`. |
| **Default brand** | Configurable in `config.yaml` via `default_brand`. If unset, `--brand` is required on every `automedia run`. |
| **Switching brands** | Human: `automedia run --brand "wechat-tech"`. Agent: `run_pipeline(brand="wechat-tech")`. No directory switching required. |
| **Established brand** | Once configured, brand voice persists across all pipeline runs. User doesn't reconfigure per run. |
| **Agent: select brand** | `run_pipeline(brand="my-brand")` — agent passes brand as a string param. Agent-friendly: same param works across all modes. |
| **Agent: discover brands** | `list_brands` MCP tool returns `[{"name": "wechat-tech", "industry": "tech"}, {"name": "xiaohongshu-lifestyle", "industry": "lifestyle"}]`. Previously a gap (agent was blind to available brands) — now discoverable. |
| **Agent: multi-brand workflow** | Agent calls `list_brands` → picks best match for topic → passes brand string to `run_pipeline`. Fully autonomous brand selection. |

#### F06 — Setup Verification

| UX Detail | Specification |
|-----------|---------------|
| **Human verification** | `automedia doctor` serves as the setup verification tool. Checks Python version, FFmpeg, Bun, edge-tts, Whisper, Chrome availability, LLM API connectivity. Per-dependency pass/fail with detail. |
| **Agent verification** | `health_check` MCP tool returns `{status, version, uptime_s, tools_count}`. Agent does not check system dependencies — `health_check` only verifies the server is running. |
| **LLM check** | Human: `doctor` can confirm LLM API key is valid. Agent: no dedicated tool — agent may run a minimal pipeline and handle key errors. |
| **Missing dep guidance** | For each missing dependency, `doctor` prints install instructions (`sudo apt install ffmpeg`, `brew install ffmpeg`, etc.). |

#### F07 — Pipeline Mode Default

| UX Detail | Specification |
|-----------|---------------|
| **Human: default mode** | Configurable. `automedia run --topic "X" --brand "Y"` uses whatever `default_mode` is set in `.automedia/config.yaml`. If unset, there is no default — user must specify `--mode`. |
| **Agent: default mode** | `run_pipeline` MCP tool has `mode` parameter with the same default behavior — reads from config if available, otherwise requires explicit parameter. |
| **Available modes** | 8 modes: `auto` (full pipeline: content → quality gates → video → lifecycle), `text_only` (content writing + quality gates, skip video), `text_with_cover` (text content with cover image), `video_only` (video processing only, uses existing content), `qa_only` (re-run selected quality gates on existing output), `image-carousel` (image carousel with lifecycle gates), `social-thread` (social media thread format), `short-video` (short-form video pipeline). |
| **Implementation status** | ✅ 8 modes fully implemented with mode-specific gate lists in `_MODE_MAP` in `runner.py`: `auto`, `text_only`, `text_with_cover`, `video_only`, `qa_only`, `image-carousel`, `social-thread`, `short-video`. |
| **Rationale** | `auto` mode may fail due to missing video deps; `text_only` is a conscious choice per run. No silent default that could fail unexpectedly. Mode determines what the pipeline produces; platform adapters then consume what they can from the output (see F34). |

#### F08 — Runtime Output

| UX Detail | Specification |
|-----------|---------------|
| **Human: during execution** | Real-time, line-by-line streaming output. Each gate's progress and sub-checks printed as they occur. User sees what's happening now. |
| **Agent: during execution** | `run_pipeline` returns `{project_id, status: "started"}` immediately. Agent polls `get_pipeline_progress(project_id)` for structured gate-by-gate progress events: `{gate_name, event: "start"|"passed"|"failed", duration_s, checks[]}`. |
| **Latency expectation** | Human: first gate result visible within 10-30 seconds. Agent: progress poll returns within 1s, gate results available as they complete. |
| **Gate status format — human** | Clearly visible pass/fail per gate (green ✅ / red ❌). Gate name, duration, and result summary on each line. |
| **Gate status format — agent** | Structured JSON: `{"gate_name": "CW", "status": "passed", "duration_s": 1.2, "checks": [{"name": "...", "passed": true}]}`. |
| **Pipeline completion — human** | Prints project directory path and list of core output files. Summary with total duration and final status. |
| **Pipeline completion — agent** | Agent calls `get_pipeline_status(project_id)` which returns full `PipelineResult` as JSON with `status`, `gates_log[]`, `assets[]`. |

#### F09 — Failure & Error Display

| UX Detail | Specification |
|-----------|---------------|
| **Human: gate failure** | Red-colored message: gate name, which specific check failed, why it failed, and whether the pipeline stops or continues (stop vs retry mode). No raw Python traceback to the user. |
| **Agent: gate failure** | `get_pipeline_progress` returns `{"gate_name": "G3", "event": "failed", "error": "brand_cta_missing: CTA not found in last paragraph"}`. Structured — agent can read and self-correct. |
| **Missing API key — human** | Pipeline refuses to start with a clear message telling user how to set the key. |
| **Missing API key — agent** | `run_pipeline` returns `{"error": "LLM API key not configured. Ask human to set AUTOMEDIA_LLM_API_KEY."}`. Agent should relay to human. |
| **Missing dependency** | If a gate needs a missing dependency, it reports the specific dependency and suggests install command. `text_only` mode does not check video deps. |
| **MCP tool error** | Returns structured JSON error dict with `error` key containing human-readable message. Agent-friendly: error keys are consistent, actionable. |
| **Implementation status** | ✅ Working — structured errors throughout; tracebacks only surface with `--verbose` flag. `automedia/cli/output_format.py` provides `output_formatted_error()` and `output_pipeline_error()` which replace raw Python tracebacks with concise, actionable messages. All MCP tools return structured JSON error dicts with a consistent `error` key. Full tracebacks are still captured by structlog for debugging and are shown only when the caller passes `--verbose`. |

#### F10 — Project Output Location

| UX Detail | Specification |
|-----------|---------------|
| **Human: default path** | Current working directory, auto-named `{YYYYMMDD}_{slugified_topic}/`. E.g. `./20260714_ai视频工具对比/`. |
| **Agent: finding outputs** | `get_project_assets(project_dir)` returns list of all files with types. `get_pipeline_status(project_id)` returns `assets[]` with paths. Agent does not need to know the directory naming convention. |
| **Inside project dir** | Standard subdirectory layout: `01_content/drafts/`, `02_images/`, `03_video/`, `04_subtitle/`, `05_review/`, `06_publish/`, plus `00_project_info.json` and `pipeline_md5.json`. |

### 3.2 Phase 2: Input

> "I should be able to tell the system what to produce with minimal friction."

#### F11 — Topic Input (Topic → Article)

*Core promise: give a topic, get a full article.*

| UX Detail | Specification |
|-----------|---------------|
| **Human: direct topic** | `automedia run --topic "AI视频工具对比2026" --brand my-brand` — one command with topic string |
| **Agent: direct topic** | `run_pipeline(topic="AI video tools comparison 2026", brand="my-brand")` — same via MCP |
| **Agent: select from pool** | `select_topic(category="tech")` returns the highest-scored pending topic → `run_pipeline(topic=result.title)` |
| **Pool auto-collection** | Cron job calls `research_topics` → results auto-added to pool → scored and stored |
| **One topic at a time** | Each `run_pipeline` call processes exactly one topic. Batch = sequential calls. |
| **Agent workflow without a specific topic** | If agent has no explicit topic: `research_topics` → review results → `select_topic` from pool → `run_pipeline`. Fully autonomous. |
| **Topic format** | Plain text string in any language. Slugified for project directory naming. |

#### F12 — Input Source Material

*Beyond a topic string, I can give the system source material to work from.*

| UX Detail | Specification |
|-----------|---------------|
| **Human: local file** | `automedia run --topic "X" --source /path/to/article.md` — raw text, PDF, or markdown |
| **Human: URL** | `automedia run --topic "X" --source-url "https://example.com/article"` — system fetches and extracts |
| **Human: no material** | `automedia run --topic "X"` — LLM generates based solely on its training knowledge |
| **Agent: local file** | `run_pipeline(topic="X", source_path="/path/to/doc.md")` |
| **Agent: URL** | Option 1: `extract_brief(file_path="https://...", source_lang="zh", target_lang="zh")` → then `run_pipeline(topic="X", source_path=result)`. Option 2: pass URL directly if tool supports it. |
| **Agent: no material** | `run_pipeline(topic="X")` — LLM-only |
| **Material auto-detect** | Given a path: if it's a directory, scan for readable files (`.md`, `.txt`, `.pdf`). If it's a file, read it. If it's a URL, fetch and extract. If nothing given, LLM-only. |
| **Mixed sources** | File + URL + LLM knowledge merged. System should handle all combinations without conflict. |
| **Implementation status** | ✅ Full implementation. `source_path` (local file/directory) and `source_url` (URL fetch) both supported in `run_pipeline`. Auto-detection of file types, mixed sources merged. Directory scan finds first readable file. |
| **Material intended use** | Material serves as reference/inspiration, not strict source. The LLM uses it as context but can adapt, restructure, and transform. |

#### F13 — Omni Triad Processing (Extract · Translate · Convert)

*I can process source documents through the Omni pipeline before content generation.*

| UX Detail | Specification |
|-----------|---------------|
| **Human: extract content** | `automedia omni extract --file doc.pdf --source-lang zh --target-lang zh` |
| **Agent: extract content** | `extract_brief(file_path="/path/to/doc.pdf", source_lang="zh", target_lang="zh")` |
| **Human: translate** | `automedia omni translate --file draft.md --source-lang zh --target-lang en` |
| **Agent: translate** | `localize_content(md_content="...", source_lang="zh", target_lang="en")` |
| **Human: format conversion** | `automedia omni convert --input file.md --output-format html` |
| **Agent: format conversion** | `format_output(content="...", target_format="html")` |
| **Use case: extract → generate** | Agent calls `extract_brief` → gets structured brief → passes brief (via source_path) to `run_pipeline`. The LLM uses extracted content as reference. |
| **Use case: cross-lingual production** | Agent calls `localize_output(project_dir, target_langs=["en", "ja"])` after pipeline run — creates translated drafts. |
| **Implementation status** | ✅ Full implementation. OPPAdapter (extraction via `extract_brief`), OLAdapter (localization via `localize_content` / `localize_output`), ORFAdapter (format conversion via `format_output`). All exposed as MCP tools. |
| **Agent-friendly output** | All Omni tools return structured dicts with `{content, source_lang, target_lang, metadata}`. Agent can chain them without parsing text output. |

#### F14 — Topic Pool Management

*I can maintain a pool of content ideas and let the system pick the best one.*

| UX Detail | Specification |
|-----------|---------------|
| **Human: add a topic** | `automedia pool add --title "AI视频工具对比" --category tech` |
| **Human: list pool** | `automedia pool list` — shows all topics with status (pending/scored/production/archived) |
| **Human: score pending topics** | `automedia pool score` — runs scoring algorithm on all pending topics |
| **Agent: add a topic** | `pool_add_topic(title="AI video tools", category="tech")` |
| **Agent: list pool** | `list_topic_pool(status="pending", category="tech")` — filtered query |
| **Agent: select best topic** | `select_topic(category="tech")` — returns single highest-scored topic, auto-marks as "in_production" |
| **Scoring factors** | Trending score, category relevance, freshness, platform fit, production history (dedup) |
| **Dedup** | Fuzzy title matching prevents duplicate topics. If same/similar topic exists, new add is idempotent. |
| **Cron collection** | External crond calls `automedia cron run` → runs `research_topics` → auto-adds results to pool |
| **Pool isolation** | Each pool is a SQLite DB file. Separate pools per tenant/project if needed. |

#### F15 — Trending Topic Discovery

*The system can discover what topics are currently hot.*

| UX Detail | Specification |
|-----------|---------------|
| **Trigger — agent** | `research_topics(category="tech", count=10, trending=true)` |
| **Trigger — human** | `automedia pool add --trending --category tech` (one-shot trend fetch + add to pool) |
| **Output** | Returns list of `{title, description, source, trending_score, category}` |
| **Sources** | Multi-platform trend aggregation (social media, news, search trends). Exact sources configured by brand/integration. |
| **LLM enrichment** | LLM analyzes raw trend data → generates structured topic suggestions with reasoning |
| **To pool flow** | Agent calls `research_topics` → reviews results → `pool_add_topic` for selected topics → `select_topic` for the best one → `run_pipeline`. All via MCP tools. |
| **Implementation status** | ✅ Full implementation. `research_topics` MCP tool uses LLM with optional `trending_data` parameter. Results can flow through topic pool: `research_topics` → `pool_add_topic` → `select_topic` → `run_pipeline`. |
| **Human review point** | Agent may present trending topics to human for approval before adding to pool (HITL gate). |

#### F16 — Brand Selection at Input Time

*When I run a pipeline, I can tell it which brand voice to use.*

| UX Detail | Specification |
|-----------|---------------|
| **Human: pick brand** | `automedia run --topic "X" --brand wechat-tech` — explicit brand per run |
| **Agent: pick brand** | `run_pipeline(topic="X", brand="wechat-tech")` — same parameter |
| **Agent: discover brands** | `list_brands` MCP tool returns all configured brands with metadata. Agent calls this first to see available brands. |
| **Default brand** | `config.yaml` `default_brand` field. If set, `--brand` becomes optional. |
| **Brand persistence per run** | Once the pipeline starts with a brand, all gates, content, and publishing use that brand's profile. |
| **Brand switching** | Different runs = different brands. Same `.automedia/`, just change the brand string. |
| **No brand configured** | Error: "未配置品牌。请运行 `automedia init` 或设置 config.yaml。No brands configured." |
| **Agent-side fallback** | If agent can't find a suitable brand via `list_brands`, it should ask human: "What brand should I use? Available: [...]" |

### 3.3 Phase 3: Run & Monitor

> "I should be able to run a pipeline and know what's happening."

#### F17 — One-Command Run

*Setup can be multi-step; daily repeat work must be one command.*

| UX Detail | Specification |
|-----------|---------------|
| **Human: standard run** | `automedia run --topic "AI视频工具对比" --brand wechat-tech` — single command after initial setup |
| **Human: with mode** | `automedia run --topic "X" --brand Y --mode text_only` — explicit mode override |
| **Agent: standard run** | `run_pipeline(topic="AI video tools", brand="wechat-tech")` — single MCP tool call |
| **Agent: with options** | `run_pipeline(topic="X", brand="Y", mode="text_only", source_path="/path/to/doc")` — all params in one call |
| **Setup vs repeat** | First-time user: `pip install → init → doctor → run` (4 steps). After setup: `run` only (1 step). |
| **Agent setup expectation** | Agent expects MCP server running + `.automedia/` configured. No agent-side setup beyond connecting. |

#### F18 — Progress Visibility

*While running, I can see what's happening. Human sees terminal output; agent polls structured data.*

| UX Detail | Specification |
|-----------|---------------|
| **Human: terminal output** | Detailed per-gate display. Each gate shows: gate name, duration, pass/fail status, and key sub-check results. |
| **Human: output format** | Line-by-line streaming. `CW ✅ (1.2s) — 3 checks passed` → `G0 ✅ (0.8s) — fact check passed` → `G1 ❌ stop — 人类感不足，得分 4/10` |
| **Human: no silent gaps** | Between gates, continuous heartbeat or "waiting..." output so terminal never goes silent. |
| **Human: completion** | Prints project directory path, duration summary, and final status (`✅ completed` / `⚠️ partial` / `❌ failed`). |
| **Agent: progress** | `run_pipeline` returns `{project_id: "p_abc123", status: "started"}` immediately. Agent polls `get_pipeline_progress(project_id)`. |
| **Agent: poll interval** | Every 2-3 seconds. Returns structured JSON: `{current_gate, gates_done[], gates_remaining[], overall_status}`. |
| **Agent: per-gate detail** | Each gate in response: `{name: "G0", status: "passed"|"failed"|"running", duration_s, checks: [{name, passed, detail}]}`. |
| **Agent: final status** | Agent calls `get_pipeline_status(project_id)` after completion for full `PipelineResult` with assets and gates_log. |

#### F19 — Gate Failure Detail

*When a gate fails, I know exactly which one and why.*

| UX Detail | Specification |
|-----------|---------------|
| **Human: error output** | `G1 ❌ stop — 人类感不足 (得分 4/10, 阈值 7/10). 建议: 增加口语化表达，减少排比句。` — gate name, which check, why, suggestion. |
| **Human: no traceback** | No raw Python traceback ever shown to human. Errors are framed as gate results, not code failures. |
| **Agent: structured error** | `{"gate_name": "G1", "event": "failed", "error": "humanizer_score: 4/10 below threshold 7/10", "failure_mode": "stop"}`. |
| **Agent: actionable** | Error includes enough detail for agent to self-correct (e.g., "rewrite with more conversational tone"). |
| **Error format consistency** | All gates use same error schema: `{check_name, actual_value, threshold, detail, suggestion}`. |

#### F20 — Pipeline Resilience

*If a gate fails, the pipeline doesn't crash — it follows defined failure behavior.*

| UX Detail | Specification |
|-----------|---------------|
| **Failure mode: stop** | Gate with `failure_mode="stop"` halts pipeline immediately. No further gates run. PipelineResult.status = "failed". |
| **Failure mode: retry** | Gate with `failure_mode="retry"` triggers automatic content regeneration and re-runs the gate (up to max retries). |
| **Pipeline never crashes** | `run_full_pipeline()` never raises an unhandled exception. All gate errors are captured as structured results. |
| **Partial results saved** | Even on failure, all outputs produced so far are saved to the project directory. Not lost. |
| **Human: post-failure** | Terminal shows the failure clearly. "Pipeline stopped at G1 (humanizer). Use --resume to retry from this gate." |
| **Agent: post-failure** | `get_pipeline_progress` shows all gates up to failure with their statuses. Agent decides next action: report to human, retry with different params, or resume. |

#### F21 — Pipeline Resume

*I can resume a failed pipeline without starting over.*

| UX Detail | Specification |
|-----------|---------------|
| **Human: auto-detect** | `automedia run --topic "X" --brand Y --resume` — auto-finds the most recent failed/incomplete project for this topic/brand combination. |
| **Human: explicit specify** | `automedia run --resume-from 20260714_ai视频工具对比` — resumes from a specific project directory. Topic/brand params ignored; project state takes over. |
| **Resume behavior** | Skips all previously passed gates. Re-runs from the first failed gate. Uses the same config and source material as the original run. |
| **Agent: resume** | `run_pipeline(topic="X", resume_from="p_abc123")` — agent passes project_id from `list_projects` or `get_pipeline_status`. |
| **Auto-detect logic** | Scan projects directory → find latest project with `status != "published"` → resume from last failed gate. If no failed project found, start fresh. |
| **Idempotent resume** | Resuming an already-completed project is a no-op (returns success immediately). Resuming multiple times from same failure point produces same result (assuming same inputs). |

#### F22 — Performance Expectation

*A full pipeline run should complete in a reasonable timeframe.*

| UX Detail | Specification |
|-----------|---------------|
| **No hard time target** | "时间不是问题，合理即可" — performance should be reasonable, not benchmarked to a specific minute target. |
| **text_only mode expectation** | Fast: content writing + quality gates should complete within a few minutes. LLM calls are the primary bottleneck. |
| **auto mode expectation** | Video rendering (FFmpeg, subtitle burn-in, TTS) is inherently slower. Acceptable as long as text generation phase is fast. |
| **Progress feedback as perf proxy** | Instead of a timer, continuous progress output (F18) assures the user the system is working. Silence is the real problem, not slowness. |
| **LLM latency tolerance** | LLM calls vary (1-30s per call). Multiple gates × multiple LLM calls = variable total time. This is accepted as inherent to LLM-based pipelines. |

### 3.4 Phase 4: Review

> "I supervise the output. The agent does the review work; I look at the results."

**Design principle**: Human is a **supervisor** (监工), not a hands-on operator. The agent runs gates, checks quality, and attempts self-recovery on failures. The human receives a concise summary and only intervenes for content quality before publishing.

#### F23 — Output Summary

*The agent presents a summary of what was produced. Human doesn't navigate directories.*

| UX Detail | Specification |
|-----------|---------------|
| **Human receives** | A concise summary from the agent (or printed at end of CLI run): status, core output file(s), gate results, output metrics. |
| **Summary content** | `✅ Project completed: "AI视频工具对比2026" (wechat-tech) → draft.md (2,341字) · G0-G5 all passed · Next step: review content at 01_content/drafts/draft.md` |
| **Output metrics included** | Word count, video duration (if auto mode), check pass rate (e.g. "6/8 gates passed"), project total duration. |
| **Human CLI: at end of run** | Terminal prints the same summary directly after pipeline completion. |
| **Agent: presenting to human** | Agent reads `get_pipeline_status(project_id)` → summarizes into a natural language message: "Topic X is done. Gates all passed. The article is at [path]. Want me to publish?" |
| **Agent: next step suggestion** | Summary includes a recommended action: review content, publish, or fix issues. |
| **Human: deeper inspection** | From the summary, human can request more detail: "show me gate results" / "what failed?" **Not** done by browsing directories — done through agent conversation or CLI queries. |

#### F24 — Article Quality (Not AI-Sounding)

*G1 (humanizer) gate checks that the article doesn't read like AI wrote it.*

| UX Detail | Specification |
|-----------|---------------|
| **Gate behavior** | G1 uses **hybrid LLM-first + regex fallback** detection. Default (`enable_llm=True`): attempts LLM-based evaluation with structured output (`G1CheckResult` — 9 AI pattern categories). On LLM failure (timeout/API error), falls back to deterministic regex checks. The `method` field in the result dict indicates which path was used (`"llm"` or `"deterministic"`). |
| **Detection method** | LLM path uses `humanizer_g1.j2` prompt template with few-shot examples — evaluates 9 categories (overused adverbs, hollow intros, vague subjects, filler connectors, long conjunctions, template conclusions, over-academic vocabulary, absolute assertions, repetitive structures). Deterministic fallback uses the same 9 categories via regex. |
| **On failure — auto-recovery** | GateEngine 实现多层递增恢复（仅当 `failure_mode="retry"`）：**Level 1 quality-feedback retry** — 同一 gate 用同一内容重新执行，最多 3 次（`max_quality_retries`）。**Level 2 regeneration** — Level 1 耗尽后，重新执行 CW（内容写入）gate 并携带失败反馈，然后重新执行 CW 之后所有 gates，最多 2 轮（`max_regenerations`）。Level 2 仍失败 → HITL 审批兜底（H0 gate 可人工放行）。Level 0 另有 tenacity 重试处理网络超时等瞬态异常（最多 3 次，指数退避）。 |
| **On failure — human sees** | Summary shows: `G1 ❌ stop — 人类感得分 4/10，低于阈值 7/10。建议: 增加口语化表达。` or `G1 ⚠️ retry 后通过 (quality retry 2 次)` if auto-recovery succeeded. |
| **Human intervention** | Human can: approve as-is, request rewrite with specific instructions, or manually edit. |

#### F25 — Factual Accuracy

*G0 (fact check) verifies claims against source material.*

| UX Detail | Specification |
|-----------|---------------|
| **Gate behavior** | G0 checks factual claims in the article against provided source material. Reports each check as passed/failed with evidence. |
| **No source material** | If no source material was provided, G0 does a lightweight LLM-based plausibility check instead of strict fact verification. Summary notes: "事实核查基于 LLM 知识（无源材料）"。 |
| **On failure — auto-recovery** | G0 has failure_mode="stop". Only Level 0 transient retry (ConnectionError, TimeoutError) applies via tenacity（最多 3 次，指数退避）. Pipeline halts on failed fact check — no quality retry or regeneration. |
| **Human sees** | Summary includes: `G0 ✅ 全部通过 (12 项核查)` or `G0 ⚠️ 3/12 项存疑` with details available on request. |

#### F26 — Brand Compliance

*G3 (brand CTA) gate ensures brand name, tone, and CTA rules are followed.*

| UX Detail | Specification |
|-----------|---------------|
| **Gate behavior** | G3 checks: brand name appears correctly, CTA is present and correct, banned words not used, tone matches brand profile. |
| **On failure — auto-recovery** | G3 has failure_mode="stop". Only Level 0 transient retry (ConnectionError, TimeoutError) applies via tenacity（最多 3 次，指数退避）. This is correct because deterministic pattern matches are idempotent — re-running with same content produces same result. Pipeline halts on any brand compliance failure. |
| **Human sees** | Summary: `G3 ✅ 品牌合规` or `G3 ❌ — CTA 缺失。品牌要求末尾包含官网链接。` |

#### F27 — Video & Subtitle Quality

*V0-V7 gates verify video integrity, subtitle readability, and audio/video sync.*

| UX Detail | Specification |
|-----------|---------------|
| **Gate chain** | V0 (lint) → V1 (vision QA) → V2 (whisper) → V3 (content semantic) → V4 (TTS brand) → V5 (sync) → V6 (subtitle render) → V7 (six-step hard). Each verifies a specific aspect. |
| **Per-gate auto-recovery** | Each video gate handles retry independently via GateEngine's escalating recovery. A failure in V2 doesn't restart V0 — only the failed gate enters Level 1 quality retry, then Level 2 regeneration (re-run CW + all gates from CW), then HITL. |
| **Video quality metrics** | Summary includes: video duration, resolution, subtitle readability score, audio sync status. |
| **Human review** | Human can request agent to "show me the video" — agent provides file path. No auto-play. |

#### F28 — Human Content Review Before Publish

*Before publishing, the human reviews the article content.*

| UX Detail | Specification |
|-----------|---------------|
| **Review trigger** | After pipeline completes successfully (or after auto-recovery), agent presents the content review to the human. |
| **Review format** | Agent tells human the file path: "文章已就绪：`01_content/drafts/draft.md`。请审阅内容，确认后我发布。" Human opens the file locally and reads it. |
| **Pre-publish HITL only** | HITL is a single review gate before publish, not integrated into every pipeline gate. The only review point is **content quality before publishing**. All gate-level failures are handled by auto-recovery inside GateEngine. |
| **Agent after approval** | Human says "发" or "publish" → agent calls `publish_content` or `automedia run --publish`. |
| **Human requests changes** | Human can ask for edits: "把第二段改得更口语化" → agent regenerates content and re-runs gates. |
| **Implementation status** | ✅ Documented and implemented. H0 (human review gate) pauses pipeline with `awaiting_hitl` status. GateEngine supports full HITL lifecycle: `on_gate_awaiting_hitl`, `approve_hitl`, `reject_hitl`. CLI/MCP tools: `automedia hitl approve <project_id> <gate_name>`. |
| **Skip review** | Human can pre-authorize: "不用审了，直接发" — agent publishes without waiting for content review. |

### 3.5 Phase 5: Publish

> "Content goes to the right platforms, in the right format, at the right automation level."

**Design principle**: Brand config binds to specific platforms. The bound platforms determine:
(1) What content types to produce (text / image / video) and
(2) The publish automation level per platform.

Platform → content type mapping is automatic: text-first platforms → text content; video-first → video; mixed → all types needed.

#### F29 — Publish Automation Model

*Publishing behavior is configurable per platform, not a single on/off switch.*

| UX Detail | Specification |
|-----------|---------------|
| **Automation levels** | Three configurable levels per platform: `auto` (publish immediately after gates pass), `review` (create draft, wait for human approval), `manual` (generate content only; no automatic publish attempt). |
| **Why levels exist** | (1) Some platforms can't be fully automated (e.g., Xiaohongshu has no public API). (2) During trust-building phase, users want semi-automatic HITL before full automation. (3) Different platforms have different reliability/stability. |
| **Configuration** | Per-platform in brand config: `brands.wechat.automation: auto`, `brands.zhihu.automation: review`. |
| **Human: auto mode** | Pipeline runs → gates pass → content auto-published to auto-configured platforms. Human sees: `✅ WeChat: published` in summary. |
| **Human: review mode** | Pipeline runs → gates pass → draft created on platform → agent tells human "Zhihu draft ready, review at [link], say '发' to publish." |
| **Human: manual mode** | Pipeline runs → content generated and stored → no publish attempt. Human manually publishes via platform's own interface. |
| **Agent: triggering publish** | `publish_content(project_id, platform="wechat")` or bulk `publish_content(project_id)` for all auto-configured platforms. |
| **Agent: handling review mode** | Agent calls `publish_content` → gets `{status: "draft_created", draft_url: "..."}` → presents to human for approval. |
| **Implementation status** | ✅ Full implementation. Three-level automation (auto/review/manual) per platform in brand config. `publish_engine.py` handles credential refresh, retry logic, and partial failure isolation across platforms. |
| **Brand adaptation** | Content can be adapted per platform before publishing (same source, platform-optimized version). |

#### F30 — WeChat Official Account

*Content published to WeChat as a draft, following WeChat Official Account API rules.*

| UX Detail | Specification |
|-----------|---------------|
| **Implementation status** | ✅ Full implementation (`wechat_publisher.py`, 529 lines). Uses real WeChat API (token → draft → publish). |
| **Platform category** | `text-first` — produces long-form article content. |
| **Publish flow** | API: get token → create draft → (optional) submit for publish. Draft is created even in `auto` mode. |
| **Credential** | `AUTOMEDIA_WECHAT_APPID` + `AUTOMEDIA_WECHAT_APPSECRET` (or legacy `WX_APPID` / `WX_APPSECRET`). |
| **Content format** | HTML body with WeChat-compatible styling. Title, cover image, author, body automatically set. |

#### F31 — Zhihu (知乎)

*Content published to Zhihu as an article draft.*

| UX Detail | Specification |
|-----------|---------------|
| **Implementation status** | ✅ Full implementation (`zhihu_publisher.py`). |
| **Platform category** | `text-first` — produces long-form article content. |
| **Publish flow** | Draft created via Zhihu API. Human or agent can submit for review from draft. |
| **Content format** | Markdown-compatible body with Zhihu-specific formatting (headings, code blocks, images). |

#### F32 — Known Platform Divergences

*Some platforms have no public publish API — these are documented divergences, not missing features.*

| UX Detail | Specification |
|-----------|---------------|
| **Xiaohongshu (intentional divergence)** | `xiaohongshu_publisher.py` returns `"not_implemented"` — the platform has no public API. Publishing is **manual-only** via the RED mobile app or web creator portal. Credentials are validated (cookie check) but no automated publish is attempted. Adding automated XHS publishing would require reverse-engineering private APIs, which is out of scope. |
| **IM notifications** | Not in AutoMedia scope. Agent-to-human IM conversation (e.g., agent asking "shall I publish?") is handled by the agent framework (OpenCode, Claude Code, etc.), not by AutoMedia. AutoMedia provides the tools; the agent communicates results to the human via the agent framework's own notification layer. Feishu/Discord webhook adapters are out of scope — they duplicate agent framework responsibility. |

#### F33 — Platform-Specific Formatting

*Each platform gets content in the format it expects — handled automatically by the adapter.*

| UX Detail | Specification |
|-----------|---------------|
| **Format handling** | Automatic per-platform conversion. Platform adapters handle format internally (HTML for WeChat, markdown for Zhihu, etc.). |
| **Human awareness** | Human doesn't need to know or care about format details. The system handles it. |
| **Format types by category** | `text-first` → HTML / rich text. `video-first` → video file + metadata. `image-first` → image + caption. `mixed-social` → text + optional media. `notification-only` → structured message payloads. |

#### F34 — Multi-Platform Routing

*Brand config binds to platforms; the system publishes to all bound platforms according to their automation levels. Mode determines what content is produced; platform adapters declare what they can consume.*

| UX Detail | Specification |
|-----------|---------------|
| **Binding** | Brand config declares which platforms it publishes to: `brands.my-brand.platforms: [wechat, zhihu, douyin, xiaohongshu]`. |
| **Mode determines production** | Pipeline mode (`auto`, `text_only`, `video_only`) determines what content is produced. The mode is the source of truth — platforms must adapt to what the mode produces, not the other way around. |
| **Platform capability matching** | ❌ Not implemented. The publish engine does not filter platforms by content-type compatibility with pipeline mode — only automation level (auto/review/manual) is checked. |
| | **Platform capability matrix** (reference — all registered adapters): |
| | | Platform | Content Type | Accepts From Mode | Actual Status | Priority |
| | |----------|-------------|-------------------|---------------|----------|
| | | WeChat Official Account | Long-form text + images | `auto`, `text_only` | ✅ Full implementation | P0 (done) |
| | | Zhihu | Long-form text | `auto`, `text_only` | ✅ Full implementation | P0 (done) |
| | | Xiaohongshu | Images + text, video | `auto` only (needs images) | ⚠️ Manual-only (no public API, intentional) | P1 (stub) |
| | | Douyin | Short video (9:16) | `auto`, `video_only` | ❌ Not implemented | P2 |
| | | Bilibili | Long video, text (column) | `auto`, `video_only` | ❌ Not implemented | P2 |
| | | Weibo | Short text + images, video | `auto`, `text_only`, `video_only` | ❌ Not implemented | P2 |
| | | Toutiao | Long-form text, images | `auto`, `text_only` | ❌ Not implemented | P3 |
| | | Baijiahao | Long-form text, video | `auto`, `text_only`, `video_only` | ❌ Not implemented | P3 |
| | | Kuaishou | Short video | `auto`, `video_only` | ❌ Not implemented | P3 |
| | | YouTube | Long video (16:9) | `auto`, `video_only` | ✅ Full implementation | P0 (done) |
| | | Twitter/X | Short text + media | `auto`, `text_only`, `video_only` | ✅ Full implementation | P0 (done) |
| | | Reddit | Text, link, images | `auto`, `text_only` | ✅ Full implementation | P0 (done) |
| | | TikTok | Short video (9:16) | `auto`, `video_only` | ✅ Full implementation | P0 (done) |
| | | Facebook | Text + images, video | `auto`, `text_only`, `video_only` | ✅ Full implementation | P0 (done) |
| | | Instagram | Images, video, Reels | `auto` only (needs images) | ✅ Full implementation | P0 (done) |
| | | LinkedIn | Text, images, documents | `auto`, `text_only` | ✅ Full implementation | P0 (done) |
| | | Medium | Long-form text | `text_only` | ✅ Full implementation | P0 (done) |
| | | WordPress | Blog posts | `auto`, `text_only` | ✅ Full implementation | P0 (done) |
| | | Juejin | Tech articles (Markdown) | `text_only` | ⚠️ Manual-only stub (no public API) | P1 (stub) |
| **Publish execution** | After pipeline completes: for each platform, respect its automation level. Auto → publish now. Review → create draft. Manual → skip. |
| **Per-platform adaptation** | Same core content, adapted per platform (title tweaks, format changes, CTA adjustment). Brand config can specify per-platform overrides. |
| **Implementation status** | ✅ Complete — all 19 platform adapters exist. WeChat ✅ full, Zhihu ✅ full, YouTube ✅ full, Twitter/X ✅ full, Reddit ✅ full, TikTok ✅ full, Facebook ✅ full, Instagram ✅ full, LinkedIn ✅ full, Medium ✅ full, WordPress ✅ full, Xiaohongshu ⚠️ manual-only stub, Douyin ⚠️ manual-only stub, Bilibili ⚠️ manual-only stub, Weibo ⚠️ manual-only stub, Toutiao ⚠️ manual-only stub, Baijiahao ⚠️ manual-only stub, Kuaishou ⚠️ manual-only stub, Juejin ⚠️ manual-only stub. 11 real API integrations + 8 intentional manual-only stubs (documented divergences, no API available). |
| **Partial failure** | One platform failure doesn't block others. Skipped/failed platforms reported in summary. |

#### F35 — Publish Error Handling

*When a platform publish fails, PublishEngine handles retry internally; agent sees the final result.*

| UX Detail | Specification |
|-----------|---------------|
| **Retry ownership** | Retry logic lives in `PublishEngine._publish_with_retry()`, not in the external agent. The engine classifies errors and retries transparently before returning a result to the agent. |
| **Error classification** | Three retryable categories: `credential_expired` → triggers automatic credential refresh (via `accounts/auth`) then retry; `rate_limited` → exponential backoff retry (2ⁿ seconds, up to 3 attempts); `network_error` → retry (up to 2 attempts). Non-retryable errors (`content_rejected`, `unknown`) are returned immediately. |
| **Credential refresh** | If an adapter returns `credential_expired`, the engine calls the configured refresh function (e.g., `RefreshCookieAuth`, `RefreshOAuth2Token`). If refresh succeeds → retry. If refresh fails → return `credential_refresh_failed` to agent. |
| **Platform isolation** | A failing platform does not block other platforms. Each platform's publish runs independently with its own retry budget. |
| **Agent sees** | Structured result per platform: `{platform: "zhihu", status: "published"}` or `{platform: "zhihu", status: "failed", error_code: "credential_expired", retryable: true, action: "reconnect_account"}`. Agent does not implement retry logic — it receives the final result after engine-level retries are exhausted. |
| **Human escalation** | Summary includes: `❌ Zhihu: 发布失败 (cookie 过期，自动刷新失败)。请重新连接账号。` |
| **Implementation status** | ✅ Full implementation. `_publish_with_retry` with credential refresh, exponential backoff, error classification. Platform isolation guaranteed. Structured error responses with agent-friendly format. |

### 3.6 Phase 6: Repeat

> "I produce content at scale, predictably. The agent handles execution; I give direction."

**Design principle**: Human gives the topic list (what to produce). Agent decides execution (how and when). Failures are handled by type: gate/content failures → skip and continue, system errors → stop.

#### F36 — Batch Production

*Multiple topics, one batch, sequential execution with per-topic reporting.*

| UX Detail | Specification |
|-----------|---------------|
| **Human: specify list** | Human provides a list of topics: `automedia run --topics "t1, t2, t3"` or via agent conversation: "帮我产这三篇：AI工具对比、Python入门、2026趋势" → agent calls `run_pipeline` per topic. |
| **Agent: execute batch** | Agent iterates over the topic list, calling `run_pipeline(topic=t_i)` for each. Runs are sequential within a batch unless parallel capacity is available (see F39). |
| **Agent: batch with pool** | Alternative: human says "产 3 篇科技类" → agent calls `list_topic_pool(status="pending", category="tech", limit=3)` → iterates over results. |
| **Failure handling** | Gate/content failure → log and continue to next topic. System error (crash, network) → stop batch and report. |
| **Batch report** | After batch completes, agent presents summary: `✅ 3/5 completed — 2 failed (G1 gate)。失败详情：[...]。` |
| **Partial output saved** | Each topic's output is saved regardless of batch status. Failed topics have partial output available for inspection. |
| **Implementation status** | ✅ Documented orchestration pattern. Batch is caller-driven (CLI loop, agent loop, cron trigger). Each topic is a separate `run_pipeline` call. Per-topic reporting with continue-on-failure semantics. Pool-based batch via `list_topic_pool(limit=N)`. |
| **No batch pipeline** | Batch is an orchestration pattern, not a new pipeline mode. `run_pipeline` always handles one topic. Batching is done by the caller (CLI loop, agent loop, cron trigger). |

#### F37 — Scheduled Production

*Cron-driven content production with fully configurable scheduling.*

| UX Detail | Specification |
|-----------|---------------|
| **Scheduling mechanism** | External crond calls `automedia cron run` at configured intervals. AutoMedia itself has no built-in scheduler. |
| **Config source** | Two ways: (1) `config.yaml` defines cron expressions and rules. (2) CLI/MCP tools for dynamic management (add/list/remove schedules). |
| **Config format** | `cron.schedules: [{name: "daily-tech", expression: "0 9 * * *", brand: "my-brand", category: "tech", count: 1}]` |
| **Fully configurable cadence** | Daily, weekly, multi-per-day, specific weekdays — any valid cron expression. Number of topics per trigger configurable. |
| **Topic selection on trigger** | On each cron trigger: reads config → calls `select_topic` with configured filters/category → `run_pipeline`. Selection logic is user-customizable (scoring, category balance, history). |
| **Agent involvement** | Agent can manage scheduling via MCP tools: "schedule daily tech production at 9am" → agent calls tool to add cron entry. |
| **Agent: verify cron health** | `get_cron_health()` tool returns cron daemon status, last trigger time, next scheduled trigger, missed triggers count. Agent can proactively report: "Cron is healthy. Next trigger: tomorrow 9:00 AM for daily-tech." |
| **Agent: test schedule** | `test_cron_schedule(expression="0 9 * * *")` tool returns the next N trigger times, validates cron expression syntax. Agent can confirm before setting up a schedule. |
| **Implementation status** | ✅ All 5 cron MCP tools implemented: `add_cron_schedule`, `list_cron_schedules`, `remove_cron_schedule`, `get_cron_health`, `test_cron_schedule`. External crond triggers `automedia cron run`. |
| **Human monitoring** | `automedia cron list` to see past runs. Agent uses `get_cron_health` (when implemented) to report proactively. |

#### F38 — Customizable Topic Pipeline

*How topics are generated, scored, selected, and routed — all user-customizable.*

| UX Detail | Specification |
|-----------|---------------|
| **Topic generation** | `research_topics` is the built-in method. Users can customize: provide their own topic sources, RSS feeds, webhook integrations, or manual entry. |
| **Topic scoring** | Built-in scoring (trending, freshness, category fit). Users can customize scoring weights and add custom scoring rules via the override system (`~/.automedia/overrides/rules/`). |
| **Selection logic** | `select_topic` uses the configured strategy (score-based, category-rotation, hybrid). Strategy is configurable via YAML rules — users cannot add new Python gate classes via overrides. Customization scope: YAML config + Jinja2 prompt overrides only, no custom code injection. |
| **Customization scope** | All three stages (generate → score → select) are customizable independently via config. Defaults work out of the box; customization is progressive. |
| **Agent: custom flow** | Agent can be told "use my custom topic generator" or "apply scoring rules from brand X" — respects the config. |

#### F39 — Run Isolation

*Each pipeline run is fully isolated — failures don't cascade.*

| UX Detail | Specification |
|-----------|---------------|
| **Project isolation** | ✅ Already implemented. Each run gets its own directory (`{YYYYMMDD}_{topic}/`). Independent config, assets, and pipeline_md5.json. |
| **Queue isolation** | One topic failure in a batch does not block remaining topics. Failed topic is logged; batch continues. |
| **Parallel execution** | Multiple pipelines can run concurrently without interference. Each has independent project directory, log file, and process. |
| **Resource contention** | Parallel runs share system resources (LLM API, FFmpeg, disk I/O). Contention is acceptable but should not cause corruption — queuing or rate-limiting is a future optimization. |
| **Isolation model** | Shared-nothing design. No cross-project state. Each project's `pipeline_md5.json` tracks its own integrity independently. |

### 3.7 Phase 7: Monitor

> "I can see what's been produced and how the system is doing — proactively and on demand."

**Design principle**: The agent proactively reports production status (periodic summary) and answers ad-hoc queries on demand. Human never needs to browse directories directly.

#### F40 — Project Overview

*List all projects with status — agent presents proactively or on demand.*

| UX Detail | Specification |
|-----------|---------------|
| **Proactive reporting** | Agent periodically summarizes: "本周已产 5 篇，3 篇已发布，2 篇待审。" Triggered by configurable cadence (daily/weekly) or after batch completion. |
| **On-demand query** | Human asks: "最近产了什么？" → Agent calls `list_projects(base_dir, status="all")` → summarizes results by status. |
| **Human CLI** | `automedia projects list` with `--status` filter. Shows: project date, topic, brand, mode, status, gate count pass/fail, publish status. |
| **Agent CLI equivalent** | `list_projects(status="published", limit=10)` — returns structured data for agent to format. |
| **Status categories** | `running`, `completed`, `partial` (some gates failed), `failed`, `published`, `archived`. |
| **Summary depth** | By default: high-level by status group. On request: full detail with per-project gate results. |

#### F41 — Asset Inspection

*See what files a specific project produced.*

| UX Detail | Specification |
|-----------|---------------|
| **Human query** | "AI工具对比那篇产出了什么文件？" → Agent calls `get_project_assets(project_dir)` → summarizes: "文章 (01_content/draft.md)，配图 3 张 (02_images/)，视频 1 个 (03_video/output.mp4)。" |
| **Human CLI** | `automedia projects assets <project-id>` — lists all files with sizes and types. |
| **Agent tool** | `get_project_assets(project_dir)` — returns `[{path, type, size_bytes, modified_at}]`. Agent can filter by type (e.g., only videos). |
| **Content preview** | Agent can read and summarize content on request: "给我看看文章摘要" → agent reads `draft.md` and extracts key points. |

#### F42 — Config Introspection & Asset Library Search

*Agents can discover system configuration and search across all produced content.*

| UX Detail | Specification |
|-----------|---------------|
| **Config introspection** | `get_config(key="")` tool returns merged configuration (secrets redacted). Dot-notation key lookup for any setting. |
| **Brand discovery** | `list_brands()` tool returns all configured brands with full profile metadata. Agent selects brand autonomously. |
| **Config implementation status** | ✅ `get_config` and `list_brands` both implemented. |
| **Search scope** | All produced articles, drafts, metadata. Future: images, videos. |
| **Search capabilities** | Full-text (exact + fuzzy), metadata filters (brand, platform, date, status, category), semantic / vector search. |
| **Agent: search assets** | Agent can query: `search_assets(query="AI 视频工具", brand="my-brand", limit=5)` → returns ranked results with relevance scores. |
| **Human: search assets** | "帮我找去年写的关于 AI 工具的文章" → Agent handles the search, no directory browsing needed. |
| **Search implementation status** | ✅ **Implemented.** `search_assets(query, brand, limit, filters)` MCP tool — keyword + semantic search via SQLite + Chroma. |
| **Config implementation note** | ✅ Config introspection and brand discovery are implemented. |

#### F43 — Pipeline Integrity Verification

*Each project's output integrity is verifiable via checksums.*

| UX Detail | Specification |
|-----------|---------------|
| **Automatic verification** | After each pipeline run, `pipeline_md5.json` is generated with checksums of all output files. Validation runs automatically on completion. |
| **Manual verification** | `automedia projects verify <project-id>` or MCP equivalent — re-checksums all files against stored values. |
| **Verification result** | `✅ 完整性验证通过 (12/12 文件匹配)` or `❌ 3 个文件被修改或丢失: [01_content/draft.md, 03_video/output.mp4]` |
| **Agent action on failure** | If integrity check fails, agent reports: "项目 X 的完整性检查失败 — 3 个文件已被修改。建议重新运行或从备份恢复。" |
| **Cross-project integrity** | Not applicable — each project has its own `pipeline_md5.json`. No cross-project verification. |

### 3.8 Phase 8: Iterate

> "I can improve the system without breaking existing behavior."

**Design principle**: All eight phases' expectations converge on one property: the system must be safely extensible. New gates don't break old ones. Brand changes are isolated. Old projects remain readable.

#### F44 — Gate Isolation

*Adding or modifying a gate does not affect other gates.*

| UX Detail | Specification |
|-----------|---------------|
| **Current status** | ✅ Already designed. Gates are independent `BaseGate` subclasses with auto-registration via `__init_subclass__`. Each gate operates on its own slice of the pipeline context. |
| **Isolation guarantee** | A gate reads from pipeline context and writes its results back. It never modifies another gate's state. Adding a new gate = new file + add to gate list in `runner.py`. No changes to existing gates. |
| **Failure isolation** | One gate's failure does not crash other gates. Gate execution is sequential with error boundaries per gate. |

#### F45 — Brand Isolation

*Changing one brand's configuration does not affect other brands.*

| UX Detail | Specification |
|-----------|---------------|
| **Current status** | ✅ Already designed with multi-brand config. Each brand profile has its own `brand_name`, `industry`, `tone`, `CTA_rules`, `banned_words`. |
| **Isolation guarantee** | Brands are stored as separate entries in `brand_profile.yaml`. Pipeline runs load only the selected brand's config. Changes to brand A do not affect brand B. |
| **Cross-brand content** | Content produced for one brand is not reused for another brand unless explicitly configured. Brand voice, CTA, and platform routing are per-brand. |

#### F46 — Override System

*Custom rules and prompt overrides without modifying core code.*

| UX Detail | Specification |
|-----------|---------------|
| **Current status** | ✅ Already implemented. 6-layer config hierarchy (built-in → project → user → overrides/rules → overrides/prompts → env vars). |
| **Override types** | Rule overrides (`~/.automedia/overrides/rules/*.yaml`) for config values. Prompt overrides (`~/.automedia/overrides/prompts/*.j2`) for LLM prompt templates. |
| **Safety** | Overrides are additive. Removing an override file restores default behavior. No permanent changes to system code. |
| **Override for iteration** | User can test new gate logic, change scoring rules, or adjust prompts without touching `src/automedia/`. |

#### F47 — Regression Testing

*Tests catch regressions when code changes.*

| UX Detail | Specification |
|-----------|---------------|
| **Current status** | ✅ 2,955 test functions across 145 files. CI runs on every push. |
| **Test coverage** | Unit tests per gate, integration tests for pipeline, CLI tests, MCP tests, red line enforcement tests, E2E tests. |
| **Adding new gates** | Each new gate must include tests. The `add-new-gate` skill enforces test creation. |
| **Pre-commit hooks** | Ruff, mypy, and pre-commit checks run before every commit. |

#### F48 — Forward Compatibility

*Old projects remain readable with new code.*

| UX Detail | Specification |
|-----------|---------------|
| **Scope** | **v1: Readable** — new code can read old project directories, parse `pipeline_md5.json`, access output files. Re-runnability (v2) and auto-migration (v3) are aspirational goals without concrete plans. |
| **Readability guarantee** | The project directory structure (`01_content/`, `02_images/`, etc.) and metadata files (`00_project_info.json`, `pipeline_md5.json`) are stable schemas. New versions must maintain backward compat. |
| **Breaking changes** | If a structural change is necessary, there must be: (1) a deprecation period where both old and new formats are supported, and (2) a migration tool. |
| **Implementation status** | ✅ Readability guarantee (v1) designed into project directory structure and metadata schema. Re-runnability and auto-migration are not planned for v1 MVP. |
| **Agent behavior** | Agent opening an old project with new code should be able to report: "This project was produced with v0.4.2. Content is accessible." |

---

### 3.9 Phase 9: Customize — Platform-Aware Workflow

> "I can customize prompts, media specs, gate composition, and scheduling per platform — without touching code. Defaults ship with sensible per-platform differentiation."

**Design principle**: The system ships with working defaults for every supported platform. But direct-users (agents) and director-users (humans) can override any aspect of a platform's workflow through a layered customization system. Customization is progressive: change one prompt, or define a completely new workflow.

**Current gap**: The pipeline has one set of prompts, one gate composition per mode, and one cron schedule for all platforms. Six specific gaps (G1–G6) exist, addressed by five implementation phases (P1–P5). The "director" preset in `hitl/config.py` validates this architecture.

#### F49 — Prompt Platform Routing

*Gate prompts (CW, G0, G1, G2, etc.) are platform-aware — each platform can have its own prompt template.*

| UX Detail | Specification |
|-----------|---------------|
| **Current state** | ❌ **Gap 1: Prompt has no platform routing.** The override system (`~/.automedia/overrides/prompts/`) supports brand-scoped `*.j2` overrides, but gates like CW, G0, G1, G2 all load a single prompt template (`content_writer.j2`, `fact_check_g0.j2`, etc.) regardless of target platform. All platforms use the same prompt. |
| **Where the gap lives** | `automedia/gates/content_writer.py` line 156: `load_prompt("content_writer")` — no `platform` parameter. The CW gate reads `gate_context.get("mode")` for mode awareness (lines 165–191) but never reads a platform field. Other gates have the same blind spot. |
| **What exists** | ✅ `automedia/core/overrides.py` `OverridesLoader.load_prompts(brand=None)` supports brand-scoped directories (`prompts/<brand>/*.j2`) and global (`prompts/*.j2`). The infrastructure for hierarchical prompt resolution exists. |
| **What's missing** | Platform-scoped prompt routing: `prompts/<platform>/*.j2` (e.g., `prompts/wechat/content_writer.j2`, `prompts/zhihu/content_writer.j2`), platform-dependent fallback chain (`platform > brand > global > built-in`), and gate-level `load_prompt(name, platform="...")` API. |
| **Default behavior** | Ship platform-agnostic defaults that work for all text platforms. The default `content_writer.j2` produces a generic long-form article. |
| **Customization scope** | Per-platform override files. User creates `~/.automedia/overrides/prompts/wechat/content_writer.j2` → CW gate auto-detects platform context → loads the platform-specific template. No code changes. |
| **Agent workflow** | Agent configures "write WeChat articles with a more casual tone" → creates platform-scoped prompt override → subsequent `run_pipeline(brand="my-brand")` with WeChat in the platform list automatically uses the overridden prompt. |
| **Per-platform differentiation** | WeChat → longer, more formal, WeChat-format HTML. Xiaohongshu → shorter, visual-first, image-heavy narrative. Zhihu → technical deep-dive, citation-heavy. Twitter → thread format with 280-char-aware segmentation. Douyin → conversational, hook-first, short-form narration. Each platform variant is a separate `*.j2` file. |
| **Implementation phase** | **Phase 1 (P1)** — extend `OverridesLoader.load_prompts()` with platform resolution; add `platform` parameter to `load_prompt()` API; update CW, G0, G1, G2 gates to pass `gate_context.get("platforms", [])`; ship per-platform default prompts for the 6 most-used platforms. |

#### F50 — Media Spec Mapping

*Image/video dimensions and format requirements are declared per-platform in config, not hardcoded.*

| UX Detail | Specification |
|-----------|---------------|
| **Current state** | ❌ **Gap 2: Image/video specs are hardcoded or in process-level placeholders.** Width/height placeholders exist but there is no centralized `platform → dimensions` mapping table. Each video gate and image pipeline reads dimensions from scattered configuration. |
| **Where the gap lives** | `automedia/pipelines/image_pipeline.py` and `video_pipeline.py` consume `config` dicts with width/height that come from caller-provided overrides or defaults.yaml. Platform-specific media requirements (e.g., XHS 1:1 images vs WeChat 16:9 cover) are not mapped anywhere. |
| **What exists** | ✅ `automedia/manifests/defaults.yaml` has `engines.image.comfyui` and `engines.video.hyperframes` config sections. Pipeline-level width/height can be passed as overrides. Platform-specific specs are absent. |
| **What's missing** | A platform media-spec manifest: `platforms.<platform>.media.image.width`, `platforms.<platform>.media.image.aspect_ratio`, `platforms.<platform>.media.video.max_duration_s`, `platforms.<platform>.media.video.resolution`. A lookup function `get_platform_media_spec(platform) -> dict`. |
| **Default behavior** | Ship a reference table of all 19 platforms' known media requirements as built-in defaults. E.g., WeChat cover: 900×383 (16:9), Xiaohongshu note: 1:1 or 3:4, Douyin video: 9:16 1080×1920, YouTube video: 16:9 1920×1080. |
| **Customization scope** | Per-brand override: `brands.my-brand.platforms.wechat.media.image.width: 1200`. Platform-level defaults serve as the base layer; brand-level overrides apply on top. |
| **Agent workflow** | Agent configures a new platform: "add YouTube with 4K video output" → sets `platforms.youtube.media.video.resolution: 3840x2160` in brand config. Pipeline generates appropriately sized output. |
| **Implementation phase** | **Phase 1 (P1)** — define `PlatformMediaSpec` model in `automedia/core/`; add `get_platform_media_spec(platform, brand_config) -> dict` resolver; populate `defaults.yaml` with all platforms' media specs; update image/video pipelines to consume specs from resolver instead of hardcoded values. |

#### F51 — Per-Platform Gate Composition

*Gate composition can vary per platform — add WeChat-specific checks, skip video gates for XHS text-only mode.*

| UX Detail | Specification |
|-----------|---------------|
| **Current state** | ❌ **Gap 3: Gate composition is global per mode.** 8 modes (`_MODE_MAP` in `runner.py`) define global gate lists. All platforms sharing the same mode run the exact same gate sequence. There is no mechanism to add/remove/modify gates per platform. |
| **Where the gap lives** | `automedia/pipelines/runner.py` lines 57–195: `_AUTO_GATE_NAMES`, `_TEXT_ONLY_GATE_NAMES`, etc. are static lists. `GateEngine` in `gate_engine.py` executes whatever gate list it receives. The gate list is built from mode alone — no platform influence. |
| **What exists** | ✅ The 8-mode system + `_derive_mode_from_platforms()` (line 215) which maps platform categories to modes. Mode is platform-influenced at a coarse level (text-first → `text_only`, mixed-social → `auto`), but individual gate selection is not. |
| **What's missing** | Platform-level gate modifiers: `platforms.<platform>.gates.include: ["G6"]` (add a custom gate for this platform only), `platforms.<platform>.gates.exclude: ["V3"]` (skip a gate for this platform), `platforms.<platform>.gates.override_failure_mode: {"G1": "stop"}` (change failure behavior per-platform). |
| **Default behavior** | Mode's standard gate list is the base. If no platform modifiers exist, behavior is identical to today. Platform modifiers are purely additive/restrictive — they cannot create entirely new modes (that requires a new mode entry). |
| **Customization scope** | Per-platform in brand config or override rules. `brands.my-brand.platforms.wechat.gates.exclude: [V0, V1, V2]` — skip video gates for a text-only platform. This is YAML-level customization, not Python. |
| **Agent workflow** | Human: "微信的内容不用跑视频门" → Agent adds platform gate override. Next WeChat pipeline run skips video gates, reducing processing time. Agent can introspect effective gate list via `get_pipeline_progress`. |
| **Design constraints** | Platform gate modifiers must be validated: (1) cannot exclude gates that produce required artifacts for downstream gates, (2) cannot include a gate that doesn't exist, (3) CW cannot be excluded if content generation is needed, (4) lifecycle gates (L1–L4) are always required. |
| **Implementation phase** | **Phase 2 (P2)** — define gate modifier schema in config; add `_apply_platform_gate_modifiers(base_gates, platform_config) -> list[str]` in `runner.py`; integrate into gate list building pipeline; add validation for constraint rules; expose effective gate list via `get_pipeline_progress` metadata. |

#### F52 — Override System Discoverability

*All customizable prompts, rules, and variables are discoverable — documented naming conventions, schema reference, and an MCP tool to list them.*

| UX Detail | Specification |
|-----------|---------------|
| **Current state** | ❌ **Gap 4: Override system is undocumented and undiscoverable.** F46 acknowledges the override system exists and AGENTS.md mentions it in one line. But there is no documentation of: available overrideable prompt template names, their expected Jinja2 variables, rule YAML schema, file naming conventions, or how the resolution order works. |
| **What exists** | ✅ `automedia/core/overrides.py` implements `OverridesLoader` with `load_rules(brand)` and `load_prompts(brand)` methods. The file system layout (`rules/*.yaml`, `prompts/*.j2`, `prompts/<brand>/*.j2`) works. F46 describes the 6-layer config hierarchy. |
| **What's missing** | (1) A `list_overridable()` tool or documented reference listing every prompt template name (`content_writer`, `fact_check_g0`, `humanizer_g1`, `brand_strategy`, etc.), their expected input variables, and example usage. (2) Rule YAML schema documentation with all supported keys (currently inferred from `overrides.py` code at line 121–139 where `brand` key filtering is shown). (3) Naming conventions for files. (4) Jinja2 variable reference per template. (5) An MCP tool to enumerate current overrides. |
| **Default behavior** | No overrides = use built-in defaults. Discoverability is about documentation, not runtime. Ship a "Override System Reference" doc page. |
| **Customization scope** | Users can create `rules/*.yaml` for config overrides (gate thresholds, scoring weights, etc.) and `prompts/*.j2` for LLM prompt customization. Platform-scoped prompts (F49) extend this with `prompts/<platform>/*.j2`. Brand-scoped prompts already work (`prompts/<brand>/*.j2`). |
| **Agent workflow** | Agent: "what can I customize?" → calls new `list_overridable_templates()` MCP tool → returns `[{name: "content_writer", variables: ["topic", "brand", "platform"], file: "overrides/prompts/content_writer.j2"}]`. Agent can then create or modify overrides via file operations. |
| **Implementation phase** | **Phase 2 (P2)** — document all overrideable templates with their variables in `docs/dev/override-reference.md`; create `list_overridable_templates()` MCP tool; document rule YAML schema; add Jinja2 variable reference comments to every `.j2` file header. |

#### F53 — Platform-Aware Cron Scheduling

*Scheduled jobs can target specific platforms — "daily tech article published to WeChat and Zhihu" is a single schedule entry.*

| UX Detail | Specification |
|-----------|---------------|
| **Current state** | ❌ **Gap 5: Cron scheduling has no platform awareness.** `add_cron_schedule(name, expression, brand, category, count)` supports `brand` and `category` filters but has no `platform` or `mode` parameter. A schedule entry triggers `select_topic` + `run_pipeline` with the brand's full platform list — you cannot schedule "daily WeChat-only" vs "daily Zhihu-only" separately. |
| **Where the gap lives** | `automedia/mcp/tools.py` line 827: `add_cron_schedule` signature has `brand`, `category`, `count` but no `platform` or `mode`. The cron runner consumes the schedule's brand and runs the brand's full config. |
| **What exists** | ✅ F37: all 5 cron MCP tools exist (add/list/remove/get_health/test). `add_cron_schedule` already has `brand` and `category` parameters. The external crond + `automedia cron run` pipeline works end-to-end. |
| **What's missing** | `platform` parameter in `add_cron_schedule` to restrict which platforms a scheduled run publishes to. `mode` parameter to override pipeline mode per schedule. Optional: `mode` override to decouple from brand's default. Optional: `gate_overrides` for platform-specific gate composition in scheduled runs. |
| **Default behavior** | No platform filter → publish to all brand-configured platforms (current behavior). Backward compatible: existing schedules with no `platform` field continue to publish to all platforms. |
| **Customization scope** | Per-schedule `platform` list: `add_cron_schedule(name="daily-wechat-tech", expression="0 9 * * *", brand="my-brand", platform=["wechat"])`. Per-schedule `mode` override: `mode="text_only"` for text-only cron jobs. |
| **Agent workflow** | Human: "每天上午9点产一篇科技文章只发微信" → Agent calls `add_cron_schedule(name="daily-wechat-tech", expression="0 9 * * *", brand="my-brand", platform=["wechat"])`. Cron runs at 9 AM → selects topic → runs pipeline → publishes to WeChat only. |
| **Implementation phase** | **Phase 3 (P3)** — add `platform: list[str]` and `mode: str` optional parameters to `add_cron_schedule`; extend schedule YAML schema; update cron runner to filter platforms and override mode when these are set; update `list_cron_schedules` and `test_cron_schedule` to display the new fields. |

#### F54 — Declarative Workflows

*A "workflow" is a named, composable pipeline recipe defined in YAML — platform bindings, gate list, prompt overrides, media specs, and scheduling all in one file.*

| UX Detail | Specification |
|-----------|---------------|
| **Current state** | ❌ **Gap 6: No "workflow" concept exists.** Everything is implicit in Python code. Pipeline behavior is determined by: mode + brand config + platform list + global defaults. There is no single declarative artifact that says "here is a complete recipe for producing WeChat articles." Users must understand `runner.py`, `_MODE_MAP`, gate names, config hierarchy, and override file layout to customize anything. |
| **What exists** | ✅ Building blocks exist: 8 modes, 20 gates, 6-layer config, override system, cron scheduling, platform adapters. What's missing is the glue that binds them into named, reusable workflows. |
| **What's missing** | A `workflows.yaml` file (in project `.automedia/` or user `~/.automedia/`) defining named workflows. Each workflow specifies: `mode`, `platform` binding, `gates` (base + include/exclude), `prompt_overrides` (directory or inline), `media_spec_overrides`, and optional `schedule` (cron expression + count). |
| **Example workflow** | ```yaml<br>workflows:<br>  wechat-daily:<br>    mode: text_only<br>    platforms: [wechat]<br>    gates:<br>      base: text_only<br>      exclude: [G2]  # skip copy review for daily runs<br>    prompts:<br>      dir: overrides/prompts/wechat/<br>    media:<br>      image: {width: 900, height: 383, format: jpg}<br>    schedule:<br>      expression: "0 9 * * *"<br>      count: 1<br>``` |
| **Default behavior** | No `workflows.yaml` → system uses current behavior (mode-based gate lists, global prompts, brand platform list). Workflows are entirely opt-in. |
| **Customization scope** | Workflows can be brand-scoped (a brand field) or global. Workflow inheritance: `extends: wechat-daily` + override specific fields. Director-users define workflows once; direct-users (agents) select workflow by name. |
| **Agent workflow** | Human: "给我定义一个微信每日流程" → Agent defines `wechat-daily` workflow → Agent then calls `run_pipeline(topic="X", workflow="wechat-daily")` → pipeline executes the workflow's full recipe. |
| **MCP tool integration** | New `list_workflows()` tool returning all defined workflows. `run_pipeline` gains optional `workflow` parameter. When set, workflow config merges over (does not replace) brand config — workflow is a higher-priority layer in the 6+1 hierarchy. |
| **Implementation phase** | **Phase 4 (P4)** — design `Workflow` Pydantic model; implement `WorkflowLoader` (analogous to `OverridesLoader`); add workflow resolution in `runner.py` (merge workflow config on top of mode + brand before gate list building); add `list_workflows` MCP tool; update `run_pipeline` to accept `workflow` parameter. |

#### F55 — Implementation Roadmap

*Five-phase plan to close all six gaps, with acceptance criteria per phase.*

| Phase | Gaps Addressed | Deliverables | Acceptance Criteria |
|:------|:---------------|:-------------|:--------------------|
| **P1: Prompt & Media** | G1 (prompt routing), G2 (media specs) | Platform-scoped prompt resolution; `get_platform_media_spec()` resolver; per-platform default prompts for 6 most-used platforms; media spec table in `defaults.yaml` | ✅ Prompts vary by platform (`content_writer.j2` vs `content_writer_wechat.j2` produce different output); media specs queryable per platform |
| **P2: Discoverability & Gate Modifiers** | G3 (gate composition), G4 (override discoverability) | Platform gate include/exclude/override mechanic; `list_overridable_templates()` MCP tool; override system reference doc; gate modifier validation | ✅ Gates can be added/removed per platform with validated modifiers; all prompts, variables, and rules documented and tool-enumerable |
| **P3: Platform-Aware Scheduling** | G5 (cron platform routing) | `platform` and `mode` params on `add_cron_schedule`; schedule YAML schema extended; cron runner respects platform filter | ✅ Schedule `platform: [wechat]` publishes only to WeChat; existing schedules unchanged; mode override works independently |
| **P4: Declarative Workflows** | G6 (workflow concept) | `workflows.yaml` format definition; `WorkflowLoader` implementation; workflow→config merge in `runner.py`; `list_workflows` MCP tool; `run_pipeline(workflow="...")` parameter | ✅ YAML-defined workflow produces identical output to equivalent manual config; workflow overrides merge correctly with brand config; MCP tool lists all workflows |
| **P5: Director-User Mode** | All gaps — director preset validation | "Director" HITL preset (`hitl/config.py`) becomes the default for director-users; agent workflow: human says "帮我产一篇 AI 工具对比" → agent resolves topic + chooses workflow + schedules + publishes; agent reports summary in natural language without technical details | ✅ Director-user never sees gate names, mode strings, or platform codes; agent handles all mapping; human gives intent, system delivers output |

**Priority ranking**: P1 (prompt + media) is the highest-value gap — it directly impacts content quality differentiation between platforms. P2 (discoverability) is a prerequisite for any user to actually use the customization system. P3 (scheduling) and P4 (workflows) are power-user features. P5 (director mode) is the culmination that makes the whole system invisible to director-users.

**Integration with existing expectations**: F34 (multi-platform routing) defines which platforms a brand publishes to. F54 (workflows) defines *how* each platform is serviced. F49 (prompts) defines *what voice* each platform speaks in. F37 (scheduling) defines *when* each platform receives content. Together they form a complete platform lifecycle: bind → customize → compose → schedule → execute.

---

## 4. Core Value Propositions Assessment

Beyond individual expectations, there are **core value propositions** — the fundamental reasons this project exists. Each is evaluated holistically.

### 4.1 "Give a topic, get published content"

```
Promise:  I give a topic → AutoMedia writes, checks, produces video, and publishes
Reality:  I give a topic → AutoMedia writes and checks (text_only works)
          → But: video requires HyperFrames + ComfyUI (external dependencies)
          → But: Xiaohongshu is manual-only (no public API — intentional divergence)
           → So: The "full auto" promise is partially fulfilled
```

| Aspect | Status | Gap |
|--------|--------|-----|
| Topic → article | ✅ Works | — |
| Article → quality gates | ✅ Works | — |
| Quality gates → video | ⚠️ Partial | Video requires external deps (HyperFrames, Whisper, FFmpeg, Chrome) |
| Video → publish | ⚠️ Partial | WeChat ✅, Zhihu ✅, Xiaohongshu ⚠️ (manual only) |
| **End-to-end: topic → published** | ⚠️ **Partial** | Works for text to WeChat/Zhihu; video and Xiaohongshu have gaps |

### 4.2 "20 quality gates ensure quality"

```
Promise:  20 automated gates check every aspect of content quality
Reality:  20 gates exist. G0/G1/G2 use hybrid LLM-first + fallback; others are deterministic/regex
```

| Aspect | Status | Gap |
|--------|--------|-----|
| Fact checking (G0) | ✅ Works | Deterministic checks on structured data |
| AI-sound check (G1) | ✅ Works | Hybrid LLM-first + regex fallback detection |
| Copy review (G2) | ⚠️ Partial | Structure check, not semantic quality |
| Brand CTA (G3) | ✅ Works | Pattern matching on known terms |
| WeChat format (G4) | ✅ Works | Length/count checks |
| HTML lint (G5) | ✅ Works | Tag validation |
| Video lint (V0) | ⚠️ Partial | File existence, not content quality |
| Vision QA (V1) | ⚠️ Degrades | Falls back to pixel luminance on rate limit |
| Whisper transcribe (V2) | ✅ Works | Full transcription |
| Content semantic (V3) | ⚠️ Partial | Coverage check, not quality |
| TTS brand asset (V4) | ✅ Works | Voice consistency |
| MP3 vs SRT sync (V5) | ✅ Works | Timing alignment |
| Subtitle render (V6) | ✅ Works | Pixel-level check |
| Six-step hard (V7) | ⚠️ Partial | File existence + structure |
| **Overall: 20 gates exist, ~12 do meaningful validation** | ⚠️ | Some gates are structural checks, not quality assertions |

### 4.3 "AI Agent can operate the pipeline"

```
Promise:  AI coding agents (Claude Code, OpenCode, etc.) can run AutoMedia via MCP
Reality:  MCP server exists with 41 tools, but agent integration quality varies
```

| Aspect | Status | Gap |
|--------|--------|-----|
| MCP server starts | ✅ Works | — |
| Core pipeline tools | ✅ Works | select_topic, run_pipeline, get_progress |
| File tools | ✅ Works | list_projects, get_assets, archive |
| Omni tools | ✅ Works | extract, translate, convert |
| Account tools | ✅ Works | connect, list, health, disconnect |
| **Brand discovery** | ✅ **Resolved** | `list_brands` MCP tool gives agent visibility into configured brands with full profile metadata. |
| **Config introspection** | ✅ **Resolved** | `get_config(key="")` MCP tool returns merged config (secrets redacted). Dot-notation lookup for any key (`llm.text_generation.temperature`, `default_mode`, etc.). |
| **Asset search** | ✅ **Resolved** | `search_assets(query, brand, limit, filters)` MCP tool — keyword + semantic search via SQLite + Chroma. Agent can query produced content programmatically. |
| **IM notifications** | ✅ **Out of scope** | Agent-to-human IM conversation is agent framework's responsibility, not AutoMedia's. Feishu notifier removed in July 2026. |
| Error messages are agent-friendly | ✅ **Structured** | All MCP tools return consistent `{"error": "..."}` dicts. CLI shows gate-level errors with check name and suggestion; raw tracebacks only with `--verbose`. |
| Agent can self-correct on failure | ❓ Unknown | Not tested |

### 4.4 "Not a black box — HITL available"

```
Promise:  Human can review and approve at key checkpoints
Reality:  HITL framework integrated into pipeline gate execution
          H0 (human review gate) pauses pipeline with awaiting_hitl status
          GateEngine supports approve/reject lifecycle via CLI and MCP tools
          → HITL is operational in pipeline execution
```

| Aspect | Status | Gap |
|--------|--------|-----|
| HITL config exists | ✅ Works | Presets (automated/semi/skip) |
| HITL executor works | ✅ Works | Approve/skip nodes |
| HITL in pipeline gates | ✅ **Integrated** | H0 gate pauses pipeline with `awaiting_hitl` status; GateEngine HITL lifecycle (`on_gate_awaiting_hitl`, `approve_hitl`, `reject_hitl`); HITL config injected into gate context |
| **Promise fulfilled**: HITL framework integrated into pipeline execution | ✅ | H0 gate operational with CLI (`automedia hitl approve/reject`) and MCP support |

---

## 5. Founder's Priority Matrix

Not all expectations are equal. This matrix ranks all 55 expectations by **importance to the founder** and **current gap size**.

**Quadrant guide**: Top-right = highest priority (important but gappy). Bottom-left = already good (important and working).

### Priority Grid (55 Expectations)

| Quadrant | Importance | Gap | Expectations |
|----------|-----------|-----|--------------|
| **🔴 Immediate fix** | HIGH | HIGH | **F27** (video/subtitle degraded without HyperFrames) |
| **🟡 Important gap** | HIGH | MODERATE | **F01** (system deps vary per platform), **F08** (streaming works but not all errors structured), **F11** (topic→article works in text_only, auto varies with video deps), **F18** (no webhook push for progress), **F20** (auto-recovery exists but retry thresholds untuned), **F29** (3-level automation works for API platforms, manual-only for others), **F49** (prompt routing — override infra exists but gates don't read platform), **F50** (media specs — no platform→dimensions mapping), **F51** (gate composition — no per-platform gate modifiers), **F54** (declarative workflows — building blocks exist but no workflow YAML concept) |
| **🟢 Working well** | HIGH | LOW | **F02** (MCP/CLI both work), **F03** (init creates skeleton), **F04** (single env var), **F05** (brands with list_brands), **F06** (doctor + health_check), **F07** (8 modes, fully implemented), **F09** (structured errors throughout; tracebacks only on --verbose), **F10** (standard project layout), **F12** (source_path/url), **F16** (brand selection), **F17** (one-command run), **F19** (mostly structured errors), **F21** (resume works), **F24** (G1 hybrid LLM-first + regex fallback), **F25** (G0 LLM plausibility check without sources), **F26** (brand CTA pattern matching), **F28** (HITL integrated), **F30** (WeChat), **F31** (Zhihu), **F34** (all 19 platforms have adapters — 11 real API + 8 manual-only stubs), **F35** (PublishEngine retry), **F37** (cron MCP tools all implemented), **F42** (config introspection + asset search implemented), **F47** (2955 tests) |
| **⏸ Monitor** | MEDIUM | HIGH | None — medium-importance gaps are moderate at worst |
| **👀 Watch** | MEDIUM | MODERATE | **F37** (external crond dependency), **F52** (override discoverability — templates/rules undocumented, no MCP tool), **F53** (platform-aware cron — add_cron_schedule missing platform/mode params) |
| **✅ Acceptable** | MEDIUM | LOW | **F13** (Omni Triad), **F14** (topic pool), **F15** (trending), **F21** (resume), **F23** (output summary), **F32** (divergences documented), **F33** (formatting), **F36** (batch via orchestration), **F37** (cron MCP tools: add/list/remove/test/health), **F39** (isolation), **F40** (project overview), **F41** (asset inspection), **F42** (config introspection + asset search: get_config, list_brands, search_assets), **F43** (MD5 integrity), **F44** (gate isolation), **F45** (brand isolation) |
| **💤 Low priority** | LOW | LOW / MODERATE | **F22** (perf — no hard target), **F38** (no plugin system — by design), **F46** (override system — works for YAML/prompts), **F48** (v1 readable only — adequate), **F55** (implementation roadmap — meta-tracking item) |

### Immediate Action Items (top priorities)

| Priority | Item | Why | What's needed |
|----------|------|-----|---------------|
| 🔴 P0 | **F27**: Video without HyperFrames | Subtitle/V0-V7 gates degrade without external renderer | Improve fallback path or document minimum viable setup |

---

## 6. Acceptance Evaluation Model

### 6.1 Founder's Verdict

```python
@dataclass
class FounderVerdict:
    """Result of evaluating founder's expectations against the project."""
    passed: bool                           # ALL critical expectations pass

    journey_phase_results: dict[str, PhaseResult]  # per-phase results
    value_proposition_results: dict[str, ValueResult]  # per-value-prop results

    critical_passed: int                   # Critical expectations that pass
    critical_failed: int                   # Critical expectations that fail

    blocking_issues: list[str]             # Things that make the project
                                           # "not deliverable" for the founder
    summary: str                           # One-line verdict

@dataclass
class PhaseResult:
    phase: str                             # "setup", "input", "run", etc.
    expectations_pass: int
    expectations_fail: int
    expectations_untested: int

@dataclass
class ValueResult:
    proposition: str                       # "topic to published", "20 gates", etc.
    verdict: Literal["fulfilled", "partial", "broken"]
    gaps: list[str]
```

### 6.2 Example Verdicts

```
PASS — All 8 critical expectations pass, 36/55 total pass
       Value props: 1 fulfilled, 3 partial, 0 broken

FAIL — 2 critical expectations fail (old example, pre-F49):
       F11 (topic→article): G0 gate consistently fails on real LLM output
       F29 (one-command publish): Xiaohongshu manual-only (intentional divergence)
       Value props: 0 fulfilled, 3 partial, 0 broken

PARTIAL — 42/55 expectations pass, but:
          F24 (not AI-sounding): G1 catches only 6/9 AI patterns
          F27 (readable subtitles): V6 degrades without HyperFrames
          This is acceptable for v1 with known limitations
```

---

## 7. Current Reality Assessment

Based on the project audit (`docs/dev/project-audit.md`), documentation review, and codebase analysis, here is the honest assessment of the founder's expectations for a first-time end-to-end run:

### What works (end-to-end, `text_only` mode):

```
automedia init
→ .automedia/ created

export AUTOMEDIA_LLM_API_KEY="sk-..."

automedia run --topic "AI视频工具对比2026" --brand my-brand --mode text_only
→ Writes article
→ Runs G0-G5 quality gates
→ L1-L4 lifecycle gates
→ Produces 01_content/drafts/*.md
```

This flow works. It's the project's strongest path.

### What works (with additional setup):

| Flow | Extra Steps Needed | Reliability |
|------|-------------------|-------------|
| Video production | FFmpeg, Bun, edge-tts, Whisper, Chrome/Chromium | ⚠️ Many external deps |
| WeChat publish | WeChat API credentials, account setup in AutoMedia | ✅ When configured |
| Zhihu publish | Zhihu API credentials | ✅ When configured |
| MCP agent access | Python MCP server running | ✅ Works |
| Cron scheduling | External crond configuration | ✅ Works when set up |

### What doesn't work yet:

| Feature | Status | Impact |
|---------|--------|--------|
| Xiaohongshu publish | ⚠️ Manual only (intentional divergence — no public API) | Human must post through RED app/web portal |
| Full auto mode (topic→published) | ⚠️ Partial | Video deps + platform gaps break the chain |
| LLM-based quality gates | ⚠️ Partial | G0/G1/G2 use LLM-first with fallback; other gates are regex-based |
| Video without HyperFrames | ⚠️ Degraded | Subtitles check requires external renderer |
| Discord notifications | ⏭️ Out of scope (intentional divergence) | Not implemented — no request for this feature |

### What's been resolved since last assessment:

| Feature | Status | Details |
|---------|--------|---------|
| HITL in pipeline gates | ✅ Integrated | H0 gate pauses with `awaiting_hitl` status; GateEngine approve/reject lifecycle; CLI `automedia hitl approve/reject` |
| Pipeline recovery | ✅ Operational | GateEngine: exponential backoff retry (tenacity), `max_quality_retries` for quality feedback, HITL pause-and-wait |
| Source path input | ✅ Implemented | `source_path` (local file/directory) + `source_url` (URL fetch) in `run_pipeline` |
| Omni Triad processing | ✅ Implemented | OPP (extract), OL (localize), ORF (convert) — all with MCP tools |
| Trending topic discovery | ✅ Implemented | `research_topics` MCP tool with LLM + trending data |
| 8 pipeline modes | ✅ Implemented | auto, text_only, text_with_cover, video_only, qa_only, image-carousel, social-thread, short-video |
| Publish automation model | ✅ Implemented | Three levels (auto/review/manual) per platform with credential refresh |
| Brand→platform binding | ✅ Implemented | Brand config declares platforms; content type auto-derived |
| Publish error recovery | ✅ Implemented | Retry + credential refresh + platform isolation |
| Cron MCP tools | ✅ Implemented | `add_cron_schedule`, `list_cron_schedules`, `remove_cron_schedule`, `get_cron_health`, `test_cron_schedule` — full CRUD + health + validation |
| Config introspection | ✅ Implemented | `get_config` and `list_brands` MCP tools |
| **Asset search** | ✅ **Implemented** | `search_assets(query, brand, limit, filters)` MCP tool — keyword + semantic search via SQLite + Chroma. Exposes existing asset library capability. |
| F09 doc correction | ✅ Documented | F09 status corrected from "some errors still Python traces" to "structured errors throughout; tracebacks only on --verbose". Confirmed via `cli/output_format.py` implementation and MCP tools' consistent structured error dicts. |
| F34 doc correction | ✅ Resolved | Platform capability matrix updated to reflect actual status: 11 real API adapters (WeChat, Zhihu, YouTube, Twitter/X, Reddit, TikTok, Facebook, Instagram, LinkedIn, Medium, WordPress) + 8 manual-only stubs. Platform capability matching (mode-based filtering) documented as ❌ not implemented — actually does not exist in publish engine. |

---

## 8. Evolution: From Vibe-Coded to Intention-Matched

The project was vibe-coded — built fast, iterated often. That's fine for the build phase. D3 is the **intention-matching** phase: bringing the project in line with the founder's actual expectations.

### 8.1 The Gap Analysis Process

```
For each expectation in the catalog:

  1. Define: What does "done" look like for this expectation?
     → "F11: I run one command and get a draft.md that is factually correct
          and on-brand."

  2. Test: Does the current system deliver this?
     → Run it. Not in tests — actually run the command. Look at the output.
     → Answer honestly: "yes", "mostly", "no".

  3. If no: What's the smallest change that would flip it to "yes"?
     → Write the fix as a single todo item.

  4. Lock: Write a test (D2 behavioral test) that asserts this behavior.
     → Now it's enforced.
```

### 8.2 Milestone Definition

| Milestone | Definition | Expectations Met |
|-----------|-----------|-----------------|
| **v1 MVP** | Text-only pipeline works: topic → article → quality gates | F01-F11, F17-F20, F23-F26, F40-F41, F44-F45, F47 |
| **v1 Full** | Auto mode works: topic → article → video → lifecycle | +F12, F21-F22, F27, F43 |
| **v1 Publish** | Multi-platform publish: WeChat + Zhihu + key global platforms | +F29-F35 (excluding F32 — known divergences), F46 |
| **v1 Scale** | Batch, cron, topic pool, asset library, scheduling | +F13-F16, F36-F39, F42, F48 |
| **v1 Mature** | HITL in pipeline, config introspection, search_assets, True Test pass | +F28, F42 (config introspection + search_assets MCP tools) |

### 8.3 The True Test

The ultimate acceptance criterion for D3:

> **The founder can go from idea to published content in one sitting,
> without reading documentation, without debugging errors, and with
> confidence that the output is good enough to publish.**

This is the standard. Everything else — tests, gates, architectures — is in service of this.

#### Agent-Verifiable True Test Checklist

An AI agent can evaluate the True Test by running each criterion and reporting PASS/FAIL:

| # | Criterion | How Agent Verifies | PASS | FAIL |
|---|-----------|-------------------|------|------|
| T1 | Fresh environment: `automedia init` completes | Run `automedia init` in empty dir → exits 0, creates `.automedia/` | ✅ | ❌ |
| T2 | Key configured: pipeline starts without auth errors | Run `python -m automedia.mcp.server` + `run_pipeline` → no key error | ✅ | ❌ |
| T3 | Topic → article: one command produces `draft.md` | `automedia run --topic "Test" --brand X --mode text_only` → `01_content/drafts/draft.md` exists | ✅ | ❌ |
| T4 | Gates pass: quality gates run and complete | Check `get_pipeline_status` → gates_log shows G0-G5 + L1-L4 with non-error status | ✅ | ❌ |
| T5 | Errors are human-readable: gate failures show clear reason | Trigger a known failure → check stderr/output contains gate name, check name, and suggestion (not Python traceback) | ✅ | ❌ |
| T6 | Resume works: re-run from failed gate without losing work | Fail a pipeline → resume → gates before the failure show "passed", failed gate re-runs | ✅ | ❌ |
| T7 | Agent can operate via MCP: all pipeline steps available as tools | Call `health_check` → list all tools → at minimum `run_pipeline`, `get_pipeline_progress`, `get_pipeline_status`, `list_projects`, `get_project_assets` exist | ✅ | ❌ |
| T8 | Agent can discover: brands and config are introspectable | Call `list_brands` → returns at least 1 brand. Call `get_config(key="")` → returns merged config without secrets leak | ✅ | ❌ |
| T9 | Outputs are findable: project directory has standard layout | After pipeline run, `get_project_assets` → `01_content/`, `pipeline_md5.json`, `00_project_info.json` exist | ✅ | ❌ |
| T10 | Pipeline is resilient: gate failure does not crash server | Run pipeline → let a gate fail → server still responds to `health_check` | ✅ | ❌ |

**Verdict**: PASS if ≥9/10 criteria pass (T3 is mandatory — if topic→article fails, True Test fails regardless).

---

## 9. Current Status

| Component | Status |
|-----------|--------|
| Framework design | ✅ Documented (this file) |
| Expectation catalog | ✅ 55 expectations across 9 phases |
| **All 9 phases UX specs** | **✅ All expanded from sparse tables to full detail tables with dual perspective (Human + Agent). Phase 9 (Customize) added with per-platform workflow customization expectations F49–F55.** |
| Core value propositions | ✅ 4 assessed with honest gaps; all known gaps documented (HITL corrected, config introspection resolved, IM notifications scoped out) |
| Priority matrix | ✅ Updated — all 55 expectations mapped with importance × gap ratings |
| Verdict model | ✅ Designed |
| End-to-end flow test (text_only) | ❓ Not performed |
| End-to-end flow test (auto) | ❓ Not performed |
| End-to-end flow test (publish) | ❓ Not performed |
| Expectation statuses filled in | ✅ Updated after D3 review pass: F07 (8 modes confirmed), F24/25/26/27 (3-level auto-recovery detailed), F32 (removed IM notifiers), F34 (platform matrix), F35 (PublishEngine retry), F37 (cron tools: add/list/remove/get_cron_health/test_cron_schedule), F42 (config introspection + search_assets MCP), F48 (v1 readable only) |
| Intentional divergences documented | ✅ Xiaohongshu manual-only (F32), IM notifications out of scope (agent framework responsibility) |
| Milestone mapping | ✅ Defined and aligned with current scope |
| True Test | ✅ Defined with 10-point agent-verifiable PASS/FAIL checklist |

---

## 10. The Hard Truth

This document was designed to be **honest**. Not to make the project look good, but to make it **actually good**. The expectations in §3 are high — deliberately high — because the project's promise (from `user-introduction.md`) is ambitious.

Some expectations will show gaps. That is not failure — that is **direction**. Every gap is a candidate for the next improvement.

The project is not done when all 2,955 tests pass.
The project is done when the founder can say: **"Yes, this does what I wanted."**

---

## References

- `docs/user-introduction.md` — Project's promise to users
- `docs/dev/archive/acceptance-criteria.md` — D1: Pipeline output acceptance
- `docs/dev/archive/behavioral-acceptance.md` — D2: Behavioral acceptance
- `docs/dev/project-audit.md` — Comprehensive project audit (§5 end-to-end flow, §10 testing gaps)
- `docs/user/open-core.md` — Licensing and commercial features
- `docs/dev/archive/production-e2e-test-design.md` — Production E2E test design (S1-S9)
