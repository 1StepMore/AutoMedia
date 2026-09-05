# AutoMedia — Agent Codebase Context

First file an AI coding agent reads to understand the AutoMedia codebase. Read it fully before making any changes.

## 1. Project Overview
- **Language:** Python 3.11+
- **Size:** 33,619 LOC across 150 Python files (automedia/ core) · ~90,000 LOC across 442+ files (repo)
- **Key Dependencies:** typer (CLI), mcp (Python SDK), Pydantic 2.x, PyYAML, tenacity, Pillow
- **License:** MIT
- **Install:** `pip install -e ".[dev]"` (full capability) or `pip install -e ".[mcp]"` (MCP only). See README for prerequisites and all extras.

## 2. Three Entry Points
| Layer | Command | Description |
|-------|---------|-------------|
| MCP Server | `python -m automedia.mcp.server` | JSON-RPC over stdio, 67 tools |
| CLI | `automedia <subcommand>` | 19 commands via typer |
| SDK | `from automedia import run_full_pipeline` | Python API |

## 3. Directory Layout
```
AutoMedia/
├── src/
│   └── automedia/              # Core Python package (33,619 LOC)
│       ├── core/               # Foundation: config_loader (6-layer merge), project, credential_loader, doctor, overrides, llm_client, media_spec, workflow
│       ├── pipelines/          # runner.py (shared entry point), dag.py (26-node gate DAG), state_view.py, gate_engine, audio/image pipelines, language_config
│       ├── gates/              # 33 quality gates: base, failure_modes, G0-G6, V0-V7, H0, L1-L4 (D1-D7 and P1-P4 too)
│       ├── detectors/          # AI-writing-taste detectors: base, registry, deterministic, adapters
│       ├── hooks/              # Readonly observer protocol: protocol, md5_tracker, metrics
│       ├── cli/                # Typer CLI: app.py + 19 command modules
│       ├── mcp/                # FastMCP server, 67 tools; mcp_allowlist.yaml path allowlist
│       ├── adapters/           # Publish adapters: base, registry, publish_engine, platforms/
│       ├── accounts/           # PRD-4: AES-256-GCM credential store, registry, sessions, auth flows
│       ├── platform/           # Platform logic: xiaohongshu, zhihu_draft
│       ├── omni/               # Omni Triad: ol_adapter, opp_adapter, orf_adapter, registry, config, allowlist
│       ├── decision/           # Decision Layer (PRD-3)
│       ├── hitl/               # HITL framework: config, executor, presets
│       ├── pool/               # Topic pool (SQLite): db, collector, scorer, dedup
│       ├── cron/               # Scheduled job definitions
│       ├── prompts/            # Jinja2 prompt templates (platform-scoped)
│       ├── manifests/          # defaults.yaml, brand_profile_schema, model_config_schema
│       └── asset_library/      # Vector store: db, ingest, search, vector_store, migrate
├── docs/ · scripts/ · tests/   # Documentation (§13), build scripts, test suite (synthetic fixtures only)
├── deploy/ · .github/workflows/
└── pyproject.toml · .pre-commit-config.yaml · .env.example
```

