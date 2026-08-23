# PR Review & Merge — Check, Verify, Then Merge

version: 1.0.0

**Purpose:** A maintainer's workflow for handling GitHub pull requests: CHECK eligibility, VERIFY on CI and locally, assess VALUE, and only then MERGE (merge-commit style). Branch protection is OFF in this repo, so this skill's verification IS the only merge gate — it must be strict.

---

## When to Use (Triggers)

Load this skill whenever you are asked to:

- "review / merge / handle PRs" in this repo
- Investigate why a PR's CI check is failing
- Clear an accumulation of open PRs

The gate exists because nothing else does. With branch protection disabled, no required status checks, and no required reviews on `main`, every merge decision lands on you. Treat each PR as if the repo will not catch a mistake, because it will not. There is no human reviewer downstream of you and no CI-enforced protection on `main` — the four phases below are the entire safety net, so run them in order and run them fully.

Example scenarios that trigger this skill:

- An author opens a PR and asks "can you merge this?"
- You are clearing the PR queue and find several PRs with stale or red CI
- A dependabot PR lands and you need to decide whether to merge it
- A `check-pr-title` failure appears on an otherwise green PR

---

## Repository Facts

Verified facts about `1StepMore/AutoMedia` — rely on these, do not re-derive them:

- **Two remotes.** `origin` = `git@github.com:1StepMore/AutoMedia.git` (the canonical
  GitHub repo). `backup` = `git@github.com:renanzai40/AutoMedia_BackUp.git` (a
  push-only mirror owned by the `renanzai40` account).
- **Origin is currently SUSPENDED.** While suspended, `git push origin` fails and
  the canonical repo cannot receive new work. All push operations go to `backup`.
  Push with the `renanzai40` SSH key (the default key auths as `1StepMore`):
  ```bash
  GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519_renanzai40" git push backup main
  ```
  `~/.ssh/config` already defines `github.com-renanzai40` (same key, port 443) if
  you prefer `git@github.com-renanzai40:renanzai40/AutoMedia_BackUp.git`.
- **Backup may diverge.** Commits can land on `backup/main` that are not in the
  local clone (e.g. a direct push from another machine). Before relying on
  `backup/main`, fetch it and check for surprise commits:
  ```bash
  GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519_renanzai40" git fetch backup main
  git log --oneline HEAD..backup/main   # unexpected commits on backup
  ```
  A stray backup-only commit is a real change to review, verify, and if wrong,
  fix with a corrective commit — do not assume `backup/main == origin/main`.
- **Merge style is MERGE COMMITS.** History shows `Merge pull request #N from <branch>` commits. Do NOT squash or rebase-merge. Use `gh pr merge N --merge`.
- **Branch protection is NOT enabled.** No required status checks, no required reviews on `main`. Never assume CI protection or a human reviewer will catch a problem — the agent is the gate.
- **CI checks on PRs** (ci.yml + conventional-commits.yml + labeler + DCO):
  - `build`
  - `lint-typecheck`
  - `test` (Python 3.11 / 3.12 / 3.13)
  - `test-omni`
  - `validation-affected` (runs the validation scenarios affected by the change)
  - `checkov`
  - `gitleaks`
  - `trivy`
  - `validate-deploy`
  - `check-pr-title`
  - `DCO`
  - `label`

- **Title rule** (`.github/workflows/conventional-commits.yml`, via `amannn/action-semantic-pull-request`): allowed types are `feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert`; `subjectPattern: ^(?![A-Z]).+$` means the subject must NOT start with an uppercase letter.
  - **GOTCHA:** `feat(detectors): AI-taste detector framework ...` FAILS because the subject "AI-taste" starts uppercase. This is exactly what happened to PR #80 — `check-pr-title` failed for that reason while every other check passed.
- **DCO:** every commit must be sign-off'd (`git commit -s`, `Signed-off-by:` trailer). Verified by the DCO CI check.
- **Special PR classes:**
  - **dependabot PRs:** weekly dependency bumps, `dependencies` label. Rely on CI, low-touch.
  - **release-please PRs:** auto release PRs titled `chore(main): release ...`. NEVER hand-merge — the bot manages them.
