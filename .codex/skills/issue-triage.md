# Issue Triage — Deal with GitHub Issues

version: 1.0.0

**Purpose:** When asked to deal with, triage, or close GitHub issues, classify every open issue, ADDRESS the valid un-addressed ones (ADR-005 one-commit-per-issue discipline), VERIFY before closing, and CLOSE issues already dealt with.

---

## When to Use (Triggers)

- The user asks you to "deal with", "triage", or "close" issues.
- A scheduled sweep of open issues.
- A pre-release hygiene pass over the issue tracker.

When any of these triggers fire, run the full workflow below. Do not cherry-pick a single issue and stop. The job is to leave the tracker in a defensible state: every open issue is either genuinely in flight, awaiting a human, or closed with evidence. If you were asked to handle a specific issue by number, still run the classify step for that issue before doing anything else.

## Repository Facts (verify, don't assume)

- **Repo:** `1StepMore/AutoMedia`. Issues are BILINGUAL — read the body and comment in the language the issue uses (Chinese or English; real issues like #62 are written in Chinese). Never default to English when the reporter wrote in Chinese, and never assume a language from the title alone; the body decides.
- **Remotes & push target:** `origin` = `git@github.com:1StepMore/AutoMedia.git`
  (canonical; fetch over SSH, push over HTTPS authenticated by the `gh` CLI — the
  `github.com` SSH alias is a read-only deploy key). `backup` =
  `git@github.com-renanzai40:renanzai40/AutoMedia_BackUp.git` (an archive mirror
  owned by `renanzai40`). Push new work to `origin`:
  ```bash
  git push origin main
  ```
  `~/.ssh/config` also defines `github.com-renanzai40` (the backup account's key,
  port 443) if you sync the mirror:
  ```bash
  GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519_renanzai40" git push backup main
  ```
  Commit-verification steps below (Step 4) check `origin/main`, the canonical branch.
- **Issue templates** (`.github/ISSUE_TEMPLATE/`): `bug_report.yml` auto-labels `bug` and REQUIRES a "Regression scenario" field; `feature_request.yml` auto-labels `enhancement`. There is NO `.github/config.yml` and no issue-labeling automation. Labels only arrive from templates, humans, or manual action.
- **Labels in use:** `bug`, `enhancement`, `human-gated`, `stale`, `pinned`, `security`, `dependencies`, plus path labels (core, gates, adapters, cli, mcp, omni, decision, hitl, pool, tests, docs, ci, docker, build, tooling, deploy). These are the only labels you should expect; anything else is a signal something changed.
- **Stale bot** (`.github/workflows/stale.yml`): issues stale after 60d, closed after 14 more; exempt labels `pinned`, `security`, `enhancement`. Let the bot handle pure age-closures — never close an issue on age alone unless it is ALSO already dealt with.
- **Commit discipline:** `docs/adr/ADR-005-issue-driven-commits.md` — one atomic commit per issue, conventional subjects with issue refs (`(#N)`), RED commits never land, never `git add -A` (use exact `git add <path>`).
- **Red lines** (AGENTS.md §5): run pre-commit before committing; never force-archive; synthetic test fixtures only; never modify `automedia/mcp/mcp_allowlist.yaml` without explicit user request.

These facts are verified. If anything about the repo disagrees with this list, stop and confirm with a human rather than assuming the skill is stale.

### Language of communication

Issues arrive in either Chinese or English, and the language of the issue body is the language of every comment you make on it, including close comments and status updates. A triage pass is not the place to switch an issue's language. Match the reporter. This matters most for real issues: #62 has a Chinese body, so any comment on it is written in Chinese.

### How labels and templates behave

- `bug_report.yml` fills the "Regression scenario" field on the bug template, and that field gates implementation and verification. A bug missing its Regression scenario cannot be addressed responsibly; ask for it before implementing (see Step 3).
- `feature_request.yml` routes requests to the `enhancement` label, which the stale bot exempts from age-closure. An `enhancement` issue is never closed on age alone.
- There is no label automation beyond the two template defaults. A `human-gated` label is put on an issue deliberately by a human, which is exactly why the classification table treats it as an absolute stop.

## Workflow

Run the steps in order for the full sweep. Every step depends on the one before it: classify nothing until you have read everything, address nothing until it is classified as valid and un-addressed, close nothing until verification passed.

### Step 1 — Sweep

Run `gh issue list --state open --limit 200` (optionally with `--label`, `--json number,title,labels,updatedAt`). Use the JSON variant when you need `updatedAt` to judge staleness without trusting your memory of dates.

Read EVERY open issue body in full before deciding anything. A triage pass that skips a body is a guess. Issues carry context in their Regression scenario, in the linked PRs, and in the conversation thread; all of it matters for the classification step.

Two practical notes while sweeping:

- Note, per issue, whether a PR exists and whether it is merged, open, or closed-but-unmerged. This single fact drives the most common decision row.
- Note the issue language as you read. By the end of the sweep you should know, for every issue, which language your comments will be in.

Keep a working list as you go, one line per issue, with three columns: issue number, candidate decision from the table, and the evidence you will need for the close comment (PR number, commit SHA, canonical issue, or repro result). Fill the evidence column during the sweep, not from memory later.

### Step 2 — Classify

Decide each issue with the table below. Check every row for each issue; when more than one row applies, the most conservative decision wins. Keeping an issue open is always the safe default, so when rows conflict, default to open.

| Condition | Decision |
|-----------|----------|
| Has an OPEN unmerged PR linking it (`Fixes #N` / `Closes #N` / `(#N)` in PR title or body) | KEEP OPEN. Comment noting the PR. Never close. |
| Fix already merged into main | VERIFY (Step 4), then CLOSE with evidence (PR number / commit SHA). |
| Duplicate of another issue | CLOSE with comment linking the canonical issue. |
| No longer reproducible | For a bug: attempt repro via the issue's Regression scenario; CLOSE with evidence if unresolvable. |
| Clearly out of scope / wontfix | CLOSE with rationale (ask a human first if uncertain). |
| Valid and un-addressed | ADDRESS it (Step 3). Do not close. |
| Label `human-gated` | NEVER auto-close or auto-judge. Keep open, post a status comment, flag for a human/AFk trigger. |
| Only stale by age (no other condition) | Leave for the stale bot. |

How to read the table:

- **Open-PR row first.** Check whether a linking PR is open before anything else. An issue with an open addressing PR is in flight; nothing about its age or its eventual fix changes its state. This row beats the merged row (not merged yet), the stale row (in flight, not abandoned), and the un-addressed row (it is being addressed).
- **The merged row requires evidence.** "I think I saw this land" is not a decision. Step 4 exists so every close is backed by a PR number or a commit SHA in main.
- **human-gated is absolute.** That row never yields to any other condition, including duplicate or wontfix, unless a human explicitly overrides it. The label means a human chose to gate this issue; an agent reversing that choice is the one failure this skill cannot undo cleanly.
- **Age is the bot's job.** If the only thing wrong with an issue is that it is old, the stale bot owns it. Adding a manual age-close just races the automation and can close something the exempt labels were meant to protect.

**Worked example:** issue #62 (labels `enhancement`, `human-gated`, Chinese body) is addressed by open unmerged PR #80. Two rows apply at once: the open-PR row says KEEP OPEN, and the human-gated row says never auto-close. Either alone forces the same result, so #62 stays open. The correct action is to comment on the issue (in Chinese) noting that PR #80 addresses it, and move on.

**Another worked example:** an issue with an open PR that carries only `bug` and `cli` labels, reported in English, has no other condition. The open-PR row fires, so it stays open regardless of its age. Nothing else needs checking.

Ordering the sweep's actions: process every KEEP OPEN issue first (comment and move on), then every VERIFY-and-close candidate, then every duplicate and wontfix, and leave the ADDRESS set for last, because that is the only branch that produces commits. Whatever you do, do not close an issue you have not yet classified, and do not classify an issue you have not fully read.

### Step 3 — ADDRESS a valid un-addressed issue

1. Read the full issue. For a bug, if the "Regression scenario" field is missing, comment asking the reporter to provide it BEFORE implementing. The field is required by the template for a reason: a bug without a repro path cannot be verified, and this skill never closes on assumption.
2. Implement per ADR-005: ONE atomic commit per issue, conventional subject + `(#N)`. One issue, one commit, one change. Never bundle unrelated edits into the same commit, and never stage with `git add -A`; stage exact paths with `git add <path>`.
3. Open a PR with `Fixes #N` / `Closes #N` in the body. Do NOT close the issue — the merge closes it (auto via the keyword, or manually post-merge per the pr-review-merge skill). The issue closes when the work lands, not when the PR is drafted. Closing it early would violate the open-PR rule the moment the PR is opened, and would break the one-issue-one-commit trail.
4. Run pre-commit before committing. A RED commit never lands, and the way to keep commits RED-free is the pre-commit hook, not post-hoc fixes.
5. **Push the branch to `origin`** (canonical; HTTPS via `gh`):
   ```bash
   git push origin <branch>
   ```
   Then open the PR as usual. If you also keep the `backup` mirror, sync `main`
   with the `renanzai40` key after the merge (see the pr-review-merge skill).

If two issues in the same sweep both qualify as valid and un-addressed, address them as separate commits and separate PRs. Never fold issue A into issue B's PR to save a round trip; that is exactly the discipline ADR-005 exists to prevent.

### Step 4 — VERIFY before closing

Confirm the fix is actually in main: `git log --oneline main | grep -i '#N'` or `gh pr view N --json mergedAt`. For bugs: the Regression scenario is confirmed resolved. Never close on memory or assumption — always evidence. If the fix is not in main, the issue is not done, and the correct state is either KEEP OPEN (PR pending) or ADDRESS (no PR exists). There is no third state where an issue is both closed and unverified.

Verification is not the same as recalling the merge. A commit SHA from `git log` or a `mergedAt` from `gh pr view` is evidence; a vague recollection is not. When the issue is a bug, add the repro step: run the Regression scenario from the issue against current main and confirm it no longer reproduces, then say so in the close comment.

### Step 5 — CLOSE

Run `gh issue close N --comment "<summary in the issue's language, citing evidence>"` (add `--reason completed|not planned` when appropriate). The comment must name the evidence: the PR number or commit SHA that resolved it, or the canonical issue for duplicates, or the repro attempt for not-reproducible. Write the comment in the language of the issue body.

Keep the comment short: what was decided, why, and the evidence. No essays. A reader (the reporter, or a later maintainer) should be able to tell in one glance why the issue is no longer open.

### Reporting back

When the sweep is done, summarize what happened, grouped by outcome:

- **Kept open** (in flight): the issues with open PRs, and any `human-gated` issues you flagged.
- **Closed with evidence**: issue numbers with the PR/SHA each was closed on.
- **Closed as duplicate / wontfix**: issue numbers plus the canonical issue or rationale.
- **Addressed**: issues you implemented, with the PR numbers you opened.
- **Left for the stale bot**: issues that are only old.

Keep the summary in the language of the person who asked. If the ask was in Chinese, report in Chinese. End with a count of open issues remaining and any issue that still needs a human decision, so nothing is silently dropped.

## Red Lines

- Never close an issue whose addressing PR is still open (except explicit duplicate/wontfix).
- Never auto-close a `human-gated` issue.
- Never commit production data or credentials; use synthetic fixtures only.

These are not suggestions. A triage pass that violates any of them needs to be undone, and the undone work is worse than the open issue it was meant to clear. When in doubt about any single issue, leave it open and note it for the human rather than force a verdict.

## Pitfalls

- **Closing an issue with an open PR.** The merge closes the issue, not you. If the PR is still open, the issue stays open; the only exceptions are explicit duplicate or wontfix calls.
- **Closing a `human-gated` issue for any reason.** There is no agent-side justification. Flag it for a human and stop.
- **Commenting in the wrong language.** The issue body sets the language. A Chinese issue answered in English is a broken communication, not a cosmetic slip.
- **Closing on age alone.** The stale bot has the schedule, the exempt labels, and the 60d/14d timing. Your job is not to race it.
- **Closing a bug without running its Regression scenario.** "No longer reproducible" requires an actual repro attempt and evidence in the close comment.
- **Judging a bug without its Regression scenario.** If the field is missing, ask for it before implementing. Do not guess at the repro.
- **One issue, multiple commits, or multiple issues, one commit.** ADR-005 is strict: one atomic commit per issue, conventional subject with `(#N)`.
- **`git add -A`.** Never. Stage exact paths only.
- **Closing before verifying in main.** Memory is not evidence; `git log` and `gh pr view` are.
