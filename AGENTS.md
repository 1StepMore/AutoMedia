# AutoMedia — Agent Codebase Context

This is the first file an AI coding agent reads to understand the AutoMedia codebase. Read it fully before making any changes.

---

## 1. Project Overview

AutoMedia is an automated media production pipeline. It handles the full content lifecycle: topic selection, draft writing, video generation, subtitle rendering, and multi-platform publishing.

- **Language:** Python 3.11+
- **Size:** 33,619 LOC across 150 Python files (automedia/ core) · ~90,000+ LOC across 442+ Python files (entire repo)
- **Key Dependencies:** typer (CLI), mcp (Python SDK), Pydantic 2.x, PyYAML, tenacity, Pillow
- **License:** MIT

### Recommended Agent Install

For full capability (all LLM providers, MCP server, dev tools):
```bash
pip install -e ".[dev]"
```

For MCP-only setups:
```bash
pip install -e ".[mcp]"
```

---

## 2. Three Entry Points

| Layer | Command | Description |
|-------|---------|-------------|
| MCP Server | `python -m automedia.mcp.server` | JSON-RPC over stdio, 63 tools |
| CLI | `automedia <subcommand>` | 18 commands via typer |
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
│       ├── gates/                  # Quality gates (33 implementations including H0, D1-D7, P1-P4)
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
│       ├── detectors/              # Pluggable AI-writing-taste detectors (issue #62)
│       │   ├── base.py             # BaseDetector ABC + DetectorResult + auto-registration
│       │   ├── registry.py         # DetectorRegistry singleton (BaseRegistry-based)
│       │   ├── deterministic.py    # deterministic_taste — reuses G1 humanizer's 9 regex checks
│       │   └── adapters.py         # gptzero_style_api — env-gated external detector (AUTOMEDIA_DETECTOR_GPTZERO_API_KEY)
│       │
│       ├── hooks/                  # Readonly observer protocol
│       │   ├── protocol.py         # GateHook Protocol + GateObserver base
│       │   ├── md5_tracker.py      # MD5 checksum tracking → pipeline_md5.json
│       │   └── metrics.py          # Metrics collection hook
│       │
│       ├── cli/                    # Typer CLI application
│       │   ├── app.py              # Main app — registers all commands
│   │       └── commands/           # 18 command modules
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
│   │       ├── server.py           # FastMCP server — 63 tools
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
│       │   └── platforms/              # Platform-scoped templates (10 platforms)
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
├── docs/                       # Documentation (20 files)
│   ├── index.md                # Documentation site home
│   │
│   ├── dev/                    # Developer-oriented docs
│   │   ├── agent-troubleshooting.md
│   │   ├── api-gotchas.md
│   │   ├── cron-troubleshooting.md
│   │   ├── developer-guide.md   # Also includes: enforcement mechanisms, PRD-4 summary, ADRs
│   │   ├── evaluation-matrix-principles.md
│   │   ├── forward-compat.md
│   │   ├── founder-expectations.md
│   │   ├── gate-failure-modes.md
│   │   ├── override-reference.md
│   │   ├── project-validation-framework.md
│   │   └── video-synthesis-design.md
│   │
│   ├── user/                   # User-facing docs
│   │   ├── api-reference.md
│   │   ├── asset-library.md
│   │   ├── cli-reference.md
│   │   ├── hitl-framework.md
│   │   ├── mcp-setup.md         # Also includes: systemd deployment, error code reference
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

Gates are ordered: pre-gate → CW → G0-G6 → V0-V7 → H0 → L1-L4. Nine pipeline modes (`auto`, `text_only`, `text_with_cover`, `video_only`, `qa_only`, `image-carousel`, `social-thread`, `short-video`, `repurpose`) select different gate subsets. D-gates (D1-D7) are standalone distribution gates invoked via CLI/MCP. P-gates (P1-P4) run as sub-pipelines at the end of repurpose mode. See `automedia/pipelines/runner.py` for the exact lists.

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
6. **MUST** follow the gate naming convention: G0-G6 (copy/content gates), V0-V7 (video/quality gates), L1-L4 (lifecycle gates), D1-D7 (distribution gates), P1-P4 (sub-pipeline repurpose gates). Additional gates include H0, pre-gate, and CW.
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
6. Write an ADR entry in `docs/adr/` documenting the new gate's design decision
7. Create tests in `tests/test_gates/`

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

