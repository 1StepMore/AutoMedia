<!-- AUTO-GENERATED from src/automedia/governance/redlines.yaml -->
<!-- Do not edit by hand. Regenerate: python scripts/render_redlines.py -->

# Agent Red Lines

This file is the **distribution format** for agent red lines. The source of
truth is `src/automedia/governance/redlines.yaml`, which is a compiler input —
harnesses read this Markdown, never the YAML.

| ID | Constraint |
|---|---|
| `RL-ARCHIVE-FORCE` | MUST NOT archive projects using --force. Only the user may force-archive. |
| `RL-NO-PROD-DATA` | MUST NOT commit real production data, topic pool contents, or credentials to git. |
| `RL-ALLOWLIST` | MUST NOT modify src/automedia/mcp/mcp_allowlist.yaml without explicit user request. |
| `RL-SYNTH-FIXTURES` | MUST use synthetic test fixtures from tests/fixtures/synth/ for testing. |
| `RL-ARCHIVE-CMD` | MUST use the automedia archive command for archiving projects — never manual directory operations. |
| `RL-GATE-NAMING` | MUST follow the gate naming convention: G0-G6, V0-V7, L1-L4, D1-D7, P1-P4; plus H0, pre-gate, CW. |
| `RL-FAILURE-MODES` | MUST add new gates to automedia/gates/failure_modes.py when creating them. |
| `RL-PRECOMMIT` | MUST NOT skip pre-commit checks. Run pre-commit run --all-files before committing. |
| `RL-HOOK-READONLY` | MUST respect the GateHook readonly contract — hooks observe but never mutate. |
