# Scenarios: the agent-tester validation library

This directory is AutoMedia's agent-tester validation framework. Every YAML
file here is a declarative script of real calls against the live product,
written to be executed and graded by an AI agent and adjudicated by a human.
This README is the onboarding doc: read it before you read any scenario file.
It explains the two roles, how to read a scenario field by field, one complete
worked example, the five verdict statuses, and how to run the suite. The
authority for the schema semantics is `docs/agent-tester-validation-guide.md`
§2; where this README and the guide differ, this README reflects the
AutoMedia implementation.

## What this is

AutoMedia is an agent-oriented product, so its validation is agent-oriented
too: AI agents are the testers, and humans are the director. A scenario is a
declarative script of real calls against the live system. It names which MCP
tool or CLI command to invoke, what to verify on the real response, and which
standard governs that verification. An agent executes the scenario, grades
each step against its expect block, and writes an immutable run record. A
human reads the record, inspects the captured artifacts, and signs off. The
pipeline is: agents produce evidence, humans accept or reject it. Nothing the
agent decides alone is final, and nothing the director has not seen is
accepted.

## Two-role model

The framework has exactly two roles.

**Validator agent.** The AI agent that runs scenarios. It loads the scenario
files, dispatches each step as a real call through the shipped surface, grades
the responses against the declared expects, and writes the run record. The
agent grades; it never disposes. What it reads: `scenarios/*.yaml` (the
scripts to execute), `scenarios/STANDARDS.md` (the standard keys to cite), and
this file.

**Director (human).** The human owner who adjudicates. The director reviews
the run record and its artifacts, checks that GREEN claims are backed by
shown evidence, and signs off by appending the run name, date, and verdict to
`signed.txt` in the run directory. The director also decides the open items:
unconfigured scenarios to resolve or waive, and RED results to fix. What the
director reads: `validation-runs/<timestamp>/scenarios.json` (the run record),
the `artifacts/` subdirectory of each run, and `scenarios/` when a verdict
needs to be replayed against what was declared.

Run records live in `validation-runs/` at the repo root. They are gitignored:
they are evidence of a moment in time, not source. The `latest.txt` pointer
inside names the most recent run.

## How to read a scenario

### Read a scenario in ten lines

1. `name` is the identity. It must be unique across the library and survive
   renames of the file that contains it.
2. `description` says, in one or two sentences, what the scenario proves.
3. `intent` says WHY it exists. It is schema-required. Read it first.
4. `requires_env` lists the environment variables the scenario needs. A
   missing one gates the whole scenario to `unconfigured`.
5. `steps` are ordered, top to bottom. Each step is one real call plus an
   expect block. A later step can depend on earlier state.
6. Per step: `kind` picks the surface (`tool`, `cli`, `file`); `check` says
   WHAT to verify; `standard` says WHICH standard governs, as a key that must
   exist in `STANDARDS.md`.
7. `expect` holds the assertions on the real response. Every assertion present
   in the block must hold for the step to pass.
8. `recovery_steps` repair state after a primary step fails.
   `cleanup_steps` remove scenario-created state after the run. Neither one
   proves the capability under test.
9. Artifacts are the evidence. `collect_artifacts` copies files into the run
   record; the `artifact_*` expect keys grade them.
10. `min_passing` and `pass_ratio` set the partial-pass policy. `regression`
    pins the scenario to a specific bug or fix.

### Scenario header fields

| Field | What it means | Why it exists |
|---|---|---|
| `name` | Unique identifier of the scenario | Run records, reports, and sign-off discussions refer to a scenario by its name, never by its file path |
| `description` | One or two sentences stating what the scenario proves | Orients the director and future readers before they read a single step |
| `intent` | WHY the scenario exists: the capability or risk it proves | Schema-required. An agent must know the purpose before trusting the steps |
| `category` | Grouping label for reporting and the coverage audit | Lets reports and audits slice the library |
| `requires_env` | List of env var names the scenario needs | The gate: a missing var marks the whole scenario `unconfigured`, never a pass |
| `requires_http` | Flag that the scenario needs a live HTTP service | Inert in AutoMedia (no HTTP adapter ships); kept for guide portability |
| `requires_real_llm` | Flag that the scenario must use the real LLM provider | Opt-out from the fake-LLM-aware gate: with `AUTOMEDIA_FAKE_LLM=1` a scenario without this flag runs against the deterministic mock instead of short-circuiting to `unconfigured`; with it, a missing provider key still gates |
| `requires_real_adapter` | Flag that the scenario must use a real (credentialed) platform adapter | Excluded from the CI denominator when set: the 21-credential publish scenario is proved once by a recorded real-adapter dry-run, not by the credential-free suite |
| `min_passing` | Integer count of primary steps that must succeed | Partial-pass policy, checked before `pass_ratio` |
| `pass_ratio` | Fraction of primary steps that must succeed | Partial-pass policy for scenarios whose step count grows |
| `regression: true` | Marks the scenario as pinned to a specific fix | The regression flywheel: it must stay green forever |
| `regression_issue` | Bug or issue reference for the pinned fix | Required whenever `regression: true`; lets a reader jump from name to fix |
| `error_boundary: true` | The scenario's probes EXPECT an error to occur | The coverage audit reads it as an allowlisted probe: excluded from `covered`, listed loudly, never phantom or missing coverage |
| `hard: true` | Marks the scenario as hard-safety-critical | A `hard` scenario whose run status is not `passed` (failed/unconfigured/partial-pass/recovered) is a hard-safety violation: `validate run` exits 1, the suite is blocked, and the report shows a `## Hard Safety` section |
| `proves_gates` | List of gate names the scenario proves (for example `G0`, `CW`, `pre-gate`) | Declarative coverage metadata; the coverage audit reads it to compute which declared gates the suite exercises |
| `proves_modes` | List of pipeline mode names the scenario proves (for example `text_only`) | Declarative coverage metadata; the coverage audit reads it to compute which declared modes the suite exercises |
| `steps` | Ordered list of primary steps | The body of the proof; execution order is top to bottom |
| `cleanup_steps` | Best-effort state removal after the main steps | Leaves the surface as it was found; never influences the scenario status |