## 9. MCP Tools Quick Reference (63 tools, incl. 4 deprecated aliases)

The MCP server runs on stdio transport. Start with `python -m automedia.mcp.server`. All file operations are gated by a path allowlist (`mcp_allowlist.yaml`). The four validation tools below are the agent-tester validation surface; see the Validation Layer section for how to drive them.

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
| `list_active_pipelines` | — | List active and recently-finished pipelines (running, lost, or finished within the last 5 minutes) |
| `list_projects` | base_dir, status | List all projects found under a base directory |
| `get_project_assets` | project_dir | List asset files in a project directory |
| `archive_project` | project_id, base_dir, force | Archive a project (Red Line 8 enforced) |
| `list_topic_pool` | status, category, pool_db_path | List topics in the pool with optional filters |
| `register_platform_adapter` | platform_name, adapter_class | Register a publish adapter (stub until PRD-1 NG6) |
| `list_platforms` | — | List all registered publishing platforms |
| `extract_brief` | file_path, source_lang, target_lang | Extract a content brief from a document using OPP |
| `localize_content` | md_content, source_lang, target_lang | Translate markdown content via OL shield pipeline |
| `localize_output` | project_dir, target_langs | Translate all project drafts into multiple languages |
| `format_output` | content, target_format, **options | Convert content format via ORF adapter |
| `evaluate_content_quality` | content, criteria, brand | Score content quality against criteria (clarity, accuracy, brand voice, etc.) |
| `analyze_content` | project_id | Analyze project content and return analytics stats (word count, sentiment, readability, brand mentions, SEO scores) |
| `distribute_content` | project_id, platforms, all, dry_run, base_dir | Distribute pipeline content to targeted platforms via D-gates |
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
| `add_brand` | name, industry, target_audience | Create a new brand profile (name required; industry and target audience optional) |
| `get_config` | key | Return merged configuration (secrets redacted) |
| `init_config` | project_dir | Initialize AutoMedia configuration: create `.automedia/` and a default `config.yaml` |
| `configure_llm` | provider, model, api_key | Configure the LLM provider in `~/.automedia/model_config.yaml` |
| `onboard` | brand_name, llm_provider, llm_key, base_url | One-step onboarding: configure the LLM and create a brand profile without interactive prompts |
| `get_redlines` | — | Return the list of agent red-line constraints |
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
| `list_validation_scenarios` | — | List the agent-tester validation scenario library (name, description, category, status hint) |
| `run_validation_scenario` | scenario_name, runs_root, save | Run ONE named validation scenario in-process; scenario_name is required (the recursion bound) |
| `get_validation_report` | run_dir | Read a persisted validation run record from validation-runs/ (defaults to the latest run) |
| `validation_coverage_audit` | — | Run the static coverage audit: declared/used/covered/missing/phantom per surface |

---

## 10. CLI Commands Quick Reference (18 commands)

| Command | Description |
|---------|-------------|
| `automedia run` | Execute the full AutoMedia production pipeline |
| `automedia pool` | Topic pool management (list, add, score) |
| `automedia projects` | List and manage production projects |
| `automedia distribute` | Distribute pipeline content to platforms (D-gates with --platforms, --all, --dry-run) |
| `automedia effects` | Compute content analytics stats (word count, sentiment, readability, SEO) |
| `automedia adapter` | Platform adapter management |
| `automedia cron` | Execute scheduled cron jobs |
| `automedia account` | Platform account management (connect, list, health, disconnect, refresh) |
| `automedia archive` | Archive a project (Red Line 8: requires --force unless published) |
| `automedia init` | Initialize AutoMedia configuration |
| `automedia doctor` | Check system dependencies and environment health |
| `automedia omni` | Omni Triad operations (extract, translate, convert) |
| `automedia hitl` | Human-in-the-loop review operations |
| `automedia onboard` | Onboarding wizard |
| `automedia mcp` | MCP server management |
| `automedia history` | Show pipeline execution history for a project |
| `automedia rollback` | Roll back a project: archive it and revert status to draft |
| `automedia validate` | Run the agent-tester validation suite (list, run, report, diff, coverage) |

