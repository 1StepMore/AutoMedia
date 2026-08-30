# ADR-006: Explicit Per-Mode Gate DAG

### Status
Accepted · Effort: Large (3 waves, committed 2026-08-30)

### Context

AutoMedia's pipeline executes gates from linear per-mode lists. `automedia/pipelines/runner.py` maps 9 modes (`auto`, `text_only`, `text_with_cover`, `video_only`, `qa_only`, `image-carousel`, `social-thread`, `short-video`, `repurpose`) to module-level `list[str]` constants via `_MODE_MAP`. The copy track (CW, G0-G6) and the video track (V0-V7) are conceptually parallel branches, but in code they are a pure sequential linked list: each mode list is executed top to bottom by the `GateEngine`.

The Graph Engineering paradigm (arXiv:2608.21156) argues that complex agent tasks should be organized as an explicit graph: task organization, agent coordination, and runtime state management. The gap analysis in `docs/dev/2026-08-30-AutoMedia-GraphEngineering落地实施方案-修正版.md` concluded that AutoMedia is roughly 80 percent there: it already has a gate engine, gate-granular resume (`--resume-from` threaded through runner, CLI, and MCP), and per-gate history rows written to `history.db` by `PipelineHistoryHook`. What is missing is the graph itself, automatic resume-point discovery, failure localization, and a run-state audit view.

The plan proposed three phases: P0 (explicit DAG plus an `export-dag` command), P1 (auto-resume plus failure localization), P2 (a read-only state view). All three shipped, and this ADR records what was actually built.

### Decision

Four additive changes, none of which alters default execution behavior.

**1. Additive per-mode gate DAG.** A new pure-declarative module `src/automedia/pipelines/dag.py` defines a `GateNode` frozen dataclass (`name`, `track`, `depends_on`, `failure_mode`, `async_parallel`) and a canonical `AUTO_GATE_DAG` covering all 26 gates: the 22 auto-mode gates (pre-gate, CW, G0-G6, V0-V7, H0, L1-L4) plus the P1-P4 repurpose chain. The graph is expressed with dict insertion order as the canonical gate order; every edge respects it. Two pure helpers operate on it:

- `topological_order(dag, mode_gates)` reproduces the runner's linear lists byte-exact under "present-parents" semantics (parents outside the mode subset are ignored, which is what lets `qa_only` and `text_only` run without pre-gate/CW).
- `downstream(dag, gate)` returns the reverse-topological closure of a gate: every gate that transitively depends on it, in dependency-before-dependent order.

`_MODE_MAP` and every `_*_GATE_NAMES` list in `runner.py` stay byte-identical. An equivalence test (`tests/test_runner/test_dag.py`) asserts `topological_order(AUTO_GATE_DAG, _MODE_MAP[m]) == _MODE_MAP[m]` for all 9 modes. `async_parallel` (set on V0, which forks off CW) is documentation-only metadata: the engine stays strictly sequential and it is never read for execution.

**2. Opt-in `--auto-resume`.** A new `auto_resume: bool = False` kwarg is threaded through `run_full_pipeline`, `_run_pipeline`, `_select_gates`, the CLI `--auto-resume` flag on `automedia run`, and the MCP `run_pipeline` tool. When enabled and no explicit `resume_from` is given, `_find_auto_resume_point(project_dir, mode, gate_names)` reads `history.db`, anchors on the latest `{gate}:completed` row whose `metadata_json.passed == true`, and returns the next gate in the effective gate list. The existing `resume_from` slicing path in `_select_gates` runs unchanged, so an explicit `resume_from` always wins. An anchor outside the effective list yields no resume (returns `None`, a full run) rather than raising, which is the semantic contrast with explicit `resume_from` slicing.

**3. Failure localization.** `PipelineResult` gains an additive `affected_downstream: list[str]` field (empty on success; the existing `error: str | None` is untouched and remains reserved for pipeline-level unexpected errors, never gate failures). `_compute_affected_downstream(gate_names, failed_gate)` computes `downstream(AUTO_GATE_DAG, failed_gate)` intersected with the mode's gate list, and `_finalize_pipeline` fills the field from the first gate log entry with status `failed` or `error`. The CLI renders it as "⚠ Downstream affected: ..." after the gates-executed block for both `partial` and `failed` results.

