# AutoMedia — Agent Codebase Context

This is the first file an AI coding agent reads to understand the AutoMedia codebase. Read it fully before making any changes.

---

## 1. Project Overview

AutoMedia is an automated media production pipeline. It handles the full content lifecycle: topic selection, draft writing, video generation, subtitle rendering, and multi-platform publishing.

- **Language:** Python 3.11+
- **Size:** 33,619 LOC across 150 Python files (automedia/ core) · ~90,000+ LOC across 442+ Python files (entire repo)
- **Key Dependencies:** typer (CLI), mcp (Python SDK), Pydantic 2.x, PyYAML, tenacity, Pillow
- **License:** MIT

---

## 2. Three Entry Points

| Layer | Command | Description |
|-------|---------|-------------|
| MCP Server | `python -m automedia.mcp.server` | JSON-RPC over stdio, 50 tools |
| CLI | `automedia <subcommand>` | 14 commands via typer |
| SDK | `from automedia import run_full_pipeline` | Python API |

All three share the same `run_full_pipeline()` implementation in `automedia/pipelines/runner.py`.

---

## 3. Directory Layout

```
AutoMedia/
├── src/
│   └── automedia/              # Core Python package (33,619 LOC)
│       ├── __init__.py             # Public API surface
│       ├── __main__.py             # `python -m automedia`
│       ├── _version.py             # Version string
│       │
│       ├── core/                   # Foundation layer
│       │   ├── config_loader.py    # 6-layer config merge (defaults → env → overrides)
│       │   ├── project.py          # Project directory management
│       │   ├── credential_loader.py# Credential loading
│       │   ├── doctor.py           # System dependency checks
│       │   ├── overrides.py        # Override rule processing
│       │   ├── llm_client.py       # LLM API client abstraction
│       │   ├── media_spec.py       # PlatformMediaSpec + 19-platform defaults
│       │   └── workflow.py          # Workflow dataclass + WorkflowLoader
│       │
│       ├── pipelines/              # Pipeline execution
│       │   ├── runner.py           # run_full_pipeline() — shared entry point
│       │   ├── gate_engine.py      # GateEngine — sequential gate executor
│       │   ├── audio_pipeline.py   # Audio processing pipeline
│       │   ├── image_pipeline.py   # Image/video processing pipeline
│       │   └── language_config.py  # Language configuration resolution
│       │
│       ├── gates/                  # Quality gates (21 implementations including H0)
│       │   ├── base.py             # BaseGate ABC + GateRegistry singleton
│       │   ├── failure_modes.py    # Failure mode knowledge base
│       │   ├── fact_check.py       # G0
│       │   ├── humanizer.py        # G1
│       │   ├── copy_review.py      # G2
│       │   ├── brand_cta.py        # G3
│       │   ├── wechat_checklist.py # G4
│       │   ├── html_hard.py        # G5
│       │   ├── lint.py             # V0
│       │   ├── vision_qa.py        # V1
│       │   ├── pre_send_whisper.py # V2
│       │   ├── content_semantic.py # V3
│       │   ├── tts_brand_asset.py  # V4
│       │   ├── mp3_vs_srt.py       # V5
│       │   ├── subtitle_render.py  # V6
│       │   ├── six_step_hard.py    # V7
│       │   ├── publish_log_schema.py # L1
│       │   ├── archive_validation.py # L2
│       │   ├── platform_integrity.py # L3
│       │   ├── topic_selection.py  # pre-gate
│       │   ├── content_writer.py   # CW
│       │   └── translation_quality.py # L4
│       │
│       ├── hooks/                  # Readonly observer protocol
│       │   ├── protocol.py         # GateHook Protocol + GateObserver base
│       │   ├── md5_tracker.py      # MD5 checksum tracking → pipeline_md5.json
│       │   └── metrics.py          # Metrics collection hook
│       │
│       ├── cli/                    # Typer CLI application
│       │   ├── app.py              # Main app — registers all commands
│   │       └── commands/           # 13 command modules
│       │       ├── account.py      # automedia account
│       │       ├── run.py          # automedia run
│       │       ├── pool.py         # automedia pool
│       │       ├── projects.py     # automedia projects
│       │       ├── adapter.py      # automedia adapter
│       │       ├── cron.py         # automedia cron
│       │       ├── archive.py      # automedia archive
│       │       ├── init_cmd.py     # automedia init
│       │       ├── doctor.py       # automedia doctor
│       │       ├── omni.py         # automedia omni
│       │       ├── hitl.py         # automedia hitl
│       │       ├── onboard.py      # automedia onboard
│       │       └── __init__.py
│       │
│       ├── mcp/                    # MCP server
│       │   ├── server.py           # FastMCP server — 50 tools
│       │   ├── accounts.py         # Account management tools (connect/list/health/disconnect)
│       │   ├── tools.py            # Core pipeline tools
│       │   ├── resources.py        # MCP resource handlers
│       │   ├── parallel.py         # Parallel execution helpers
│       │   └── mcp_allowlist.yaml  # Path allowlist (do not modify without request)
│       │
│       ├── adapters/               # Platform publish adapters
│       │   ├── base.py             # Base adapter classes
│       │   ├── registry.py         # AdapterRegistry
│       │   ├── publish_engine.py   # Publish orchestration
│       │   └── platforms/          # Platform-specific adapters
│       │
│       ├── accounts/               # PRD-4 account & credential management
│       │   ├── __init__.py         # Public API: AccountRegistry, AccountStore, AuthFlowEngine, SessionManager
│       │   ├── models.py           # Pydantic v2 models for accounts, credentials, sessions
│       │   ├── store.py            # AES-256-GCM encrypted credential store
│       │   ├── registry.py         # AccountRegistry — CRUD with label uniqueness
│       │   ├── session.py          # TTL-aware token cache, concurrency locks, rate-limit backoff
│       │   └── auth/               # Auth flow implementations
│       │       ├── __init__.py     # AuthFlowEngine, AuthFlow, AuthResult
│       │       ├── flows.py        # CookieAuthFlow, APIKeyAuthFlow
│       │       └── oauth2.py       # OAuth2ClientCredentialsFlow, OAuth2AuthCodeFlow
│       │
│       ├── platform/               # Platform-specific logic
│       │   ├── xiaohongshu.py
│       │   └── zhihu_draft.py
│       │
│       ├── omni/                   # Omni Triad integration
│       │   ├── base.py             # Base adapter classes
│       │   ├── ol_adapter.py       # OL (localization) adapter
│       │   ├── opp_adapter.py      # OPP (extraction) adapter
│       │   ├── orf_adapter.py      # ORF (format conversion) adapter
│       │   ├── registry.py         # Omni adapter registry
│       │   ├── config.py           # Omni configuration
│       │   ├── allowlist.py        # Omni path allowlist
│       │   ├── artifact_mapping.py # Artifact mapping utilities
│       │   └── md5_integration.py  # MD5 integration with Omni
│       │
│       ├── decision/               # Decision Layer (PRD-3)
│       │   ├── orchestrator.py     # DecisionOrchestrator
│       │   ├── base.py             # BaseDecisionAgent
│       │   ├── build.py            # Decision build logic
│       │   ├── dependency.py       # Dependency resolution
│       │   ├── preflight.py        # Preflight checks
│       │   ├── schema_validator.py # Schema validation
│       │   ├── diagnostic.py       # Diagnostics
│       │   ├── audit.py            # Decision audit
│       │
│       ├── hitl/                   # Human-in-the-loop framework
│       │   ├── config.py           # HITL configuration
│       │   ├── executor.py         # HITL execution engine
│       │   ├── presets/            # HITL preset configurations (automated, semi-automated, director)
│       │   └── __init__.py
│       │
│       ├── pool/                   # Topic pool (SQLite)
│       │   ├── db.py               # PoolDB — SQLite CRUD
│       │   ├── collector.py        # Topic collection
│       │   ├── scorer.py           # Topic scoring
│       │   └── dedup.py            # Deduplication
│       │
│       ├── cron/                   # Scheduled job definitions
│       │
│       ├── prompts/                # Jinja2 prompt templates (platform-scoped)
│       │   ├── __init__.py             # load_prompt() with 3-layer resolution
│       │   └── platforms/              # Platform-scoped templates (7 platforms)
│       │
│       ├── manifests/              # Default config + schemas
│       │   ├── defaults.yaml       # Built-in default config
│       │   ├── brand_profile_schema.py
│       │   └── model_config_schema.py
│       │
│       └── asset_library/          # Asset library / vector store
│           ├── db.py
│           ├── ingest.py
│           ├── search.py
│           ├── vector_store.py
│           └── migrate.py
│
├── docs/                       # Documentation (26 files)
│   ├── index.md                # Documentation site home
│   ├── d3-gap-analysis.md      # D3 gap closure analysis
│   │
│   ├── dev/                    # Developer-oriented docs
│   │   ├── adr/architecture-decisions.md
│   │   ├── agent-troubleshooting.md
│   │   ├── api-gotchas.md
│   │   ├── cron-troubleshooting.md
│   │   ├── developer-guide.md
│   │   ├── enforcement-mechanisms.md
│   │   ├── evaluation-matrix-principles.md
│   │   ├── forward-compat.md
│   │   ├── founder-expectations.md
│   │   ├── gate-failure-modes.md
│   │   ├── PRD-4.md
│   │   ├── project-audit.md
│   │   ├── project-validation-framework.md
│   │   └── video-synthesis-design.md
│   │
│   ├── user/                   # User-facing docs
│   │   ├── api-reference.md
│   │   ├── asset-library.md
│   │   ├── cli-reference.md
│   │   ├── hitl-framework.md
│   │   ├── mcp-setup.md
│   │   ├── mcp-systemd-setup.md
│   │   ├── omni-integration.md
│   │   ├── production-workflow.md
│   │   └── user-introduction.md
│
├── scripts/                    # Build and utility scripts
│   ├── setup.sh                # One-command venv + install + init
│   ├── run-tests.sh            # pytest with coverage
│   ├── mcp-server.sh           # MCP launcher with SIGTERM handler
│   └── doctor.sh               # Dependency checker
│
├── tests/                      # Test suite
│   ├── conftest.py             # Shared fixtures (synthetic data only)
│   ├── fixtures/
│   │   ├── synth/              # Synthetic test fixtures (use these)
│   │   └── real_config/        # Real config templates
│   ├── test_e2e/               # End-to-end tests
│   ├── test_gates/             # Gate-specific tests
│   ├── test_cli/               # CLI tests
│   ├── test_mcp/               # MCP server tests
│   ├── test_pipeline/          # Pipeline tests
│   ├── test_pool/              # Topic pool tests
│   ├── test_omni/              # Omni adapter tests
│   ├── test_orchestration/     # Pipeline orchestration tests
│   ├── test_decision_layer/    # Decision layer tests
│   ├── test_hooks/             # Hook tests
│   ├── test_enforcement/       # Red line enforcement tests
│   └── [130+ test files]
│
├── deploy/                     # systemd deployment files
├── .github/workflows/          # CI pipeline
├── pyproject.toml              # Build & dependency config
├── .pre-commit-config.yaml     # Pre-commit hooks
└── .env.example                # Environment template
```

