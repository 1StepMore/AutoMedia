# Doc-Sync — Documentation Awareness & Impact Mapping

**Purpose:** When code changes happen in this project, agents use this skill to identify **exactly which documentation files need updating** and **what sections to change**.

---

## When to Use (Triggers)

Load this skill automatically whenever any change touches:

| Trigger | Example |
|---------|---------|
| **CLI command** added/removed/renamed/param-changed | `automedia/cli/commands/` |
| **MCP tool** added/removed/renamed/param-changed | `automedia/mcp/server.py`, `automedia/mcp/tools.py`, `automedia/mcp/accounts.py` |
| **Gate** added/removed/renamed/behavior-changed | `automedia/gates/` |
| **API signature** changed | `automedia/pipelines/runner.py`, `automedia/__init__.py` |
| **Config key / env var** added/removed | `automedia/core/config_loader.py`, `.env.example` |
| **Pipeline mode** changed | `automedia/pipelines/runner.py` |
| **Feature area** modified (Omni, HITL, Asset Lib, Accounts, etc.) | The feature's source directory |
| **Dependency / install** changed | `pyproject.toml`, `Makefile` |
| **Deploy / Docker / systemd** changed | `Dockerfile`, `docker-compose.yml`, `deploy/` |
| **Override system** changed | `automedia/core/overrides.py` |
| **Workflow system** changed | `automedia/core/workflow.py` |
| **Forward compat** policy changed | `docs/dev/forward-compat.md` |
| **Founder expectations** changed | `docs/dev/founder-expectations.md` |
| **Doc nav / site structure** changed | `mkdocs.yml` |
| **New feature / subsystem** landed | Any new `src/automedia/` directory |
| **CHANGELOG** needed | Any user-visible change |
| **doc-sync itself** (this skill) | `.opencode/skills/doc-sync.md` + agent sync copies |

---

## Step 0 — Read the Existing Docs

Before editing any doc, **read the current version** of the affected files to know what to preserve and what to update. Do not overwrite content you haven't read.

---

## Step 1 — DOC MAP: Complete Documentation Inventory

Every doc file in the project, what it covers, and who it's for.

### Root docs (human + agent entry points)

| File | Coverage | Triggers |
|------|----------|----------|
| `AGENTS.md` | Agent-role context, directory layout, 3 entry points, gate list + ordering, MCP tool table (52 tools), CLI command table (16 commands), config key ref, doc index, skills list, 10 red lines, architecture decisions | Gate count/tools/commands change, config keys, new skills, architecture changes |
| `README.md` | Project overview, install instructions, three-layer API, agent quickstart, gate system summary, architecture diagram, config hierarchy, tech stack, security, deployment options, doc index | CLI/MCP tool counts, gate counts, install deps, feature additions, deployment changes |
| `CHANGELOG.md` | Version history with Added/Fixed/Changed/Docs sections | Every user-visible change (features, fixes, breaking changes, doc updates) |

### `docs/` — User docs (operators, human users)

| File | Coverage | Triggers |
|------|----------|----------|
| `docs/index.md` | Mkdocs home — feature summary, quick start, doc index links, agent info | Feature additions, gate count changes, doc structure changes |
| `docs/user/api-reference.md` | `run_full_pipeline()` params, `PipelineResult`, `GateEngine`, `GateRegistry`, `GateHook`, `AccountRegistry`, `AccountStore`, `AuthFlowEngine`, `SessionManager`, `Doctor`, `Project`, `Evaluator`, path safety | API signature changes, new public classes, account subsys changes |
| `docs/user/cli-reference.md` | 16 CLI commands with full param docs, MCP-CLI equivalence table | CLI command add/remove/rename, param changes |
| `docs/user/mcp-setup.md` | MCP server start, tool list (52), client config (Claude, OpenCode, Codex, Cline, Cursor), env var table, systemd deploy, error codes | MCP tool add/remove/rename, client config changes, systemd changes, env vars |
| `docs/user/deployment.md` | 4 deployment method comparison table (Docker, native, systemd, Windows), Docker Compose profiles | Dockerfile changes, compose changes, systemd changes, new deployment method |
| `docs/user/production-workflow.md` | Daily schedule, pre-production checks, topic ops, distribution ops, archive ops, cron config, gate progress | Cron jobs, publishing flow, archive behavior, pipeline resume behavior |
| `docs/user/hitl-framework.md` | HITL concept, 3 presets (automated, semi-automated, director), CLI/MCP usage, override config | Director mode, HITL presets, gate approval flow changes |
| `docs/user/omni-integration.md` | OPP/OL/ORF architecture, MCP-CLI equivalence, install, standalone servers, usage | Omni adapter changes, new triad tools |
| `docs/user/asset-library.md` | SQLite+Chroma architecture, ingest/search/archive API, auto-ingest hook, migration | Asset library code changes, schema changes, search changes |
| `docs/user/user-introduction.md` | High-level project intro for end users | Major feature additions |
| `docs/user/windows-deployment.md` | Windows-specific install via WSL2, Docker Desktop, native | Windows-specific changes |

