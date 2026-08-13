# RFC-001: Deep-Module Refactor — `automedia/pipelines/runner.py` Friction-Zone Scan

**Status:** Proposed
**Date:** 2026-08-13
**Scope:** Document-only scan per the deep-module methodology (see
`docs/dev/七阶段AI开发流程-用CodingAgent交付成品的方法论.md` §3.1 — "Deep Modules（深模块）",
after *Philosophy of Software Design*, John Ousterhout).

---

## 1. Context — Why This Zone

§3.1 defines a *deep module* as **small interface + large implementation**,
and prescribes a 5-step scan: (1) explore to find a friction zone, (2) list
candidates without designing interfaces, (3) pick one candidate, (4) design
maximally-different interfaces in parallel, (5) recommend and write an RFC.

**Step 1–2 — candidates scanned (evidence gathered):**

| Candidate | Evidence | Verdict |
|-----------|----------|---------|
| `src/automedia/pipelines/runner.py` | 1,617 lines; 23 functions; ~3 public symbols; 13 function-level lazy imports; 47 callers of `run_full_pipeline` | **Strongest friction — selected** |
| `src/automedia/core/config_loader.py` | 266 lines; 7 functions; `_env_to_config()` (lines 105–192) holds ~87 lines of env-mapping | Moderate; self-contained, no cycle risk |
| `src/automedia/adapters/registry.py` | 89 lines; single `AdapterRegistry(BaseRegistry)` class | Small; shallow but not frictional |
| `src/automedia/gates/base.py` | 171 lines; `GateRegistry` + `BaseGate`; gate implementations already one-class-per-file (7,702 lines across `gates/`) | Already well-factored; no god-object |

**Step 3 — selection.** `src/automedia/pipelines/runner.py` is the shared
orchestration entry point for all three API layers (SDK, CLI, MCP) and is the
single largest module in the `automedia/` core. Concrete friction observed:

1. **God-object orchestrator.** One file mixes six+ distinct sub-concerns:
   mode derivation, gate selection/composition, brand/workflow resolution,
   context building, engine execution, source-material resolution, MD5
   tracking, asset collection, and error handling.
2. **Import-cycle web.** 13 function-level (lazy) imports force the module to
   defer importing `gate_engine`, `gates.base._registry`, `engines`, `hitl`,
   `hooks`, `core`, `manifests`, and `language_config` until call time —
   evidence that `runner.py` sits at the center of the package import graph
   (see §3 for line references).
3. **Signature sprawl.** The single public entry `run_full_pipeline()` takes
   **17 parameters** (line 727); every new capability (workflow, director
   mode, source material, platform filtering) extends the signature rather
   than composing.
4. **Agent cognitive load.** Per §3.1's motivation, any agent (or human)
   working on pipeline behavior must load ~1,600 lines into context because
   sub-concerns have no module boundary of their own — they exist only as
   private functions inside one file.

This scan is **document-only**. Implementation of the recommended option is a
follow-up plan and is out of scope for this RFC.

---

## 2. Scan Findings

### 2.1 Structure

`src/automedia/pipelines/runner.py` (1,617 lines) exposes a thin public
surface over a large private implementation:

**Public symbols (consumed outside the module):**

| Symbol | Location | External consumers (verified) |
|--------|----------|-------------------------------|
| `run_full_pipeline` | line 727 | 47 callers: `src/automedia/cli/commands/run.py:19`, `src/automedia/cron/runner.py:15`, `src/automedia/mcp/tools/pipeline.py:193,276`, `src/automedia/mcp/tools/strategy.py:200`; lazy re-export via `automedia/__init__.py:58` and `automedia/pipelines/__init__.py:34`; tests incl. `tests/test_runner.py`, `tests/test_e2e/` |
| `VALID_MODES` | line 207 | `cli/commands/run.py:19,132`, `core/workflow.py:238–244` (lazy), `mcp/tools/cron_tools.py:15,89`, `mcp/tools/_shared.py:62` |
| `validate_gate_modifiers` | line 383 | `core/workflow.py:53` (doc reference) |

**Private functions grouped by sub-concern (line ranges):**