---

## 4. Key Architecture Decisions

### Gate Engine
The pipeline runs an ordered sequence of gates. Each gate has a `failure_mode`:
- **`"stop"`** — halts the entire pipeline on failure
- **`"rewrite"`** — retries the gate (content regeneration)

Gates are ordered: pre-gate → CW → G0-G5 → V0-V7 → H0 → L1-L4. Eight pipeline modes (`auto`, `text_only`, `text_with_cover`, `video_only`, `qa_only`, `image-carousel`, `social-thread`, `short-video`) select different gate subsets. See `automedia/pipelines/runner.py` for the exact lists.

### 6-Layer Configuration
Configuration merges from lowest to highest priority:
1. Built-in `automedia/manifests/defaults.yaml`
2. Project `.automedia/` directory
3. User `~/.automedia/` directory
4. `~/.automedia/overrides/rules/*.yaml`
5. `~/.automedia/overrides/prompts/*.j2`
6. `AUTOMEDIA_*` environment variables + explicit overrides parameter

See `automedia/core/config_loader.py` for the implementation.

### GateHook Observer Protocol
Hooks are readonly observers. They receive gate context but must not mutate anything or skip gate execution. Three lifecycle methods:
- `before_gate(gate_name, context)` — called before a gate runs
- `after_gate(gate_name, context, result)` — called after a gate succeeds
- `on_gate_failed(gate_name, context, error)` — called when a gate raises