### `docs/dev/` — Developer docs (contributors, agents maintaining the code)

| File | Coverage | Triggers |
|------|----------|----------|
| `docs/dev/developer-guide.md` | Full from-scratch setup, prerequisites, install, CLI usage, test commands, enforcement mechanisms, ADRs, PRD-4 summary | Install deps, test commands, make targets, new developer-facing features |
| `docs/dev/agent-troubleshooting.md` | Pipeline failures, config issues, MCP connection issues, gate failures, env vars, FFmpeg/Chrome issues, account auth issues | Troubleshooting scenarios, error codes, env vars, dependency changes |
| `docs/dev/gate-failure-modes.md` | Per-gate failure diagnosis + remediation, organized by gate name | New gates, gate behavior changes, failure mode additions |
| `docs/dev/cron-troubleshooting.md` | Cron syntax, direct execution, log inspection, service management | Cron implementation changes, new scheduled jobs |
| `docs/dev/api-gotchas.md` | Common mistakes — topic slugification, config layering, credential loading, brand profiles, gate ordering, MD5 tracking, evaluate_content_quality | API behavior changes that could cause confusion |
| `docs/dev/override-reference.md` | Override dir layout, 11 prompt template ref, rule schema, 5 worked examples, gate modifiers | Override system changes, new prompt templates, rule schema changes |
| `docs/dev/evaluation-matrix-principles.md` | 8 evaluation dimensions, scoring rubric, data collection protocol | Evaluation criteria changes, new dimensions |
| `docs/dev/forward-compat.md` | 3-tier compat (v1 readable, v2 rerunnable, v3 migration), stability guarantees, deprecation policy | Project metadata format changes, schema changes |
| `docs/dev/founder-expectations.md` | D3 expectations (F01-F55+), priority matrix, action items, 3 user types | Any behavioral/architectural change that affects founder expectations |
| `docs/dev/project-validation-framework.md` | Impact map (file pattern → expectation → verification), validation workflow | Code changes that affect expectations mapping |
| `docs/dev/agent-troubleshooting.md` | Diagnostic guide for agents — pipeline, config, MCP, gate, account issues | New error modes, env var changes, dependency changes |

### `docs/archived/` — Historical (read-only, do not edit)

| File | Content |
|------|---------|
| `docs/archived/AGENT_QUICKSTART.md` | Superseded agent quickstart |
| `docs/archived/architecture-decisions.md` | Historical ADRs |
| `docs/archived/d3-gap-analysis.md` | D3 gap analysis snapshot |
| `docs/archived/enforcement-mechanisms.md` | Superseded enforcement doc |
| `docs/archived/error-code-reference.md` | Superseded error code table |
| `docs/archived/mcp-systemd-setup.md` | Superseded by mcp-setup.md |
| `docs/archived/PRD-4.md` | PRD-4 design spec (implementation complete) |
| `docs/archived/project-audit.md` | Superseded audit |

### Config / infra docs (code-adjacent)

| File | Coverage | Triggers |
|------|----------|----------|
| `mkdocs.yml` | Mkdocs site nav, theme, plugins | New doc files, doc restructuring |
| `.env.example` | All supported env vars with descriptions | New env vars |
| `pyproject.toml` | Package metadata, deps, build config | New dependencies, version bumps |
| `Makefile` | Dev commands (test, lint, typecheck, install) | Make target changes |
| `Dockerfile` / `docker-compose.yml` | Container build and services | Docker changes |
| `deploy/systemd/` | Service units, timer | Systemd changes |
| `.github/workflows/` | CI/CD pipeline | CI workflow changes |

