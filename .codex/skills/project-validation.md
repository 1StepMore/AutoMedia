# Project Validation

Maintain founder expectations alignment after code changes.
Load this skill as part of completion criteria when modifying `src/automedia/` files.

## When to Use

After completing any code change in `src/automedia/`, load this skill to:

1. Determine which D3 founder expectations are affected by your change
2. Run the relevant validation steps
3. Record the result in the validation framework's review history

This ensures the project never silently drifts away from founder expectations.

## Usage

```
skill(name="project-validation", user_message="<list of changed files>")
```

## Workflow

### Step 1: Identify Changed Files

List the files you modified, created, or deleted.

### Step 2: Match Against Impact Map

Open `docs/dev/project-validation-framework.md` and find the `impact_map` section.
Match your changed files against each `pattern` entry.

For each match:
- Note the `affects` list (which D3 expectations are touched)
- Execute the `steps` list (validation actions)

### Step 3: Run Validation

For each affected expectation, run the corresponding steps:

**Common validation commands:**

```bash
# Test-specific
pytest tests/test_gates/ -v                     # Gate changes
pytest tests/test_adapters/ -v                  # Adapter changes
pytest tests/test_mcp/ -v                       # MCP changes
pytest tests/test_cli/ -v                       # CLI changes
pytest tests/test_pipeline/ -v                  # Pipeline changes
pytest tests/ -k account                        # Account changes

# CLI sanity
automedia --help                                # All commands listed

# MCP sanity
timeout 5 python -m automedia.mcp.server 2>&1   # Server starts clean
python -c "
import json, sys
from automedia.mcp.server import create_server
print('MCP server imports OK')
"                                               # Imports clean

# SDK sanity
python -c "from automedia import run_full_pipeline; print('SDK OK')"

# Config sanity
python -c "
from automedia.core.config_loader import load_config
cfg = load_config()
print(f'Config layers: {len(cfg._history) if hasattr(cfg, \"_history\") else \"OK\"}')
"
```

### Step 4: Record in Review History

If validation reveals a status change (expectation went from passing to failing, or vice versa), update the review history table in `docs/dev/project-validation-framework.md §5`.

Add a row:
```
| {date} | L1 | {files changed} | {affected expectations} | {PASS/FAIL} | {verdict} |
```

### Step 5: If Something Fails

- If a validation step fails, it means your change broke an expectation.
- Fix the root cause before declaring the task complete.
- If the expectation itself is outdated (the project evolved), update `founder-expectations.md` instead.

## Mapping Reference

Quick reference — for the full mapping table with steps, see `docs/dev/project-validation-framework.md §2`.

| If You Changed | You Affect |
|---------------|------------|
| `gates/**/*.py` | F24, F25, F26, F27 |
| `mcp/tools.py` | F05, F12, F42, F17 |
| `pipelines/runner.py` | F07, F11, F17, F21 |
| `pipelines/gate_engine.py` | F19, F20, F24 |
| `adapters/platforms/**/*.py` | F29, F30, F31, F34, F35 |
| `adapters/publish_engine.py` | F29, F34, F35 |
| `cli/commands/**/*.py` | F02, F03, F06, F17 |
| `core/config_loader.py` | F01, F03, F04 |
| `accounts/**/*.py` | F04, F35 |
| `hitl/**/*.py` | F28 |
| `hooks/**/*.py` | F43 |
| `cron/**/*.py` | F37 |

## See Also

- `docs/dev/project-validation-framework.md` — Full framework with mapping table, cadence, freshness checks
- `docs/dev/founder-expectations.md` — D3: 48 founder expectations
- `docs/dev/evaluation-matrix-principles.md` — 8-dimension diagnostic toolkit
