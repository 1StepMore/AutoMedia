# AutoMedia Agent Reference

Deep reference split out of `AGENTS.md` (plan T-14) so the root agent file stays
under 200 lines. Read the section you need — none of it is required up front.

## Directory Layout

```
AutoMedia/
├── src/
│   └── automedia/              # Core Python package (22 subpackages; size claims live in AGENTS.md)
│       ├── core/               # Foundation: config_loader (6-layer merge), project, credential_loader, doctor, overrides, llm_client, media_spec, workflow, md5_tracker
│       ├── pipelines/          # runner.py (shared entry point), gate_plan.py (per-mode gate lists — THE authority), dag.py (26-node gate DAG), state_view.py, gate_engine, audio/image pipelines, language_config
│       ├── gates/              # 33 quality gates: base, failure_modes, G0-G6, V0-V7, H0, L1-L4 (D1-D7 and P1-P4 too)
│       ├── detectors/          # AI-writing-taste detectors: base, registry, deterministic, adapters
│       ├── engines/            # Media engine backends: base, errors, registry, implementations/ (asr_whisper, asr_faster_whisper, tts_edge, tts_piper, image_comfyui, image_local, video_hyperframes)
│       ├── effects/            # Content analytics: stats (word count, sentiment, readability, brand mentions, SEO) + cli/mcp entry points
│       ├── validation/         # Agent-tester validation layer: engine, schema, coverage, matrix, persist, signoff, standards, doc_reality
│       ├── features/           # Open-core feature tier marker (declarative only — no license enforcement)
│       ├── templates/          # Render templates: hyperframes/ (HTML/Jinja2 scene templates + package.json)
│       ├── hooks/              # Readonly observer protocol: protocol, cost_tracker, pipeline_history
│       ├── cli/                # Typer CLI: app.py + command modules under commands/ (19 commands)
│       ├── mcp/                # FastMCP server, 68 tools; mcp_allowlist.yaml path allowlist; tools/* handler modules
│       ├── adapters/           # Publish adapters: base, registry, publish_engine, platforms/
│       ├── accounts/           # PRD-4: AES-256-GCM credential store, registry, sessions, auth flows
│       ├── omni/               # Omni Triad: ol_adapter, opp_adapter, orf_adapter, registry, config, allowlist
│       ├── decision/           # Decision Layer (PRD-3)
│       ├── hitl/               # HITL framework: config, executor, presets
│       ├── pool/               # Topic pool (SQLite): db, collector, scorer, dedup
│       ├── cron/               # Scheduled job definitions
│       ├── prompts/            # Jinja2 prompt templates (platform-scoped)
│       ├── manifests/          # defaults.yaml, brand_profile_schema, model_config_schema
│       └── asset_library/      # Vector store: db, ingest, search, vector_store, migrate
├── docs/ · scripts/ · tests/   # Documentation, build scripts, test suite (synthetic fixtures only)
├── deploy/ · .github/workflows/
└── pyproject.toml · .pre-commit-config.yaml · .env.example
```

## Common Task Patterns

### Add a New Gate
1. Create a file in `automedia/gates/` inheriting from `BaseGate`
2. Set class-level `_gate_name` (e.g. `"G6"`) and `_failure_mode` (`"stop"` or `"retry"`)
3. Implement `execute(self, gate_context: dict) -> dict`
4. Add a failure mode entry in `automedia/gates/failure_modes.py`
5. Add the gate name to the mode gate lists in `automedia/pipelines/gate_plan.py` (`MODE_GATE_NAMES` / `_AUTO_GATE_NAMES`, etc.) — this module is the single authority; `runner.py` only re-exports it.
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
1. Define the handler function in the matching module under `automedia/mcp/tools/` (one module per domain: `pipeline.py`, `topics.py`, `cron_tools.py`, `brands.py`, …)
2. Import it into `create_server()` in `automedia/mcp/server.py` and register it via `mcp.tool()` — `server.py` only wires registration, it holds no handlers

### Add a New Environment Variable
1. Define it with the `AUTOMEDIA_` prefix
2. Add mapping in `_LLM_KEY_MAP` in `automedia/core/config_loader.py` if it maps under `llm.text_generation.*`
3. Add to the Config Key Reference below

