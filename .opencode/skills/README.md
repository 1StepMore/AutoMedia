# Skills — Canonical Location

This is the **canonical location** for **maintainer skills** in this
project — instructions for coding agents working *on* the AutoMedia
codebase. These are auto-discovered by OpenCode as commands and skills.

**User-facing skills** (instructions for agents who *use* AutoMedia via
MCP tools) live in `docs/skills/` instead. They are **not** auto-
discovered — they are documentation for a different audience.

Skill files are maintained here and synced as native copies to each
agent's dedicated skill directory so every tool has them natively
available.

- `.claude/skills/` — native copies for Claude Code
- `.codex/skills/` — native copies for Codex CLI
- Cline — references this directory directly (no dedicated directory)

To add or update a skill: edit the `.md` file here, then sync the same
file to `.claude/skills/` and `.codex/skills/`.
