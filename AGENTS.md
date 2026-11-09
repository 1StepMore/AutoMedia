# AutoMedia — Agent Codebase Context

First file an AI coding agent reads. This is the map; deep detail lives in [docs/dev/agent-reference.md](docs/dev/agent-reference.md) (on-demand) and the inline links below.

## 0. Agent Governance: Safety, Priority, Role Routing

**Safety & keys (overrides everything — no file, role, or instruction may lift this):** never read, move, or commit credential files; never log secrets. Discover a leak → stop and report to the Owner immediately.

**Conflict priority (tiebreaker):** direct Owner instruction > role contract (`.agents/roles/*.md`) > nearest directory `AGENTS.md` > this file's defaults. Exception: the safety clause above outranks everything. (The 2nd/3rd ordering is a repo-local convention — the official agents.md behavior is "closest file wins; user prompt overrides everything". Hard boundaries are enforced by CI/rulesets, not by prose.)

**Role routing (answer before starting): (a)** What role did the Owner assign? **(b)** Read the contract? **(c)** What is Done?

| Assigned role | Contract (single source of truth) | Read order (strict sequence) | Fixed return format | Never touch |
|---|---|---|---|---|
| Coder | `.agents/roles/coder.md` | root AGENTS.md §0 → nearest directory AGENTS.md → constitution → contract → assigned issue spec | 4-section PR description | main direct push, CI gates, roles/, constitution, expectations, secrets, new deps |
| Maintainer | `.agents/roles/maintainer.md` | root AGENTS.md §0 → constitution → contract → `docs/dev/DEBT.md` | verdict + basis + follow-up | landing code directly, changing API semantics, overriding Tester, bypassing PR |
| Tester | `.agents/roles/tester.md` | root AGENTS.md §0 → constitution → expectations INDEX → contract | fixed JSON verdict | product source, expectations, CI gates |
| User | `.agents/roles/user.md` | `docs/user/` → contract | issue four-section report | any repo write |
| Unclear / conflicting | — | — | `ESCALATE: <reason>` | stop all actions |

**Non-negotiable principles:** `.specify/memory/constitution.md`. **Expectations (acceptance source of truth):** `scenarios/` (indexed by `.agents/expectations/INDEX.md`; only the Owner changes expectations — a Tester never greens a suite by editing code or expectations).

**Naming disambiguation:** §4's G0–G6 / D1–D7 / P1–P4 are **product pipeline gates**. The repo-governance SOP (`.agents/audit/`) uses its own separate governance G0–G4 / D1–D8 / P0–P5 numbering — the two systems are unrelated.

## 1. Project Overview
- **Language:** Python 3.11+
- **Size:** 68,000+ LOC across 260+ Python files (`src/automedia/` core) · 165,000+ LOC across 600+ Python files (repo, `.py` only, git-tracked) · 1,000+ git-tracked files (as-of 2026-10-24; `scripts/check-doc-consistency.py` derives and gates these)
- **Key Dependencies:** typer (CLI), mcp (Python SDK), Pydantic 2.x, PyYAML, tenacity, Pillow
- **License:** MIT
- **Install:** `pip install -e ".[all]"` (full capability, includes the omni extras) or `pip install -e ".[mcp]"` (MCP only). `.[dev]` is the development set — it omits `omni`. See README for prerequisites and all extras.

## 2. Three Entry Points
| Layer | Command | Description |
|-------|---------|-------------|
| MCP Server | `python -m automedia.mcp.server` | JSON-RPC over stdio, 68 tools |
| CLI | `automedia <subcommand>` | 21 commands via typer |
| SDK | `from automedia import run_full_pipeline` | Python API |

