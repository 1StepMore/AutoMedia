# AutoMedia — Claude Code Project Rules

## Overview
AutoMedia is an automated media production pipeline. Python 3.11+ with typer CLI, mcp SDK, Pydantic 2.x.

## Entry Points
- MCP Server: `python -m automedia.mcp.server` (33 tools)
- CLI: `automedia <subcommand>` (12 commands)
- SDK: `from automedia import run_full_pipeline`

## Agent Constraints
- **MUST NOT** archive with `--force` (Red Line 8 — only user may force-archive)
- **MUST NOT** commit real production data or credentials
- **MUST** use synthetic test fixtures from `tests/fixtures/synth/`
- **MUST** follow gate naming: G0-G5 (copy), V0-V7 (video), L1-L4 (lifecycle)

## Dev Workflow
```bash
pip install -e ".[dev]"    # Install
pytest                      # Test
ruff check .                # Lint
mypy src/automedia/         # Type check
python -m automedia.mcp.server  # Start MCP server
```

## Key Files
- `AGENTS.md` — Full agent codebase context (read first)
- `automedia/` — Core package
- `tests/` — Test suite (~2,634, 6 pre-existing failures)
- `docs/` — Documentation
- `deploy/` — systemd deployment units