---

## Step 2 — CHANGE TRIGGER TABLE

When you make a specific code change, here is **exactly which docs to update**:

### CLI Changes

| Change | MUST Update | SHOULD Update |
|--------|-------------|---------------|
| Add new CLI command | `docs/user/cli-reference.md` — add command section | `AGENTS.md` sec 10 — update command table + count |
| Remove CLI command | `docs/user/cli-reference.md` — remove section, update overview table | `AGENTS.md` sec 10 — remove from table + update count |
| Rename CLI command | `docs/user/cli-reference.md` — rename everywhere | `AGENTS.md` sec 10 — rename in table |
| Change CLI param | `docs/user/cli-reference.md` — update param docs | — |
| Change CLI group structure | `docs/user/cli-reference.md` — restructure | — |

### MCP Changes

| Change | MUST Update | SHOULD Update |
|--------|-------------|---------------|
| Add new MCP tool | `docs/user/mcp-setup.md` — add to tool list table + `--show-tools` output | `AGENTS.md` sec 9 — add to table + update tool count. `docs/user/api-reference.md` if new public API |
| Remove MCP tool | `docs/user/mcp-setup.md` — remove from all lists | `AGENTS.md` sec 9 — remove from table + update count |
| Rename MCP tool | `docs/user/mcp-setup.md` — rename everywhere. Add deprecation note for old name | `AGENTS.md` sec 9 — rename in table |
| Change MCP tool params | `docs/user/mcp-setup.md` — update param table | `README.md` if in featured tool list |
| Change MCP server startup | `docs/user/mcp-setup.md` — update server start/stop | `docs/user/deployment.md` — update systemd if affected |
| Change path allowlist | `docs/user/mcp-setup.md` — note if policy changed | `docs/dev/agent-troubleshooting.md` — update allowlist section |

### Gate Changes

| Change | MUST Update | SHOULD Update |
|--------|-------------|---------------|
| Add new gate | `docs/dev/gate-failure-modes.md` — add new section. `AGENTS.md` sec 3 + sec 8 — add to dir listing + gate count table | `README.md` — update gate count. `docs/index.md` — update count |
| Remove gate | `docs/dev/gate-failure-modes.md` — archive section. `AGENTS.md` sec 3 + sec 8 — remove | Update gate counts in all docs |
| Change gate failure mode | `docs/dev/gate-failure-modes.md` — update remediation. `automedia/gates/failure_modes.py` — must be in sync | — |
| Change gate behavior | `docs/dev/gate-failure-modes.md` — update diagnosis/remediation | — |
| Change gate ordering | `AGENTS.md` sec 8 — update ordering list | `docs/user/api-reference.md` — mode tables if gate lists change |
| New pipeline mode | `docs/user/api-reference.md` — add to mode table with gate list | `AGENTS.md` sec 8 — mention. `README.md` — mention in features |

### API / SDK Changes

| Change | MUST Update | SHOULD Update |
|--------|-------------|---------------|
| Change `run_full_pipeline()` params | `docs/user/api-reference.md` — update param table + code example | `AGENTS.md` sec 2 — update if entry point changes |
| Change return type | `docs/user/api-reference.md` — update PipelineResult docs | — |
| Add new public class | `docs/user/api-reference.md` — add class docs | — |
| Change GateEngine behavior | `docs/user/api-reference.md` — update GateEngine section | `docs/dev/gate-failure-modes.md` — update if failure behavior changes |
| Change hook protocol | `docs/user/api-reference.md` — update GateHook section | `docs/dev/developer-guide.md` — update if docs reference it |

### Config / Env Var Changes

| Change | MUST Update | SHOULD Update |
|--------|-------------|---------------|
| Add new env var | `.env.example` — add with description. `AGENTS.md` sec 11 — add to table. `docs/user/mcp-setup.md` — add to env var table | `docs/dev/agent-troubleshooting.md` — add if relevant to troubleshooting |
| Remove env var | `.env.example` — remove. `AGENTS.md` sec 11 — remove | Docs referencing it |
| Change config layer priority | `AGENTS.md` sec 4 — update. `docs/dev/developer-guide.md` — update | `README.md` — update config section |
| Change default config | `AGENTS.md` — update if defaults change | `docs/dev/developer-guide.md` — update if install behavior changes |