- **Post-merge behavior:** release-please handles releases (auto version bump + CHANGELOG + GitHub release). A `Fixes #N` / `Closes #N` keyword in a merged PR auto-closes the linked issue; if it is absent, close the issue manually per the issue-triage skill.
- **Red lines** (AGENTS.md §5): run pre-commit before committing; never force-archive; use synthetic test fixtures only; never modify `mcp_allowlist.yaml` without explicit request.

---

## Workflow

Four phases, in order. Phase 1 and Phase 2 are hard gates: if either fails, the PR does not merge. Phase 3 decides whether the PR is worth merging at all. Phase 4 is the mechanical merge. Never skip a phase, and never merge on a partial pass.

### Phase 0 — Classify the PR

Before the four phases, identify what kind of PR you are dealing with, because the class changes how strict you are:

- **dependabot** (label `dependencies`) → rely on CI, low-touch, merge directly when green (see Special Cases).
- **release-please** (title `chore(main): release ...`) → do NOT hand-merge, the bot manages it.
- **Everything else** → full four-phase review below.

A quick `gh pr view N --json title,labels` tells you the class in one call.

### Phase 1 — CHECK (metadata, before the CI verdict)

Run these before trusting any CI result:

1. **Inspect the PR metadata and changed files:**
   ```
   gh pr view N --json title,body,labels,author,headRefName,baseRefName,files
   ```
   Confirm the base branch is `main`, note the labels, and scan the file list for scope (code, docs, dependency bumps, or mixed).

2. **Title rule:** the title must use a correct conventional type AND the subject must NOT start with an uppercase letter. If `check-pr-title` fails: **DO NOT merge.** Ask the author to edit the title (e.g. "AI-taste ..." → "ai-taste ..."), or edit it yourself as maintainer.
   - Live example: PR #80 fails ONLY `check-pr-title` because the subject starts with uppercase "AI-taste". Everything else passes. It still must not merge.
   - A corrected title like `feat(detectors): ai-taste detector framework` passes: `feat` is an allowed type and the subject starts lowercase.
   - Do not try to "fix" a failing title by bypassing the check — the check is the contract. Fix the title itself, then let CI re-run.

3. **DCO:** the DCO check must be green — every commit signed with a `Signed-off-by:` trailer. If the DCO check fails, ask the author to re-sign their commits (`git rebase --signoff`), then re-run checks.

