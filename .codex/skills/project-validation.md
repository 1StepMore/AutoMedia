# Project Validation

version: 2.0.0

Validate code changes against the project's living verification surfaces.
Load this skill as part of completion criteria when modifying `src/automedia/` files.

## What Changed in v2.0.0 (2026-10-30)

v1.0.0 routed validation through `docs/dev/project-validation-framework.md`'s
impact map against `founder-expectations.md`. That flow no longer works: the
expectations file is a frozen historical snapshot (agent-reference §Skills:
"do not refresh"), its impact-map patterns predate the `mcp/tools/` package
split, and no automation executes the framework. The living verification
surfaces are the agent-tester validation library, the test suite, and the
doc gates — this skill now routes through them (remediation plan A1).

## When to Use

After completing any code change in `src/automedia/`:

1. Run the targeted tests for the subsystem you touched
2. Run the validation scenarios that cover the changed surface
3. Run the doc gate when any claim-bearing file changed

## Workflow

### Step 1: Targeted Tests

```bash
pytest tests/test_gates/ -v          # Gate changes
pytest tests/test_mcp/ -v            # MCP tool changes
pytest tests/test_cli/ -v            # CLI changes
pytest tests/test_pipeline/ -v       # Runner/engine changes
pytest tests/test_validation/ -v     # Validation-layer changes
```

### Step 2: Affected Validation Scenarios

The CI `validation-affected` job maps changed files to scenarios; run the
same mapping locally:

```bash
python scripts/validation_run_affected.py        # CI's exact affected-surface runner
automedia validate list                          # full library load check
automedia validate run --category surface        # or scope by category
```

If your change touched an MCP tool, CLI command, gate, or mode, the
coverage audit demands a scenario for it:

```bash
automedia validate coverage        # missing surfaces fail (exit 1)
```

New surface without a scenario = hard red in CI (`missing_hard_count`).
Add or extend a scenario in the matching `scenarios/<category>/` directory;
cite a `standard:` key that exists in `scenarios/STANDARDS.md` (the
vocabulary is pinned to the citation set — see `test_standards.py`).

If your change alters a numeric assertion threshold in a scenario, you MUST
regenerate `scenarios/baseline/threshold-snapshot.json` and add a waiver row
to `scenarios/THRESHOLD_WAIVERS.md` in the same PR (plan A7;
`test_threshold_snapshot.py` enforces both halves).

### Step 3: Doc Gates (when docs or counts changed)

```bash
python scripts/check-doc-consistency.py            # counts, params, trees, links
python scripts/doc_inventory.py --check            # after adding/removing docs
python scripts/check_rfc_aging.py                  # after touching docs/dev/rfcs
```

### Step 4: If Something Fails

- A failing test or scenario means the change broke a verified behavior:
  fix the root cause before declaring the task complete.
- A coverage gap means the new surface is unproven: add the scenario, not
  an allowlist entry.
- Never weaken a scenario threshold to make it pass without a waiver row —
  that is the exact failure mode A7 exists to prevent.

## Mapping Reference

Subsystem → first-line verification surface (v2; the v1 founder-expectation
IDs were retired with the frozen snapshot):

| If You Changed | Verify With |
|---------------|------------|
| `gates/**` | gate tests + `proves_gates` scenarios + `gate_plan.py`/`failure_modes.py` wiring tests |
| `mcp/tools/**`, `mcp/tools_distribution.py` | `tests/test_mcp/` + `scenarios/surface/**` |
| `pipelines/runner.py`, `gate_engine.py`, `gate_plan.py` | `tests/test_runner/`, `tests/test_gate_plan.py` + `scenarios/journeys/**` |
| `adapters/**` | `tests/test_distribution/`, adapter tests + `scenarios/publish/**` |
| `cli/commands/**` | `tests/test_cli/` + `scenarios/cli/**` |
| `core/config_loader.py` | `tests/test_config_loader.py` |
| `accounts/**` | `tests/test_accounts*` |
| `hitl/**`, `decision/**` | `tests/test_hitl/`, `tests/test_decision*/` |
| `hooks/**` | `tests/test_gate_hooks.py`, `tests/test_hooks/` |
| `cron/**` | `tests/test_cron*` |
| `validation/**`, `scenarios/**` | `tests/test_validation/` + `automedia validate run --scenario <changed>` |

## See Also

- `docs/dev/agent-reference.md` §Validation Layer — the evidence contract
- `scenarios/README.md` — scenario authoring + threshold governance (A7)
- `.opencode/skills/validation-runner.md` — the RED→GREEN regression flywheel
- `docs/dev/founder-expectations.md` — frozen historical snapshot (context only, do not refresh or validate against it)