Every method returns `None`. See `automedia/hooks/protocol.py`.

### MD5 Tracking
Every gate writes product checksums to `pipeline_md5.json` in the project directory for integrity verification. Implemented in `automedia/hooks/md5_tracker.py`.

### External Scheduling
AutoMedia has no built-in scheduler. An external crond calls `automedia cron run` at configured intervals. See `automedia/cron/`.

### Three-Entry-Point Design
CLI (`automedia/cli/app.py`), MCP (`automedia/mcp/server.py`), and SDK (`automedia/pipelines/runner.py`) all delegate to `run_full_pipeline()`. The MCP server also exposes individual Omni triad tools (extract, translate, convert).

### Gate Auto-Registration
Concrete `BaseGate` subclasses are automatically registered in the global `GateRegistry` singleton via Python's `__init_subclass__`. The registry maps gate name strings to gate classes.

---

## 5. Agent Constraints (Red Lines) — MUST OBEY

These constraints are enforced by the test suite and must never be violated:

1. **MUST NOT** archive projects using `--force`. Only the user may force-archive (Red Line 8). The MCP `archive_project` tool enforces this — it refuses unless status is `"published"` or `force=True`.
2. **MUST NOT** commit real production data, topic pool contents, or credentials to git.
3. **MUST NOT** modify `automedia/mcp/mcp_allowlist.yaml` without explicit user request.
4. **MUST** use synthetic test fixtures from `tests/fixtures/synth/` for testing. Zero production data in tests.
5. **MUST** use `automedia archive` command for archiving projects — never manual directory operations.
6. **MUST** follow the gate naming convention: G0-G5 (copy/content gates), V0-V7 (video/quality gates), L1-L4 (lifecycle gates). Additional gates include H0, pre-gate, and CW.
7. **MUST** add new gates to `automedia/gates/failure_modes.py` when creating them.
8. **MUST NOT** skip pre-commit checks. Run `pre-commit run --all-files` before committing.
9. **MUST** respect the GateHook readonly contract — hooks observe but never mutate.