### Step fields

| Field | What it means | Why it exists |
|---|---|---|
| `name` | Human-readable label | Appears in the run record and per-step traces |
| `kind` | Surface selector: `tool`, `cli`, `file` | Dispatch: which adapter turns the step into one real call |
| `check` | WHAT to verify at this step | Schema-required. The agent knows exactly what to look at before the call runs |
| `standard` | WHICH standard governs the check | Schema-required. Must be a key that exists in `STANDARDS.md`; the loader rejects unknown keys at load time |
| `tool` + `arguments` | Call spec for `kind: tool` | The named tool and its parameters; `arguments` may be an empty dict but must be present |
| `command` | Call spec for `kind: cli`; artifact path for `kind: file` | For cli it is the exact command line; for file it carries the path to inspect |
| `timeout_seconds` | Hard wall-clock cap for this step | Overrides the 180 second ceiling; exceeding it fails the step |
| `expect` | The assertions on the real response | The heart of the step: it turns a real call into a graded verdict |
| `error_boundary` | Marks this step as a boundary probe | A probe that expects an error passes on error and fails on full success |
| `recovery_steps` | Steps run only after this primary step fails | Restore the surface; a passing recovery marks the step `recovered`, never `passed` |
| `collect_artifacts` | Files to copy into the run record when the step is GREEN | The concrete evidence a GREEN step must show the director |

### Expect keys

Every assertion present in the block must hold; absent assertions are not
evaluated. Key-presence and substring checks assert containment, not position
or value.

| Key | What it means |
|---|---|
| `success` | The call envelope reports success; the call completed without a protocol-level error |
| `data_has` | `output.data` is a dict containing every listed key |
| `exit_code` | The CLI process exited with the given code |
| `stdout_has` | CLI stdout contains every listed substring |
| `stderr_has` | CLI stderr contains every listed substring |
| `artifact_exists` | The given path is a file |
| `artifact_size_min` | That file is at least N bytes; applies to the path named in `artifact_exists` of the same block |
| `artifact_nonempty` | The given path exists and is non-empty |
| `gate_records_pass` | The artifact's JSON carries non-empty gate or pass records |

## Worked example

The scenario below is complete, schema-valid, and loads through the real
loader. It is a minimal baseline: it proves the MCP surface answers, the CLI
surface honors its dependency contract, and the repo ships a project manifest.
It creates no state, so it needs no recovery or cleanup steps.

```yaml
name: server-health-baseline
description: The MCP server answers health checks, doctor honors its dependency-listing contract, and the repo ships a project manifest.
intent: Prove both shipped surfaces answer real calls before an agent relies on them for a production run.
category: baseline
requires_env: []
steps:
  - name: MCP health_check answers
    kind: tool
    check: health_check returns a success envelope carrying the server status.
    standard: tool.contract
    tool: health_check
    arguments: {}
    expect:
      success: true
  - name: doctor lists every dependency
    kind: cli
    check: doctor prints a JSON payload that lists each dependency by name with an installed flag.
    standard: cli.doctor
    command: automedia --json doctor
    timeout_seconds: 60
    expect:
      stdout_has: [python, ffmpeg]
  - name: project manifest artifact exists
    kind: file
    check: The project manifest exists on disk and is non-empty.
    standard: founder-expectations.F01
    command: pyproject.toml
    expect:
      artifact_exists: pyproject.toml
      artifact_nonempty: pyproject.toml
    collect_artifacts:
      - path: pyproject.toml
        required: true
```

