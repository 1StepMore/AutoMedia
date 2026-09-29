# Skills — Canonical Location

version: 1.0.0

This is the **canonical location** for **maintainer skills** in this
project — instructions for coding agents working *on* the AutoMedia
codebase. These are auto-discovered by OpenCode as commands and skills.

Available skills:

- `project-validation.md` — Post-change validation against founder expectations
- `doc-sync.md` — Documentation awareness & impact mapping
- `validation-runner.md` — Validation workflow, regression flywheel, RED→GREEN evidence
- `deep-modules.md` — Deep-module refactoring practice

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
file to `.claude/skills/` and `.codex/skills/`. That applies to the skills
listed above.

## Maintainer-only skills

`pr-review-merge.md` and `issue-triage.md` may exist in this directory on a
maintainer's own checkout. They act on **this repository's** issue tracker and
branch, so they are useless to AutoMedia's users — whose agents drive the
content pipeline over MCP and have no pull request here — and to outside
contributors. They are therefore deliberately **unlisted above, unsynced, and
uncommitted**; the matching `.gitignore` entries are what keep them out of the
repository. Do not create per-agent copies of them and do not commit them.

If you are cloning rather than maintaining: nothing is missing. The two files
simply do not ship.
