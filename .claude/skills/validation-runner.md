---
name: validation-runner
description: AutoMedia dev-side validation workflow — run scenario waves, author regression scenarios, capture RED→GREEN evidence, produce acceptance evidence. Load whenever fixing a bug (a regression scenario is mandatory), adding or authoring validation scenarios, running an acceptance wave, or preparing validation evidence.
author: AutoMedia
version: 1.0.0
---

# AutoMedia Validation Runner Skill

The QA loop for developing AutoMedia. Canonical depth lives in
`scenarios/STANDARDS.md` (the single schema authority — standard keys and
semantics) and `scenarios/README.md` (how to read a scenario field by field,
one worked example). This skill is the loadable procedure.

## When to load

- **Fixing a bug** → a regression scenario is **mandatory** (the
  `.github/ISSUE_TEMPLATE/bug_report.yml` field "Regression scenario" gates
  implementation and verification). Produce it PLUS RED→GREEN evidence.
- **Feature wave done** → run the affected scenario group before declaring done.
- **Authoring a new scenario** → follow the contract, drop YAML into
  `scenarios/` (regression ones into `scenarios/regression/` with
  `category: regression` + `regression: true` + `regression_issue: "#NN"`;
  the recursive glob auto-loads them — no registration).
- **Acceptance run** → run the suite, persist the record, write the evidence.

## Scenario library (142)

`scenarios/` holds 142 declarative YAML scripts across `cli/`, `journeys/`,
`publish/`, `quality/`, `regression/`, `surface/`, `meta/`, `fixtures/`,
`baseline/`. Every step is one **real** MCP/CLI/file call graded against an
`expect` block. Authority: `scenarios/STANDARDS.md`.
Run `automedia validate list` for the live list — never trust a stale count.

## Execution discipline

1. **Real surface, no mock** (honesty rule): every step makes a real
   MCP/CLI/file call and asserts on the real response. Env-gated steps report
   `unconfigured` — **never** a pass.
2. **RED→GREEN**: capture the honest failing state BEFORE the fix (call fails
   / `unconfigured` / artifact absent), then the verified positive state AFTER
   (call succeeds AND artifact exists). Both captured or it didn't happen.
3. Run one scenario:
   ```
   automedia validate run --scenario <name>
   ```
   Run the whole suite in-process:
   ```python
   from automedia.validation.engine import run_validation_suite
   record = run_validation_suite(server=<live FastMCP>, runs_root="validation-runs")
   ```
   Persisted results land in `validation-runs/<timestamp>/` (gitignored, with
   a `latest.txt` pointer). A failing scenario may declare `recovery_steps`;
   scenarios can partial-pass via `min_passing` / `pass_ratio`; a missing
   `requires_env` var marks the whole scenario `unconfigured`.
4. Report / diff / coverage / matrix (all exit 1 on their hard conditions):
   ```
   automedia validate report [--run <name|latest>]
   automedia validate diff  [--baseline <path>]
   automedia validate coverage   # exits 1 when declared-but-missing on any surface
   automedia validate matrix
   ```
   The same surface is exposed as MCP tools: `list_validation_scenarios`,
   `run_validation_scenario`, `get_validation_report`,
   `validation_coverage_audit`, `validation_matrix`.

## Bug → regression flywheel (mandatory)

Every bug fix ends with a new regression scenario named after the issue
(`regression-<issue>-<slug>`), marked `regression: true`, in
`scenarios/regression/`. It stays green forever (recursive-glob auto-load).
`automedia validate coverage` prints the regression tally — keep it climbing.
This is the process-improvement loop of the 七阶段 methodology's Review stage
(`docs/dev/七阶段AI开发流程-用CodingAgent交付成品的方法论.md`).

Authoring a regression scenario — follow the existing exemplar
`scenarios/regression/regression-83-configure-llm-preserves-fallback.yaml`:

- `name: regression-<issue>-<slug>` (the name, not the filename, is the identity)
- `description` — one or two sentences stating what the fix proves
- `intent` — WHY it exists; schema-required, read it first
- `category: regression`, `regression: true`, `regression_issue: "#NN"`
- `steps` — ordered, top to bottom; each step is one real call plus an
  `expect` block; each `check` cites a `standard` key that must exist in
  `scenarios/STANDARDS.md`
- `cleanup_steps` — best-effort state removal, never influences the verdict

## Evidence & reports

```bash
# Run one scenario against the real server (CLI surface)
automedia validate run --scenario <name>

# Full suite in-process (persists an immutable run record)
python3 - <<'PY'
from automedia.mcp.server import create_server
from automedia.validation.engine import run_validation_suite
record = run_validation_suite(server=create_server(), runs_root="validation-runs")
print(record)
PY

# CI-mirroring driver: --all or explicit scenario file paths (no LLM, no persist)
python3 scripts/validation_run_affected.py --all
python3 scripts/validation_run_affected.py surface/health/engine-health-alias.yaml
```

Evidence layout: `validation-runs/<timestamp>/scenarios.json` (immutable run
record), `validation-runs/<timestamp>/artifacts/` (collected evidence),
`validation-runs/<timestamp>/signed.txt` (director sign-off — the human
appends the run name, date, and verdict; the agent grades, the human disposes).

## Grading & change control

- Verdicts: `passed` / `failed` / `unconfigured` / `recovered` /
  `partial-pass`. The honesty rules in `scenarios/README.md` govern all five.
- `hard: true` marks a scenario hard-safety-critical: a non-`passed` status
  on a hard scenario is a hard-safety violation — `validate run` exits 1, the
  suite is blocked, the report shows a `## Hard Safety` section.
- Director sign-off: the director appends the run name, date, and verdict to
  `signed.txt` in the run directory. Nothing the agent decides alone is final.

## Relationship to other skills

- `doc-sync` — a new scenario is a doc change: the library count is a
  drift-prone fact. Update `AGENTS.md` §11 / `README.md` counts if they cite
  the scenario total, and add a CHANGELOG entry.
- `deep-modules` — when a refactor changes observable behavior, add/update an
  integration scenario (regression flywheel); do not rely on per-function
  unit tests alone.
- `project-validation` — after any behavior change, run the founder-expectation
  validation steps for the touched files.