| Sub-concern | Functions |
|-------------|-----------|
| Mode derivation | `_derive_mode_from_platforms` (241), `_check_hyperframes` (262) |
| Gate selection & composition | `_compose_gate_list` (466), `_collect_platform_gate_modifiers` (504), `_filter_gates_for_platform` (594), `_select_gates` (984), `_build_gates_from_names` (1535), `validate_gate_modifiers` (383) |
| Brand / workflow resolution | `_resolve_brand_and_workflow` (906), `_merge_workflow_config` (666) |
| Context & engine execution | `_build_pipeline_context` (1067), `_setup_and_run_engine` (1207), `_run_pipeline` (835) |
| Source material | `_resolve_source_material` (1385) |
| MD5 / integrity | `_verify_resume_integrity` (307), `_record_gate_md5s` (356) |
| Asset collection | `_collect_assets` (284), `_collect_video_assets` (1585) |
| Error handling | `_handle_pipeline_error` (1348), `_collect_gate_failure_overrides` (1476) |
| Result formatting | `_finalize_pipeline` (1234), `_build_gates_log` (1567) |

### 2.2 Coupling

**Outward (imports):** only two top-level internal imports
(`automedia.core.overrides.OverridesLoader` at line 19; structlog). All other
dependencies are lazy, function-level imports — 13 sites at lines 286, 318,
361, 415, 854, 912, 994, 1083, 1215, 1246, 1355, 1553, 1569 — pulling from
`pipelines.gate_engine` (incl. `AssetInfo`, `GateEngine`, `PipelineResult`,
`GateLogEntry`), `gates.base._registry`, `hooks.md5_tracker`,
`hooks.cost_tracker`, `hooks.pipeline_history`, `core.config_loader`,
`core.llm_client`, `core.logging`, `core.project`, `core.workflow`,
`manifests.brand_profile_schema`, `engines` (+`engines.errors`,
`engines.base`), `hitl`, `pipelines.language_config`, `gates._context`, and
`automedia.gates` (side-effect import for registration, line 994).

**Inward (dependents):** CLI (`cli/commands/run.py`), cron
(`cron/runner.py`), MCP (`mcp/tools/pipeline.py`, `mcp/tools/strategy.py`,
`mcp/tools/cron_tools.py`, `mcp/tools/_shared.py`), `core/workflow.py`
(lazy), and the package `__init__` files, which re-export
`run_full_pipeline` through a **lazy `__getattr__` import map** —
`automedia/pipelines/__init__.py:34` and `automedia/__init__.py:58`. The
lazy re-export plus the 13 in-function imports are direct evidence that
eager import of `runner.py` would create import cycles.

### 2.3 Shallow-module candidates & god-object smell

- **God-object smell:** `runner.py` is the only file an agent must read to
  understand pipeline behavior, yet 6+ concepts (gate selection, source
  material, MD5 integrity, asset collection, workflow merging, error
  handling) have no identity of their own. Per §3.1's "识别标准", the fix is
  **not** to extract tiny pure functions "for testability" (the documented
  anti-pattern), but to give whole sub-processes real module boundaries.
- **Shallow-module risk elsewhere (noted, not chosen):** `adapters/registry.py`
  (89 lines) and `gates/base.py` (171 lines) are small but their interfaces
  match their size — they are legitimately shallow and fine as-is.
- **Already-observed friction markers:** `decision_mode` and
  `force_provenance` parameters are deprecated-but-retained (lines 766–769,
  782–784 in the `run_full_pipeline` docstring; `_run_pipeline` emits a
  `DeprecationWarning` at lines 863–869) — signature creep that a
  config-object interface would absorb.

---

## 3. Interface Proposals (maximally different)

Three designs, deliberately divergent along the axes of *call-shape change*,
*module granularity*, and *abstraction mechanism*.

### Proposal A — Keep the facade, extract sub-process modules (minimal structural diff)

Move the buried sub-concerns out of `runner.py` into sibling modules under
`automedia/pipelines/` — e.g. `gate_selection.py` (gate-name lists,
`_compose_gate_list`, `_filter_gates_for_platform`,
`_collect_platform_gate_modifiers`, `validate_gate_modifiers`), `context.py`
(`_build_pipeline_context`, `_resolve_source_material`), `integrity.py`
(`_verify_resume_integrity`, `_record_gate_md5s`), `assets.py`
(`_collect_assets`, `_collect_video_assets`), `finalize.py`
(`_finalize_pipeline`, `_build_gates_log`, `_handle_pipeline_error`).
`runner.py` shrinks to a thin coordinator (~400 lines) whose public signature
stays byte-identical.