4. **Linked issue:** the PR should link a real issue (Related Issues section or a Fixes/Closes #N). No linked issue → require justification before proceeding.

5. **Diff sanity:** `gh pr diff N` — reasonable size, no unrelated changes, no secrets, no dead code / AI slop (gitleaks also guards secrets). A large diff that also renames unrelated modules is a red flag; request it be split.

### Phase 2 — VERIFY (CI + local)

1. **Required checks:** `gh pr checks N --required` — ALL must pass. NEVER merge with a failing or pending required check. Wait for pending checks to settle before making a decision. A single red or pending check blocks the merge, no exceptions.
2. **Local verification** mirroring the CI gate: check out the branch, then run:
   - `pytest`
   - `ruff check .`
   - `mypy src/automedia/ --ignore-missing-imports`
   - `python3 scripts/check-doc-consistency.py`
   - If the PR touches docs, tool/command counts, or any doc-claim, load the **doc-sync** skill to validate doc consistency.
   - CI green is necessary but not sufficient — the local run is the second opinion on the exact branch state.
3. **ADR-005:** confirm the PR history contains no RED commits (no commit whose tests fail). The commit sequence should read as atomic, issue-driven steps.

### Phase 3 — VALUE assessment

- Does it fix a real issue or add meaningful value, with tests and synced docs?
- Decision tree:
  - Unfixable / duplicate / superseded → close with a comment (`gh pr close N`).
  - Fixable issues → review with requested changes.
  - Good → proceed to merge.
- **No-slop gate:** no unrelated edits, no dead code, no gratuitous refactors. A PR that passes every check but adds nothing of value is still a no.

### Phase 4 — MERGE

1. Only after Phase 1 + Phase 2 pass AND Phase 3 confirms value.
2. Merge with a merge commit:
   ```
   gh pr merge N --merge
   ```
   Do NOT use `--squash` or `--rebase`.
3. The linked issue auto-closes via the Fixes/Closes keyword. If it did not, close it with a comment (per issue-triage Step 5).
4. **Do NOT merge when:**
   - `check-pr-title` is failing
   - ANY required CI check is failing or pending
   - there is no real value (bad diff, no issue, no tests)
   - the PR is a dependabot or release-please PR (special handling below)

---

## Worked Example — PR #80

Scenario: title `feat(detectors): AI-taste detector framework + G1 humanize-verify loop (#62)`.

- Phase 1 title rule: type `feat` is allowed, but the subject starts with uppercase "AI-taste" → violates `subjectPattern: ^(?![A-Z]).+$` → **DO NOT MERGE**.
- CI: `check-pr-title` fails while `build`, `lint-typecheck`, `test`, and the security checks all pass. The green checks do not rescue the PR.
- Action: request a title edit ("AI-taste" → "ai-taste") or edit it as maintainer, then re-verify before merging. Under no circumstances merge while `check-pr-title` is red.

This is the canonical failure pattern in this repo: a PR that is otherwise perfect in every respect, blocked by a one-word title fix. The rule is not negotiable.

---

## Common Situations & Responses

| Situation | Response |
|-----------|----------|
| `check-pr-title` red, everything else green (e.g. PR #80) | Do not merge. Fix the title (lowercase the subject start) or ask the author, then re-verify. |
| DCO red | Do not merge. Ask author to `git rebase --signoff`, then re-run checks. |
| Required CI check pending | Wait. Do not merge while pending. |
| Required CI check failing | Do not merge. Investigate, report the failure, request a fix. |
| No linked issue, no justification | Do not merge. Request an issue link or written justification. |
| Diff is large or touches unrelated files | Request the PR be split or scoped down. |
| dependabot PR, all checks green | Merge directly with `--merge` (low-touch, rely on CI). |
| release-please PR | Do not touch. Let the bot manage it. |

---

## Decision Checklist (fast path)

Run through this in order; any "no" stops the merge:

1. PR class is not dependabot/release-please? → else handle per Special Cases.
2. `check-pr-title` green (type allowed, subject lowercase)? → else DO NOT MERGE.
3. DCO green (all commits signed)? → else request re-sign.
4. Links a real issue? → else require justification.
5. Diff is sane (scoped, no secrets, no slop)? → else request changes.
6. All required CI checks pass, none pending? → else wait or request fixes.
7. Local suites pass (pytest, ruff, mypy, doc-consistency)? → else request fixes.
8. No RED commits in history (ADR-005)? → else request cleanup.
9. Real value with tests and synced docs? → else close or request changes.
10. If all of the above → `gh pr merge N --merge`.

---

## Post-Merge

- Confirm the merge landed on `main` as a merge commit (`Merge pull request #N from <branch>`).
- **Push the updated `main` to `backup`** (origin is suspended — backup is the
  only place new work reaches the remote):
  ```bash
  GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519_renanzai40" git push backup main
  ```
  Verify the push landed and no local commits are stranded:
  ```bash
  GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519_renanzai40" git fetch backup main
  git rev-list --count backup/main..HEAD   # 0 = fully synced
  ```
- Verify the linked issue closed if a Fixes/Closes keyword was present; otherwise close it with a comment referencing the merge (per issue-triage Step 5).
- Do not hand-run releases. release-please handles version bumps, CHANGELOG, and the GitHub release automatically. If a release is expected and did not happen, note it but do not attempt a manual release.

---

## Special Cases

- **dependabot:** CI-green dependency bumps can be merged directly (merge-commit style) after checks pass. Low-touch, rely on CI. Review the diff size and changelog if present, but do not block on reviewer-style back-and-forth.
- **release-please:** never hand-merge; let the bot manage release PRs. Touching them manually breaks the release automation.

---

## Red Lines

- The merge gate IS the verification gate — never merge on CI green alone without local verification of the core suites.
- Never merge a PR that fails `check-pr-title` (repo-enforced rule).
- Merge commits only — never squash or rebase-merge.