### Feature Area Changes

| Change | MUST Update | SHOULD Update |
|--------|-------------|---------------|
| **Accounts** (`src/automedia/accounts/`) | `docs/user/api-reference.md` — AccountRegistry, AccountStore, AuthFlowEngine, SessionManager | `docs/user/cli-reference.md` — account CLI if changed |
| **Adapters** (`src/automedia/adapters/`) | `docs/user/api-reference.md` — adapter base/registry if public API changes | `docs/user/cli-reference.md` — adapter CLI if changed |
| **Omni** (`src/automedia/omni/`) | `docs/user/omni-integration.md` — update affected sections | `docs/user/cli-reference.md` — omni CLI |
| **HITL** (`src/automedia/hitl/`) | `docs/user/hitl-framework.md` — update relevant sections | `docs/user/api-reference.md` — if director params changed |
| **Asset Library** (`src/automedia/asset_library/`) | `docs/user/asset-library.md` — update ingest/search/archive API | `docs/user/api-reference.md` — if GateHook integration changed |
| **Pool** (`src/automedia/pool/`) | `docs/user/cli-reference.md` — pool CLI | `docs/user/production-workflow.md` — if pool ops changed |
| **Cron** (`src/automedia/cron/`) | `docs/user/production-workflow.md` — daily schedule | `docs/dev/cron-troubleshooting.md` |
| **Prompts** (`src/automedia/prompts/`) | `docs/dev/override-reference.md` — update template ref table | — |

### Dependency / Build Changes

| Change | MUST Update | SHOULD Update |
|--------|-------------|---------------|
| Add new dependency | `README.md` — update key deps. `docs/dev/developer-guide.md` — add to prerequisites | `docs/dev/agent-troubleshooting.md` — if new dep needs troubleshooting |
| Remove dependency | `README.md` — update key deps. `docs/dev/developer-guide.md` — remove from prerequisites | — |
| Change Python min version | `README.md` — update. `pyproject.toml` — update. `docs/dev/developer-guide.md` — update | `AGENTS.md` sec 1 — update |
| Change install extras | `README.md` — update. `docs/dev/developer-guide.md` — update | — |
| Change Makefile targets | `README.md` — update make target table | — |

### Deployment Changes

| Change | MUST Update | SHOULD Update |
|--------|-------------|---------------|
| Dockerfile change | `docs/user/deployment.md` — update Docker section. `README.md` — update Docker usage | `docs/user/mcp-setup.md` — if MCP Docker affected |
| Docker Compose change | `docs/user/deployment.md` — update compose profiles | — |
| systemd change | `docs/user/mcp-setup.md` — update systemd section. `docs/user/deployment.md` — update systemd section | — |
| New deployment method | `docs/user/deployment.md` — add to comparison table + new section | — |

### Cross-Cutting Owner Docs

| Change | MUST Update | SHOULD Update |
|--------|-------------|---------------|
| Gate count changes in any way | `AGENTS.md` sec 1 + sec 8. `README.md` features section. `docs/index.md` features section. `docs/user/api-reference.md` mode tables | — |
| Tool/command count changes | `AGENTS.md` sec 9 + sec 10. `README.md` three-layer table. `docs/index.md` features | — |
| New feature area added | Create new doc in `docs/user/` or `docs/dev/`. Update `docs/index.md`, `AGENTS.md` sec 12, `README.md` doc index, `mkdocs.yml` nav | — |
| Architecture changes | `AGENTS.md` sec 3 (dir layout) + sec 8 (gate ordering). `README.md` architecture diagram | — |
| mkdocs.yml nav changes | `docs/index.md` — update links | — |
| docs/index.md changes | `mkdocs.yml` nav may need sync | — |
| CHANGELOG update | `CHANGELOG.md` — add entry under appropriate section | — |

### doc-sync Skill Itself

| Change | MUST Update |
|--------|-------------|
| Add/remove doc file | This skill — update DOC MAP section |
| Change code area behavior | This skill — update CHANGE TRIGGER TABLE |
| New trigger scenario | This skill — add to trigger table |
| Wrong/missing mapping found | This skill — fix the mapping |

### README Doc Triggers

