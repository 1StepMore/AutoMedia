# AutoMedia Glossary

Plain-language definitions of AutoMedia terms for AI coding agents. Each entry points to the file or module that implements the concept. For the full codebase map, see [AGENTS.md](https://github.com/1stepmore/automedia/blob/main/AGENTS.md).

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

## Credential store (AES-256-GCM)

Platform credentials are encrypted at rest with AES-256-GCM in `accounts/store.py`. The master key derives from `AUTOMEDIA_MASTER_KEY` via SHA-256, and credentials never appear in logs or MCP responses.

**See:** `automedia/accounts/store.py`

## MCP path allowlist

`automedia/mcp/mcp_allowlist.yaml` restricts which file paths the MCP server may touch. An empty list denies all paths. Do not modify it without an explicit user request.

**See:** `automedia/mcp/mcp_allowlist.yaml`

## Red Lines

Agent constraints in AGENTS.md section 5 that the test suite enforces and that must never be violated, such as not force-archiving, not committing production data, and not modifying `mcp_allowlist.yaml` without permission.

**See:** `AGENTS.md` section 5