- **Tradeoffs:** (+) Zero API break — 47 callers, lazy `__init__` maps, and
  tests untouched; (+) directly reduces the §3.1 cognitive-load cost, the
  primary goal; (+) each sub-module becomes independently testable at its own
  level (per §3.1: integration-test the sub-process, not the helper);
  (−) does not address signature sprawl — `run_full_pipeline` still takes 17
  params; (−) module boundaries follow existing function clusters rather than
  a redesigned flow.

### Proposal B — Single `PipelineRunSpec` config object (data-driven interface)

Replace the 17-parameter signature with one dataclass, e.g.
`PipelineRunSpec` (topic, brand, mode, workflow, hooks, platforms,
resume_from, director, source_path, source_url, …), and keep
`run_full_pipeline(spec: PipelineRunSpec)` (plus a thin
`run_full_pipeline(**kwargs)` compat shim) as the entry. Internal
sub-concerns are reorganized into pure functions of the spec: a
`build_pipeline_plan(spec) -> PipelinePlan` (gate list + context seed) and a
`execute_plan(plan) -> PipelineResult`.

- **Tradeoffs:** (+) Kills signature sprawl and the deprecated-parameter
  treadmill (`decision_mode`, `force_provenance` can be dropped from the
  spec with a clean migration path); (+) a spec object is serializable —
  MCP tools can validate it against a schema instead of hand-plumbing 17
  kwargs; (+) call sites read as data, not as a positional minefield;
  (−) breaking change to the SDK surface unless a compat shim is kept
  indefinitely; (−) does not by itself reduce the 1,617-line file — the
  sub-process extraction of Proposal A is still needed; (−) risks becoming a
  "kitchen-sink DTO" if sub-concerns are not given real boundaries.

### Proposal C — `PipelineRunner` service class with pluggable stages (full OO re-architecture)

Introduce an ordered stage pipeline: `PipelineRunner` owns
`run(spec) -> PipelineResult` and executes a sequence of stage objects
(`SelectionStage`, `ContextStage`, `EngineStage`, `FinalizeStage`), each with
a tiny interface (`prepare(run) -> context`, `execute(run, context)`).
`run_full_pipeline` becomes a thin adapter that assembles the default stage
list; modes/features select stages instead of growing `if mode ==` chains in
one function. New pipeline modes become new stage compositions.

- **Tradeoffs:** (+) Maximally deep per PoSD — consumers see one
  `PipelineRunner` with a tiny interface, and stages are composable
  (director mode, workflow mode, and new modes become configuration, not
  branching); (+) enables behavior-level integration tests per stage (§3.1's
  preferred testing strategy); (−) largest diff and highest regression risk
  for the 47 callers and the lazy-import cycle web — the import graph must be
  re-wired first; (−) overkill if AutoMedia never gains new pipeline modes;
  (−) abstraction layer (stage protocol) adds indirection that §3.1 warns
  against when it merely re-shapes, rather than reduces, the interface.

---

## 4. Recommendation

**Adopt Proposal A as the first step, with Proposal B's spec object layered
second.**

Rationale:

1. **Friction priority.** The dominant, measurable friction is
   cognitive-load: one 1,617-line file that every agent must fully load. §3.1
   ranks this above interface aesthetics. Proposal A removes it with
   zero behavioral risk.
2. **§3.1 anti-pattern compliance.** A extracts whole sub-processes into
   cohesive modules — exactly the direction the methodology prescribes —
   and explicitly avoids extracting tiny pure functions "for testability"
   (the documented trap). Test strategy stays integration-level per
   sub-process.
3. **Cycle-web safety.** A keeps all public imports identical, so the 13
   lazy-import sites and the `__init__` lazy maps remain valid; the import
   graph can be de-cycled incrementally afterwards.
4. **B as a compatible follow-up.** Once sub-concerns have boundaries,
   collapsing the 17-parameter signature into a `PipelineRunSpec` is a
   localized, shim-guarded change with an obvious migration path for the 47
   callers. C remains a viable future direction if new pipeline modes make
   stage composition valuable, but its cost is not justified today.

Implementation of Proposal A (and optionally B) is a **follow-up plan**,
tracked separately from this RFC.

---

## 5. Scope & Exclusions

This RFC is **document-only**; implementation of the chosen option is a
follow-up plan. `src/automedia/mcp/server.py` is excluded — already split
per PR #55.

No code was modified in producing this document. Every file, function, and
symbol named above was verified to exist against the current tree
(`git rev-parse HEAD` = `6c7ca2a`).
