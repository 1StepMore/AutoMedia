# ADR-007: Gate Engine Verdict Is an Aggregate, Not a Latch

### Status
Accepted · Effort: Small (one function + one helper + eight test assertions) · Issue #261

### Context

`GateEngine.run()` returns `(success, results)`. `success` was carried by a
local `all_ok` variable assigned in twelve places inside `_run()`. Every
passing gate executed `all_ok = True` (`gate_engine.py`, the `if passed:`
branch), so `all_ok` was **last-write-wins**: a gate that failed could have its
failure erased by any later gate that passed.

The documented contract appeared to bless this: the `Returns` section said
`success` is `True` when "every gate passed (**or no `failure_mode="stop"`
gate failed**)", and two tests pinned the behaviour
(`test_rewrite_does_not_stop`, `test_exception_in_rewrite_gate_continues`,
both asserting `ok is True` with a failed retry gate).

The consequence was a contradiction between four artefacts that are supposed
to describe the same run:

| Artefact | Value on such a run |
|---|---|
| `GateEngine.run()` `success` | `True` |
| `results` / `gates_log` | contains a `passed: False` row |
| gate-report (`failed=0 / errored=0`) | shows the failure |
| `PipelineResult.status` | `"success"` → CLI exits 0, MCP reports success |

The reachable path is narrow but real. A retry-mode gate that exhausts its
quality retries reaches level-2 regeneration, which needs a `CW` gate to
rebuild content from; in a CW-less mode (`qa_only` = `G0 G2 G3 V1 V6`,
`video_only` = `V0..V7`) level-2 returns `(False, [])`, the loop continues,
and a later passing gate reset the flag. `G2` and `V5` are both retry-mode and
both live in CW-less modes, so both were reproducible.

Reproduction (real gate classes, only the target gate forced to fail):

```
qa_only      engine_flag=True  ->  status='success'  failed=['G2']
video_only   engine_flag=True  ->  status='success'  failed=['V5']
```

Two interpretations were available: the flag is correct and the consumer is
wrong, or the flag is wrong. The flag's own name and its only production
consumer (`_finalize_pipeline` → `PipelineResult.status` → CLI exit code, MCP
status, cron status) both treat it as a verdict on the run. A verdict that can
be overwritten by a later pass is not a verdict.

### Decision

`success` becomes a pure function of the executed results:

```python
def _verdict_from_results(results: list[dict[str, Any]]) -> bool:
    return all(r.get("passed", True) for r in results)
```

Every terminal return in `_run()` derives the verdict from it, and ten of the
twelve `all_ok` assignments are deleted — the two inside the level-2 branch
survive, where a local `all_ok` still carries the one sanctioned override: when
regeneration is exhausted and the H0 gate passed, a human (or a run that
pre-authorised review via `--skip-review`) accepted the remaining failures.

`run()`'s `Returns` section now states the real contract. Eight test
assertions that had pinned the latch are updated to assert `ok is False`,
keeping their real subject (the pipeline **continues** past a retry gate)
intact.

Skipped gates are unaffected: `gates/_result.missing_input_result` returns
`passed=True` with `status="skipped"`, so an absent video track or missing V
gate input still does not fail a run.

### Alternatives Considered

#### Option A: Reconcile in the consumer (`_finalize_pipeline`)
Derive `status` from `gates_log` at the point where the report is written, and
leave `GateEngine.run()` alone.

- **Pros:** smallest possible diff; no existing test rewritten; fixes CLI, MCP
  and cron at once because all three read `PipelineResult.status`.
- **Cons:** leaves `run()` returning a value that is wrong for its own name,
  so the next consumer of the boolean inherits the defect. Puts the truth in
  two places (engine flag and gate log) and relies on one of them to correct
  the other. Rejected: it hides the bug instead of fixing it.

#### Option B: Keep the latch and add a monotone `ever_failed` flag
Leave every `all_ok` assignment in place and `and` the new flag into the final
return.

- **Pros:** truly minimal behaviour change; preserves all existing tests.
- **Cons:** leaves twelve assignments that look meaningful but are not, and
  leaves the documented contract describing the defect. Rejected for the same
  reason as A, plus it keeps a misleading variable alive.

#### Option C: Change nothing, document the latch
Treat `success` as a "did the pipeline complete" signal and add a separate
quality signal.

- **Pros:** zero code change.
- **Cons:** the only production consumer reads it as a verdict, and the four
  artefacts listed above would keep disagreeing. Rejected.

### Consequences

- `GateEngine.run()` and `PipelineResult.status` now agree with the gate log
  and the gate-report by construction; a failed gate can no longer produce
  exit code 0 in `qa_only` or `video_only`.
- Eight test assertions changed from `ok is True` to `ok is False` (across
  `tests/test_gate_engine.py`, `tests/test_gate_retry.py` and
  `tests/test_pipeline/test_gate_engine_retry_sites.py`). Their
  subjects (continuation past a retry gate, transient-exception survival,
  quality retry without a progress tracker) are unchanged and still asserted.
- `_run()` loses a mutable accumulator; the verdict now has one definition, in
  one function, and can be unit-tested without an engine.
- The one override remains explicit and local: level-2 exhaustion plus an H0
  pass.

### Watch Out For

- **Do not re-introduce an accumulator.** If a new branch needs to record
  "this run is still OK", compute it from `results`, not by reassigning a flag
  mid-loop.
- **The H0 override is positional, not global.** It lives inside the level-2
  branch, so an H0 pass cannot mask a failure of a gate that runs *after* H0
  (the `P1-P4` repurpose tail). Do not hoist it into `_verdict_from_results`.
- **Skipped vs failed.** Skipped results carry `passed=True`; do not "tighten"
  `_verdict_from_results` to require `status == "passed"`, which would turn
  every missing-input video gate into a run failure.
- `docs/dev/gate-failure-modes.md` and the `failure_mode="retry"` prose in
  `docs/dev/founder-expectations.md` describe retry as "regenerate and re-run";
  they do not claim a failed retry leaves the run successful, so no doc change
  was required — but do not add such a claim.