### Field-by-field annotation

**`name: server-health-baseline`** is the identity. Every record, report, and
sign-off discussion calls this scenario by this name. It survives any future
rename of the file.

**`description: ...`** states, in one sentence, what the scenario proves. It
tells a reader and the director what to expect before they read the steps.

**`intent: ...`** is WHY this scenario exists, and it is schema-required.
This one says: an agent should not rely on the product surface for production
work until these two surfaces have answered a real call. When a step ever
looks arbitrary, `intent` is the tiebreaker.

**`category: baseline`** is a grouping label. This scenario belongs to the
deterministic first batch that runs without credentials.

**`requires_env: []`** is the gate. Empty, so this scenario always runs. A
scenario that needs credentials would list them here (for example
`AUTOMEDIA_LLM_API_KEY`); a missing variable marks the whole scenario
`unconfigured`, never a pass. The governing honesty rule is the
`honesty.unconfigured` standard in `STANDARDS.md`: an unconfigured scenario
reports loudly with its reason and counts toward neither pass nor fail.

**Step 1, `MCP health_check answers`**. `kind: tool` selects the MCP tool
dispatcher, so this step runs through the real FastMCP instance, never a
mock. `check` states what to verify: a success envelope carrying the server
status. `standard: tool.contract` cites the
tool return contract in `STANDARDS.md`. `tool: health_check` and
`arguments: {}` are the self-contained call spec; the empty dict is present so
the trace can echo exactly what was called. The expect block asserts
`success: true`. Note what is deliberately absent: `data_has`. AutoMedia
tools flatten their returns through `success_response`, so the output
envelope has no nested `data` dict to probe. Asserting `success` is the honest
check for this surface.

**Step 2, `doctor lists every dependency`**. `kind: cli` runs the command
through a subprocess. `standard: cli.doctor` cites the doctor and CLI
contract in `STANDARDS.md`. `timeout_seconds: 60`
caps this step below the 180 second default. The expect block asserts
`stdout_has: [python, ffmpeg]`, the dependency-listing contract. Deliberately
absent: `exit_code` and `success`. Doctor exits 1 when any dependency is
missing, so a hardcoded exit code would fail by design on healthy machines.
The listing contract, every dependency appearing by name in the JSON payload,
holds on any machine.

**Step 3, `project manifest artifact exists`**. `kind: file` inspects an
artifact on disk, and `command` carries the path: `pyproject.toml`.
`standard: founder-expectations.F01` cites the F01
ever-green clause in `STANDARDS.md`. The expect block asserts
`artifact_exists` and `artifact_nonempty`: the file must exist and carry
bytes. `collect_artifacts` then copies the manifest into the run record under
`artifacts/`, with `required: true`, so the director can see the evidence
itself, not just a verdict.

**Absent fields, and why.** No `recovery_steps`: nothing here mutates, so
nothing can half-complete on failure. No `cleanup_steps`: the scenario creates
no state, so there is nothing to remove. No `error_boundary`: this is a
GREEN-able baseline, not a probe that expects an error. No
`min_passing`/`pass_ratio`: the default is all-or-nothing, which is the right
policy for three tightly coupled health checks. No `regression`: this
scenario is not pinned to a bug fix.

## The 5 statuses and the honesty rules

### The 5 statuses

- **passed**: every primary step met its expect block and reached the
  surface. The capability is proven.
- **failed**: at least one primary step failed its expect and no partial-pass
  policy saved it. The run record names each failing expect key and the
  observed value.
- **unconfigured**: a required environment variable was missing, so nothing
  ran. It is a state, never a verdict of acceptance: it appears with its
  reason and an empty step list.
- **recovered**: a primary step failed and a recovery step succeeded. The
  failure stays in the run record; only its effect on the verdict is
  downgraded. Recovery never erases RED.
- **partial-pass**: some steps failed, but the header's `min_passing` or
  `pass_ratio` policy was met. Every failed step still appears with its trace;
  partial-pass never hides a failure.

### Honesty rules

- **unconfigured never passes, and never fails silently.** A missing
  prerequisite is reported loudly with its reason. A suite that reports
  unconfigured is more useful than one that reports nothing.
- **RED first.** Record the honest negative state before fixing anything. A
  result that jumps straight to GREEN with no recorded RED is suspect and is
  re-run from the pre-flight baseline.
- **Mocks prove plumbing, never capability.** Every step dispatches a real
  call through the shipped surface. The ONE sanctioned exception is the
  deterministic fake LLM (`AUTOMEDIA_FAKE_LLM=1`) and the validation stub
  seam (`AUTOMEDIA_VALIDATION_STUB_BIN`, a committed `scenarios/stubs/bin/`
  fixture directory prepended to `PATH`): a run executed against a simulated
  layer is recorded with
  `confidence: mock` and its passes are labelled **`Proved (mock)`**. A
  `Proved (mock)` pass proves the plumbing (the call routed, the record
  persisted), NOT the capability; it never satisfies real-surface coverage
  (`validate coverage` keeps the surface `unproven`). A run against the
  shipped provider is `confidence: real` and its passes are `Proved`.
  Seeded fixtures and simulated layers still never count as real evidence.
