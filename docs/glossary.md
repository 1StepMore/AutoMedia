# AutoMedia Glossary

Plain-language definitions of AutoMedia terms for AI coding agents. Each entry points to the file or module that implements the concept. For the full codebase map, see [AGENTS.md](https://github.com/1StepMore/AutoMedia/blob/main/AGENTS.md).

## G0-G6 (copy gates)

Copy quality gates that run in the middle of the pipeline: fact check (G0), humanizer (G1), copy review (G2), brand CTA (G3), WeChat checklist (G4), HTML check (G5), tone check (G6).

**See:** `automedia/gates/`, gate lists in `automedia/pipelines/runner.py`

## V0-V7 (video/quality gates)

Video and production-quality gates that run after the copy gates: lint (V0), vision QA (V1), pre-send whisper (V2), content semantic (V3), TTS brand asset (V4), MP3 vs SRT (V5), subtitle render (V6), six-step hard check (V7).

**See:** `automedia/gates/lint.py`, `automedia/pipelines/runner.py`

## L1-L4 (lifecycle gates)

Lifecycle gates at the end of the pipeline: publish log schema (L1), archive validation (L2), platform integrity (L3), translation quality (L4).

**See:** `automedia/gates/publish_log_schema.py`, `automedia/pipelines/runner.py`

## D1-D7 (distribution gates)

Standalone gates that rewrite content for specific platforms (WeChat, Twitter/X, Zhihu, Xiaohongshu, Bilibili, YouTube, TikTok). They are invoked via CLI/MCP `distribute`, not as part of a normal pipeline run.

**See:** `automedia/cli/commands/distribute.py`, `automedia/pipelines/runner.py`

## P1-P4 (repurpose gates)

Sub-pipelines that run at the end of `repurpose` pipeline mode to produce deep repurposed versions (WeChat, Twitter/X, Newsletter, Bilibili).

**See:** `automedia/pipelines/runner.py`

## pre-gate

The topic selection gate that runs before content writing. It validates that the topic is suitable before any generation happens.

**See:** `automedia/gates/topic_selection.py`, `automedia/pipelines/runner.py`

## CW (content writer)

The content writing gate, the first real generation step. It writes the article draft with inline SEO scoring.

**See:** `automedia/gates/content_writer.py`

## H0 (human review gate)

The human-in-the-loop gate where a person approves content and video quality before the pipeline proceeds. In director mode the pipeline pauses here for approval.

**See:** `automedia/gates/`, `automedia/hitl/`

## failure_mode

Every gate declares a `failure_mode`. `"stop"` halts the whole pipeline when the gate fails. `"rewrite"` (also called `"retry"`) regenerates content and reruns the gate.

**See:** `automedia/gates/base.py`, `automedia/gates/failure_modes.py`

## GateEngine

The sequential executor that runs the ordered gate list for a pipeline. It supports pause and resume, which is what director mode uses for human approval.

**See:** `automedia/pipelines/gate_engine.py`

## AUTO_GATE_DAG / dag.py

The canonical gate dependency graph defined in `automedia/pipelines/dag.py`: 26 nodes (the 22 auto-mode gates plus P1-P4) with `depends_on` edges. It is an additive, order-equivalent representation of `_MODE_MAP` — `topological_order(AUTO_GATE_DAG, mode_gates)` reproduces every mode list byte-for-byte. It also answers structural questions `_MODE_MAP` cannot, like "which gates are downstream of G0?".

**See:** `automedia/pipelines/dag.py`

## automedia pipeline state

A read-only per-gate audit view for a project. It aggregates `history.db` and `pipeline_md5.json` into a passed/failed/pending status per gate (with asset md5 and recorded timestamp), grouped by track (copy, video, qa, lifecycle). Also exposed as the MCP `get_pipeline_state` tool.

**See:** `automedia/cli/commands/pipeline.py`, `automedia/pipelines/state_view.py`

## --auto-resume

A CLI/MCP/SDK flag that resumes a pipeline from the last passed gate. It reads the project's `history.db`, finds the latest gate recorded as `completed` with `passed: true`, and resumes from the gate after it. An explicit `--resume-from` always takes precedence.

**See:** `automedia/pipelines/runner.py` (`_find_auto_resume_point`), `automedia/hooks/pipeline_history.py`

## affected_downstream

A `PipelineResult` field listing the gates that a pipeline failure blocked. It is computed as the DAG downstream closure of the first failed gate, intersected with the mode's gate list, in canonical order. Empty when all gates passed or the pipeline aborted before any gate ran. The CLI renders it as a "⚠ Downstream affected" line.

**See:** `automedia/pipelines/runner.py` (`_compute_affected_downstream`), `automedia/pipelines/dag.py`

## gate report / gate-report

The per-run gate report written to `<project_dir>/05_review/gate-report/gate-report-<timestamp>.{md,json}` at the end of every production run, whether it passed or failed. It renders one row per gate: the verdict (pass/fail/review), the blocking reason when one exists, per-check detail where present, and the gate duration. The Markdown file is human-readable; the JSON side-by-side is what the MCP `get_gate_report` tool reads. "review" is the report vocabulary for a crashed gate or an H0 the run's hitl mode covered.

**See:** `automedia/pipelines/gate_report.py`

## get_gate_report

MCP tool (one of 67) that returns the latest gate-report JSON for a project by reading `<project_dir>/05_review/gate-report/gate-report-*.json`. The project's base_dir must be allowlisted in `mcp_allowlist.yaml`, otherwise the request is denied fail-closed. Read-only: it never writes to the project.

**See:** `automedia/mcp/tools/pipeline.py` (registered in `automedia/mcp/server.py`)

## gate_diffs (.automedia/gate_diffs/)

Per-gate before/after content records captured when a content gate rewrites the draft on a failing quality retry. G1 (humanizer) and G2 (copy review) writes land in `<project_dir>/.automedia/gate_diffs/<gate>_<seq>.json`, with the record's texts and an `applied: true|false` flag saying whether the rewrite was promoted into the content flow. Only the texts are stored; a unified diff is rendered on demand (the Director review view), never persisted.

**See:** `automedia/pipelines/gate_engine.py` (`_write_gate_diff_record`)

## review_decision

MCP tool that approves or rejects a pipeline paused at a HITL review gate on the live H0 path. It signals the paused `PipelineProgress` directly: approve resumes the pipeline, reject halts it (the rejection becomes a stop-failure, so downstream gates never run). Same-process only: it reaches pipelines started by this MCP server process, not CLI-started ones. `show_diff=True` renders a unified diff from the latest `.automedia/gate_diffs/` record so the director sees exactly what the gate changed.

**See:** `automedia/mcp/tools/review.py`

## review-decision audit log

An append-only JSON-lines log at `~/.automedia/audit/review_decisions.log` recording every approve/reject from `review_decision`: timestamp, project_id, gate_name, decision, reason, diff_record_path, and actor. Full before/after texts stay in the gate_diffs records; only the record's path is logged. A write failure is logged and swallowed so it never fails the review call.

**See:** `automedia/decision/review_audit.py`

## GateRegistry

A global singleton that maps gate name strings to gate classes. Concrete `BaseGate` subclasses register themselves automatically via `__init_subclass__`, so new gates need no manual registration.

**See:** `automedia/gates/base.py`

## GateHook

A readonly observer protocol. Hooks receive gate context through `before_gate`, `after_gate`, and `on_gate_failed`, but they must never mutate anything or skip gate execution.

**See:** `automedia/hooks/protocol.py`

## MD5 tracker / pipeline_md5.json

Every gate writes product checksums to `pipeline_md5.json` in the project directory. This gives integrity verification for pipeline artifacts.

**See:** `automedia/hooks/md5_tracker.py`

## Omni Triad (OPP / OL / ORF)

Three adapter families: OPP (extraction, turns documents into content briefs), OL (localization, translation shield pipeline), and ORF (format conversion). Exposed as MCP tools `extract_brief`, `localize_content`, and `format_output`.

**See:** `automedia/omni/opp_adapter.py`, `automedia/omni/ol_adapter.py`, `automedia/omni/orf_adapter.py`

## 6-layer configuration

Config merges from lowest to highest priority: built-in defaults, project `.automedia/`, user `~/.automedia/`, override rules, override prompts, then `AUTOMEDIA_*` env vars and explicit overrides.

**See:** `automedia/core/config_loader.py`, `automedia/manifests/defaults.yaml`

## Override system

User-level overrides that adjust behavior without touching the package: YAML rules under `~/.automedia/overrides/rules/`, Jinja2 prompt overrides under `~/.automedia/overrides/prompts/`, and gate modifiers.

**See:** `automedia/core/overrides.py`, `docs/dev/override-reference.md`

## feature tiers (FEATURE_TIERS / check_tier)

Declarative open-core tier markers: every gate (33 total) is assigned to core, pro, or enterprise in `FEATURE_TIERS`. `check_tier(name)` reports a feature's tier and availability. With no override everything is available, so the free local install runs all 33 gates; setting `AUTOMEDIA_FEATURE_TIER=core|pro|enterprise` (or a user-level `~/.automedia/features.yaml`) excludes gates above that tier when gate lists are composed. Marker only: it never blocks execution itself and contains no license logic. The tier union is checked against the gate registry at import.

**See:** `automedia/features/__init__.py`, `automedia/pipelines/runner.py` (`_filter_gates_by_tier`)

## Platform-scoped prompt templates

Jinja2 prompt templates resolved per platform with a 3-layer lookup (brand > platform > global). Templates live under `automedia/prompts/platforms/` for 10 platforms.

**See:** `automedia/prompts/__init__.py`, `automedia/prompts/platforms/`

## Topic pool

A SQLite-backed store of candidate topics with scoring, collection, and deduplication. The MCP `select_topic` tool picks the highest-scored pending topic from it.

**See:** `automedia/pool/db.py`, `automedia/pool/scorer.py`

## Director mode (HITL)

A human-in-the-loop preset where GateEngine pauses at approval gates (such as H0) and a human approves or rejects via MCP tools `approve_gate` and `reject_gate`. The other presets are `automated` and `semi-automated`.

**See:** `automedia/hitl/presets/director.yaml`, `automedia/hitl/executor.py`

## Publish adapters / AdapterRegistry

Platform publish adapters registered in a global `AdapterRegistry`. The publish engine orchestrates them to push content to platforms.

**See:** `automedia/adapters/registry.py`, `automedia/adapters/publish_engine.py`

## adapter audit (real / stub / notifier)

`automedia adapter list --real/--stub/--json` surfaces the platform-automation partition. Of the 20 adapter modules, 11 are real publish APIs plus 1 feishu notifier (`is_stub=False`), and 8 are intentional manual-only stubs: douyin, kuaishou, baijiahao, bilibili, weibo, toutiao, juejin, and xiaohongshu. Those platforms have no public API for automated publishing, so manual-only is the documented divergence (F32/F34), not a gap. Every row carries its automation status derived from the adapter's `is_stub` attribute.

**See:** `automedia/cli/commands/adapter.py`, `automedia/adapters/platforms/`

## Credential store (AES-256-GCM)

Platform credentials are encrypted at rest with AES-256-GCM in `accounts/store.py`. The master key derives from `AUTOMEDIA_MASTER_KEY` via SHA-256, and credentials never appear in logs or MCP responses.

**See:** `automedia/accounts/store.py`

## MCP path allowlist

`automedia/mcp/mcp_allowlist.yaml` restricts which file paths the MCP server may touch. An empty list denies all paths. Do not modify it without an explicit user request.

**See:** `automedia/mcp/mcp_allowlist.yaml`

## setup_agent_mcp.sh

A one-command script that detects the active agent client (OpenCode, Claude Code, Codex, Cursor, Hermes, OpenClaw) and writes or updates that client's MCP server config so it can call AutoMedia's tools. Idempotent: re-running converges to the canonical entry without touching other keys. `--uninstall` removes only the automedia entry, `--list` shows detected clients and config state, and `--client-dir DIR` operates on a given config directory. Config files get the literal `${AUTOMEDIA_LLM_API_KEY}` placeholder, never a real key.

**See:** `scripts/setup_agent_mcp.sh`

## Red Lines

Agent constraints in AGENTS.md section 5 that the test suite enforces and that must never be violated, such as not force-archiving, not committing production data, and not modifying `mcp_allowlist.yaml` without permission.

**See:** `AGENTS.md` section 5
