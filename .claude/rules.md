# AutoMedia — Claude Code Project Rules

## Overview
AutoMedia is an automated media production pipeline. Python 3.11+ with typer CLI, mcp SDK, Pydantic 2.x.

## Entry Points
- MCP Server: `python -m automedia.mcp.server` (68 tools)
- CLI: `automedia <subcommand>` (21 commands)
- SDK: `from automedia import run_full_pipeline`

## Agent Constraints

Full text: `docs/dev/redlines.md`. Source: `src/automedia/governance/redlines.yaml`.

- `RL-ARCHIVE-FORCE` — never `--force` archive
- `RL-NO-PROD-DATA` — no production data or credentials in git
- `RL-SYNTH-FIXTURES` — synthetic fixtures only
- `RL-GATE-NAMING` — G0-G6, V0-V7, L1-L4, D1-D7, P1-P4

(remaining IDs: `RL-ALLOWLIST`, `RL-ARCHIVE-CMD`, `RL-FAILURE-MODES`, `RL-PRECOMMIT`, `RL-HOOK-READONLY`)

## Dev Workflow
```bash
pip install -e ".[dev]"    # Install
pytest                      # Test
ruff check .                # Lint
mypy src/automedia/ --ignore-missing-imports   # Type check
python -m automedia.mcp.server  # Start MCP server
```

## Key Files
- `AGENTS.md` — Full agent codebase context (read first)
- `src/automedia/` — Core package
- `tests/` — Test suite
- `docs/` — Documentation
- `deploy/` — systemd deployment units