- **Cleanup never influences status.** Cleanup runs best-effort after the main
  steps, is reported separately, and never touches the scenario verdict.
- **Artifacts must be shown.** GREEN means the call succeeded, the artifact
  exists, and that artifact was carried to the director.

### Mock-aware evidence (`confidence`)

Every run record — the suite record at the top level and each scenario record
inside it — carries a `confidence` field:

- `confidence: real` — the run reached the shipped provider (the default for
  records written before this field existed).
- `confidence: mock` — the run executed against the deterministic fake LLM
  (`AUTOMEDIA_FAKE_LLM=1`). A step that passes here is `Proved (mock)`:
  plumbing only, never capability proof. Coverage excludes its surfaces from
  `covered`; they stay `unproven` until a real `Proved` step reaches them.

A surface therefore becomes `covered` only when a `real`-confidence run
records a passed step that reaches it. This is what keeps the fake-LLM
dev path (T-15) and the stub seam (T-21) honest rather than silently
inflating the coverage claim.

## How to run

The engine lives in `automedia.validation.engine`. Today you run the suite
through `run_validation_suite`, which loads the library, runs every scenario,
and persists one immutable run record under `validation-runs/` (gitignored,
with a `latest.txt` pointer):

```python
from automedia.validation.engine import run_validation_suite

# server=None makes tool-kind steps fail loudly; pass the live FastMCP
# instance to exercise tool steps (W4 wires it). save=True (the default)
# requires runs_root.
record = run_validation_suite(server=None, runs_root="validation-runs")
```

The suite needs `scenarios/STANDARDS.md` to exist: the loader cross-checks
every step's `standard` key against it and rejects unknown keys at load time.
The environment variable `AUTOMEDIA_VALIDATION_SCENARIOS_DIR` replaces the
default scenarios directory, so tests and alternate libraries can swap the
whole tree. The first run of a freshly written scenario is expected RED in
places; that RED is the baseline, not a failure of the framework. Record it,
then fix toward GREEN.

The long-lived MCP server must call the `*_async` engine cores from its own
running loop; the sync wrappers shown above are for the CLI and tests.

The `automedia validate` command family drives this layer from the CLI:

- `automedia validate list` — load the scenario library and list every scenario
  (load only, no engine run)
- `automedia validate run --scenario <name>` — run ONE named scenario against
  the real MCP server; `--scenario` is required (the recursion bound)
- `automedia validate report [--run <name|latest>]` — render the run record for
  a run, defaulting to the latest
- `automedia validate diff [--baseline <path>]` — diff the latest two runs
  against each other or a baseline record
- `automedia validate coverage` — run the **evidence-backed** coverage audit:
  coverage is the declared surface ∩ surfaces reached by a `passed` step in
  the newest persisted suite run (`--runs-root`, default `validation-runs`).
  It reports `covered`/`unproven`/`missing` per surface (CLI, MCP, gates,
  pipeline modes) and exits 1 while any non-allowlisted surface is
  `unproven` or `missing`.  Mock-confidence passes (`Proved (mock)`),
  `unconfigured` scenarios, boundary probes, and meta scenarios never count
  as `covered`.  A surface is excluded from `unproven` only while a versioned
  `boundary_only_allowlist.yml` entry (owner + reason + expiry) covers it.
  The static declared/used/phantom sets are still printed alongside.
- `automedia validate matrix` — render the validation matrix: per-surface
  coverage summary plus one row per scenario (surface cells, hard flag,
  last-run status); non-recursive, takes no scenario name

The same surface is exposed as five MCP tools: `list_validation_scenarios`,
`run_validation_scenario`, `get_validation_report`,
`validation_coverage_audit`, and `validation_matrix`. Drive the engine
directly as shown above when you need to run the whole suite in-process.

## Regression flywheel

Every bug is pinned forever by a regression scenario: it reproduces the
failure, carries `regression: true` plus `regression_issue: "#NN"`, and must
stay GREEN — a RED regression scenario IS the bug, re-surfaced. Pinned
scenarios live in `regression/` (or carry the marker in place next to their
family); the loader's recursive glob picks them up with no registration. The
bug template (`.github/ISSUE_TEMPLATE/bug_report.yml`) mandates the scenario
name, so a bug cannot be filed without committing to its lock. The
`automedia.validation.regression` helpers list the pins and verify the
discipline. See `docs/agent-tester-validation-guide.md` §5.2 for the full
flywheel lifecycle.