---

## 6. Dev Workflow

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=src/automedia

# Run E2E tests only
pytest tests/test_e2e/ -v

# Run by marker
pytest -m e2e        # End-to-end tests
pytest -m redline    # Red line enforcement tests
pytest -m slow       # Slow tests

# Lint
ruff check .

# Type check
mypy src/automedia/ --ignore-missing-imports

# Pre-commit
pre-commit run --all-files
```

### Docker

```bash
# Run the MCP server
docker run -it --rm --entrypoint python kevinzhow/automedia-pipeline:latest -m automedia.mcp.server

# Run CLI commands
docker run -it --rm kevinzhow/automedia-pipeline:latest automedia doctor
docker run -it --rm kevinzhow/automedia-pipeline:latest automedia run --topic "..." --brand my-brand --mode text_only

# Run tests
docker run -it --rm --entrypoint pytest kevinzhow/automedia-pipeline:latest

# Run tests with coverage
docker run -it --rm --entrypoint pytest kevinzhow/automedia-pipeline:latest -- --cov=src/automedia
```

---

## 7. Test Conventions

- **Markers:** `e2e`, `redline`, `slow` — registered in `tests/conftest.py`
- **Fixtures:** Shared fixtures in `tests/conftest.py` use `tmp_path` for isolation. All fixtures produce synthetic data only.
- **Synthetic data:** Always use `tests/fixtures/synth/` files. Never reference production data.
- **Public API surface:** Integration tests should import from `automedia/__init__.py` (e.g. `run_full_pipeline`, `GateEngine`, `PipelineResult`).
- **Gate tests:** Each gate has a corresponding test file in `tests/` (e.g. `test_fact_check.py`, `test_humanizer.py`).
- **MCP tests:** Located in `tests/test_mcp/`.
- **CLI tests:** Located in `tests/test_cli/`.

---

## 8. Common Task Patterns

### Add a New Gate
1. Create a file in `automedia/gates/` that inherits from `BaseGate`
2. Set class-level `_gate_name` (e.g. `"G6"`) and `_failure_mode` (`"stop"` or `"retry"`)
3. Implement `execute(self, gate_context: dict) -> dict`
4. Add a failure mode entry in `automedia/gates/failure_modes.py`
5. Add the gate name to the appropriate gate list in `automedia/pipelines/runner.py` (`_AUTO_GATE_NAMES`, etc.)
6. Create tests in `tests/test_gates/`

### Add a New CLI Command
1. Create a file in `automedia/cli/commands/`
2. Define a typer `app` with the command(s)
3. Register in `automedia/cli/app.py` via `app.add_typer()` (for subcommand groups) or `app.command()` (for standalone commands)

### Add a New Platform Adapter
1. Create an adapter class in `automedia/adapters/` implementing the adapter protocol
2. Register via `AdapterRegistry.register()`
3. Or use the MCP tool `register_platform_adapter(platform_name="...", adapter_class="...")`

### Add a New MCP Tool
1. Define a module-level handler function in `automedia/mcp/server.py`
2. Register it inside `create_server()` via `mcp.tool()`

### Add a New Environment Variable
1. Define it with the `AUTOMEDIA_` prefix
2. Add mapping in `_LLM_KEY_MAP` in `automedia/core/config_loader.py` if it maps under `llm.text_generation.*`
3. Add to the Config Key Reference section below

---

## 9. MCP Tools Quick Reference (46 tools, +4 deprecated aliases)

The MCP server runs on stdio transport. Start with `python -m automedia.mcp.server`. All file operations are gated by a path allowlist (`mcp_allowlist.yaml`).

| Tool | Parameters | Description |
|------|-----------|-------------|
| `health_check` | — | Return server health status (version, uptime, tool count) |
| `select_topic` | category, tenant_id, pool_db_path | Select the highest-scored pending topic from the pool |
| `research_topics` | category, count, trending | Research trending topics within a category using LLM |
| `run_brand_strategy` | brand_name, industry, target_audience, context | Generate a brand strategy using LLM analysis |
| `run_pipeline` | topic, brand, mode, tenant_id, resume_from | Execute full production pipeline in a background thread (async) |
| `run_pipeline_from_strategy` | topic, brand, mode, strategy_context | Generate content strategy via LLM then execute pipeline |
| `get_pipeline_progress` | project_id | Poll a running pipeline's gate-by-gate progress |
| `get_pipeline_status` | project_id, base_dir | Query project status from its info file |
| `list_projects` | base_dir, status | List all projects found under a base directory |
| `get_project_assets` | project_dir | List asset files in a project directory |
| `archive_project` | project_id, base_dir, force | Archive a project (Red Line 8 enforced) |
| `list_topic_pool` | status, category, pool_db_path | List topics in the pool with optional filters |
| `register_platform_adapter` | platform_name, adapter_class | Register a publish adapter (stub until PRD-1 NG6) |
| `extract_brief` | file_path, source_lang, target_lang | Extract a content brief from a document using OPP |
| `localize_content` | md_content, source_lang, target_lang | Translate markdown content via OL shield pipeline |
| `localize_output` | project_dir, target_langs | Translate all project drafts into multiple languages |
| `format_output` | content, target_format, **options | Convert content format via ORF adapter |
| `evaluate_content_quality` | content, criteria, brand | Score content quality against criteria (clarity, accuracy, brand voice, etc.) |
| `connect_account` | platform, auth_type, credentials, label | Register a new platform account (returns account_id) |
| `list_accounts` | platform, status | List registered accounts with optional filters |
| `get_account_health` | account_id | Check an account's health status |
| `disconnect_account` | account_id | Remove a platform account |
| `add_pool_topic` | topic, category, source | Add a topic to the topic pool |
| `pool_add_topic` | topic, category, source | ⚠️ Deprecated: use add_pool_topic |
| `publish_content` | project_id, platform, mode | Publish a project to a platform |
| `run_batch` | topics, brand, mode | Run pipeline sequentially for multiple topics |
| `batch_run` | topics, brand, mode | ⚠️ Deprecated: use run_batch |
| `add_cron_schedule` | schedule, command | Add a cron schedule entry |
| `list_cron_schedules` | — | List all cron schedules |
| `remove_cron_schedule` | schedule_id | Remove a cron schedule entry |
| `get_cron_health` | — | Check cron job configuration health |
| `test_cron_schedule` | expression, count | Validate cron expression and compute next trigger times |
| `search_assets` | query, brand, limit, filters | Search produced content via keyword + semantic search |
| `list_brands` | — | Return all configured brands with profile metadata |
| `get_config` | key | Return merged configuration (secrets redacted) |
| `cancel_pipeline` | project_id | Cancel a running pipeline by project_id (sets cancellation flag) |
| `pause_pipeline` | project_id | Pause a running pipeline by project_id |
| `resume_pipeline` | project_id | Resume a paused pipeline by project_id |
| `retry_gate` | project_id, gate_name | Mark a specific gate for retry in a running pipeline |
| `skip_gate` | project_id, gate_name | Mark a specific gate for skipping in a running pipeline |
| `health_engine` | — | Check all engine-related dependencies and return their health status |
| `engine_health` | — | ⚠️ Deprecated: use health_engine |
| `update_engine_config` | modality, setting, value | Update an engine configuration setting |
| `help_mcp` | — | Get a categorized listing of all available MCP tools with descriptions |
| `mcp_help` | — | ⚠️ Deprecated: use help_mcp |

---

## 10. CLI Commands Quick Reference (13 commands)

| Command | Description |
|---------|-------------|
| `automedia run` | Execute the full AutoMedia production pipeline |
| `automedia pool` | Topic pool management (list, add, score) |
| `automedia projects` | List and manage production projects |
| `automedia adapter` | Platform adapter management |
| `automedia cron` | Execute scheduled cron jobs |
| `automedia account` | Platform account management (connect, list, health, disconnect, refresh) |
| `automedia archive` | Archive a project (Red Line 8: requires --force unless published) |
| `automedia init` | Initialize AutoMedia configuration |
| `automedia doctor` | Check system dependencies and environment health |
| `automedia omni` | Omni Triad operations (extract, translate, convert) |
| `automedia hitl` | Human-in-the-loop review operations |
| `automedia onboard` | Onboarding wizard |

---

## 11. Config Key Reference

Key `AUTOMEDIA_*` environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `AUTOMEDIA_LLM_PROVIDER` | LLM provider name | `deepseek` |
| `AUTOMEDIA_LLM_MODEL` | Model identifier | `deepseek-chat` |
| `AUTOMEDIA_LLM_BASE_URL` | API endpoint | `https://api.deepseek.com/v1` |
| `AUTOMEDIA_LLM_API_KEY` | API key | (required) |
| `AUTOMEDIA_LLM_TEMPERATURE` | LLM temperature | (varies) |
| `AUTOMEDIA_LLM_MAX_TOKENS` | Max tokens per request | (varies) |
| `AUTOMEDIA_DEFAULT_BRAND` | Default brand for pipelines | `my-brand` |
| `AUTOMEDIA_DATA_DIR` | Data directory | `./data` |
| `AUTOMEDIA_OUTPUT_DIR` | Output directory | `./output` |
| `AUTOMEDIA_PROJECTS_DIR` | Projects root override | (auto) |