**4. Read-only state view.** A new module `src/automedia/pipelines/state_view.py` defines a `GateState` dataclass (`gate`, `status`, `track`, `md5`, `recorded_at`) and `aggregate_pipeline_state(project_dir, mode="auto") -> list[GateState]`. It reads `history.db` and `pipeline_md5.json` only: latest-row-wins per gate, `completed` rows default to passed unless `passed: false`, `failed` action rows are failed, everything else pending, ordered by `_MODE_MAP[mode]`. A new CLI command group `automedia pipeline state` renders a track-grouped table (with `--json`), and a new MCP tool `get_pipeline_state` returns the same shape. There are no new state writes; the view is best-effort over existing records.

### Alternatives Considered

#### Option A: Replace the mode lists with the DAG outright
- **Pros:** One source of truth; the runner would consume the graph directly.
- **Cons:** Touches the exact code path that defines the 9 mode execution orders, so any topological or ordering bug becomes a production behavior change. The additive approach achieves the same graph with zero risk: the equivalence test proves byte-identical order, and the runner keeps executing its existing lists.

#### Option B: Use an external graph engine (networkx, Neo4j)
- **Pros:** Battle-tested graph algorithms, traversal, and visualization tooling.
- **Cons:** Adds a heavy dependency for a 26-node static graph with hand-declared edges. A stdlib dataclass plus dict insertion order is sufficient and keeps the module import-free, which also satisfies the import-isolation contract (see Consequences).

#### Option C: True parallel execution of the copy and video tracks
- **Pros:** Matches the conceptual parallelism of the two tracks; a real throughput gain for video-heavy runs.
- **Cons:** Changes execution semantics, retry behavior, and failure atomicity, none of which this rollout was scoped to touch. The plan explicitly defers real concurrency for later evaluation. `async_parallel` therefore records the intent on V0 without any execution effect.

### Consequences

- No new dependencies. The DAG is stdlib-only; there is no networkx, no Neo4j, no added runtime cost.
- No change to gate pass/fail semantics, `failure_mode` behavior, or the default execution order. Every existing pipeline run behaves identically unless `--auto-resume` is passed.
- The `resume_from` order is preserved: the equivalence invariant pins the DAG to the byte-identical mode lists, so auto-resume computes its point against the same effective list the runner slices.
- Public API surface grows additively: one new field on `PipelineResult` (keyword-constructed everywhere, verified by grep), one new backward-compatible kwarg on `run_full_pipeline`, one new MCP tool (64 to 65), and one new CLI command group (18 to 19). Existing callers are unaffected.
- Known limitation, accepted: state view and auto-resume are best-effort because `history.db` has no run-boundary marker. Rows from multiple runs of the same project can interleave, so "latest row wins" reflects the most recent gate record, not necessarily the current run. This is documented and accepted rather than fixed with a schema change.
- Import isolation: `dag.py` imports nothing from `automedia.pipelines.runner` or any other automedia subpackage. This avoids a circular import (runner depends on the DAG helpers lazily) and is enforced by a subprocess-based test asserting `automedia.pipelines.runner` is absent from `sys.modules` after importing `dag`.

### Watch Out For

- Doc and test assertions that count surfaces must move in the same commit as the code that changes them: the MCP tool count (64 to 65) and CLI command count (18 to 19) are asserted in `tests/test_mcp/test_mcp_validation_tools.py`, the exact-tool-list test in `tests/test_mcp/test_mcp_server.py`, and the doc-consistency gate.
- The `passed` key on `completed` history rows defaults to true (`PipelineHistoryHook.after_gate` writes `result.get("passed", True)`). Only an explicit `passed: false` marks a completed gate as failed; do not "fix" this asymmetry.
- `dag.py` must never import from `runner.py`. Keeping it a leaf module is what makes the lazy import in `_compute_affected_downstream` and the state view safe.
- Auto-resume anchors only on `completed` with `passed: true`. A gate that exhausted retries lands as `completed` with `passed: false` and must not anchor.
- If the DAG edges change (for example a gate moves tracks), re-run the equivalence test for all 9 modes: the byte-exact invariant is the contract that keeps the DAG additive.