## 4. Key Architecture Decisions
- **Gate Engine:** ordered gates with `failure_mode`: `"stop"` halts the pipeline, `"rewrite"` retries. Order: pre-gate → CW → G0-G6 → V0-V7 → H0 → L1-L4. Nine modes (`auto`, `text_only`, `text_with_cover`, `video_only`, `qa_only`, `image-carousel`, `social-thread`, `short-video`, `repurpose`) select gate subsets; D-gates (D1-D7) run standalone via CLI/MCP, P-gates (P1-P4) end repurpose. See `automedia/pipelines/runner.py`.
- **6-Layer Configuration:** built-in `defaults.yaml` → project `.automedia/` → user `~/.automedia/` → override rules → override prompts → `AUTOMEDIA_*` env vars + explicit overrides. See `automedia/core/config_loader.py`.
- **GateHook Observer Protocol:** readonly observers; never mutate or skip gates. Lifecycle: `before_gate()`, `after_gate()`, `on_gate_failed()`; each returns `None`. See `automedia/hooks/protocol.py`.
- **MD5 Tracking:** gates write product checksums to `pipeline_md5.json` in the project dir. See `automedia/hooks/md5_tracker.py`.
- **External Scheduling:** no built-in scheduler; external crond calls `automedia cron run`. See `automedia/cron/`.
- **Three-Entry-Point Design:** CLI, MCP, and SDK all delegate to `run_full_pipeline()` (see §2); MCP also exposes Omni triad tools (extract, translate, convert).
- **Gate Auto-Registration:** `BaseGate` subclasses auto-register in the global `GateRegistry` singleton via `__init_subclass__`.
- **Canonical Gate DAG:** `pipelines/dag.py` (`AUTO_GATE_DAG`, 26 nodes) + `pipelines/state_view.py` are an additive, order-equivalent representation of `_MODE_MAP` — mode gate lists stay authoritative, and the DAG layer adds topological/downstream/state queries on top.
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
pip install -e ".[dev]"      # install with dev deps
pytest                       # all tests
pytest --cov=src/automedia   # coverage
pytest tests/test_e2e/ -v    # E2E only
pytest -m e2e|redline|slow   # by marker
ruff check .                 # lint
mypy src/automedia/ --ignore-missing-imports   # type check
pre-commit run --all-files   # pre-commit
```
## 7. Test Conventions
- **Markers:** `e2e`, `redline`, `slow`, registered in `tests/conftest.py`
- **Fixtures:** Shared fixtures in `tests/conftest.py` use `tmp_path` for isolation; synthetic data only
- **Synthetic data:** Always use `tests/fixtures/synth/`; never production data
- **Public API surface:** Integration tests import from `automedia/__init__.py` (`run_full_pipeline`, `GateEngine`, `PipelineResult`)
- **Gate tests:** One test file per gate in `tests/` (e.g. `test_fact_check.py`, `test_humanizer.py`)
- **MCP tests:** `tests/test_mcp/`; **CLI tests:** `tests/test_cli/`

## 8. Common Task Patterns
### Add a New Gate
1. Create a file in `automedia/gates/` inheriting from `BaseGate`
2. Set class-level `_gate_name` (e.g. `"G6"`) and `_failure_mode` (`"stop"` or `"retry"`)
3. Implement `execute(self, gate_context: dict) -> dict`
4. Add a failure mode entry in `automedia/gates/failure_modes.py`
5. Add the gate name to the gate lists in `automedia/pipelines/runner.py` (`_AUTO_GATE_NAMES`, etc.)
6. Write an ADR entry in `docs/adr/` documenting the design decision
7. Create tests in `tests/test_gates/`

### Add a New CLI Command
1. Create a file in `automedia/cli/commands/`
2. Define a typer `app` with the command(s)
3. Register in `automedia/cli/app.py` via `app.add_typer()` (subcommand groups) or `app.command()` (standalone)

### Add a New Platform Adapter
1. Create an adapter class in `automedia/adapters/` implementing the adapter protocol
2. Register via `AdapterRegistry.register()`
3. Or use MCP tool `register_platform_adapter(platform_name="...", adapter_class="...")`

### Add a New MCP Tool
1. Define a module-level handler function in `automedia/mcp/server.py`
2. Register inside `create_server()` via `mcp.tool()`

### Add a New Environment Variable
1. Define it with the `AUTOMEDIA_` prefix
2. Add mapping in `_LLM_KEY_MAP` in `automedia/core/config_loader.py` if it maps under `llm.text_generation.*`
3. Add to the Config Key Reference section

## 9. MCP Tools Quick Reference (67 tools, incl. 4 deprecated aliases)

stdio transport. Start with `python -m automedia.mcp.server`. File ops gated by the `mcp_allowlist.yaml` path allowlist.

| Tool | Parameters | Description |
|------|-----------|-------------|
| `health_check` | — | Server health (version, uptime, tool count) |
| `select_topic` | category, tenant_id, pool_db_path | Select highest-scored pending topic |
| `research_topics` | category, count, trending | Research trending topics via LLM |
| `run_brand_strategy` | brand_name, industry, target_audience, context | Generate brand strategy via LLM |
| `run_pipeline` | topic, brand, mode, tenant_id, resume_from | Run full pipeline, async |
| `run_pipeline_from_strategy` | topic, brand, mode, strategy_context | Strategy via LLM, then pipeline |
| `get_pipeline_progress` | project_id | Poll gate-by-gate progress |
| `get_pipeline_state` | project_id, base_dir, mode | Per-gate state view (passed/failed/pending + md5) |
| `get_gate_report` | project_id, base_dir, latest | Latest gate-report JSON from 05_review/gate-report/ (base_dir must be allowlisted) |
| `get_pipeline_status` | project_id, base_dir | Query project status |
| `list_active_pipelines` | — | List active / recent pipelines |
| `list_projects` | base_dir, status | List projects under a directory |
| `get_project_assets` | project_dir | List project asset files |
| `archive_project` | project_id, base_dir, force | Archive a project (Red Line 8) |
| `list_topic_pool` | status, category, pool_db_path | List pool topics with filters |
| `register_platform_adapter` | platform_name, adapter_class | Register a publish adapter |
| `list_platforms` | — | List registered platforms |
| `extract_brief` | file_path, source_lang, target_lang | Extract brief via OPP |
| `localize_content` | md_content, source_lang, target_lang | Translate via OL shield pipeline |
| `localize_output` | project_dir, target_langs | Translate all drafts to target langs |
| `format_output` | content, target_format, **options | Convert format via ORF |
| `evaluate_content_quality` | content, criteria, brand | Score content quality |
| `analyze_content` | project_id | Content analytics stats |
| `distribute_content` | project_id, platforms, all, dry_run, base_dir | Distribute via D-gates |
| `connect_account` | platform, auth_type, credentials, label | Register a platform account |
| `list_accounts` | platform, status | List registered accounts |
| `get_account_health` | account_id | Check account health |
| `disconnect_account` | account_id | Remove an account |
| `add_pool_topic` | topic, category, source | Add topic to pool |
| `pool_add_topic` | topic, category, source | Deprecated: use add_pool_topic |
| `publish_content` | project_id, platform, mode | Publish a project |
| `run_batch` | topics, brand, mode | Run pipeline sequentially |
| `batch_run` | topics, brand, mode | Deprecated: use run_batch |
| `add_cron_schedule` | schedule, command | Add a cron schedule |
| `list_cron_schedules` | — | List cron schedules |
| `remove_cron_schedule` | schedule_id | Remove a cron schedule |
| `get_cron_health` | — | Cron config health |
| `test_cron_schedule` | expression, count | Validate cron expression |
| `search_assets` | query, brand, limit, filters | Keyword + semantic asset search |
| `list_brands` | — | List configured brands |
| `add_brand` | name, industry, target_audience | Create a brand profile |
| `get_config` | key | Merged config, secrets redacted |
| `init_config` | project_dir | Init `.automedia/` + default config |
| `configure_llm` | provider, model, api_key | Configure LLM provider |
| `onboard` | brand_name, llm_provider, llm_key, base_url | One-step onboarding |
| `get_redlines` | — | List red-line constraints |
| `cancel_pipeline` | project_id | Cancel a running pipeline |
| `pause_pipeline` | project_id | Pause a running pipeline |
| `resume_pipeline` | project_id | Resume a paused pipeline |
| `retry_gate` | project_id, gate_name | Mark a gate for retry |
| `skip_gate` | project_id, gate_name | Mark a gate for skipping |
| `review_decision` | project_id, gate_name, action, reason, show_diff | Approve/reject a pipeline paused at H0 (live HITL; same-process only) |
| `health_engine` | — | Engine dependency health |
| `engine_health` | — | Deprecated: use health_engine |
| `update_engine_config` | modality, setting, value | Update engine config |
| `help_mcp` | — | Categorized tool listing |
| `mcp_help` | — | Deprecated: use help_mcp |
| `list_validation_scenarios` | — | List validation scenario library |
| `run_validation_scenario` | scenario_name, runs_root, save | Run one validation scenario |
| `get_validation_report` | run_dir | Read a persisted run record |
| `validation_coverage_audit` | — | Static coverage audit |
| `validation_matrix` | — | Validation matrix render |

## 10. CLI Commands Quick Reference (19 commands)

| Command | Description |
|---------|-------------|
| `automedia run` | Run full production pipeline |
| `automedia pool` | Topic pool management (list, add, score) |
| `automedia projects` | List and manage projects |
| `automedia distribute` | Distribute to platforms (D-gates: --platforms, --all, --dry-run) |
| `automedia effects` | Content analytics stats |
| `automedia adapter` | Platform adapter management |
| `automedia cron` | Execute scheduled cron jobs |
| `automedia account` | Account management (connect, list, health, disconnect, refresh) |
| `automedia archive` | Archive a project (Red Line 8: --force unless published) |
| `automedia init` | Initialize configuration |
| `automedia doctor` | Check dependencies and environment health |
| `automedia omni` | Omni Triad operations (extract, translate, convert) |
| `automedia hitl` | Human-in-the-loop review operations |
| `automedia onboard` | Onboarding wizard |
| `automedia mcp` | MCP server management |
| `automedia history` | Pipeline execution history |
| `automedia pipeline` | Pipeline DAG export and state inspection (export-dag, state) |
| `automedia rollback` | Archive project, revert to draft |
| `automedia validate` | Validation suite (list, run, report, diff, coverage, matrix) |

## 11. Validation Layer

AutoMedia is agent-oriented; the validation framework makes agents the testers. Agents run real calls against the live surface, grade each response against a declared expect block, and write an immutable run record. Humans are the director: they review the record and its artifacts and sign it off. Nothing the agent decides alone is final, nothing the director has not seen is accepted.

### Driving surface

CLI (run from the repo root so relative artifact paths resolve):
- `automedia validate list`: load and list the scenario library
- `automedia validate run --scenario <name>`: run ONE named scenario; `--scenario` is required (the recursion bound); exits 1 on failed or hard-safety violations
- `automedia validate report [--run <name|latest>]`: render a run record
- `automedia validate diff [--baseline <path>]`: diff the latest two runs or a baseline
- `automedia validate coverage`: static coverage audit (CLI, MCP, gates, modes); exits 1 on declared-but-missing
- `automedia validate matrix`: per-scenario surface coverage + status matrix; non-recursive

MCP tools: `list_validation_scenarios`, `run_validation_scenario`, `get_validation_report`, `validation_coverage_audit`, `validation_matrix`.

### The evidence contract
**How to read a scenario (mirrors scenarios/README.md):**

1. `name` is the identity: unique across the library, survives file renames.
2. `description` says what the scenario proves, in one or two sentences.
3. `intent` says WHY it exists. Schema-required; read it first.
4. `requires_env` lists env vars; a missing one gates the scenario to `unconfigured`, never a pass.
5. `steps` are ordered; each is one real call plus an expect block; later steps can depend on earlier state.
6. Per step: `kind` picks the surface (`tool`, `cli`, `file`); `check` says WHAT to verify; `standard` cites a key in STANDARDS.md.
7. `expect` holds the assertions; every assertion present must hold.
8. `recovery_steps` repair state after a primary step fails; `cleanup_steps` remove scenario-created state. Neither proves capability.
9. Artifacts are the evidence: `collect_artifacts` copies files into the run record; `artifact_*` expect keys grade them.
10. `min_passing` / `pass_ratio` set the partial-pass policy; `regression` pins the scenario to a specific bug or fix.

**The 5 statuses:**
- `passed`: every primary step met its expect block and reached the surface.
- `failed`: a primary step failed its expect and no partial-pass policy saved it.
- `unconfigured`: a required env var was missing, so nothing ran. A state, never a verdict of acceptance.
- `recovered`: a primary step failed and a recovery step succeeded. The failure stays in the record; recovery never erases RED.
- `partial-pass`: some steps failed but `min_passing`/`pass_ratio` was met. Never hides a failure.

**Honesty rules:**
- Unconfigured never passes and never fails silently; the missing prerequisite is reported loudly with its reason.
- RED first. Record the honest negative state before fixing anything. GREEN with no recorded RED is suspect and re-run from the pre-flight baseline.
- Artifacts must be shown. GREEN means the call succeeded, the artifact exists, and it was carried to the director.
- Director sign-off: the director appends run name, date, and verdict to `signed.txt` in the run dir; the agent grades, the human disposes.

### Where things live
- `scenarios/`: committed scenario library (107 scenarios across cli/, journeys/, publish/, quality/, regression/, surface/, meta/, fixtures/, baseline/).
- `scenarios/STANDARDS.md`: handbook of standard keys (14 core plus 33 `gate.*` and 9 `mode.*`); unknown keys rejected at load.
- `scenarios/baseline/`: committed pre-flight baseline run record and coverage audit.
- `validation-runs/`: gitignored immutable run records with a `latest.txt` pointer.
- `AUTOMEDIA_VALIDATION_SCENARIOS_DIR`: env override for the scenarios directory.

Any agent can drive this layer standalone (Hermes, Claude Code, Codex CLI, OpenCode); the surface is CLI and MCP only. See `scenarios/README.md` for the full reference.

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
| `AUTOMEDIA_FAKE_LLM` | Set to `1` for deterministic mock LLM responses | (unset) |
| `AUTOMEDIA_DEFAULT_BRAND` | Default brand for pipelines | `my-brand` |
| `AUTOMEDIA_FEATURE_TIER` | Open-core tier override: core\|pro\|enterprise; gates above the override tier are excluded at gate-list composition (declarative; unset = all tiers available) | (unset) |
| `AUTOMEDIA_DATA_DIR` | Data directory | `./data` |
| `AUTOMEDIA_OUTPUT_DIR` | Output directory | `./output` |
| `AUTOMEDIA_PROJECTS_DIR` | Projects root override | (auto) |

These env vars map to `llm.text_generation.*` config keys in `automedia/core/config_loader.py`.

## 13. Documentation Index
| File | Content |
|------|---------|
| `docs/dev/developer-guide.md` | Full developer guide (enforcement mechanisms, PRD-4 summary, ADRs) |
| `docs/user/api-reference.md` | SDK API reference |
| `docs/user/cli-reference.md` | CLI command reference |
| `docs/user/mcp-setup.md` | MCP server setup guide (systemd deployment, error code reference) |
| `docs/user/hitl-framework.md` | Human-in-the-loop framework docs |
| `docs/user/omni-integration.md` | Omni Triad integration docs |
| `docs/user/asset-library.md` | Asset library documentation |
| `docs/glossary.md` | Plain-language AutoMedia term glossary for agents |
| `docs/adr/README.md` | ADR index + template (`docs/adr/TEMPLATE.md`), immutable decision records |
| `docs/dev/gate-failure-modes.md` | Gate failure troubleshooting |
| `docs/user/production-workflow.md` | Production operations guide |
| `docs/dev/cron-troubleshooting.md` | Cron job debugging |
| `docs/dev/api-gotchas.md` | Common API pitfalls |
| `docs/dev/override-reference.md` | Override system reference (rules, prompts, platform scoping) |
| `CHANGELOG.md` | Version history |
| `docs/dev/agent-troubleshooting.md` | Agent troubleshooting guide for pipeline, config, MCP, and gate issues |
| `docs/dev/七阶段AI开发流程-用CodingAgent交付成品的方法论.md` | 7-phase AI development methodology note (own your process, AFK implementation) |
| `docs/archived/` | One-off historical reports (migration guides, per-run acceptance, superseded master plans) — not authoritative |
| `docs/doc-inventory.md` | AUTO-GENERATED doc inventory — regenerate with `python3 scripts/doc_inventory.py`; never hand-edit |

For troubleshooting common issues, see [Agent Troubleshooting Guide](docs/dev/agent-troubleshooting.md).

## 14. Skills
Agent skills live in `.opencode/skills/` (canonical), with native copies synced to `.claude/skills/` and `.codex/skills/`. Cline references `.opencode/skills/` directly. When updating a skill, edit the canonical file and sync the copies.

- `project-validation`: Post-change validation against founder expectations
- `doc-sync`: Documentation impact mapping when code changes affect docs (CLI/MCP tools, gates, config, API, pipelines, adapters)
- `validation-runner`: Dev-side validation workflow; author regression scenarios on every bug fix; RED to GREEN evidence
- `deep-modules`: Deep-module refactoring practice (Ousterhout, methodology §3.1)

## 15. User-Facing Skills (for Agents Using AutoMedia)
Skills for agents who USE AutoMedia (calling MCP tools to produce content) live in `docs/skills/`. They are not auto-discovered as OpenCode commands; they target users, not codebase maintainers.

| File | Description |
|------|-------------|
| `docs/skills/brand-strategy.md` | How to call `run_brand_strategy` MCP tool: parameters, output structure, error handling |
