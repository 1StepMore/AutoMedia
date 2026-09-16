# AutoMedia — Agent Codebase Context

First file an AI coding agent reads. This is the map; deep detail lives in
[docs/dev/agent-reference.md](docs/dev/agent-reference.md) (on-demand) and the inline links below.

## 1. Project Overview
- **Language:** Python 3.11+
- **Size:** 62,461 LOC across 252 Python files (automedia/ core) · ~183,000 LOC across 737+ files (repo)
- **Key Dependencies:** typer (CLI), mcp (Python SDK), Pydantic 2.x, PyYAML, tenacity, Pillow
- **License:** MIT
- **Install:** `pip install -e ".[dev]"` (full capability) or `pip install -e ".[mcp]"` (MCP only). See README for prerequisites and all extras.

## 2. Three Entry Points
| Layer | Command | Description |
|-------|---------|-------------|
| MCP Server | `python -m automedia.mcp.server` | JSON-RPC over stdio, 68 tools |
| CLI | `automedia <subcommand>` | 19 commands via typer |
| SDK | `from automedia import run_full_pipeline` | Python API |

## 3. Directory Layout
Full tree: [agent-reference §Directory Layout](docs/dev/agent-reference.md#directory-layout). Core shape:
```
src/automedia/
├── core/        # config_loader (6-layer merge), project, doctor, overrides, llm_client, media_spec, workflow
├── pipelines/   # runner.py, dag.py (26-node gate DAG), state_view.py, gate_engine, audio/image pipelines
├── gates/       # 33 quality gates: G0-G6, V0-V7, H0, L1-L4, D1-D7, P1-P4
├── cli/ mcp/    # Typer CLI (19 commands) · FastMCP server (68 tools)
├── detectors/ hooks/ adapters/ accounts/ omni/ decision/ hitl/ pool/ cron/ prompts/ manifests/ asset_library/
docs/ · scripts/ · tests/ · deploy/ · .github/workflows/
└── pyproject.toml · .pre-commit-config.yaml · .env.example
```

## 4. Key Architecture Decisions
- **Gate Engine:** ordered gates with `failure_mode`: `"stop"` halts the pipeline, `"rewrite"` retries. Preset order: pre-gate → CW → G0-G3 → G6 → V0-V7 → H0 (G4/G5 and L1-L4 stay registered but are in no preset; L1-L4 run via their lifecycle commands). Nine modes (`auto`, `text_only`, `text_with_cover`, `video_only`, `qa_only`, `image-carousel`, `social-thread`, `short-video`, `repurpose`) select gate subsets; D-gates (D1-D7) run standalone via CLI/MCP, P-gates (P1-P4) end repurpose. See `automedia/pipelines/runner.py`.
- **6-Layer Configuration:** built-in `defaults.yaml` → project `.automedia/` → user `~/.automedia/` → override rules → override prompts → `AUTOMEDIA_*` env vars + explicit overrides. See `automedia/core/config_loader.py`.
- **GateHook Observer Protocol:** readonly observers; never mutate or skip gates. Lifecycle: `before_gate()`, `after_gate()`, `on_gate_failed()`; each returns `None`. See `automedia/hooks/protocol.py`.
- **MD5 Tracking:** gates write product checksums to `pipeline_md5.json` in the project dir. See `automedia/hooks/md5_tracker.py`.
- **External Scheduling:** no built-in scheduler; external crond calls `automedia cron run --due` (dispatches every schedule entry due now; `automedia cron run <job>` remains the explicit single-job path). See `automedia/cron/`.
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
Full recipes (add a gate / CLI command / platform adapter / MCP tool / env var):
[agent-reference §Common Task Patterns](docs/dev/agent-reference.md#common-task-patterns).

## 9. MCP Tools Quick Reference (68 tools, incl. 4 deprecated aliases)

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
| `list_overridable_templates` | — | List overridable prompt templates + override status |
| `list_workflows` | — | List configured workflows from workflows.yaml |
| `approve_gate` | gate_name | Approve a paused gate in director mode (HITL) |
| `reject_gate` | gate_name, reason | Reject a paused gate (triggers failure handling) |
| `get_pending_approvals` | — | List gates awaiting human approval in director mode |
| `list_validation_scenarios` | — | List validation scenario library |
| `run_validation_scenario` | scenario_name, runs_root, save | Run one validation scenario |
| `run_validation_suite` | scenarios_dir, runs_root, save | Run the whole validation library; persist one suite record |
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
| `automedia validate` | Validation suite (list, run, report, diff, coverage, matrix, sign) |

## 11. Validation Layer
AutoMedia is agent-oriented, so agents are the testers and humans are the director. The single
schema authority is `scenarios/STANDARDS.md`; `scenarios/README.md` is the onboarding guide.
- Scenario library: 142 scenarios; `scenarios/baseline/` holds the committed pre-flight baseline.
- CLI: `automedia validate list|run|report|diff|coverage|matrix|sign`
- MCP: `list_validation_scenarios`, `run_validation_scenario`, `run_validation_suite`, `get_validation_report`, `validation_coverage_audit`, `validation_matrix`
- The validation-driving surface is the CLI and MCP server only; the SDK is a product entry point, explicitly out of validation scope.
Full evidence contract (5 statuses, honesty rules, where things live): [agent-reference §Validation Layer](docs/dev/agent-reference.md#validation-layer).

## 12. Config, Docs, and Skills
- **Config keys:** `.env.example` and [agent-reference §Config Key Reference](docs/dev/agent-reference.md#config-key-reference)
- **Documentation index:** [docs/index.md](docs/index.md) and [agent-reference §Documentation Index](docs/dev/agent-reference.md#documentation-index)
- **Maintainer skills:** `.opencode/skills/` — `project-validation`, `doc-sync`, `validation-runner`, `deep-modules`
- **User-facing skills:** `docs/skills/brand-strategy.md`

For troubleshooting common issues, see [Agent Troubleshooting Guide](docs/dev/agent-troubleshooting.md).