| Change | MUST Update | SHOULD Update |
|--------|-------------|---------------|
| Any CLI/command count change | `README.md` three-layer table + features | — |
| Any MCP tool count change | `README.md` three-layer table + features | — |
| Any gate count change | `README.md` Gate System section + features | — |
| Install instructions change | `README.md` Installation section | — |
| Dependency change | `README.md` Prerequisites section | — |
| Architecture change | `README.md` Architecture section | — |
| Feature addition/removal | `README.md` Features section | — |
| Security policy change | `README.md` Security section | — |
| Config hierarchy change | `README.md` Configuration section | — |
| Test command change | `README.md` Testing section | — |
| Doc structure change | `README.md` Documentation Index | — |
| AGENTS.md change | `README.md` Agent Configuration section | — |

### AGENTS.md Doc Triggers

| Change | MUST Update |
|--------|-------------|
| Gate add/remove | Sec 3 (dir layout) + Sec 8 (gate list + order) |
| MCP tool count | Sec 2 (entry points) + Sec 9 (MCP tool table) |
| CLI command count | Sec 2 (entry points) + Sec 10 (CLI table) |
| Directory structure change | Sec 3 (dir layout) |
| Config key/env var change | Sec 11 (config key ref) |
| Architecture change | Sec 4 (6-layer) |
| Doc structure change | Sec 12 (doc index) |
| Skill add/remove | Sec 13 (skills list) |
| Red line change | Sec 5 (agent constraints) |
| Gate ordering change | Sec 8 (gate ordering) |
| Pipeline mode change | Sec 8 (gate lists per mode) |

---

## Step 3 — VERIFICATION PROTOCOL

After updating docs, verify correctness:

### 3.1 Count Assertions

Some docs assert specific numbers (tool count, gate count, command count). Verify these match reality:

```bash
# MCP tool count (from AGENTS.md sec 9 and README)
grep -c '^\| `[a-z_]' AGENTS.md | head -1  # rough check

