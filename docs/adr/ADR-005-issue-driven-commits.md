# ADR-005: Issue-Driven Atomic Commit Discipline

### Status
Proposed · records the discipline this repository's work plans already follow

### Context

The repository's git history is issue-driven. Commits are organized around discrete issues, tasks, and waves rather than long-running feature branches with squash-merges. Conventional commit prefixes carry the intent of each entry, and subjects frequently reference issue and PR numbers. Recent history shows the pattern clearly:

| Commit | Subject |
|--------|---------|
| `798b497` | `refactor(mcp): split tools.py into 17 domain-specific submodules (PR #55)` |
| `145daf1` | `fix: resolve 113 masked test failures from tools-split regression` |
| `9b13793` | `fix: resolve test-collection blocking (#65) - restore gate_engine re-exports and fix mock gate-name collisions` |
| `9f2d7a4` | `docs: add AUTOMEDIA_FAKE_LLM and AUTOMEDIA_LLM_TIMEOUT to AGENTS.md and .env.example` |
| `fc57fe4` | `fix: address issues #56 #57 #58 #59 #60` |

Wave/task/Phase labels, issue numbers, and PR references all appear in subjects. Each entry is meant to be read, reviewed, and if needed reverted on its own. That intent deserves to be written down so it survives new contributors and agent-driven work.

### Decision

Each commit must be one atomic unit of work: one issue, or one task, maps to one commit. The discipline has four rules:

- **One commit per issue/unit of work.** A unit is the smallest piece of work that can be independently verified and reverted.
- **Conventional subjects restricted to** `docs:`, `feat:`, `fix:`, `refactor:`, `ci:`, `chore:`. Scopes are allowed (`refactor(mcp):`, `feat(pipeline):`) as are issue/PR references (`#65`, `PR #55`).
- **Independent verifiability.** The tree at each commit must pass its own tests and receipts. A commit that depends on a later commit for correctness is not atomic.
- **RED commits never land.** No commit is pushed while its test suite is red.

### Rationale

The adopted 7-phase AI development methodology, `docs/dev/七阶段AI开发流程-用CodingAgent交付成品的方法论.md` §5 (阶段 5: Issues), states the granularity rule directly: one issue corresponds to one verifiable commit. That rule pays off in four ways:

- **Bisectability.** `git bisect` and manual `git log` walks stay precise because every commit is a single logical change.
- **Reviewer clarity.** A reviewer can judge each commit's subject, diff, and test results in isolation, the same way the history above presents them.
- **Revert safety.** A bad commit can be reverted without dragging unrelated changes along.
- **Per-commit receipt checks.** The repo's gate discipline, including doc-consistency and test receipts, can be asserted at each commit, which only works if each commit is self-contained.

### Watch Out For

- **Lazy typer/mcp registrations do not change commit structure.** A commit that registers a CLI command or MCP tool is still one atomic commit; the registration lands with its feature, not as a separate chore.
- **Doc-count changes must land with the code change that makes them true.** Tool/command/gate counts asserted in `AGENTS.md`, `README.md`, and `docs/index.md` must move in the same commit as the code that changes the count, or the doc-consistency gate fails (`scripts/check-doc-consistency.py`).
- **No `--force` archive commits.** Red Line 8 forbids force-archiving projects; the archive CLI and MCP tool enforce it, and no commit may circumvent that.
- **No commits touching untracked test-run dirs.** `20260807_*` test directories and similar scratch output are never staged. Use exact `git add <path>` lists, never `git add -A` or `git add .`.

### Consequences

- History stays a reviewable sequence of verified units, consistent with the existing `git log` style.
- Work plans decompose into sequential commits, one per task, which is the pattern the plans in this repository already follow.
- Contributors and agents get an explicit, checkable definition of "done" per commit.
