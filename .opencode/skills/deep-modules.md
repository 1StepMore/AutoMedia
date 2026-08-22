---
name: deep-modules
description: AutoMedia deep-module refactoring practice (from the 七阶段 methodology, Ousterhout's Philosophy of Software Design). Load when refactoring src/automedia/, adding a feature that crosses multiple modules, or reviewing module shape — find shallow module clusters, merge into deep modules, lock behavior with module-boundary integration tests.
author: AutoMedia
version: 1.0.0
---

# AutoMedia Deep Modules Skill

> **Deep module** = small public interface + large hidden implementation
> (John Ousterhout). Agents cannot "remember" the codebase — every session
> rebuilds the map. Deep modules let an agent read the interface and navigate
> without tracing import/export chains. Shallow modules (interface ≈
> implementation, lots of thin glue) make agents get lost and make changes
> accidentally break structure.
>
> **Why now (human side)**: in the AI era the human's cognitive load is
> *rising* — the agent changes code constantly, so the "internal code map"
> you maintain in your head keeps invalidating. Any strategy that lowers
> cognitive load improves your AI experience directly. Deep modules are such
> a strategy: remember the interface, not the implementation map.

AutoMedia's methodology (doc `docs/dev/七阶段AI开发流程-用CodingAgent交付成品的方法论.md`
§3.1) defines deep modules and prescribes the 5-step friction-zone scan. This
skill is the loadable procedure; the RFC process has a live exemplar:
`docs/dev/deep-module-rfc-001.md` (the `pipelines/runner.py` friction-zone
scan — read it before your first scan).

## When to load

- Refactoring `src/automedia/` — especially merging "small, scattered, coupled"
  module groups.
- Adding a feature that touches 2+ existing modules (check whether the new
  code should be one deep module instead of three thin ones).
- Reviewing module shape before a large change (the AX-first lens: module
  shape IS agent experience).
- Writing the module-sketch section of a plan/PRD (methodology §3.1
  "预防": PRD-stage module sketch — new code starts deep).

## Procedure

Aligned with the methodology's 5-step "improved code-base architecture"
(预防: PRD-stage module sketch; 治疗: this procedure — fix existing bad modules):

1. **Explore for friction points** (explore mode, targeted area or full-library
   scan). Record: how many small files must you jump to understand one concept?
   Which modules have interface ≈ implementation (shallow)? Which pure
   functions were extracted "for testability" but the bug lives at the call
   site? Which coupled modules carry integration risk?
2. **List candidates WITHOUT designing interfaces.** Circle clusters that
   *share a concept and are coupled*. Do not design interfaces yet — that comes
   after the user picks.
3. **User selects one candidate** (B3 decides).
4. **Parallel divergent interface design.** Spawn multiple subagents to
   independently produce **maximally divergent** interface proposals — diversity
   is the point (you can mix the best parts later). The convergence is a human
   judgment call, not a merge of the first two.
5. **Recommend / mix → refactor RFC.** Land the chosen interface as a GitHub
   issue/RFC → one issue = one verifiable commit (ADR-005 discipline).
   Follow the shape of `docs/dev/deep-module-rfc-001.md`.
6. **Merge into the deep module.** Combine the cluster behind ONE small
   interface. AutoMedia's interface truth: `docs/user/api-reference.md`
   (public API), `AGENTS.md` §3 (Project Structure), `docs/dev/developer-guide.md`.
   Known watch-list from RFC-001 and AGENTS.md §3:
   - `pipelines/runner.py` — 1,617 lines, 23 functions, 13 lazy imports,
     47 callers of `run_full_pipeline` (RFC-001 selected it as the strongest
     friction zone — god-object orchestrator, import-cycle web, signature sprawl)
   - `cli/` — deliberately thin adapter layer over MCP, keep thin *by design*
   - `adapters/registry.py` — small, shallow but not frictional
   - `gates/` — already one-class-per-file, well-factored
7. **Lock behavior at the module boundary + verify + sync.** Integration
   tests exercising the module's public interface (input → observable
   output/effect), NOT unit tests per merged internal function. The MCP/CLI
   tool surface is the ultimate boundary test: a scenario asserting on the
   real response (see `validation-runner`). Then: full suite green
   (`make test` / `pytest`), `lsp_diagnostics` clean on changed files, doc
   layer synced (`doc-sync` if the interface changed).

## Guardrails

- **⚠️ The testability-extraction trap (LLM's most common bad refactor).**
  LLMs habitually say "let's extract this so it's testable" and pull out a
  pure function — but the real bug usually lives at the **call site** (how the
  frontend calls the backend, how the backend calls the CLI). Extracted small
  functions are shallow modules; the tests then lock the *shape*, not the
  *behavior*. Detection heuristic: **if after extraction you still need a pile
  of mocks to test it, you extracted wrong** — the direction should be the
  opposite: wrap the whole flow into one big service (a deep module), not peel
  off a testable fragment.
- **Never merge for merging's sake.** A module is shallow only if its
  interface fails to hide complexity from callers. Small single-responsibility
  modules that are easy to navigate are fine — the pathology is *scattered,
  coupled, thin* clusters.
- **Preserve the public contract.** SDK (`automedia/__init__.py`), CLI (18
  commands), and MCP (64 tools) surface shapes are entry-point-bound —
  internal merges must not change tool names, parameters, or the success
  envelope.
- **Tests first for refactors** (characterization): pin current observable
  behavior with boundary tests BEFORE merging; keep them green throughout.
- **Deep-module tests prefer the boundary**, not internals — per the
  methodology, read tests instead of implementations (gray-box view).

## Relationship to other skills

- `doc-sync` — after any refactor that changes a documented interface, follow
  its code-to-doc dependency map (MCP/CLI/gate/API sections) and its ADR
  pre-flight gate.
- `validation-runner` — add/update an integration scenario when the merge
  changes observable behavior (regression flywheel).
- `project-validation` — after the refactor, run the founder-expectation
  validation steps for the touched files.