## Validation Layer

AutoMedia is agent-oriented; the validation framework makes agents the testers.
Agents run real calls against the live surface, grade each response against a
declared expect block, and write an immutable run record. Humans are the
director: they review the record and its artifacts and sign it off. Nothing the
agent decides alone is final, nothing the director has not seen is accepted.

### Driving surface

CLI (run from the repo root so relative artifact paths resolve):
- `automedia validate list`: load and list the scenario library
- `automedia validate run --scenario <name>`: run ONE named scenario; `--scenario` is required (the recursion bound); exits 1 on failed or hard-safety violations
- `automedia validate report [--run <name|latest>]`: render a run record
- `automedia validate diff [--baseline <path>]`: diff the latest two runs or a baseline
- `automedia validate coverage`: static coverage audit (CLI, MCP, gates, modes); exits 1 on declared-but-missing
- `automedia validate matrix`: per-scenario surface coverage + status matrix; non-recursive
- `automedia validate sign`: record the director's verdict in the run dir's `signed.txt`

MCP tools: `list_validation_scenarios`, `run_validation_scenario`, `run_validation_suite`, `get_validation_report`, `validation_coverage_audit`, `validation_matrix`.

### Per-run sandbox

Every run installs a sandbox (`automedia.validation.sandbox`) before the env
gate: `AUTOMEDIA_CONFIG_DIR` and `AUTOMEDIA_PROJECTS_DIR` point at a fresh
`config/` + `projects/` pair under one `automedia-validation-*` temp root, and
the root is removed when the run ends. This is what makes validation
non-destructive: accounts, brand profiles, `active_pipelines.json`, and project
dirs land in scratch space instead of `~/.automedia` and the repo root, and a
second identical run starts from a clean slate (#333/#334). An explicitly
exported directory is honoured (only the missing half is filled in);
`AUTOMEDIA_VALIDATION_KEEP_SANDBOX=1` preserves the root for inspection. The
run record carries `sandbox: {root, config_dir, projects_dir, temporary}` at
the top level and on each scenario. CLI steps expand `${VAR}` in `command`,
tool/post-call arguments, and artifact paths, so scenarios reference the
sandbox by name instead of hardcoding a path.

### The evidence contract

The single schema authority is `scenarios/STANDARDS.md`; `scenarios/README.md`
is the onboarding guide. How to read a scenario:

1. `name` is the identity: unique across the library, survives file renames.
2. `description` says what the scenario proves, in one or two sentences.
3. `intent` says WHY it exists. Schema-required; read it first.
4. `requires_env` lists env vars; a missing one gates the scenario to `unconfigured`, never a pass.
5. `steps` are ordered; each is one real call plus an expect block; later steps can depend on earlier state.
6. Per step: `kind` picks the surface (`tool`, `cli`, `file`); `check` says WHAT to verify; `standard` cites a key in `STANDARDS.md`.
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
- `scenarios/`: committed scenario library (160 scenarios across cli/, journeys/, publish/, quality/, regression/, surface/, production/, meta/, fixtures/, baseline/).
- `scenarios/STANDARDS.md`: the single schema authority — standard keys (23 core plus 33 `gate.*` and 9 `mode.*`); unknown keys rejected at load.
- `scenarios/baseline/`: committed pre-flight baseline run record and coverage audit.
- `validation-runs/`: gitignored immutable run records with a `latest.txt` pointer.
- `AUTOMEDIA_VALIDATION_SCENARIOS_DIR`: env override for the scenarios directory.

Any agent can drive this layer standalone (Hermes, Claude Code, Codex CLI, OpenCode); the **validation-driving surface is the CLI and the MCP server only**. The Python SDK (`automedia/__init__.py`, 19 public symbols) is a **product entry point, not a validation-driving surface**: agents drive real calls through the CLI and MCP, and the SDK's behavior is exercised transitively where those entry points delegate to the same `run_full_pipeline()` implementation. No SDK scenario is added to `scenarios/`; SDK-only behavior is explicitly out of validation scope. See `scenarios/README.md` for the full reference.

## Config Key Reference

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
| `AUTOMEDIA_ASSET_LIBRARY` | AssetLibrary root pulled into new projects; unset uses the built-in workspace default | `/mnt/d/Hermes-Workspace/01-Projects/AutoMedia/AssetLibrary` |
| `AUTOMEDIA_SKIP_ASSET_PULL` | Set to `1`/`true`/`yes` to skip the project-init asset pull | (unset) |

The `AUTOMEDIA_LLM_*` vars map to `llm.text_generation.*` config keys in `automedia/core/config_loader.py`. See `.env.example` for the complete list.

Optional engine extras and their version constraints:

- `[tts-piper]` installs Piper TTS.
- `[asr-faster]` installs `faster-whisper` **and** `av<19`. The upper bound is
  required: av 19 removed the `metadata_errors` kwarg that faster-whisper 1.2.x
  still passes to `av.open`, so `transcribe()` raises `TypeError` even though
  `import faster_whisper` succeeds. `FasterWhisperASREngine.check_available()`
  therefore decodes 10 ms of silence in memory, reporting the incompatible
  combination as unavailable instead of failing mid-pipeline (issue #332).

## Documentation Index

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
| `docs/dev/agent-troubleshooting.md` | Agent troubleshooting guide for pipeline, config, MCP, and gate issues |
| `docs/dev/founder-expectations.md` | Timestamped founder expectation baseline — **historical snapshot, do not refresh** |
| `docs/dev/evaluation-matrix-principles.md` | How the evaluation matrix is scored |
| `docs/dev/forward-compat.md` | Forward-compatibility rules for schema evolution |
| `docs/dev/project-validation-framework.md` | Structural validation framework |
| `docs/dev/validation-loop-log.md` | Running log of validation loop iterations |
| `docs/dev/plans/NIGHTLY.md` | Nightly re-run plan + latest gap report |
| `docs/dev/deep-module-rfc-001.md` | Deep-module refactor RFC for `runner.py` (see its Status header) |
| `docs/user/deployment.md` | Deployment options comparison (Docker, native pip, systemd, Windows) |
| `docs/user/windows-deployment.md` | Windows setup: WSL2, Docker Desktop, native |
| `docs/user/user-introduction.md` | Getting-started walkthrough for new users |
| `docs/skills/` | User-facing MCP how-to skills (see §User-Facing Skills) |
| `CHANGELOG.md` | Version history |
| `docs/dev/七阶段AI开发流程-用CodingAgent交付成品的方法论.md` | 7-phase AI development methodology note (own your process, AFK implementation) |
| `docs/archived/` | One-off historical reports (migration guides, per-run acceptance, superseded master plans) — not authoritative |
| `docs/doc-inventory.md` | AUTO-GENERATED doc inventory — regenerate with `python3 scripts/doc_inventory.py`; never hand-edit |

## Skills

Agent skills live in `.opencode/skills/` (canonical). `.claude/skills/` and `.codex/skills/` hold synced copies (currently 4 of the 6 — `issue-triage` and `pr-review-merge` are canonical-only). Cline references `.opencode/skills/` directly. When updating a skill, edit the canonical file and sync the copies.

- `project-validation`: Post-change validation against founder expectations
- `doc-sync`: Documentation impact mapping when code changes affect docs (CLI/MCP tools, gates, config, API, pipelines, adapters)
- `validation-runner`: Dev-side validation workflow; author regression scenarios on every bug fix; RED to GREEN evidence
- `deep-modules`: Deep-module refactoring practice (Ousterhout, methodology §3.1)
- `issue-triage`: Triage incoming issues into the repository's label/priority conventions
- `pr-review-merge`: PR review and merge workflow

## User-Facing Skills

Skills for agents who USE AutoMedia (calling MCP tools to produce content) live in `docs/skills/`. They are not auto-discovered as OpenCode commands; they target users, not codebase maintainers.

| File | Description |
|------|-------------|
| `docs/skills/brand-strategy.md` | How to call `run_brand_strategy` MCP tool: parameters, output structure, error handling |
| `docs/skills/pipeline-workflow.md` | End-to-end pipeline run: mode selection, gate progression, resuming |
| `docs/skills/batch-workflow.md` | Batch production across multiple topics via `run_batch` |
| `docs/skills/distribution-workflow.md` | Distributing finished content to platforms via the D-gates |