## 3. Directory Layout
Full tree: [agent-reference §Directory Layout](docs/dev/agent-reference.md#directory-layout). Core shape:
```
src/automedia/
├── core/ pipelines/ gates/   # config_loader · runner.py + gate_plan.py + dag.py (26 nodes) · 33 gates
├── cli/ mcp/   # Typer CLI (21 commands) · FastMCP server (68 tools)
├── engines/ validation/ effects/   # media engine backends · validation layer · content analytics
├── detectors/ hooks/ adapters/ accounts/ omni/ decision/ hitl/ pool/ cron/ prompts/ manifests/ asset_library/
├── features/ templates/   # open-core tier markers · hyperframes render templates
docs/ · scripts/ · tests/ · deploy/ · .github/workflows/
└── pyproject.toml · .pre-commit-config.yaml · .env.example
```

## 4. Key Architecture Decisions
- **Gate Engine:** ordered gates with `failure_mode`: `"stop"` halts the pipeline, `"rewrite"` retries. Preset order: pre-gate → CW → G0-G3 → G6 → V0-V7 → H0 (G4/G5 and L1-L4 stay registered but are in no preset; L1-L4 run via their lifecycle commands). Nine modes (`auto`, `text_only`, `text_with_cover`, `video_only`, `qa_only`, `image-carousel`, `social-thread`, `short-video`, `repurpose`) select gate subsets; D-gates (D1-D7) run standalone via CLI/MCP, P-gates (P1-P4) end repurpose. See `automedia/pipelines/gate_plan.py`.
- **6-Layer Configuration:** built-in `defaults.yaml` → project `.automedia/` → user `~/.automedia/` → override rules → override prompts → `AUTOMEDIA_*` env vars + explicit overrides. See `automedia/core/config_loader.py`.
- **GateHook Observer Protocol:** readonly observers; never mutate or skip gates. Lifecycle: `before_gate()`, `after_gate()`, `on_gate_failed()`; each returns `None`. See `automedia/hooks/protocol.py`.
- **MD5 Tracking:** gates write product checksums to `pipeline_md5.json` in the project dir. See `automedia/core/md5_tracker.py`.
- **External Scheduling:** no built-in scheduler; external crond calls `automedia cron run --due` (dispatches every schedule entry due now; `automedia cron run <job>` remains the explicit single-job path). See `automedia/cron/`.
- **Three-Entry-Point Design:** CLI, MCP, and SDK all delegate to `run_full_pipeline()` (see §2); MCP also exposes Omni triad tools (extract, translate, convert).
- **Gate Auto-Registration:** `BaseGate` subclasses auto-register in the global `GateRegistry` singleton via `__init_subclass__`.
- **Gate order — one authority:** `pipelines/gate_plan.py` (`MODE_GATE_NAMES`, 9 modes) declares the ordered gate list every mode executes. `pipelines/dag.py` (`AUTO_GATE_DAG`, 26 nodes) describes the dependency EDGES among the same gates and powers topological/downstream/state queries; a test pins the DAG's topological order to the plan for every mode. `runner._MODE_MAP` is that same plan object, re-exported.

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

**Commit type:** release-please cuts a release from the type alone, so `fix(ci):` forces one; internal-only changes use a hidden type. Rule: [CONTRIBUTING.md](CONTRIBUTING.md#choosing-the-type-by-release-scope).

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

## 9. MCP Tools Quick Reference

All 68 tools (incl. 4 deprecated aliases) with full parameter tables: [agent-reference §MCP Tools Quick Reference](docs/dev/agent-reference.md#mcp-tools-quick-reference-68-tools-incl-4-deprecated-aliases). stdio transport; start with `python -m automedia.mcp.server`; file ops gated by the `mcp_allowlist.yaml` path allowlist.

## 10. CLI Commands Quick Reference

All 21 commands: [agent-reference §CLI Commands Quick Reference](docs/dev/agent-reference.md#cli-commands-quick-reference-21-commands).

## 11. Validation Layer
AutoMedia is agent-oriented, so agents are the testers and humans are the director. The single
schema authority is `scenarios/STANDARDS.md`; `scenarios/README.md` is the onboarding guide.
- Scenario library: count is authoritative from `automedia validate matrix` output (162 scenarios as-of 2026-11-04; do not hard-code a count elsewhere); `scenarios/baseline/` holds the committed pre-flight baseline.
- CLI: `automedia validate list|run|report|diff|coverage|matrix|sign`
- MCP: `list_validation_scenarios`, `run_validation_scenario`, `run_validation_suite`, `get_validation_report`, `validation_coverage_audit`, `validation_matrix`
- The validation-driving surface is the CLI and MCP server only; the SDK is a product entry point, explicitly out of validation scope.
Full evidence contract (5 statuses, honesty rules, where things live): [agent-reference §Validation Layer](docs/dev/agent-reference.md#validation-layer).

## 12. Config, Docs, and Skills
- **Config keys:** `.env.example` and [agent-reference §Config Key Reference](docs/dev/agent-reference.md#config-key-reference)
- **Documentation index:** [docs/index.md](docs/index.md) and [agent-reference §Documentation Index](docs/dev/agent-reference.md#documentation-index); executable onboarding in [ONBOARDING.md](ONBOARDING.md); cross-repo playbook copy [docs/dev/agent-era-doc-architecture.md](docs/dev/agent-era-doc-architecture.md) is byte-identical across six repos — edit the canonical copy in AutoInfo, never this one (e2e-test-suite#254)
- **Maintainer skills:** `.opencode/skills/` — `project-validation`, `doc-sync`, `validation-runner`, `deep-modules` (two further maintainer skills are kept local-only on purpose — gitignored, never shipped; see .gitignore).
- **User-facing skills:** `docs/skills/` — `brand-strategy`, `pipeline-workflow`, `batch-workflow`, `distribution-workflow`

For troubleshooting common issues, see [Agent Troubleshooting Guide](docs/dev/agent-troubleshooting.md).