---

## 11. Validation Layer

AutoMedia is an agent-oriented product, and its validation framework makes the agents the testers. Any agent can prove the product works before relying on it: it runs real calls against the live surface, grades each response against a declared expect block, and writes an immutable run record. Humans are the director: they review the record and its artifacts and sign it off. Nothing the agent decides alone is final, and nothing the director has not seen is accepted.

### Driving surface

CLI (run from the repo root so relative artifact paths resolve):

- `automedia validate list`: load the scenario library and list every scenario (load only, no engine run)
- `automedia validate run --scenario <name>`: run ONE named scenario against the real MCP server; `--scenario` is required (the recursion bound); exits 1 when the status is failed
- `automedia validate report [--run <name|latest>]`: render the run record for a run, defaulting to the latest
- `automedia validate diff [--baseline <path>]`: diff the latest two runs against each other or a baseline record
- `automedia validate coverage`: run the static coverage audit; exits 1 when declared-but-missing is non-empty

MCP tools:

- `list_validation_scenarios`: list the scenario library (name, description, category, status hint)
- `run_validation_scenario`: run ONE named scenario in-process against the server; scenario_name is required, save=True persists an immutable record
- `get_validation_report`: read a persisted run record from validation-runs/ (defaults to the latest run)
- `validation_coverage_audit`: compute the static coverage audit (declared/used/covered/missing/phantom per surface)

### The evidence contract

**How to read a scenario (mirrors scenarios/README.md):**

1. `name` is the identity. It must be unique across the library and survive renames of the file that contains it.
2. `description` says, in one or two sentences, what the scenario proves.
3. `intent` says WHY it exists. Schema-required; read it first.
4. `requires_env` lists the environment variables the scenario needs. A missing one gates the whole scenario to `unconfigured`, never a pass.
5. `steps` are ordered, top to bottom. Each step is one real call plus an expect block; a later step can depend on earlier state.
6. Per step: `kind` picks the surface (`tool`, `cli`, `file`); `check` says WHAT to verify; `standard` cites a key that must exist in STANDARDS.md.
7. `expect` holds the assertions on the real response. Every assertion present must hold for the step to pass.
8. `recovery_steps` repair state after a primary step fails; `cleanup_steps` remove scenario-created state after the run. Neither proves the capability under test.
9. Artifacts are the evidence. `collect_artifacts` copies files into the run record; the `artifact_*` expect keys grade them.
10. `min_passing` and `pass_ratio` set the partial-pass policy; `regression` pins the scenario to a specific bug or fix.

**The 5 statuses:**

- `passed`: every primary step met its expect block and reached the surface.
- `failed`: at least one primary step failed its expect and no partial-pass policy saved it.
- `unconfigured`: a required environment variable was missing, so nothing ran. It is a state, never a verdict of acceptance; it appears with its reason and an empty step list.
- `recovered`: a primary step failed and a recovery step succeeded. The failure stays in the run record; recovery never erases RED.
- `partial-pass`: some steps failed, but the header's `min_passing` or `pass_ratio` policy was met. Partial-pass never hides a failure.

**Honesty rules:**

- Unconfigured never passes and never fails silently. A missing prerequisite is reported loudly with its reason.
- RED first. Record the honest negative state before fixing anything. A result that jumps straight to GREEN with no recorded RED is suspect and is re-run from the pre-flight baseline.
- Artifacts must be shown. GREEN means the call succeeded, the artifact exists, and that artifact was carried to the director.
- Director sign-off. The director appends the run name, date, and verdict to `signed.txt` in the run directory; the agent grades, the human disposes.

### Where things live

- `scenarios/`: the committed scenario library (one YAML file per scenario).
- `scenarios/STANDARDS.md`: the handbook of 28 standard keys that every step's `standard:` must cite; unknown keys are rejected at load time.
- `scenarios/baseline/`: the committed pre-flight baseline run record and the coverage audit.
- `validation-runs/`: gitignored immutable run records with a `latest.txt` pointer; evidence of a moment in time, not source.
- `AUTOMEDIA_VALIDATION_SCENARIOS_DIR`: environment override that replaces the default scenarios directory.

