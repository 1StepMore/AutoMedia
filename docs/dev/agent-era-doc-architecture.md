<!-- doc-type: instruction -->
<!-- scope: generic — portable to any AI-agent-driven project -->
<!-- version: 1.1 -->
<!-- status: active -->

# Agent-Era Documentation Architecture — Generic Instruction

> **What this is.** A portable playbook for designing the documentation system of a
> software project that is built and operated by **AI coding agents** (vibe coding /
> agent-driven development). It answers: what docs to keep, which to delete, how to
> keep them current, and how to make the maintenance itself agentic.
>
> **How to use it.** Place one copy in each participating repo as
> `docs/dev/agent-era-doc-architecture.md` (or the repo's instruction home). Apply it
> as a checklist when (a) setting up a new agent-driven repo, (b) restructuring an
> existing repo's docs, or (c) auditing doc health. Each section is a decision
> procedure — not prose to admire.
>
> **Multi-repo projects.** Every participating repo carries this file **byte-identical**
> at the same path. There is one editing entry point (the canonical copy); downstream
> copies are never forked or hand-edited. Each copy declares the same `version` and is
> pinned by that repo's `scripts/doc_inventory.py --check` (see §7).
>
> **Worked example.** A production agent-driven project applying this playbook is
> [AutoInfo](https://github.com/1StepMore/AutoInfo), used here only as an example
> implementation. Its project-specific map lives in
> [`agent-era-doc-architecture-autoinfo.md`](agent-era-doc-architecture-autoinfo.md).
>
> **Status:** v1.1 (2026-11). Synthesized from 2024-2026 industry research
> (Anthropic context engineering, agents.md/CLAUDE.md conventions, Diátaxis, llms.txt,
> context-rot research) and validated against a production agent-driven system.

---

## 0. The one-paragraph doctrine

> Context is a finite attention budget. Every document an agent loads in a session
> costs tokens forever. The goal of a doc architecture for agent-driven development is
> **the smallest possible set of high-signal documents that maximizes the probability
> of correct agent behavior** — arranged so that detail is loaded *just in time*, never
> all at once.

Five consequences:

1. **Delete-first.** The highest-value doc edit is deletion. A doc that changes no agent
   behavior is dead weight.
2. **Index + progressive disclosure.** Agents hold lightweight identifiers (paths,
   links, queries); detail lives behind links, loaded on demand.
3. **Mechanical truth.** Facts that drift (counts, lists, statuses) are enforced by a
   deterministic check script — not by "please keep this updated" prose.
4. **Intent isolation.** One document = one purpose (reference / how-to / tutorial /
   explanation / instruction / archive). Mixing intents degrades both humans and agents.
5. **Archive aggressively.** One-off artifacts go to an archive path with a status
   marker. Nothing stays in a maintained path unless it is current and authoritative.

---

## 1. Document-type taxonomy: who reads what

The single most important move is to **separate documents by reader and by intent**.
An agent-driven project has two distinct agents and two distinct human readers:

| Reader | What they need | Canonical homes |
|--------|---------------|-----------------|
| **Coding Agent** (builds/maintains the code) | Rules, constraints, architecture decisions, conventions, "gotchas", build/test commands | Root `AGENTS.md` (or `CLAUDE.md`), nested `AGENTS.md` per subproject, `docs/adr/`, skills, generated inventory |
| **Direct User Agent** (operates the product via MCP tools / API) | Tool catalog, invocation patterns, error semantics, examples | Operator skills (`.opencode/skills/`: autoinfo-skill, translator-qa-skill), tool docs, usage examples, machine-readable index (`llms.txt`) |
| **Human maintainer** (director) | Status, decisions, roadmap, "why" | `README.md`, ADRs, CHANGELOG, governance docs |
| **Human end user** (consumer of the product) | Feature overview, quickstart, license | `README.md`, product docs |

**Classification rule — every document answers three questions before it earns a place:**

| Question | If NO → |
|----------|---------|
| Is it **read by** an agent or human in a real workflow? | Archive or delete. |
| Is its content **current and single-sourced** (no fact duplicated elsewhere)? | Fix, merge, or delete. |
| Is its **purpose single** (one quadrant, one reader)? | Split or merge. |

Document intents (Diátaxis + agent-specific genres):

| Intent | Purpose | Load cost | Example |
|--------|---------|-----------|---------|
| **Instruction** | Governs agent behavior (rules, constraints, must-not) | Always-loaded (root file) — keep tiny | `AGENTS.md` |
| **Reference** | Facts an agent looks up on demand | On-demand | Tool catalogs, API docs, data models |
| **How-to** | Procedure with steps | On-demand | "Add a new collector", "Run validation" |
| **Tutorial** | Learning a concept end-to-end | On-demand | Onboarding walkthrough |
| **Explanation** | Why a decision was made | On-demand | ADRs, research reports |
| **Decision record** | Immutable "we chose X because Y" | On-demand | `docs/adr/NNNN-*.md` |
| **Index/Map** | Pointers to the right doc for a task | Always-loaded (small) | `AGENTS.md` index, `llms.txt`, generated inventory |
| **Archive** | Historical record, never authoritative | Never (unless archaeology) | `docs/archive/` |

**Rule:** a root instruction file is an **index**, not a corpus. If your root file is
over ~200 lines, it has exceeded the adherence ceiling (Anthropic 2026 guidance:
Claude Code hard-caps CLAUDE.md at 200 lines; Codex at 32 KiB; industry consensus
100-200 lines). Move detail into on-demand files; keep only what changes agent
behavior and cannot be discovered from the repo itself.

---

## 2. What must exist (the necessary minimum)

A lean agent-driven repo needs exactly these layers. Anything beyond them must justify
its existence.

| # | Artifact | Purpose | Content (minimal) |
|---|----------|---------|-------------------|
| 1 | `AGENTS.md` (root) | Agent operating manual — always loaded | What the project is; build/test/lint commands; architecture rules (the non-negotiable invariants); MUST-NOT constraints; index of where detail lives |
| 2 | `README.md` | Human front door | What it is; quickstart; license; status summary (may duplicate a *few* facts with AGENTS.md — enforced by check) |
| 3 | `docs/adr/` | Decision records | One file per architecture decision: Context / Decision / Alternatives (why they lost) / Consequences; immutable; `README.md` index; `TEMPLATE.md` |
| 4 | Generated inventory | Machine-truth doc map | Every doc with path/size/type/status; regenerated by script, never hand-maintained |
| 5 | Consistency checker | Drift enforcement | Script that compares drift-prone facts across docs (README ↔ AGENTS ↔ skills) and exits non-zero on mismatch; wired into CI |
| 6 | One or more specs (optional, per project size) | Single-source authoritative reference | Data models, pipeline, quality gates — each owned by exactly one doc |
| 7 | Skills (optional) | On-demand procedures for agents | One `SKILL.md` per procedure: when to load, steps, constraints; loaded by name, zero context cost when idle |
| 8 | `docs/archive/` | Everything retired | Archived docs with status marker; never authoritative; referenced only as history |

**What to actively DELETE (the anti-patterns):**

- Second READMEs, "notes" files, meeting notes in maintained paths.
- Docs that duplicate a fact already held in a canonical place (drift magnets).
- One-off run reports, issue-closure evidence, migration snapshots, "final verdict"
  epics — these belong in `docs/archive/` (or git history), not maintained paths.
- Scripts that were used once to mutate data (backfills, matrix fills, one-time
  fixes). Git history retains them; `scripts/` should contain only *repeatable* tools.
- Any doc with a "Status: baseline" marker that hasn't been re-run per its own
  protocol. Either re-run it or archive it.

---

## 3. Dynamic content: the update mechanism

Document content splits into **static** (decisions, rules, explanations) and
**dynamic** (numbers, lists, statuses that change with every feature wave). The
architecture must make the dynamic part *self-updating*, not *diligently maintained*.

### 3.1 Classify every dynamic fact

| Fact class | Example | Update trigger | Mechanism |
|-----------|---------|---------------|-----------|
| **Registry counts** | MCP tool count, CLI groups, channels, domains | Any surface change | Generated from source (tool registry, config) — never hand-counted |
| **Scenario/test counts** | validation scenarios, test suite size | Feature wave | Regenerated by script; cross-checked by the consistency checker |
| **Status tables** | component ✅/🟡/❌ | Feature wave | Human-updated at wave end; verified by `--check` for the drift-prone subset |
| **Changelog** | version history | Every merge | Keep a Changelog format; versioned per release |
| **Roadmap/deferred items** | "planned" features | Wave end | Reviewed at wave close; moved to archive when shipped |
| **Decision records** | ADRs | Never (immutable) | New decision = new ADR; old one marked `Superseded by NNNN` |

### 3.2 The verification loop (the heart of the mechanism)

```
[any doc/code change]
        │
        ▼
[regenerate generated inventory]  ← script, 1 command
        │
        ▼
[run consistency checker]         ← script, exits non-zero on drift
        │
        ▼
[fix what it flags]               ← deterministic, no LLM needed for the flags
        │
        ▼
[commit]                          ← docs-as-code: the check is a CI gate
```

**Principles that make this work:**

1. **Deterministic over LLM.** A regex/glob check that catches "stale number" and
   "broken link" beats an LLM that "reviews" docs (LLM inconsistency detection has
   98% false-positive rates without careful filtering). Use scripts for what is
   checkable; use LLMs only for prose-quality judgments (and treat those as advisory).
2. **Check the referential, not just the numeric.** Beyond count equality, verify:
   every `docs/...` / `src/...` relative link in instruction files resolves; every
   code identifier referenced in instructions still exists in `src/`. This catches
   the "context rot" that silently misleads agents (23% of agent-config files in a
   2026 study contain stale references).
3. **A stale-inventory marker.** The generated inventory carries a
   `AUTO-GENERATED` header; the checker fails if the header is absent → a hand-edited
   or stale inventory is detected immediately.
4. **Re-run protocol tied to a real event.** "Re-run when a feature wave ends" (or a
   monthly cadence). A protocol with no trigger is a hope, not a mechanism.
5. **Regenerate after editing, not before.** The inventory's line counts must reflect
   the docs' current state when the check runs.

---

## 4. Skill synchronization (docs ↔ agent skills)

Skills (on-demand agent procedures) are themselves documentation — and they drift
like any doc. The sync mechanism:

1. **Every skill that documents a count or a surface** (tool counts, scenario counts,
   command groups) **is checked by the same consistency checker** that checks
   README/AGENTS. If a skill quotes "151 tools", the checker verifies 151 against the
   source of truth — the skill can no longer drift silently.
2. **Skill update is a code change**, subject to the same workflow: edit `SKILL.md`,
   regenerate inventory, run checker, commit. No "docs update" is exempt from the gate.
3. **Skills are loaded on demand** (by name) — so a skill's context cost is zero when
   idle. This means skills can be *detailed* (unlike the root file) — but they must be
   **narrow**: one skill = one procedure/domain. A skill that tries to be the whole
   operating manual is mis-architected.
4. **Separate the two skill audiences**: operator skills for the *direct user agent*
   (how to use the product's tools) vs developer skills for the *coding agent* (how to
   build/maintain the code). Keep them in separate homes with separate owners, so a
   change to one never silently affects the other's contract.
5. **Version the skill** (a `version:` field or CHANGELOG entry) so a behavioral change
   is traceable, and so the checker can flag "skill version older than the surface it
   documents."

---

## 5. The decision procedure (when in doubt)

Apply this checklist bottom-up when deciding whether a document/script earns its place:

```
1. Is it referenced by any real workflow (agent instruction, CI, Makefile, doc)?
   └─ No → DELETE or ARCHIVE.
2. Does it duplicate a fact held in a canonical place?
   └─ Yes → DELETE the copy (or merge and cross-reference).
3. Is its content current (verified against the code, not assumed)?
   └─ No → UPDATE, or ARCHIVE if it's a snapshot/one-off.
4. Does it have a single clear purpose and reader?
   └─ No → SPLIT or MERGE.
5. Is it dynamic content with no update mechanism?
   └─ Yes → Add a script/check, or MOVE to archive (snapshot).
6. Is it a repeatable tool (vs a one-time mutation)?
   └─ One-time → DELETE (git history retains it).
7. Would deleting it change any agent or human behavior?
   └─ No → DELETE. (This is the final test for every line of every file.)
```

**The acid test:** after the restructure, a fresh coding agent, given only the repo,
should be able to: (a) build and test the project from `AGENTS.md`; (b) find the right
doc for any task from the index; (c) never act on a stale number or a broken link —
because the checker would have failed CI first.

---

## 6. Worked example

This playbook is validated against a production agent-driven project. The example
implementation's project-specific map — every section pinned to concrete files,
plus its remaining debt — lives in the companion doc:
[`agent-era-doc-architecture-autoinfo.md`](agent-era-doc-architecture-autoinfo.md).

Read the generic rule here, then see one repo implement it there. Treat the example's
remaining gaps as a checklist, not as proof that the playbook is already complete.

---

## 7. Maintaining this standard

This playbook is itself a maintained document. Without an explicit protocol it
becomes a second rotting copy.

| Role | Owner / mechanism |
|------|-------------------|
| Source of truth (editing entry) | the canonical copy in the coordinating repo |
| Downstream copies | one byte-identical copy per participating repo, same path |
| Version marker | `<!-- version: N.N -->` in every copy's header |
| Hash pin | each repo's `scripts/doc_inventory.py` carries `DOC_ARCH_SHA256`; `--check` compares the copy's byte hash against the pin and fails on drift |

Change procedure for a rule change:

1. Edit the canonical copy — never a downstream copy — and bump `version`.
2. Sync the new bytes to every participating repo.
3. Update `DOC_ARCH_SHA256` in each repo's `scripts/doc_inventory.py`.
4. Run `python3 scripts/doc_inventory.py --check` in every repo; all must pass.
5. Record the cross-repo coordination in the umbrella issue.

Drift is detected by the per-repo `--check` (hash pin + inventory freshness). If a
copy and its pin disagree, the copy is wrong by definition — never "fix" the pin to
match an unreviewed edit.

---

## 8. Source index (retrieved 2026-08)

| Source | What it establishes |
|--------|--------------------|
| [Anthropic — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Context as finite budget; just-in-time context; progressive disclosure |
| [Anthropic — The new rules of context engineering for Claude 5](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models) | Remove 80% of system prompt with no loss; keep CLAUDE.md lightweight; spend tokens on gotchas |
| [Claude Code docs — CLAUDE.md/Memory](https://code.claude.com/docs/en/memory) | ≤200-line root file; hooks for deterministic rules; path-scoped rules; skills for on-demand |
| [Anthropic — Steering: CLAUDE.md vs skills vs hooks](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more) | Load-cost hierarchy: always-loaded / on-demand / zero-cost enforcement |
| [agents.md (official convention)](https://agents.md/) | README for humans, AGENTS.md for agents; nested files; plain markdown |
| [Chatcode — What Actually Helps Agents](https://chatcode.dev/articles/agents-md-claude-md-best-practices) | Three-part test for root-file facts; "measure a file by the behavior it changes" |
| [Continuum — AGENTS.md guide](https://continuumcode.ai/guides/agents-md/) | <100-line target; reactive authoring; symlink CLAUDE.md→AGENTS.md |
| [arXiv — Context Rot in AI-Assisted Development](https://arxiv.org/html/2606.09090) | 23% of agent-config files contain stale references; doc-consistency tooling transfers |
| [IBM — Markdown Mayhem](https://research.ibm.com/publications/markdown-mayhem-taming-the-agentic-documentation-explosion) | Governance of agent-written markdown; "erosion of authoritative truth" |
| [Springer — Detecting outdated code element references](https://link.springer.com/article/10.1007/s10664-023-10397-6) | 82.3% of popular repos have had a stale reference; they rot silently for years |
| [llmstxt.org (v2)](https://llmstxt.org/) | Index-file pattern: 10-30 curated links, detail behind links |
| [Diátaxis](https://diataxis.fr/) + [Diátaxis × AI](https://pasqualepillitteri.it/en/news/5528/diataxis-framework-documentation-ai) | Intent taxonomy; single-quadrant purity; retrieval-friendly reference |
| [David Lapsley — The Vibe Coding Trap](https://blog.davidlapsley.io/engineering/ai%20infrastructure/2026/03/30/vibe-coding-trap-architecture-matters-more.html) | Three artifacts agents need: tests, conventions, explicit decisions |
| [arXiv — Does My README Need Updating?](https://arxiv.org/html/2603.00489v1) | Surgical human-in-the-loop updates beat full regeneration |
| [arXiv — DocPrism](https://arxiv.org/html/2511.00215v1) | Deterministic checks beat naive LLM inconsistency detection |
| [OpenCode — Rules/Instructions](https://opencode.ai/docs/rules/) | AGENTS.md read first; progressive disclosure via `instructions` |

---

**End of playbook.** Apply §5 (decision procedure) to every existing doc and script;
apply §3 (update mechanism) to whatever remains; apply §4 (skill sync) to every skill.
Then the architecture maintains itself.
