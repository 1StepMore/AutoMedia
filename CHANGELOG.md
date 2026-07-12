# Changelog

## [Unreleased]

### Added

#### Account & Publishing Management (PRD-4)

- **Encrypted Credential Store**: AES-256-GCM encrypted storage for platform credentials with atomic index writes and fingerprint deduplication (`accounts/store.py`)
- **Account Registry**: Full CRUD for platform accounts with label uniqueness enforcement per platform (`accounts/registry.py`)
- **Auth Flow Engine**: OAuth2 Client Credentials and Authorization Code flows with PKCE/state support, localhost server for interactive login, Cookie auth, API Key auth (`accounts/auth/`)
- **Session Manager**: TTL-aware token cache with per-account thread-safe locking, rate-limit backoff with configurable cooldown (`accounts/session.py`)
- **Account Models**: Pydantic v2 models for account metadata, credentials, sessions (`accounts/models.py`)
- **Platform Adapter Auth Integration**: `authenticate()`, `refresh_session()`, `check_health()`, `get_analytics()` methods on `BasePlatformAdapter` with concrete defaults; `account_ids` parameter on `PublishEngine.publish_all()` with partial failure continuation
- **CLI**: `automedia account connect|list|health|disconnect|refresh` — 5 subcommands (16 total)
- **MCP Tools**: `connect_account`, `list_accounts`, `get_account_health`, `disconnect_account` — 4 new tools (18 total)
- **Credential Bridging**: `load_credential_with_account_fallback()` in `credential_loader.py` for backward-compatible credential resolution
- **Test Coverage**: 191 PRD-4-specific tests across accounts models, store, registry, auth flows, session, CLI, and MCP — all passing

#### Security

- **Master Key Encryption**: All platform credentials encrypted at rest with AES-256-GCM; key derived from `AUTOMEDIA_MASTER_KEY` environment variable via SHA-256
- **Credential Leak Prevention**: `SessionToken.__repr__` masks access/refresh tokens (shows first 8 chars); account credentials never appear in logs or MCP responses

## [1.0.0] - 2026-07-07

### Added

#### Core Library

- **Three-Layer Entry Points**: Python SDK (`from automedia import run_full_pipeline`), CLI (`automedia`), MCP Server (`python -m automedia.mcp.server`) three ways to invoke the pipeline
- **Configuration System**: Six-layer priority config loading (`config_loader.py`), supports built-in defaults, project-level, user-level, overrides, environment variables
- **Project Management**: `Project.init()` creates standard directory structure, automatic slugify and safe path validation
- **Credential Management**: Four-layer credential loading (`credential_loader.py`): environment variables > keyring > oscreds.yaml > credentials.yaml
- **Health Checks**: `Doctor` class checks python/bun/ffmpeg/whisper/edge-tts/comfyui/chrome dependencies

#### Pipeline Orchestration

- **GateEngine**: Sequential Gate execution engine, supports "stop" and "rewrite" failure modes
- **`run_full_pipeline()`**: Complete pipeline execution function, supports mode/resume_from/config_dir/tenant_id parameters
- **Four Run Modes**: auto (full pipeline), text_only (copy only), video_only (video only), qa_only (QA only)

#### Gate System

- **BaseGate** abstract base class, auto-registers to `GateRegistry`
- **Copy Gates (G0-G5)**: Fact check, Humanizer (de-AI-ify), copy review, brand CTA, WeChat checks, HTML hard gate
- **Video Gates (V0-V7)**: Lint, Vision QA, Pre-Send Whisper, content semantic, TTS brand asset, MP3 vs SRT, subtitle render, six-step hard gate
- **Lifecycle Gates (L1-L3)**: Publish log schema, archive validation, platform integrity
- **Failure Mode Knowledge Base**: `failure_modes.py` records common failure reasons and fix steps for each Gate

#### Hook System

- **GateHook Protocol**: Readonly observer pattern, three methods: `before_gate`, `after_gate`, `on_gate_failed`
- **MD5 Tracking**: `md5_tracker.py` records and verifies MD5 hashes for each Gate's output (Red Line 7)

#### CLI

- `automedia run`: Execute pipeline, supports --mode, --resume-from, --timeout
- `automedia pool`: Topic pool management (list/add/prune/attach-brief)
- `automedia projects`: Project listing and details (list/get/get-assets)
- `automedia archive`: Project archive (Red Line 8 enforced)
- `automedia adapter`: Platform adapter management (list/create)
- `automedia cron`: Scheduled task execution and health check (run/check-health)
- `automedia init`: Interactive/minimal config initialization
- `automedia doctor`: Dependency and environment health check
- `automedia omni`: Omni Triad operations (extract/translate/convert)
- `automedia hitl`: Human-in-the-loop review flow (config/preset)
- `automedia license`: License management (check/features)
- `automedia sop`: SOP flow execution (generate)
- `automedia tenant`: Multi-tenant management (create/list/delete/invite/members/audit-log)
- `automedia solution`: Decision layer solutions (next-node/approve-node/complete-node/preflight-check/validate-artifact)
- `automedia onboard`: Guided configuration wizard (list)

Total 15 top-level commands, 50+ subcommands.

#### MCP Server

- 13 MCP tools: select_topic, run_pipeline, get_pipeline_progress, get_pipeline_status, list_projects, get_project_assets, archive_project, list_topic_pool, register_platform_adapter, extract_brief, localize_content, localize_output, format_output
- Path allowlist security mechanism
- stdio transport, compatible with Claude Desktop / OpenCode / Cline / Codex CLI / Hermes Agent

#### Adapter System

- **BasePlatformAdapter**: Abstract base class defining publish/validate/platform_name
- **AdapterRegistry**: Global singleton registry, supports register/get/list/clear
- **Template Generation**: `automedia adapter create` generates adapter template code

#### Topic Pool

- **PoolDB**: SQLite topic pool CRUD, supports schema creation and migration
- **Scoring and Dedup**: Basic scorer and deduplication logic

#### Tech Stack

- Python 3.11+
- Typer (CLI)
- Pydantic 2.x (data models)
- PyYAML (configuration)
- MCP official Python SDK (MCP Server)
- SQLite3 (topic pool)

#### Documentation

- **Developer Guide** (`docs/developer-guide.md`)
- **API Reference** (`docs/api-reference.md`)
- **CLI Reference** (`docs/cli-reference.md`)
- **MCP Setup Guide** (`docs/mcp-setup.md`)
- **Runbook**: Gate failure modes / Cron debugging / API pitfalls / Production workflow

### Changed

- Hermes Agent v0.17 coupling fully decoupled, all 20 coupling points resolved (17 resolved, 3 isolated)
- `skill_view(name='...')` to pure Python class + typer CLI
- `execute_code` sandbox to pure Python execution
- Hermes cron to external crond + `automedia cron run`
- `~/.hermes/` to `~/.automedia/` config directory
- OpenCode Go binding to swappable provider (OpenAI/Anthropic)
- Brand hardcoding to brand-profile.yaml configuration
- MiniMax API dependency completely removed

### Removed

- Hermes Agent runtime dependency
- `sys.path.insert` hack
- All user home directory and workspace hardcoded paths removed
- `hermes.*` runtime API calls
- Hermes proprietary log format and cron jobs.json

### Security

- Path safety: `sanitize_path()` rejects path traversal (`..`, `~`, `//`)
- Archive red line: agents must not archive, only user `--force` can bypass
- MCP path allowlist
- Credentials are not written to config files, loaded via environment variables or keyring
- tenant_id field reserved (multi-tenant foundation)