Any agent can drive this layer standalone. Hermes, Claude Code, Codex CLI, and OpenCode all read this file; the surface is CLI and MCP only, no product UI required. An agent that has never seen the framework can list, run, report, and diff scenarios without reading anything else, and can always check `scenarios/README.md` for the full reference.

---

## 12. Config Key Reference

Key `AUTOMEDIA_*` environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `AUTOMEDIA_LLM_PROVIDER` | LLM provider name | `deepseek` |
| `AUTOMEDIA_LLM_MODEL` | Model identifier | `deepseek-chat` |
| `AUTOMEDIA_LLM_BASE_URL` | API endpoint | `https://api.deepseek.com/v1` |
| `AUTOMEDIA_LLM_API_KEY` | API key | (required) |
| `AUTOMEDIA_LLM_TEMPERATURE` | LLM temperature | (varies) |
| `AUTOMEDIA_LLM_MAX_TOKENS` | Max tokens per request | (varies) |
| `AUTOMEDIA_LLM_TIMEOUT` | LLM request timeout (seconds) | `60` |
| `AUTOMEDIA_FAKE_LLM` | Set to `1` to use deterministic mock LLM responses (no real API calls) | (unset) |
| `AUTOMEDIA_DEFAULT_BRAND` | Default brand for pipelines | `my-brand` |
| `AUTOMEDIA_DATA_DIR` | Data directory | `./data` |
| `AUTOMEDIA_OUTPUT_DIR` | Output directory | `./output` |
| `AUTOMEDIA_PROJECTS_DIR` | Projects root override | (auto) |

These env vars are mapped to `llm.text_generation.*` config keys by `automedia/core/config_loader.py`.

---

## 13. Documentation Index

| File | Content |
|------|---------|
| `docs/dev/developer-guide.md` | Full developer guide (includes enforcement mechanisms, PRD-4 summary, ADRs) |
| `docs/user/api-reference.md` | SDK API reference |
| `docs/user/cli-reference.md` | CLI command reference |
| `docs/user/mcp-setup.md` | MCP server setup guide (includes systemd deployment, error code reference) |
| `docs/user/hitl-framework.md` | Human-in-the-loop framework docs |
| `docs/user/omni-integration.md` | Omni Triad integration docs |
| `docs/user/asset-library.md` | Asset library documentation |
| `docs/glossary.md` | Plain-language AutoMedia term glossary for agents |
| `docs/dev/gate-failure-modes.md` | Gate failure troubleshooting |
| `docs/user/production-workflow.md` | Production operations guide |
| `docs/dev/cron-troubleshooting.md` | Cron job debugging |
| `docs/dev/api-gotchas.md` | Common API pitfalls |
| `docs/dev/override-reference.md` | Override system reference (rules, prompts, platform scoping) |
| `CHANGELOG.md` | Version history |
| `docs/dev/agent-troubleshooting.md` | Agent troubleshooting guide for common pipeline, config, MCP, and gate issues |
| `docs/dev/七阶段AI开发流程-用CodingAgent交付成品的方法论.md` | 7-phase AI development methodology note (own your process, AFK implementation) |

For troubleshooting common issues, see [Agent Troubleshooting Guide](docs/dev/agent-troubleshooting.md).

---

## 14. Skills

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
- `project-validation` — Post-change validation against founder expectations
- `doc-sync` — Documentation awareness & impact mapping. Use when code changes affect documentation — CLI/MCP tools, gates, config, API, pipelines, adapters, or any feature area. Maps code changes to docs that must be updated and provides verification steps.

---

## 15. User-Facing Skills (for Agents Using AutoMedia)

Skills for agents who are **users** of AutoMedia (calling MCP tools to
produce content) live in `docs/skills/`. These describe how to invoke
AutoMedia tools effectively — they are **not** auto-discovered as
OpenCode commands because they target a different audience than
codebase maintainers.

| File | Description |
|------|-------------|
| `docs/skills/brand-strategy.md` | How to call `run_brand_strategy` MCP tool — parameters, output structure, error handling |