# Gate count (from AGENTS.md sec 8)
# Count actual gate files
ls src/automedia/gates/*.py | grep -v '__\|base\|failure' | wc -l

# CLI command count (from AGENTS.md sec 10)
grep -c '^| `automedia' AGENTS.md
```

**If counts mismatch, you forgot to update a doc section.**

### 3.2 Cross-Doc Consistency Check

Check that the same information is consistent across all docs that reference it:

- **Gate ordering**: Verify `AGENTS.md` sec 8, `docs/user/api-reference.md` mode tables, and `src/automedia/pipelines/runner.py` gate lists match
- **MCP tool list**: Verify `AGENTS.md` sec 9, `docs/user/mcp-setup.md` tool list, and `src/automedia/mcp/server.py` registration match
- **CLI command list**: Verify `AGENTS.md` sec 10, `docs/user/cli-reference.md`, and `src/automedia/cli/app.py` registration match
- **Config keys**: Verify `AGENTS.md` sec 11, `.env.example`, and `src/automedia/core/config_loader.py` `_LLM_KEY_MAP` match
- **Feature claims**: If a feature is mentioned in `README.md` Features, `docs/index.md`, and `AGENTS.md`, all three must agree

### 3.3 Broken Link Check

```bash
# Check for broken internal doc links (basic)
grep -rn '](docs/' AGENTS.md README.md --include="*.md" 2>/dev/null | grep -v 'https://'
# For each link found, verify the target file exists
```

### 3.4 mkdocs.yml Nav Sync

If you added/removed a doc file in `docs/`, check if `mkdocs.yml` nav needs updating.

### 3.5 CHANGELOG Entry

**Every user-visible change MUST have a CHANGELOG entry.** The CHANGELOG is at `CHANGELOG.md`. Add under the appropriate section:
- `### Added` — new features, tools, commands, gates
- `### Fixed` — bug fixes
- `### Changed` — behavior changes, deprecations
- `### Docs` — documentation updates
- `### Removed` — deleted features

If you updated docs, add a `### Docs` entry listing which docs were updated and what changed.

---

## APPENDIX: Quick-Reference Maps

### Map A — Loc: `src/automedia/cli/` → Doc

| File | Primary Doc(s) |
|------|----------------|
| `cli/app.py` | `docs/user/cli-reference.md`, `AGENTS.md` sec 10 |
| `cli/commands/run.py` | `docs/user/cli-reference.md` (run) |
| `cli/commands/pool.py` | `docs/user/cli-reference.md` (pool) |
| `cli/commands/projects.py` | `docs/user/cli-reference.md` (projects) |
| `cli/commands/account.py` | `docs/user/cli-reference.md` (account) |
| `cli/commands/distribute.py` | `docs/user/cli-reference.md` (distribute), `docs/user/production-workflow.md` |
| `cli/commands/adapter.py` | `docs/user/cli-reference.md` (adapter) |
| `cli/commands/cron.py` | `docs/user/cli-reference.md` (cron), `docs/dev/cron-troubleshooting.md` |
| `cli/commands/archive.py` | `docs/user/cli-reference.md` (archive) |
| `cli/commands/init_cmd.py` | `docs/user/cli-reference.md` (init) |
| `cli/commands/doctor.py` | `docs/user/cli-reference.md` (doctor) |
| `cli/commands/omni.py` | `docs/user/cli-reference.md` (omni), `docs/user/omni-integration.md` |
| `cli/commands/hitl.py` | `docs/user/cli-reference.md` (hitl), `docs/user/hitl-framework.md` |
| `cli/commands/onboard.py` | `docs/user/cli-reference.md` (onboard) |

### Map B — Loc: `src/automedia/mcp/` → Doc

| File | Primary Doc(s) |
|------|----------------|
| `mcp/server.py` | `docs/user/mcp-setup.md`, `AGENTS.md` sec 9 |
| `mcp/tools.py` | `docs/user/mcp-setup.md` tool list |
| `mcp/accounts.py` | `docs/user/mcp-setup.md`, `docs/user/api-reference.md` |
| `mcp/resources.py` | `docs/user/mcp-setup.md` |
| `mcp/parallel.py` | `docs/user/mcp-setup.md` |
| `mcp/mcp_allowlist.yaml` | `docs/user/mcp-setup.md` (security), `docs/dev/agent-troubleshooting.md` |

### Map C — Loc: `src/automedia/gates/` → Doc

| File(s) | Primary Doc(s) |
|---------|----------------|
| `gates/base.py` | `docs/dev/developer-guide.md`, `docs/user/api-reference.md` |
| `gates/failure_modes.py` | `docs/dev/gate-failure-modes.md` (must stay in sync) |
| `gates/fact_check.py` (G0) | `docs/dev/gate-failure-modes.md` sec G0 |
| `gates/humanizer.py` (G1) | `docs/dev/gate-failure-modes.md` sec G1 |
| `gates/copy_review.py` (G2) | `docs/dev/gate-failure-modes.md` sec G2 |
| `gates/brand_cta.py` (G3) | `docs/dev/gate-failure-modes.md` sec G3 |
| `gates/wechat_checklist.py` (G4) | `docs/dev/gate-failure-modes.md` sec G4 |
| `gates/html_hard.py` (G5) | `docs/dev/gate-failure-modes.md` sec G5 |
| `gates/tone_check.py` (G6) | `docs/dev/gate-failure-modes.md` sec G6 |
| `gates/content_writer.py` (CW) | `docs/dev/gate-failure-modes.md` sec CW |
| `gates/topic_selection.py` (pre-gate) | `docs/dev/gate-failure-modes.md` sec pre-gate |
| `gates/lint.py` (V0) → V7 | `docs/dev/gate-failure-modes.md` sec V0-V7 |
| `gates/publish_log_schema.py` (L1) | `docs/dev/gate-failure-modes.md` sec L1 |
| `gates/archive_validation.py` (L2) | `docs/dev/gate-failure-modes.md` sec L2 |
| `gates/platform_integrity.py` (L3) | `docs/dev/gate-failure-modes.md` sec L3 |
| `gates/translation_quality.py` (L4) | `docs/dev/gate-failure-modes.md` sec L4 |
| D1-D7 gates | `docs/dev/gate-failure-modes.md` + `docs/user/production-workflow.md` |
| P1-P4 gates | `docs/dev/gate-failure-modes.md` |

### Map D — Loc: `src/automedia/core/` → Doc

| File | Primary Doc(s) |
|------|----------------|
| `core/config_loader.py` | `docs/dev/developer-guide.md`, `AGENTS.md` sec 4+11, `docs/dev/override-reference.md` |
| `core/project.py` | `docs/user/api-reference.md`, `docs/user/production-workflow.md` |
| `core/credential_loader.py` | `docs/user/mcp-setup.md`, `docs/user/api-reference.md` |
| `core/doctor.py` | `docs/user/cli-reference.md`, `docs/dev/agent-troubleshooting.md` |
| `core/overrides.py` | `docs/dev/override-reference.md` |
| `core/llm_client.py` | `docs/user/api-reference.md`, `docs/dev/api-gotchas.md` |
| `core/media_spec.py` | `docs/dev/override-reference.md` |
| `core/workflow.py` | `docs/user/production-workflow.md`, `docs/user/api-reference.md` |

### Map E — Loc: `src/automedia/pipelines/` → Doc

| File | Primary Doc(s) |
|------|----------------|
| `pipelines/runner.py` | `docs/user/api-reference.md`, `AGENTS.md` sec 2, `docs/dev/developer-guide.md` |
| `pipelines/gate_engine.py` | `docs/user/api-reference.md`, `docs/dev/gate-failure-modes.md` |
| `pipelines/audio_pipeline.py` | `docs/dev/developer-guide.md` |
| `pipelines/image_pipeline.py` | `docs/dev/developer-guide.md` |
| `pipelines/language_config.py` | `docs/dev/developer-guide.md` |

### Map F — Feature Dirs → Doc

| Directory | Primary Doc(s) |
|-----------|----------------|
| `src/automedia/accounts/` | `docs/user/api-reference.md` (AccountRegistry, AccountStore, AuthFlowEngine, SessionManager), `docs/user/cli-reference.md` (account CLI) |
| `src/automedia/adapters/` | `docs/user/api-reference.md` (base/registry), `docs/user/cli-reference.md` (adapter CLI) |
| `src/automedia/omni/` | `docs/user/omni-integration.md`, `docs/user/cli-reference.md` (omni CLI) |
| `src/automedia/hitl/` | `docs/user/hitl-framework.md`, `docs/user/api-reference.md` (director params) |
| `src/automedia/asset_library/` | `docs/user/asset-library.md`, `docs/user/api-reference.md` |
| `src/automedia/pool/` | `docs/user/cli-reference.md` (pool CLI), `docs/user/production-workflow.md` |
| `src/automedia/cron/` | `docs/user/production-workflow.md`, `docs/dev/cron-troubleshooting.md` |
| `src/automedia/prompts/` | `docs/dev/override-reference.md` |
| `src/automedia/hooks/` | `docs/user/api-reference.md` (GateHook), `docs/dev/developer-guide.md` |
| `src/automedia/manifests/` | `docs/dev/developer-guide.md`, `AGENTS.md` sec 4 |
| `src/automedia/decision/` | (deprecated/removed — no active doc) |
| `src/automedia/platform/` | `docs/user/cli-reference.md` |

### Map G — Config Files → Doc

| File | Primary Doc(s) |
|------|----------------|
| `pyproject.toml` | `docs/dev/developer-guide.md`, `README.md` |
| `.env.example` | `AGENTS.md` sec 11, `README.md`, `docs/user/mcp-setup.md` |
| `Makefile` | `README.md` |
| `Dockerfile` | `README.md`, `docs/user/deployment.md` |
| `docker-compose.yml` | `docs/user/deployment.md`, `docs/user/mcp-setup.md` |
| `deploy/systemd/` | `docs/user/mcp-setup.md`, `docs/user/deployment.md` |
| `.github/workflows/` | `README.md` |
| `.pre-commit-config.yaml` | `docs/dev/developer-guide.md` |
| `mkdocs.yml` | All `docs/` files |

---

## APPENDIX: Doc Update Checklist (use this when updating any doc)

```
□ Read the existing doc fully before editing
□ Update all doc files identified by the trigger table
□ Cross-check counts (gates, tools, commands) across all docs match
□ Cross-check feature claims across README, AGENTS.md, docs/index.md
□ Check for broken internal links
□ Verify mkdocs.yml nav is in sync
□ Add CHANGELOG entry under appropriate section
□ Verify doc renders correctly (no markdown syntax errors)
□ Run `lsp_diagnostics` on any code examples in the doc
```