These env vars are mapped to `llm.text_generation.*` config keys by `automedia/core/config_loader.py`.

---

## 12. Documentation Index

| File | Content |
|------|---------|
| `docs/dev/developer-guide.md` | Full developer guide |
| `docs/user/api-reference.md` | SDK API reference |
| `docs/user/cli-reference.md` | CLI command reference |
| `docs/user/mcp-setup.md` | MCP server setup guide |
| `docs/user/mcp-systemd-setup.md` | systemd deployment guide |
| `docs/user/hitl-framework.md` | Human-in-the-loop framework docs |
| `docs/user/omni-integration.md` | Omni Triad integration docs |
| `docs/dev/enforcement-mechanisms.md` | Red line enforcement docs |
| `docs/user/asset-library.md` | Asset library documentation |
| `docs/dev/gate-failure-modes.md` | Gate failure troubleshooting |
| `docs/user/production-workflow.md` | Production operations guide |
| `docs/dev/cron-troubleshooting.md` | Cron job debugging |
| `docs/dev/api-gotchas.md` | Common API pitfalls |
| `CHANGELOG.md` | Version history |
| `docs/dev/agent-troubleshooting.md` | Agent troubleshooting guide for common pipeline, config, MCP, and gate issues |

For troubleshooting common issues, see [Agent Troubleshooting Guide](docs/dev/agent-troubleshooting.md).

---

## 13. Skills

Skills (agent instructions for specific tasks) are stored in
`.opencode/skills/` and are available to **all agent types** — OpenCode,
Claude Code, Codex CLI, and Cline.

- **Canonical location:** `.opencode/skills/` — edit skills here
- **Claude Code:** `.claude/skills/` — native copies for Claude Code
- **Codex CLI:** `.codex/skills/` — native copies for Codex CLI
- **Cline:** Reference `.opencode/skills/` directly — no dedicated directory

Each agent directory receives a native copy of each skill file so that
every tool can load them without indirection. When updating a skill,
edit the canonical file in `.opencode/skills/` and sync the same content
to `.claude/skills/` and `.codex/skills/`.

Currently available skills:
- `brand-strategy` — Brand positioning, audience analysis, competitive landscape
- `project-validation` — Post-change validation against founder expectations
