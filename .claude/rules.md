# AutoMedia — Claude Code Project Rules

## Overview
AutoMedia is an automated media production pipeline. Python 3.11+ with typer CLI, mcp SDK, Pydantic 2.x.

## Entry Points
- MCP Server: `python -m automedia.mcp.server` (64 tools)
- CLI: `automedia <subcommand>` (21 commands)
- SDK: `from automedia import run_full_pipeline`

## Agent Governance (read AGENTS.md §0 first)
- Route every task through the role table in `AGENTS.md` §0 (Coder / Maintainer / Tester / User) and follow the role contract it points to.
- Conflict priority and the safety clause live in `AGENTS.md` §0; non-negotiable principles in `.specify/memory/constitution.md`.

## Agent Constraints
- **MUST NOT** archive with `--force` (Red Line 8 — only user may force-archive)
- **MUST NOT** commit real production data or credentials
- **MUST** use synthetic test fixtures from `tests/fixtures/synth/`
- **MUST** follow gate naming: G0-G6 (copy/content), V0-V7 (video), L1-L4 (lifecycle), D1-D7 (distribution), P1-P4 (repurpose) — plus pre-gate, CW, and H0
- **MUST** run `pre-commit run --all-files` before committing

## Dev Workflow
```bash
pip install -e ".[dev]"    # Install
pytest                      # Test
ruff check .                # Lint
mypy src/automedia/ --ignore-missing-imports   # Type check
python -m automedia.mcp.server  # Start MCP server
```

## Key Files
- `AGENTS.md` — Full agent codebase context (read first: §0 role routing, §4 gate order)
- `src/automedia/` — Core package
- `tests/` — Test suite
- `docs/` — Documentation (index: `docs/index.md`)
- `deploy/` — systemd deployment units

Numeric claims above (tools / commands) are gated by
`scripts/check-doc-consistency.py`, which derives them from the running
package — update them together with `AGENTS.md` §2, never by hand-count.
