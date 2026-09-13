# Validating Coding Agents as Testers: A General Implementation Guide

This guide shows any project how to build validation that a coding agent runs as a tester: declarative scenarios that make real calls against the shipped surface, honest evidence rules, coverage and regression machinery, and a human director who reads the artifacts and signs off. It is written for a new project or a brownfield one, for tool servers, CLI apps, web services, and libraries alike. AutoInfo, the project this pattern was distilled from, appears only in boxed worked examples and in the reference map at §8; every mechanism is described generically first so you can port it anywhere. Compiled 2026-08-14.

## §0 How this guide is organized

**Purpose.** This guide teaches any project how to build an agent-executed, human-directed validation layer: a repeatable machine that sends real calls against the shipped system, collects the evidence those calls produce, and turns that evidence into a verdict a human can accept or reject. It is not a tool tutorial. The pattern here is portable across tool servers, CLI apps, web and REST services, and libraries.

**Audience.** You are a coding agent or engineer implementing validation in one of those projects. You will write scenario files, an executor that runs them, and the reporting that brings results to a director. You do not need to be the project's author, but you do need read access to its real surface.

**How to read.** Generic principles come first in every section; the worked examples are boxed and project-specific, so you can skip them and keep the method. Cross-references point at the section that elaborates, for example (see §4). Start with §1 to lock vocabulary, then read §2 and §3 together (schema and engine), §4 for the honesty rules that keep evidence trustworthy, §5 for coverage and regression machinery, §6 for the director loop, and §7 when you port the whole stack elsewhere.

**TL;DR of the pattern.** Write scenarios as declarative scripts of real calls, each with expects. Run them through an adapter onto the shipped surface. Keep only evidence from real calls, and record what actually happened. Grade each step honestly, recording RED before fixes and `unconfigured` when prerequisites are missing. Persist a run record with per-step traces. The director reviews artifacts and signs off. Pin fixes as regression scenarios that stay green forever.

## §1 Concept and vocabulary

The operating model has exactly two roles. The **validator agent** executes scenarios, runs real calls, and drafts verdicts; the **director (human)** adjudicates those verdicts, reads the artifacts, and signs off. The agent grades, the human disposes. Anything the agent decides alone is a draft; anything the director has not seen is not accepted.

| Term | Meaning |
|------|---------|
| `validator agent` | the AI agent that executes real calls and collects evidence |
| `director (human)` | the human owner who adjudicates verdicts, reviews artifacts, and signs off |
| `scenario` | a declarative script of real calls against the live system |
| `step` | one real call plus one `expect` block inside a scenario |
| `expect` | the assertions on the real response a step must satisfy |
| `artifact` | the concrete evidence a step proves (file, DB row, log line, payload) |
| `RED` | the honest negative state recorded before a fix (call fails / prerequisite missing / artifact absent) |
| `GREEN` | the verified positive state: call succeeded AND artifact exists AND was shown to the director |
| `unconfigured` | a scenario that could not run because a prerequisite (e.g. a credential) is missing; never a pass |
| `real-surface evidence` | evidence from real calls through the shipped surface; no mocks or seeded stores |
| `evidence contract` | the five-part record (surface, real call, expect, actual, artifact-to-show) every proof follows |
| `surface` | the interface the scenario calls (tool server, CLI command, REST endpoint, library API) |
| `adapter` | the executor component that turns one step into one real call on a surface |
| `run record` | the persisted JSON of one validation run with per-step traces |
| `verdict` | the acceptance outcome (PASS / FAIL / RISK / unconfigured) |
| `sign-off` | the director's acceptance of a run after reviewing verdicts and artifacts |
| `coverage audit` | a script that reports which declared surfaces are exercised and which are missing |
| `regression scenario` | a scenario pinned to a specific bug/fix and expected to stay green forever |
| `phantom coverage` | a step that names an undeclared/nonexistent surface; must never count as coverage |
| `partial-pass` | a scenario policy letting a subset of steps pass while failures still surface |
| `cleanup step` | a step that removes scenario-created state after the run, pass or fail |
| `recovery step` | a step executed after a primary step fails, to try to recover |
| `pre-flight baseline` | the recorded RED state of the whole suite before credentials are configured |

Two terms deserve emphasis. `GREEN` is not merely "the call returned". It is the full chain: the call succeeded, the artifact exists, and that artifact was shown to the director. `unconfigured` is a state, never a verdict of acceptance; a suite that skips work for missing credentials must say so loudly, not quietly count it as a pass.

> **Evidence contract template.** Every proof in this guide follows five parts, and every section that mentions evidence returns to them (see §4):
> 1. **surface**: the interface that was called
> 2. **real call**: the exact call made on that surface
> 3. **expect**: the assertions the step declared
> 4. **actual**: what the live response really contained
> 5. **artifact-to-show**: the concrete evidence carried to the director

> **Test pyramid note.** This validation layer sits ON TOP of the unit and integration test suite, it does not replace it. Unit tests verify the code; scenarios verify the shipped surface. Keep the pyramid: fast in-process tests cover the logic, and the scenario layer covers the real calls that only the running system can prove.

> **Worked example (AutoInfo).** The project ships its scenarios as YAML files under `src/autoinfo/mcp/scenarios/`. The porting map for that layout lives in §8; here the path only anchors the naming.

## §2 Scenario schema

### §2.1 Scenario anatomy

A scenario is a declarative script of real calls against the live system. A scenario file is YAML with two parts: a header that identifies the scenario and declares its prerequisites, and a body that lists the steps in execution order. The header never contains behavior; behavior lives entirely in the steps list. The file is the contract between the validator agent and the director (human): both read the same YAML.

Header fields:

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Unique identifier; addresses the scenario to the executor and labels it in reports and run records |
| `description` | yes | One or two sentences stating what the scenario proves |
| `category` | no | Grouping label for reporting and the coverage audit (see §5) |
| `requires_env` | no | Environment variables the scenario needs; a missing one gates the whole scenario (see §2.5) |
| `requires_http` | no | Flag that the scenario needs a live HTTP service (see §2.5) |
| `min_passing` / `pass_ratio` | no | Partial-pass policy (see §2.7) |
| `regression: true` + `regression_issue` | no | Marks a regression scenario and pins it to a bug reference |
| `proves_gates` | no | Declarative coverage metadata: the product gates this scenario proves (for example `G0`, `CW`, `pre-gate`); consumed by the coverage audit (see §5) |
| `proves_modes` | no | Declarative coverage metadata: the product run modes this scenario proves (for example `text_only`); consumed by the coverage audit (see §5) |

The steps list is the core of the file. It is ordered: the adapter executes steps top to bottom, and a later step can depend on state an earlier step created. Each step carries its own expect block; that block is what turns a real call into a graded judgment. A scenario with no steps is a declaration, not a proof.

A naming convention matters because names become keys: run records, coverage audits, and sign-off discussions all refer to a scenario by its name. Choose a name that survives renaming of the file that contains it, and keep it unique across the library. A regression scenario is commonly named after the bug or issue it pins, so a reader can jump from the name to the fix (see §5). The file path is an implementation detail; the name is the identity.

> **Worked example (AutoInfo).** The minimal scenario is `src/autoinfo/mcp/scenarios/meta-validation.yaml:4-22`: name, description, `category: system`, `requires_env: []`, and two steps, each with `tool`, `arguments`, and an `expect` block. The library holds 68 scenario files, 62 functional scenarios in the root plus 6 regression scenarios in the `regression/` subdirectory (`src/autoinfo/mcp/scenarios/`), discovered automatically by a recursive glob over the directory tree (`src/autoinfo/mcp/validation.py:809`). The executor's entry point returns a run record shaped as `{scenario, status, summary, steps, trace_id, cleanup}` (`src/autoinfo/mcp/validation.py:1275`).

### §2.2 Step anatomy

A step is one real call plus one expect block. The executor reads the step, selects the surface from the `kind` field, makes the real call, and grades the response against `expect` (see §3 for the executor, §4 for the evidence contract this produces).

| Field | Meaning |
|---|---|
| `name` | Human-readable label; appears in the run record and per-step traces |
| `kind` | The surface selector: which surface the call targets (tool server, CLI command, REST endpoint, and so on) |
| `tool` + `arguments` | The call spec for tool-kind steps: the named tool and its parameters |
| `command` | The call spec for CLI-kind steps: the exact command line |
| `method` + `url` | The call spec for REST-kind steps: HTTP verb and endpoint |
| `expect` | The assertions the real response must satisfy (see §2.3) |
| `timeout_seconds` | Hard wall-clock cap for this step; exceeding it fails the step |
| `recovery_steps` | Optional steps run only after the primary step fails (see §2.6) |
| `collect_artifacts` | Optional list of files or payloads the step proves exist (see §4) |

The `kind` field is what keeps a scenario independent of any one surface. One file can mix tool steps, CLI steps, and HTTP steps; porting to another project mostly means changing the adapter, not the scenarios (see §7). A step without an expect block cannot be graded, so treat `expect` as the mandatory heart of every step.

Distinguish primary steps from secondary steps. A primary step is the graded evidence: it makes the real call and its expect block decides pass or fail. `recovery_steps` and `cleanup_steps` are secondary: they exist to repair state, never to prove the capability under test. A recovery step's own expect block only decides whether the recovery worked; it never replaces the primary step's verdict.

A tool that takes no parameters still carries an explicit empty `arguments` object, so the call spec is self-contained and the run record can echo exactly what was called.

> **Worked example (AutoInfo).** Both step shapes ship in the reference files. A tool-kind step carries `tool` plus `arguments`, calling `list_validation_scenarios` with `{}` (`src/autoinfo/mcp/scenarios/meta-validation.yaml:10-14`). A CLI-kind step carries `kind: cli` and a `command` (`src/autoinfo/mcp/scenarios/regression/collect-int-id.yaml:21-51`). At execution the run record gains per-step trace fields: the 1-based `step_index`, `duration`, the echoed `arguments`, and one `trace_id` UUID for the whole run (`src/autoinfo/mcp/validation.py:901-923`).

### §2.3 The expect block

The expect block is the assertion layer of a step: it grades the real response. Every assertion in the block must hold for the step to pass. The assertion types group by surface kind:

| Assertion | Meaning |
|---|---|
| `success: true` | The call envelope reports success; the call completed without a protocol-level error |
| `data_has: [...]` | The returned data object contains every listed key |
| `exit_code: 0` | The CLI process exited with the given code |
| `stdout_has: [...]` | The CLI standard output contains every listed substring |
| `stderr_has: [...]` | The CLI standard error contains every listed substring |
| `status_code: 200` | The HTTP response returned the given status code |
| `json_has: [...]` | The HTTP response body, parsed as JSON, contains every listed key |

Think of the expect block as the expected half of the evidence contract: it declares, before the call runs, what the real call must produce for the step to count as evidence (see §4).

All assertions in a block are conjoined: the step passes only when every listed assertion holds. Key-presence assertions (`data_has`, `json_has`) check that the listed keys exist in the parsed response, not their values. Substring assertions (`stdout_has`, `stderr_has`) check containment, not position or count. Keep assertions coarse: assert presence and exact exit codes, and leave fine-grained value checks to the unit suite, which runs faster than any real call (see §0).

> **Worked example (AutoInfo).** The tool-kind expect blocks are minimal: `success: true` plus `data_has: ["scenarios", "count"]` for listing, and the sibling block on `run_validation_scenario` (`src/autoinfo/mcp/scenarios/meta-validation.yaml:12-14,20-22`). The CLI-kind expect block combines `success`, `exit_code`, and `stdout_has` (`src/autoinfo/mcp/scenarios/regression/collect-int-id.yaml:52-55`).

### §2.4 Required fields and defaults

The loader is the contract. A scenario that reaches the executor was already validated; one that fails validation is rejected at load time, before any real call runs. Required and optional fields form a small, closed set.

| Field | Required | Default when omitted |
|---|---|---|
| `name` | yes | none; rejected |
| `description` | yes | none; rejected |
| `steps` | yes | none; rejected |
| `kind` (per step) | yes | none; rejected |
| `expect` (per step) | yes | none; rejected |
| `category` | no | general |
| `requires_env` | no | empty list |
| `requires_http` | no | false |
| `proves_gates` | no | empty list |
| `proves_modes` | no | empty list |
| `timeout_seconds` (per step) | no | project default ceiling |
| `cleanup_steps` | no | empty list |
| `min_passing` / `pass_ratio` | no | absent, meaning all-or-nothing (see §2.7) |
| `recovery_steps` / `collect_artifacts` | no | absent, meaning none |

Defaults exist so a first-time author writes the smallest possible file and still gets correct semantics. Omitting an optional field never changes the meaning of a required one; it only changes the surrounding behavior.

Load-time rejection is loud by design. A malformed scenario is reported as a load error naming the offending field, never silently skipped and never counted as coverage. The same strictness applies to unknown top-level fields: an unrecognized key is a typo in waiting, and the loader should reject it rather than guess. The closed field set above is the complete surface of a scenario file.

> **Worked example (AutoInfo).** The loader `load_scenarios()` validates the required fields, fills defaults for `category`, `requires_env`, `requires_domain`, `requires_http`, and `cleanup_steps`, and validates `min_passing` / `pass_ratio` at load time (`src/autoinfo/mcp/validation.py:781`).

### §2.5 Environment gating

Some scenarios need credentials or a live service to be meaningful. Declare that need in the header instead of hoping the environment has it. The executor checks prerequisites before running anything.

`requires_env` is a list of environment variable names. If any named variable is missing, the whole scenario is marked `unconfigured` and nothing runs. `unconfigured` is a state, never a verdict of acceptance: the run record says loudly that the scenario did not run and why. A missing prerequisite is never a silent pass and never a silent fail; both would corrupt the coverage picture. The pre-flight baseline, the recorded RED state of the whole suite before credentials are configured, depends on this honesty (see §4).

`requires_http` is a flag for scenarios that need a live HTTP service. When the service is offline, the scenario reports `unconfigured` for the same reason: the prerequisite is missing, so the real-surface evidence does not exist.

An unconfigured scenario appears in the run record with its reason, so the director (human) can see at a glance which capabilities were not exercised and why. It counts toward neither pass nor fail totals, and it should be re-run once the prerequisite is supplied. A suite that reports unconfigured loudly is more useful than one that reports nothing.

> **Worked example (AutoInfo).** A self-contained scenario declares `requires_env: []` at the top (`src/autoinfo/mcp/scenarios/meta-validation.yaml:7`). The executor converts a missing variable into an unconfigured result for the whole scenario, never a pass or a fail (`src/autoinfo/mcp/validation.py:1356-1367`).

### §2.6 Cleanup and recovery semantics

Two kinds of secondary steps exist and they answer different problems. A cleanup step removes state the scenario created; a recovery step makes the surface usable again after a primary step failed.

`cleanup_steps` run after the main steps, regardless of the scenario outcome. They run best-effort: their own pass or fail is reported separately and never influences the scenario status. Their job is to leave the surface as they found it so reruns and neighboring scenarios start clean. A scenario that creates users, files, or processes without cleanup leaks state into every later run. Cleanup steps are never evidence for the scenario's verdict.

`recovery_steps` belong to a single step. When the primary step fails, the executor runs its recovery steps in order. If one succeeds, the primary step is recorded as recovered: the failure stays in the run record, but the step no longer counts against the scenario. Recovery distinguishes "the operation failed permanently" from "the operation failed and we put things back", for example deleting a half-created account. Recovery never erases RED; it only downgrades the failure's effect on the verdict.

Ordering is fixed. Cleanup runs after the last main step, never interleaved, so a scenario cannot hide a mid-run failure by cleaning it away before grading. Recovery runs immediately after its own primary step and before the next primary step, so the surface is restored before the next call.

> **Worked example (AutoInfo).** Recovery runs after a primary failure inside `_execute_step_with_recovery`, and a failed-then-recovered step counts as `recovered`, not `failed` (`src/autoinfo/mcp/validation.py:1142`). Cleanup steps run best-effort after the main steps, are reported under the `cleanup` key of the run result, and never influence the scenario `status` (`src/autoinfo/mcp/validation.py:1486-1509`).

### §2.7 Partial-pass policies

Some scenarios contain independent checks that all prove the same capability, and a single flaky sub-check should not sink the whole proof. The header can declare a partial-pass policy so the scenario passes with enough succeeded primaries while every failure still surfaces.

Two fields set the policy. `min_passing` is an integer count of primary steps that must succeed; `pass_ratio` is a float fraction that must succeed. The scenario passes when its succeeded primary steps meet the policy. Absent both fields, the default is all-or-nothing: every step must succeed. Partial-pass never hides a failure; the run record still lists every failed step with its trace. It only changes the verdict threshold. Pair it with the coverage audit (see §5) so a partial pass on thin coverage still reads as thin coverage, and remember that a step naming a nonexistent surface is phantom coverage that never counts (see §5).

Choose the field by the shape of the scenario. `min_passing` suits scenarios with a fixed, small number of steps where you can name the exact count; `pass_ratio` suits scenarios whose step count grows as the surface grows. A policy that lets most steps fail is not a policy, it is a skipped scenario: keep the threshold high enough that a pass still means the capability is real.

> **Worked example (AutoInfo).** Status derivation from `min_passing` (int) or `pass_ratio` (float) makes a scenario pass on enough succeeded primaries; with both absent the policy is all-or-nothing (`src/autoinfo/mcp/validation.py:1441-1462`).

### §2.8 Authoring checklist

Run these before handing a scenario to the executor.

- [ ] The file parses as YAML: no tabs, no unquoted colons inside values.
- [ ] `name` is unique across the library and `description` states what the scenario proves.
- [ ] Every step has a `kind` the adapter knows (see §3).
- [ ] Every step has an `expect` block; no step runs ungraded.
- [ ] Every environment variable a scenario needs is listed in `requires_env`, or the scenario stays unconfigured.
- [ ] Every resource the scenario creates has a matching cleanup step.
- [ ] Any step that can half-complete on failure declares `recovery_steps`.
- [ ] A scenario with optional checks sets `min_passing` or `pass_ratio` deliberately, not by accident.
- [ ] The first run is expected RED; record that RED as the baseline before fixing anything (see §4).
- [ ] A bug the scenario catches gets a regression scenario pinned to the fix that stays GREEN forever (see §5).

The smallest complete scenario file, showing the core fields and the advanced keys:

```yaml
name: registration-e2e
description: "A new user can register through the CLI and be listed by the API"
requires_env: [TEST_DB_URL]
requires_http: true
min_passing: 2
pass_ratio: 0.67
steps:
  - name: "Register a user through the CLI"
    kind: cli
    command: "app register --email new@example.dev --plan free"
    timeout_seconds: 30
    expect:
      success: true
      exit_code: 0
      stdout_has: ["registered", "new@example.dev"]
    recovery_steps:
      - name: "Delete a half-created account"
        kind: cli
        command: "app user delete new@example.dev --force"
        expect:
          success: true
    collect_artifacts:
      - path: "artifacts/registration.log"
        required: true
  - name: "The new user appears in the API listing"
    kind: rest
    method: GET
    url: "http://localhost:8080/api/users/new@example.dev"
    expect:
      status_code: 200
      json_has: ["id", "email"]
cleanup_steps:
  - name: "Delete the account and its artifacts"
    kind: cli
    command: "app user delete new@example.dev --force"
    expect:
      success: true
```

## §3 Executor engine

### §3.1 Engine contract: six phases

The engine is the executor. It finds scenario files on disk, runs every step against the real product surface, checks each step's `expect` block against the real output, and writes an immutable run record. In the operating model (see §1), the engine is the machinery the validator agent drives, and its run records are what the director (human) adjudicates (see §6). The whole job decomposes into six phases: load, dispatch, assert, aggregate, trace, persist. Phases 1 and 6 happen once per run. Phases 2, 3, and 5 happen once per step. Phase 4 happens once per scenario.

**1. Load.** Discover scenario files by recursive glob over a scenarios directory. New files are picked up with zero registration: drop a YAML file anywhere in the tree and the next run executes it. Nothing to wire, nothing to forget. The glob is the registration mechanism, so adding a regression scenario means writing a file, not editing a manifest.

**2. Dispatch.** Each step names a surface. A registry maps surface name to adapter, and the adapter turns the step into one real call: an in-process tool call, a subprocess, or an HTTP request. Dispatch always goes through the real product surface, never a mock. A step that names an undeclared surface fails with a clear reason instead of fabricating a result.

**3. Assert.** Evaluate the `expect` block against the output the adapter captured. Any assertion failure means the step failed. The evaluation is deliberately generic, booleans and substring containment only, so one engine serves a tool result dict, a CLI's stdout, and an HTTP response alike.

**4. Aggregate.** Derive the scenario status: `passed`, `failed`, `unconfigured`, `recovered`, `partial-pass`. The `unconfigured` status comes only from the environment gate that runs before any dispatch (missing env key, unreachable base URL); it is never produced by an output check. Recovery and partial-pass policies adjust the status without hiding failures.

**5. Trace.** Record each step as a trace entry: step index, wall-clock duration, arguments, and the run-wide trace id. One UUID per run, threaded into every artifact the run produces, so all evidence is linkable back to a single run record.

**6. Persist.** Write the run record to a timestamped directory (immutable, written once) and refresh a stable pointer file that names the latest run. The pointer is what trend diffs read, so a later run can always find the previous one.

> **Worked example (AutoInfo).** The executor lives in `src/autoinfo/mcp/validation.py`. Phase 1 is the recursive glob at `src/autoinfo/mcp/validation.py:809`, which pulls `scenarios/regression/` in automatically. Phase 2 dispatches mcp-kind steps through the real `call_tool` dispatcher at `src/autoinfo/mcp/server.py:6243-6245`, so the scenario hits the actual product tool surface. Phase 4 derives `unconfigured` from `requires_env` at `src/autoinfo/mcp/validation.py:1356-1367`, `recovered` from the recovery loop at `:1142`, and `partial-pass` from `min_passing`/`pass_ratio` at `:1441-1462`. Phase 5 decorates per-step traces at `:901-923` with `step_index`, `duration`, `arguments`, and the run `trace_id`. Phase 6 writes `validation-runs/<ts>/scenarios.json` and refreshes the `latest.txt` pointer at `:54-89`. The pointer is `latest.txt`, not `latest.json`; that filename is a common citation trap.

### §3.2 Surface adapters (strategy pattern)

The engine never calls a surface directly. Every step goes through an adapter, and adapters are selected with the strategy pattern: a dict maps surface name to adapter instance, and dispatch is a single line, `adapters[step.surface].run(step)`. The interface has exactly one method:

```python
class Adapter:                        # strategy interface: one step -> one real call
    def run(self, step) -> StepResult:
        """Turn one step into one real call on the surface; return the result."""
        raise NotImplementedError

class StepResult:                     # what every adapter hands back
    def __init__(self, ok: bool, output: dict):
        self.ok = ok                  # did the call reach and complete the surface
        self.output = output          # surface-shaped: stdout/exit_code, status/body, data
```

Three built-in adapters cover the common surfaces:

- **ToolAdapter.** An in-process function registry: name to callable. It looks up the step target, calls the callable with the step arguments, and returns its result dict. This serves a tool server or library API, where the callable IS the real product function and the adapter adds no behavior between scenario and product.
- **SubprocessAdapter.** Runs the step target as a command via `subprocess.run`, capturing stdout, stderr, and exit code. This serves a CLI product.
- **HttpAdapter.** Performs a requests-style call to the step target URL, capturing status code and body. This serves a web or REST service.

The dict `{surface_name: adapter}` is the dispatch table. A step whose surface has no entry fails as "no such surface", which is the honest answer when a scenario names an interface the engine cannot reach. Adding a fourth surface later (a database, a message queue) means writing one adapter and one registry line; nothing else changes.

> **Worked example (AutoInfo).** The ToolAdapter's registry is the real module-level `call_tool` dispatcher. `_validation_dispatch` invokes it at `src/autoinfo/mcp/server.py:6243-6245`, so an mcp-kind step resolves its `tool` and `arguments` through the same dispatcher that serves live clients. There is no mock path between a scenario and the product surface.

### §3.3 The core loop: Python skeleton

The whole engine fits in one file. The skeleton below implements every phase of the contract, and its dataclasses consume exactly the schema shape of §2: a scenario carries `name`, `requires_env`, `base_url`, `steps`, an optional `min_passing`/`pass_ratio` partial-pass policy, and `cleanup_steps`; a step carries `surface`, `target`, `arguments`, `expect`, `timeout`, and nested `recovery_steps`. Expect evaluation, per-step wall-clock timing and timeout, the environment gate, recovery, aggregation, trace decoration, persistence, and a `main()` that walks the scenarios directory and prints a status table are all here. The only non-stdlib import is PyYAML, needed to read the YAML scenario files; keep scenarios as JSON and you can drop it entirely.

```python
"""engine.py: pure-stdlib scenario executor (guide §3). The only optional
dependency is PyYAML for the YAML scenario files (pip install pyyaml);
keep scenarios as JSON and you can drop it. All else is stdlib."""
import dataclasses, glob, json, os, subprocess, sys, time, uuid, urllib.request
from dataclasses import field

@dataclasses.dataclass
class Step:                            # one real call plus one expect block (schema §2)
    surface: str                       # "tool" | "cli" | "http"
    target: str                        # tool name | command | url
    arguments: dict = field(default_factory=dict)
    expect: dict = field(default_factory=dict)
    timeout: float = 180.0
    recovery: list = field(default_factory=list)          # [Step]

@dataclasses.dataclass
class Scenario:                        # a declarative script of real calls
    name: str
    requires_env: list = field(default_factory=list)
    base_url: str = ""                 # reachability gate when set
    steps: list = field(default_factory=list)
    min_passing: int = None            # partial-pass policy (see §5)
    pass_ratio: float = None
    cleanup: list = field(default_factory=list)           # [Step]

def mk(d):                             # one dict -> Step, shared by all step kinds
    return Step(d["surface"], d["target"], d.get("arguments", {}),
                d.get("expect", {}), d.get("timeout", 180.0),
                [mk(r) for r in d.get("recovery_steps", [])])

# Phase 1: load. Recursive glob; new files need zero registration.
def load_scenarios(dir_):
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML required for YAML scenarios (pip install pyyaml)")
    found = []
    for p in sorted(glob.glob(os.path.join(dir_, "**", "*.yaml"), recursive=True)):
        raw = yaml.safe_load(open(p, encoding="utf-8"))
        found.append(Scenario(raw["name"], raw.get("requires_env", []),
            raw.get("base_url", ""), [mk(s) for s in raw.get("steps", [])],
            raw.get("min_passing"), raw.get("pass_ratio"),
            [mk(c) for c in raw.get("cleanup_steps", [])]))
    return found

# Phase 2: dispatch. Strategy pattern: surface name -> adapter.
class Adapter:
    def run(self, step): raise NotImplementedError

class ToolAdapter(Adapter):            # in-process registry: name -> callable
    def __init__(self, registry): self.registry = registry
    def run(self, step):
        fn = self.registry.get(step.target)
        if fn is None:
            return {"success": False, "error": "undeclared: " + step.target}
        out = fn(**step.arguments)     # the real product call, never a mock
        return out if isinstance(out, dict) else {"success": True, "data": out}

class SubprocessAdapter(Adapter):      # CLI surface
    def run(self, step):
        p = subprocess.run([step.target] + list(step.arguments.get("args", [])),
            capture_output=True, text=True, timeout=step.timeout)
        return {"success": p.returncode == 0, "exit_code": p.returncode,
                "stdout": p.stdout, "stderr": p.stderr}

class HttpAdapter(Adapter):            # REST surface
    def run(self, step):
        req = urllib.request.Request(step.target,
            method=step.arguments.get("method", "GET"))
        with urllib.request.urlopen(req, timeout=step.timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return {"success": 200 <= r.status < 300, "status": r.status, "body": body}

# Phase 3: assert. Generic truthiness / containment only.
def evaluate_expect(expect, output):
    return not (
        (expect.get("success") is not None and output.get("success") != expect["success"])
        or any(n not in json.dumps(output.get("data", "")) for n in expect.get("data_has", []))
        or (expect.get("exit_code") is not None and output.get("exit_code") != expect["exit_code"])
        or any(n not in output.get("stdout", "") for n in expect.get("stdout_has", []))
        or (expect.get("status_code") is not None and output.get("status") != expect["status_code"]))

# Phase 4 gate: unconfigured before any dispatch. Missing env key or dead
# base_url -> whole scenario unconfigured, never a pass.
def env_gate(scenario):
    if any(not os.environ.get(k) for k in scenario.requires_env): return False
    if scenario.base_url:
        try: urllib.request.urlopen(scenario.base_url, timeout=5).close()
        except OSError: return False
    return True

# Phases 2+3+5, one step: dispatch, wall-clock time, assert, trace.
def execute_step(step, adapters, trace_id, index):
    start = time.monotonic()
    try:
        output = adapters[step.surface].run(step)         # REAL surface only
    except Exception as e:             # timeout and real errors surface as failed
        output = {"success": False, "error": str(e)}
    ok = evaluate_expect(step.expect, output)
    return {"step_index": index, "target": step.target, "surface": step.surface,
            "arguments": step.arguments, "passed": ok,
            "status": "passed" if ok else "failed",
            "duration": round(time.monotonic() - start, 3),
            "trace_id": trace_id, "output": output}

# Phase 4 orchestration: gate, main steps, recovery, cleanup, aggregate.
def run_scenario(scenario, adapters, trace_id):
    if not env_gate(scenario):
        return {"scenario": scenario.name, "status": "unconfigured", "steps": [],
                "cleanup": [], "trace_id": trace_id}
    records = []
    for i, step in enumerate(scenario.steps, 1):
        rec = execute_step(step, adapters, trace_id, i)
        if not rec["passed"] and step.recovery:           # recovery steps (see §5)
            for rstep in step.recovery:
                r = execute_step(rstep, adapters, trace_id, i)
                if r["passed"]:
                    rec["status"], rec["passed"] = "recovered", True
                    break
        records.append(rec)
    cleanup = [execute_step(c, adapters, trace_id, 0) for c in scenario.cleanup]
    status = aggregate(scenario, records)
    return {"scenario": scenario.name, "status": status, "steps": records,
            "cleanup": cleanup, "trace_id": trace_id}

def aggregate(scenario, records):      # passed | recovered | partial-pass | failed
    failed = [r for r in records if not r["passed"]]
    if not failed:
        return "recovered" if any(r["status"] == "recovered" for r in records) else "passed"
    passed = len(records) - len(failed)
    if scenario.min_passing is not None:
        return "partial-pass" if passed >= scenario.min_passing else "failed"
    if scenario.pass_ratio is not None and records:
        return "partial-pass" if passed / len(records) >= scenario.pass_ratio else "failed"
    return "failed"

# Phase 6: persist. Immutable timestamped run + latest.txt pointer.
def persist(runs_root, run):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(runs_root, stamp)
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, "scenarios.json")
    with open(path, "w", encoding="utf-8") as fh: json.dump(run, fh, indent=2)
    with open(os.path.join(runs_root, "latest.txt"), "w", encoding="utf-8") as fh:
        fh.write(stamp)                # latest.txt, not latest.json
    return path

def main(argv=None):                   # walk the scenarios dir, run all, print table
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("scenarios_dir", nargs="?", default="scenarios")
    ap.add_argument("--runs-dir", default="validation-runs")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args(argv)
    adapters = {"tool": ToolAdapter(REGISTRY), "cli": SubprocessAdapter(),
                "http": HttpAdapter()}
    trace_id = str(uuid.uuid4())       # one UUID per run, threaded everywhere
    results = [run_scenario(s, adapters, trace_id)
               for s in load_scenarios(a.scenarios_dir)]
    if a.save: persist(a.runs_dir, {"trace_id": trace_id, "scenarios": results})
    print(f"{'SCENARIO':<38} STATUS")
    for r in results: print(f"{r['scenario']:<38} {r['status']}")
    return 0

REGISTRY = {}                          # the project registers real callables here
if __name__ == "__main__":
    sys.exit(main())
```

Every function maps to its phase, and the phases run in contract order. `load_scenarios` is phase 1. `run_scenario` is phase 4 orchestration, but it opens with the phase 4 gate: `env_gate` returns `unconfigured` before a single dispatch, so a scenario with missing credentials never half-runs. Each step goes through `execute_step`, which is phases 2, 3, and 5 at once: dispatch to the adapter, measure wall-clock time with `time.monotonic`, evaluate the `expect` block, and attach the trace fields. Recovery steps run only after a primary failure, and only a passing recovery call converts the record to `recovered`; the scenario then reports `recovered`, never `passed`. Cleanup steps run best-effort after the main steps and live under the `cleanup` key, so they never influence the status. `aggregate` implements the all-or-nothing default and the `min_passing`/`pass_ratio` partial-pass policy. `persist` writes one timestamped directory per run and refreshes `latest.txt`. The whole file stays compact because the loop is small; the dataclasses and inline comments account for a large share of the lines.

Run it against a directory of scenario files (see §2):

```bash
python engine.py scenarios --save
```

> **Worked example (AutoInfo).** The skeleton's `run_scenario` corresponds to `run_scenario` at `src/autoinfo/mcp/validation.py:1275`; per-step trace decoration to `:901-923`; wall-clock timing and the per-step timeout to `:1084`; the recovery loop to `:1142`; partial-pass aggregation to `:1441-1462`; best-effort cleanup, reported under `cleanup`, to `:1486-1509`; and the timestamped write plus `latest.txt` pointer to `:54-89`. The ToolAdapter registry is the real module-level `call_tool` dispatcher invoked at `src/autoinfo/mcp/server.py:6243-6245`, so mcp-kind steps dispatch through the actual tool surface, no mock.

### §3.4 Honesty hooks wired in

The engine enforces the evidence rules (see §4) by construction, in four places:

1. **No mocks by construction.** Dispatch is the only path to a surface, and every adapter performs a real call: the ToolAdapter invokes a registered product callable, the SubprocessAdapter spawns the real command, the HttpAdapter hits the real URL. There is no mock path in the engine, so a step that names an undeclared surface fails rather than faking a result, and everything the engine records is real-surface evidence by construction (see §4, and §5 for how phantom coverage stays out of the count).

2. **unconfigured never passes.** The environment gate runs before any dispatch. A missing env key or an unreachable base URL returns the whole scenario as `unconfigured`, and `unconfigured` is never counted as a pass (see §4). The gate is checked once per scenario, before the first step, so nothing ever runs half-configured.

3. **Artifact capture per step.** Every step record persists the real output alongside the `expect` that was checked, so each proof can name its artifact-to-show and carry the actual, completing the evidence contract (see §4). Without the captured artifact a GREEN claim is unverifiable; with it, the director can adjudicate (see §6). The trace fields make the evidence linkable: the run-wide trace id appears in every step record and in the persisted run record.

4. **Recovery and cleanup cannot launder results.** Only a passing recovery call flips a primary to `recovered`, and a recovered scenario is reported as `recovered`, never `passed`. Cleanup steps run best-effort regardless of outcome and never influence status (see §4). RED is recorded when it happens: a run before credentials are configured is the pre-flight baseline, and it persists as RED evidence, not silence.

### §3.5 Where the engine lives in a repo

A workable layout keeps the engine and its inputs under version control and its outputs out of it. `scenarios/` holds the YAML files, committed, with regression scenarios in a `regression/` subdirectory so the recursive glob picks them up automatically (see §5). The engine module and the small scripts that read its run records, a run-to-run diff, a coverage audit, a report renderer, are committed too. Run records go to a runtime directory such as `validation-runs/`, gitignored, because they are evidence of a moment in time, not source. A listing helper sorts the timestamped run directories newest-first, and the `latest` pointer lets the diff script compare the two most recent runs without knowing their names.

> **Worked example (AutoInfo).** The run dir is `VALIDATION_RUNS_DIR` at `src/autoinfo/mcp/validation.py:37`; the newest-first listing is `list_validation_runs` at `:92-101`; the trend function is `diff_scenario_runs` at `:115`, consumed by `scripts/validation_diff.py:31-55`. Because `validation-runs/` is gitignored, the diff needs at least two persisted runs and is not runnable on a fresh clone; it is a trend tool, not a gate.

### §3.6 Zero-dependency argument

A stdlib-only engine runs on any Python 3 installation, which means any CI, any container, any laptop, with no install step and nothing to pin. It shrinks the supply chain to zero: no packages to audit, no transitive dependencies to trust. And it mirrors the honesty rules: a mock-free engine with no framework imposing hidden behavior is easier to trust, because the whole thing reads end to end in one sitting. That legibility matters, because the director is asked to sign off on verdicts built from what the engine records (see §6). When a scenario set outgrows a single file, PyYAML is the only dependency you add, and the engine itself stays dependency-free.

## §4 Evidence and honesty rules

Evidence is the only currency that moves a scenario from RED to GREEN. A verdict that can't be replayed from the run record isn't a verdict. Every scenario the validator agent runs, and every row of a coverage audit, must satisfy the rules below before a director (human) grants sign-off.

### §4.1 No-mocks rule

A step dispatches a real call through the shipped surface: the actual tool dispatch, subprocess, or HTTP path the product exposes. Unit-test output, seeded fixtures, and simulated layers verify the code, not the product; they are not real-surface evidence and never count toward a verdict. The pytest/unit layer verifies the code; the scenario verifies the shipped surface (see §1).

Consequence: a scenario whose steps call a fake adapter is graded unverifiable, and its coverage is recorded as phantom coverage.

### §4.2 unconfigured never passes

When a required credential or precondition is missing, the whole scenario is recorded as `unconfigured`, a known limit with the reason attached. It is never silently skipped and never graded GREEN. The unconfigured scenario still appears in the run record with its gating reason and an empty step list, so a coverage audit can tell "not exercised" from "failed" (see §1).

Consequence: a run with unconfigured scenarios can't reach full sign-off until each one is resolved or explicitly waived by the director (human).

### §4.3 Artifact must be shown

GREEN means the call succeeded AND the artifact exists on disk, in the database, in the log, or in the sink AND that artifact was surfaced to the director (human): a path, a pasted payload, a log line. A call that succeeds but whose artifact is never shown isn't GREEN.

Consequence: every green step names a verifiable artifact location in the run record, and sign-off requires the director (human) to see it.

### §4.4 Local sinks are labeled as sinks

A locally hosted capture endpoint (HTTP listener, SMTP sink, mock payment server) is a real network transaction and acceptable evidence of dispatch, but it must be explicitly labeled a sink in the evidence. It is never presented as a real external channel.

Consequence: evidence that hides the word sink is rejected at review; the director (human) must always be able to tell capture from production.

### §4.5 RED recorded first

For every scenario or row, including every row of a regression scenario, the honest negative state is recorded before the GREEN state. A result that jumps straight to GREEN with no recorded negative is suspect and is re-run from the pre-flight baseline.

Consequence: the run record always contains the RED observation that the GREEN state replaced, which is what makes the verdict replayable.

### §4.6 Cleanup discipline

Every mutating call has a paired cleanup. Scenarios can declare cleanup steps that run on pass AND on fail and never affect the scenario status. Created state must be removed and the working tree left clean. Cleanup guards against touching real user data with a verify-before-delete check, and recovery steps that restore the pre-flight baseline must not re-grade any step.

Consequence: a scenario that leaves state behind fails the evidence contract even if every expect passed, because the next run can't trust its pre-flight baseline.

### §4.7 Show-your-work contract

Every FAIL names the failing expect key and the actual value observed. Every GREEN names the artifact path. Neither is optional, and both feed the blocker and root-cause reporting (see §6).

Consequence: the director (human) can walk any verdict back to the raw observation without re-running the scenario.

> **Worked example (AutoInfo)**
>
> `src/autoinfo/mcp/scenarios/kb-draft.yaml` is a self-contained, self-cleaning reference pattern: real tool dispatch, RED-first recording, artifacts written to disk, and a cleanup step paired with every mutating call. Copy its shape when authoring new scenarios.

### §4.8 Reviewer checklist

A reviewer runs this list down before any sign-off:

- [ ] MUST dispatch every step through the real shipped surface; no mocks, seeded fixtures, or simulated layers counted as evidence.
- [ ] MUST record every missing credential or precondition as `unconfigured`; never silently skip, never grade GREEN.
- [ ] MUST show an artifact (path, payload, or log line) for every GREEN.
- [ ] MUST label any local capture endpoint explicitly as a sink.
- [ ] MUST record the RED state before the GREEN state for every scenario and row.
- [ ] MUST pair every mutating call with a cleanup step that runs on pass and fail.
- [ ] MUST verify before deleting anything that might be real user data.
- [ ] MUST name the failing expect key and observed value for every FAIL.
- [ ] MUST report any partial-pass as a partial result with its failing rows, never as GREEN.
- [ ] MUST NOT present unconfigured, skipped, or sink-captured steps as real external-channel GREEN, and MUST NOT sign off a verdict whose run record can't replay it.

## §5 Coverage, regression and acceptance machinery

### §5.1 Coverage auditing: declared vs exercised

A validation layer can stay green forever and still prove nothing. If the
scenarios never touch most of the product, the pass rate is theater. Coverage
auditing is the loop that answers one question with sets instead of vibes:
which parts of the product surface are actually exercised by scenarios? It is
the first of three loops that keep the layer honest over time, and the other
two depend on it.

The audit works from two source sets. `declared` is everything the product
claims to ship: the tool list, the CLI command table, the route map, the
library entry points. `scenario_used` is what the scenarios actually step
against, read out of the scenario files by the adapter calls they declare.
Everything else is derived from those two. A small worked walkthrough:

```
declared      = {list_items, create_item, update_item, delete_item, export}
scenario_used = {create_item, update_item, delete_item, export, export_csv}

covered  = declared ∩ scenario_used = {create_item, update_item, delete_item, export}
missing  = declared − covered        = {list_items}
phantom  = scenario_used − declared  = {export_csv}
```

| Set | Meaning | How you compute it |
|-----|---------|--------------------|
| `declared` | surfaces the product claims to ship | parse the declaration source of truth |
| `scenario_used` | surfaces scenarios actually step against | parse every scenario file for adapter calls |
| `covered = declared ∩ scenario_used` | claimed and proven exercised | set intersection |
| `missing = declared − covered` | claimed but never exercised | set difference |
| `phantom = scenario_used − declared` | exercised but undeclared or invented | set difference; contributes zero |
| `boundary_only` | used surfaces that only error-boundary probes touch | set difference; listed loudly, never counted as covered |

The set-family runs per surface, not once for the whole product. A product that
ships several surfaces, a tool server, a CLI, and for pipeline-shaped products
the gates and modes those tools drive, gets one set-family per surface, so a
gap in one surface cannot hide behind a healthy count in another. The
`declared` set always comes from that surface's own source of truth: a tool
list, a command table, and for gates and modes a static parse of the product's
mode map and gate declarations, never a hand-maintained copy that can drift.
Scenarios say which gates and modes they prove through the header's
`proves_gates` and `proves_modes` fields (see §2.1), which keeps the audit
complete purely by reading the suite.

Two of these sets demand policy, not just arithmetic. `missing` is the
actionable half. A declared surface with no scenario is either a gap to close
with a scenario or a claim to drop from the declaration; both decisions belong
to the director (human). `phantom` is the smell. The rule is hard:
phantom coverage never counts. A scenario that calls an undeclared or
invented surface contributes zero coverage, because a phantom step proves
nothing about the shipped product. It arises in two ways: a typo, where the
adapter errors or
no-ops and the step is dead weight, or a vestige, a surface that never existed
after an older design drifted out. Both are defects to fix in the scenario,
not surprises to absorb into the count.

The legitimate exception is the deliberate error-boundary scenario. A step
whose whole purpose is to prove the system rejects an invalid or absent surface
tests the dispatcher, not the surface, so it must be classified explicitly as
an error-boundary probe and never silently counted as coverage. The audit needs
a place for it, an allowlist, so that the exception is declared rather than
accidental. An error-boundary probe that is not marked is just a phantom hiding
behind intent. Boundary-only probes are excluded from `covered` on their
surface and listed in the `boundary_only` set instead, so a scenario that only
proves the error path never inflates the happy-path count; the director sees
them as declared probes, not as missing or phantom coverage.

The audit itself has three requirements. It must be deterministic: regex or
static parsing over committed source and scenario files, never a runtime probe.
A runtime probe mutates state, depends on the environment, and returns
different answers on different days; static parse returns the same sets for the
same commit, which is what makes the result comparable across time. It must be
automatable: one command, runnable in CI or as its own scenario. A coverage
check nobody runs is a comment, and running it as a scenario subjects the audit
to the same verdict machinery as everything else. The command should fail loud:
when `missing` is non-empty on any surface, it exits non-zero, so a
declared-but-unexercised surface blocks acceptance instead of printing a
footnote. And its output must be
committed. The audit result is an artifact like any other: versioned, diffable,
reviewable. Coverage is a set, not a count: a count catches size drift, while
set membership catches a scenario that swapped one surface for another at the
same total. Only a committed audit result makes that swap visible in review and
in the run diff (see §5.4).

> **Worked example (AutoInfo).** AutoInfo computes `declared` with a regex over
> `Tool(name="...")` declarations in `src/autoinfo/mcp/server.py`, reads
> `scenario_used` from `kind: mcp` steps in the scenario files, and derives the
> three sets in `scripts/coverage_audit.py`: the regex at line 54, the
> intersection and the two set differences at lines 71-73. The
> same script walks the full suite via `load_scenarios()` and prints a
> regression count with its issue numbers in the summary line.
> Because the scenario loader recursive-globs the scenarios directory, the audit always sees the current suite, including everything under
> `regression/`.
>
> **Worked example (AutoMedia, the source project).** The audit this pattern was
> distilled from reports four surfaces: MCP tools, CLI commands, gates, and
> pipeline modes. Each surface carries the same set-family (`declared`, `used`,
> `covered`, `missing`, `phantom`, `boundary_only`) plus summary counts. The
> gate and mode `declared` sets are derived, never hardcoded: the audit
> statically parses the pipeline runner's mode map for the mode names and reads
> the `_gate_name` attributes off the distribution gate modules for the gate
> names, so adding a gate or mode in source automatically extends `declared`.
> Scenarios declare what they prove through the header's `proves_gates` and
> `proves_modes` lists, boundary-only scenarios (`error_boundary: true`) are
> excluded from `covered`, and the standard handbook gains one `gate.*` key per
> gate and one `mode.*` key per mode for steps that want to cite them. The
> audit command prints a per-surface line for all four surfaces and exits 1 when
> `missing` is non-empty on any of them, so a declared-but-uncovered gate or
> mode blocks acceptance exactly like a missing tool or command would.

### §5.2 The regression flywheel

The second loop closes the distance between a found bug and a forgotten one. A
bug surfaces, usually as a RED run or a director rejection. The naive move is
to fix the code and move on, but an unfixed proof of the bug is a time bomb:
nothing in the suite will remember the failure, and the same defect can ship
again unnoticed. The fix is not done when the code changes; it is done when the
exact failure is locked as a regression scenario and proven GREEN.

The lifecycle has four moves. First, write a scenario that reproduces the
failure exactly, and run it against the pre-fix build. That run is RED, and
it is evidence the bug was real and this scenario exercises the failure path.
Second, fix the code. Third, run the same scenario against the fixed build.
That run is GREEN. Fourth, keep the scenario forever.
Both runs' evidence must be shown; the pair is the whole story. A scenario
that never went RED is untrustworthy: it may pass for the wrong reason. A fix
without a GREEN run is unverified. RED proves the lock bites; GREEN proves the
fix bites; one without the other is a claim.

Four rules make the lock legible. Name the scenario with the `regression-`
prefix so the suite self-identifies: the prefix makes the class globbable,
sortable, and taggable in reports. Carry the linkage as metadata: a boolean
`regression: true` plus `regression_issue: "#NN"` pointing at the ticket. The
boolean makes the class machine-detectable, and the issue reference lets any
report trace a failing scenario back to the decision that created it. Make the
lock part of the definition of done: the fix is not done until the regression
scenario is GREEN, which shifts the boundary so a fix without a lock is an
incomplete task, not a follow-up chore. And close the top of the funnel: a bug
report template that demands a regression-scenario field makes it impossible
for a reporter to open a ticket without committing to the lock. The field is
mandatory; if the reporter cannot name the scenario, the ticket is not complete.

The flywheel is the compounding payoff. Every bug permanently strengthens the
suite, so the space of failures covered by regression scenarios grows
monotonically. A re-break turns the lock RED again, and the trend diff flags
it as a regression before the director notices (see §5.4). The suite stops being
a snapshot of what was tested once and becomes a ledger of every bug the
product has ever had and survived.

> **Worked example (AutoInfo).** AutoInfo keeps its regression scenarios in
> `src/autoinfo/mcp/scenarios/regression/`. The file `collect-int-id.yaml`
> there declares the scenario `regression-collect-int-id` with
> `regression: true` and `regression_issue: "#104"`. Note the file
> name and the scenario name differ: the file is `collect-int-id.yaml`, and the
> `regression-` prefix lives in the `name:` field, which is the citation trap
> to avoid. The recursive glob at `src/autoinfo/mcp/validation.py:809` pulls
> the `regression/` subdirectory into every run automatically, so the lock
> executes with zero extra wiring. The report isolates failed
> regression scenarios with their issue references under `## Regression
> failures`, the coverage audit prints the regression count and
> issues in its summary, and the bug template at
> `.github/ISSUE_TEMPLATE/bug_report.md` makes the regression scenario a
> mandatory field, pre-named to the `scenarios/regression/` directory.

### §5.3 Acceptance as executable specification

The third loop turns single runs into an accumulating specification. It has
three parts: verdicts that cannot be gamed, a report built for action, and a
sign-off that assigns responsibility to the right role.

Verdicts come in four values: PASS, FAIL, RISK, and `unconfigured`. PASS and
FAIL are the outcomes the director acts on. RISK flags something that succeeded
but carries uncertainty worth a human look. `unconfigured` means the step could
not run because a prerequisite was missing, and it is never a pass. The honest
response to `unconfigured` is to count it loudly, report it as a gap, and
re-run once the prerequisite is configured; a suite that quietly skips work for
missing credentials is manufacturing a pass rate. The suite's first run is
expected to be full of `unconfigured` steps; that run is the pre-flight
baseline, the recorded RED state the first configured run is measured against
(see §4). A partial-pass policy can let a scenario reach a PASS on
enough succeeded primaries, but the verdict table still carries the failed
primaries, so a pass never hides a failure (see §2 for where the policy lives
in the schema).

The report keeps findings actionable by structure. A verdict table gives
per-scenario status at a glance, with regression rows tagged. An executive
summary gives the pass, fail and `unconfigured` totals plus the
regression-failure count. Failures and blockers carry the detail needed to act:
which step failed, what the evidence said, what the assertion expected. A
per-step trace gives forensics after the fact. Blockers are findings only: the
report states what failed and why, and it never auto-fixes. An agent that
rewrites the product while reporting is not validating, it is deploying; an
auto-fix is an unverifiable claim injected into the evidence stream. Fixes
belong to the fix cycle, not the report.

| Report part | What it carries | What the director does with it |
|-------------|-----------------|--------------------------------|
| verdict table | per-scenario status, regression rows tagged | scan, spot the non-PASS rows |
| executive summary | totals, regression-failure count | gauge suite health in one glance |
| failures and blockers | step, evidence, expectation; findings only | decide the fix, no auto-fix present |
| per-step trace | step, duration, trace id per scenario | forensics when a verdict is disputed |

Sign-off assigns the final decision to the director (human). The validator
agent grades and drafts verdicts; the director disposes. The agent produces
verdicts and evidence, and the director makes the accept or reject call; only
the director's acceptance is a sign-off (see §6). That single act converts a
run into acceptance evidence: the signed run becomes part of the executable
specification, and the archive of signed runs becomes that specification's
change history. Each accepted run is a commit; each rejected run is an
amendment the next run must address. The acceptance only binds when the
evidence underneath it is real-surface evidence, and the five-part
evidence contract (see §4) is what makes a verdict auditable after the fact.
Without the contract, a PASS is a claim; with it, a PASS is a record that any
later diff can re-derive.

The specification itself is the scenario suite plus its signed runs, not a
separate prose document. That is what makes it executable: the same files that
demand behavior also verify it, so the specification cannot drift from the code
it describes. A prose spec rots; a scenario suite either passes or it does not.

> **Worked example (AutoInfo).** AutoInfo renders five sections in
> `scripts/validation_report.py`: `## Verdicts` with regression rows tagged,
> `## Executive summary` with pass/fail/unconfigured totals, `## Regression
> failures` with issue references, `## Blockers`, and `## Per-step trace`.
> Blockers carry `step_index`, `llm_reason` and `llm_meta`,
> findings only, no auto-fix. The verdict semantics PASS / FAIL /
> RISK / `unconfigured` are pinned in
> `docs/dev/acceptance-framework.md:325-328`, with `unconfigured` never a pass.
> P3 mandates real-surface evidence at line 86 and P5 states the
> agent grades and the human disposes at line 88. The framework
> names the validation layer itself the executable specification under AC9
> and catalogs the accepted evidence A1-A24, including a scenario
> pass-rate baseline.

### §5.4 Persistence and trends

None of the three loops work if runs vanish. Run records are immutable
artifacts: every run writes its own timestamped record with per-step traces,
and one stable pointer always names the latest record. Nothing overwrites a
past run; a re-run is a new record, which is exactly what makes comparison
possible. The latest pointer is a convenience, never a claim of exclusivity;
the history is the point.

Immutability is not bureaucracy. If a run record can be overwritten, a later
disagreement about what happened cannot be settled, and the sign-off is only
as durable as the last edit. An immutable record means the director can always
answer the question "why did we accept this?" by opening the exact run that
was accepted, and a later trend tool can always attribute a regression to the
exact step that flipped.

A run record must therefore carry more than a status. It needs the verdicts,
the per-step trace with the step index, duration, arguments and a trace id per
run, and either the artifacts or a pointer to them. That is the forensic floor:
enough detail that a diff can name the step, and a human can re-derive the
outcome without re-running the suite.

The diff tool is the director's drift detector. It compares two run records and
prints what changed: new passes, new failures, regressions. After a deployment,
one invocation answers "did anything flip?" and the regressed line names the
scenario and the step. Reading one diff beats re-reading two full runs, and it
beats hunting through a hundred scenarios by hand. Trends only function if runs
are persisted and the diff is actually invoked, so wire it into the review loop
rather than leaving it as a manual curiosity (see §6). The cost of
non-persistence: every run is a fresh start, drift is invisible until it
bites, and the executable specification loses its history.

> **Worked example (AutoInfo).** AutoInfo's `save_scenario_results` writes
> `validation-runs/<ts>/scenarios.json` per run and then refreshes a single
> `latest.txt` pointer (the pointer is `latest.txt`, not
> `latest.json`). `list_validation_runs()` lists run directories newest-first.
> `diff_scenario_runs(base, head)` at
> `src/autoinfo/mcp/validation.py:115` compares two records, and
> `scripts/validation_diff.py` defaults to the two newest runs, printing new
> passes, new failures and regressed scenarios. Each step in a run
> record carries `step_index`, `duration`, `arguments` and `trace_id`, so the
> trend tool can attribute a regression to the exact step that flipped. One caveat: the diff needs at least two persisted runs, and
> `validation-runs/` is runtime state, so on a fresh clone you must re-run the
> suite before the trend tool has anything to compare.

### §5.5 Retrofitting checklist

You already have a test suite and you want all three loops. These steps apply
in order, and each one is small enough to land in a day.

1. Make the surface declaration machine-readable first. A tool list, command
 table, or route map that a script can parse. Without `declared` there is no
 `covered` and no `missing`.
2. Write the coverage audit as a static parse: regex over the declaration and
 the scenario files. Run it in CI or as its own scenario, and commit its
 output so coverage is versioned and diffable.
3. Treat every phantom entry as a defect in the audit or the scenario, never in
 the product: fix the typo, drop the vestige, or move the step to an explicit
 error-boundary allowlist.
4. Close every bug ticket with a regression scenario: `regression-` prefix,
 `regression: true`, `regression_issue: "#NN"`, and proof of RED on the
 pre-fix build plus GREEN on the fixed build before the fix counts as done.
5. Add the regression-scenario field to your bug report template so reporters
 cannot skip the lock; make it mandatory and pre-named to your regression
 directory.
6. Build the report in the four parts that keep findings actionable: verdict
 table, executive summary, failures and blockers, per-step trace. Blockers
 are findings only; the validator agent grades, the director (human)
 disposes.
7. Persist every run as an immutable timestamped record with a single latest
 pointer, and wire a diff that prints new passes, new failures and
 regressions into your review loop (see §6).
8. Capture a pre-flight baseline: the RED run before credentials are
 configured. Re-run `unconfigured` scenarios once configured, and never count
 them as passes.

## §6 The director (human) in the loop

§6 is written for the director (human), the one reader in this guide who is not an
agent. Everything before this section built the machinery: the scenarios, the
executor, the honest reporting. This section is what you do with the output. The
validator agent runs the suite, drafts verdicts, and persists a run record; your
job is to read, verify, and dispose. The whole section assumes you never touch
the tooling yourself, only the artifacts it leaves behind.

### §6.1 What a run hands the director

A completed run arrives as a small stack of artifacts, not a wall of logs. The
`run record` persists what happened; the report turns it into decisions. Five
pieces deserve your attention, and each invites a different action.

1. **The verdicts table.** One row per `scenario`, carrying its `verdict`
 (PASS / FAIL / RISK / unconfigured), with `regression scenario` rows flagged.
 It tells you the shape of the run at a glance: what passed, what did not,
 what never ran. It invites you to scan for surprises before anything else.
 This is the artifact you read first, because it decides whether the rest of
 the review is a formality or an investigation.
2. **The executive summary.** Totals only: pass, fail, and unconfigured counts,
 plus how many regression scenarios failed. It tells you whether this run is
 anywhere near `sign-off`. It invites a go / no-go read before you open a
 single artifact. If the totals look healthy, the detailed sections are a
 confirmation pass; if they do not, you know immediately which sections
 deserve your full attention.
3. **The regression failures.** The `regression scenario`s that failed, each
 linked to the issue it was pinned to. It tells you whether a fixed bug came
 back. It invites immediate triage; this is the signal that costs the most if
 missed, because a silent regression ships bad behavior that someone already
 paid to fix once. Each entry carries its issue reference, so you can hand it
 back to the team that owns that fix without hunting for context.
4. **The blockers.** Every failing `step` with its `step_index` and the
 machine's reason. It tells you what the agent could not prove, and why. It
 invites a decision about each one: fix the environment, tighten the
 scenario, or change the code. Blockers are findings only; the tool never
 auto-fixes. That is deliberate. The report is a witness, not a repairman,
 and a finding you route yourself is one you understand.
5. **The per-step trace.** A table of `step_index`, duration, and `trace_id`
 for every step of every scenario. It tells you what actually ran and how
 long it took. It invites spot-checking: pick a step, find its trace, open
 its artifact. It is also your thread when something fails later in
 production; the `trace_id` ties a past verdict back to the exact call that
 produced it.

Read the five pieces in that order. The table orients you, the summary sizes
the problem, the regression section and blockers tell you what to do, and the
trace lets you verify. Each later section of this chapter deepens one of those
moves.

> **Worked example (AutoInfo).** AutoInfo renders these five pieces as a single
> validation report with the sections `## Verdicts`, `## Executive summary`,
> `## Regression failures`, `## Blockers`, and `## Per-step trace`. The run persists under `validation-runs/<timestamp>/scenarios.json`,
> and the `validation-runs/latest.txt` pointer names the newest run. The division of labor is the acceptance framework's P5: the agent
> grades; the human disposes.

### §6.2 Reading the verdicts

The four `verdict`s mean different things, and misreading the quiet ones is
where reviews go wrong. A row's status is a claim about the environment and the
code together, not about the code alone.

- **unconfigured is not a failure, and it is not a pass.** It means the
 environment gate blocked the `scenario`: a missing env var, or an endpoint
 that could not be reached. The scenario never had a chance to run, so its
 verdict proves nothing either way. A suite with many unconfigured rows is
 close to its `pre-flight baseline` state, the honest RED recorded before the
 environment was configured. Fix the environment and re-run before drawing any
 conclusion, good or bad.
- **A FAIL on a regression scenario is your highest-priority signal.** A
 `regression scenario` is pinned to a bug that was fixed, and its whole purpose
 is to stay green forever. If it fails, the fix regressed. Do not pass over it
 on the way to the newer features; nothing else in the run matters more,
 because nothing else tells you the past is coming back.
- **A FAIL on a plain scenario is a work item, not a crisis.** It says the
 shipped surface does not satisfy the declared `expect`s today. Decide whether
 the scenario is right or the product is wrong, then route one of them for a
 fix.
- **RISK means the scenario passed with reservations.** The `expect`s held, but
 something about the run was not clean: a thin artifact, a slow step, a
 `partial-pass`. It is a pass with a footnote. Before you sign off, inspect
 the artifacts of every RISK row, because the footnote usually marks the edge
 of what the scenario can actually prove.

Triage in this order: regression FAILs first, then other FAILs, then RISK rows,
then the unconfigured re-runs. The order tracks how much each verdict endangers
work already believed done.

> **Worked example (AutoInfo).** AutoInfo's engine produces the unconfigured
> state, the scenario author does not choose it: missing `requires_env`
> variables make the whole scenario return `unconfigured` via
> `_unconfigured_scenario_result`, never a silent pass or fail. The
> acceptance framework records the same semantics: unconfigured is never a
> pass, and the scenario is re-run once configured.

### §6.3 Verifying evidence, not trusting verdicts

Your core duty is not to read verdicts but to open artifacts. The
`evidence contract` (see §4) says GREEN is earned only when the call succeeded
AND the `artifact` exists AND it was shown. The report is the "shown" part; you
supply the confirmation. Remember the honesty rule behind it (see §4): a
scenario records RED before it is fixed, and GREEN only after real proof.
Nothing in the verdicts table relieves you of that final check.

Confirm each artifact you open is real: an actual file or payload the run
produced, not a stub, not a sink that wrote to a local-only path. Two quick
tests cover most cases. Does the artifact exist at the path the report claims?
Does its content match what the `expect` says it should contain? A file that
exists but holds nothing is as damning as a file that never existed.

Spot-check one or two steps whose artifacts look thin. Thin means short, empty,
or suspiciously generic: a one-line log where the step claims a payload, a
table row where it claims a file. A verdict that survives a spot-check is worth
more than one you take on faith, and the whole pass takes minutes, not hours.

If a spot-check fails, you are done reviewing. Do not sign off and do not
negotiate; return the finding with the artifact, and let the next run prove the
fix. The check exists precisely so that a cheap five-minute look can stop an
untrue GREEN from becoming acceptance evidence.

> **Worked example (AutoInfo).** AutoInfo's evidence contract is the five-part
> record, surface, real call, expect, actual, artifact-to-show, defined in
> `docs/dev/validation-scenario-contract.md`, and its
> `real-surface evidence` rule forbids mocks and seeded stores.
> When you open an artifact in the run directory you are checking that record
> against what is actually on disk. The porting map in §8 tells you where those
> files live.

### §6.4 Closing the loop and sign-off

The validator agent grades; you dispose. `sign-off` converts a run into
acceptance evidence. Until you sign, the run is a draft; after you sign, it
becomes part of the specification's change history, something later runs and
later reviewers can rely on. The distinction matters because a draft is
disposable and a signed run is precedent.

In practice, sign-off is a recorded decision, not a feeling: an archived
`run record`, an acceptance note naming the run and the date, or an equivalent
entry in whatever change log you keep. It should say which run you accepted and
why. The recording is the whole point. An unrecorded sign-off is a memory, and
memories drift; a recorded one is evidence the next director can consult.

Rejection works the same way, in reverse. Blockers and FAIL verdicts go back to
the agent as new work items: fix the environment, extend the scenario, change
the code. Nothing is auto-fixed. You close the loop by handing the findings
over, not by re-running the suite yourself. The agent picks the findings up,
makes the change, and the next run either earns sign-off or produces new
findings. The loop is a conversation that ends only when you say it ends.

> **Worked example (AutoInfo).** This is P5 of the acceptance framework: the
> agent executes and drafts verdicts, the human adjudicates and signs off, and
> blockers are findings only. The validation layer itself is
> retained as positive acceptance evidence for the executable specification,
> which is why the sign-off has somewhere to live.

### §6.5 Watching trends

Comparing two runs beats re-reading one. A run-to-run diff surface shows three
things: new passes (work is converging), new failures (something changed for
the worse), and regressed scenarios (a scenario that passed before now fails).
With a diff, drift announces itself instead of hiding in a freshly scanned
table. The report tells you the current state; the diff tells you the change,
and the change is what you act on. Coverage questions are a separate report:
the `coverage audit` (see §5) tracks which surfaces are exercised, and
`phantom coverage` never counts, so leave coverage to the machinery and keep
this review about verdicts.

A small worked reading. Suppose the diff shows three new passes, one regressed
scenario, and no new failures. The converging work is real, but the regressed
scenario is a bug that came back, and it now owns the review. Suppose instead
the diff shows only new passes, run after run. That is the good kind of
monotony, and it takes seconds to confirm.

As a suggestion, not a rule: schedule a diff before every merge-to-main or
release, and again after any bug fix lands. That cadence catches both kinds of
drift, the slow one and the sudden one, on a schedule that fits a normal
development week. You do not need a diff after every run; you need one at every
decision point.

> **Worked example (AutoInfo).** AutoInfo's `scripts/validation_diff.py`
> compares the two newest runs through `diff_scenario_runs` and prints new
> passes, new failures, and regressed scenarios. One caveat:
> it needs at least two persisted runs, and `validation-runs/` is
> runtime-gitignored, so on a fresh clone there may be nothing to diff yet.
> Treat it as a trend tool on an established checkout, not as something that
> works out of the box.

### §6.6 A director's 10-minute review checklist

Ten checks, roughly in the order that costs the least time first. If a check
passes, move on; if it fails, that is your work item. Nothing here asks you to
run tooling; you read, you confirm, you decide.

1. **Verdicts table scanned.** Any unexpected FAIL, or any PASS where you
 expected RISK? Read the table top to bottom once, fast.
2. **Regression failures empty.** If not, each one is a re-opened bug; triage
 them first, before any other finding.
3. **Blockers read and assigned.** Every blocker went back to the agent as a
 finding, with an owner. A blocker with no owner is a blocker that will
 recur.
4. **Artifacts spot-checked.** Opened the artifacts of one or two thin-looking
 steps and confirmed they are real, not stubs or local-only sinks, and that
 their content matches the `expect`.
5. **unconfigured rows explained.** For each one, the gate reason (missing env
 var, unreachable endpoint) confirmed against the current environment, and a
 re-run scheduled once configured.
6. **RISK rows inspected.** Every RISK verdict's artifacts reviewed before you
 consider sign-off, so no footnote reaches acceptance unseen.
7. **Totals cross-checked.** The executive summary's counts match the verdicts
 table, with nothing counted as a pass that was not one. Discrepancies here
 mean the report itself is unreliable.
8. **Trace skimmed.** Per-step trace scanned for absurd durations or missing
 `trace_id`s, either of which marks a step worth opening directly.
9. **Run record confirmed.** The run is persisted, and the pointer names it, or
 the archive copy exists. A run you cannot find later is a run you cannot
 cite.
10. **Loop closed.** Sign-off recorded, or the findings returned for rework.
 Nothing left pending.

Ten minutes, one pass, and the run is either accepted or back in the agent's
hands. That is the whole director loop: read, verify, dispose.

## §7 Porting checklist: adopt this in your own project

This section is the payoff of the guide: how to take the pattern into a new
project, brownfield or greenfield, one increment at a time. Everything before it
is a prerequisite: the schema (see §2), the engine (see §3), the honesty rules
(see §4), the coverage machinery (see §5), and the director loop (see §6). You
are adopting a two-role operating model, not a tool: the validator agent runs
scenarios and drafts verdicts; the director (human) adjudicates and signs off.

Every phase ends in an observable you can show someone: a listing, a run record,
an artifact, an audit, a signed decision. A brownfield project already has a
surface and a test suite; the scenario layer sits on top of the fast in-process
tests (see §1). A greenfield project defines the surface as it ships.

| Phase | Time | Outcome check |
|-------|------|---------------|
| 0. Scaffold | half a day | engine lists zero scenarios cleanly |
| 1. First scenario, RED first | half a day | one scenario GREEN, artifact shown, run record archived |
| 2. Honest evidence plumbing | 1 day | every GREEN step has a real artifact on disk |
| 3. Coverage audit | 1 day | deterministic audit committed, missing printed |
| 4. Regression flywheel | 1 day | one regression scenario with two-run evidence |
| 5. Director loop | half a day | one accepted run record, second run diffed |
| 6. Acceptance as executable specification | ongoing | no release on uncovered surfaces or failing regressions |

### §7.1 Phase 0: scaffold (half a day)

**Goal.** Commit the engine skeleton: a `scenarios/` dir, a gitignored run-records
dir, stub diff and report scripts, and a README stating the two-role model.
**Steps.**

1. Commit the adapter and run loop from §3: load a scenario, turn each
 step into one real call on a surface, grade the `expect`, persist a run
 record. Point it at your shipped surface or your first command.
2. Create `scenarios/` for scenario files in the schema of §2. One
 directory, no registration mechanism.
3. Create the run-records directory (for example `validation-runs/`) at repo
 root and gitignore it. A run record is runtime evidence, not source.
4. Add stubs for the diff and report scripts. "List the run directories newest
 first" is enough to prove the plumbing.
5. Write one README in `scenarios/` stating the two-role model: the validator
 agent runs scenarios and drafts verdicts; the director (human) adjudicates and
 signs off.
6. Run the engine's listing entry point.

**Outcome check.** The engine lists zero scenarios cleanly, with no error.

> **Blank-project example.** The product is a CLI tool with 3 commands: `greet`,
> `stats`, `export`. In half a day you commit a 200-line engine that runs a
> scenario's steps as subprocesses against the real binary, a `scenarios/` dir,
> a gitignored `validation-runs/`, stub scripts, and a README naming the two
> roles. `python -m validator list` prints `0 scenarios`.

> **Worked example (AutoInfo).** The engine auto-loads every `*.yaml` under
> `src/autoinfo/mcp/scenarios/` via a recursive glob, so subdirectories join
> with no registration (`src/autoinfo/mcp/validation.py:809`). Runs persist to
> a repo-root `validation-runs/`; each writes `scenarios.json` and refreshes a
> `latest.txt` pointer (`src/autoinfo/mcp/validation.py:37`, `src/autoinfo/mcp/validation.py:54-89`).

### §7.2 Phase 1: first scenario, RED first (half a day)

**Goal.** One scenario, two steps, run end to end. You MUST see RED (or
unconfigured, which you then fix by configuring the env gate) before any GREEN.
**Steps.**

1. Pick the single most-valuable surface of the product: the command, endpoint,
 or tool the director (human) would notice breaking first.
2. Author one scenario with exactly two steps, each one real call plus one
 `expect`, per §2. Minimal: name, description, category, `requires_env`, steps.
3. Run it. The honest result is RED (call fails, artifact absent) or
 unconfigured (prerequisite missing). Record the negative state as your
 pre-flight baseline; unconfigured is never a pass, so configure the env
 gate and re-run.
4. Fix the cause of RED. Wrong scenario, fix the scenario; wrong product, fix
 the product. Keep the RED record.
5. Re-run to GREEN, confirm the artifact exists on disk, and show it to the
 director (human).
6. Archive the run record.

**Outcome check.** One scenario GREEN with an artifact shown to the director
(human), and the run record archived.

> **Blank-project example (continued).** The most-valuable surface is `greet`.
> `scenarios/greet-works.yaml` has two steps: run `cli-tool greet --name Ada`,
> expect exit 0 and stdout to contain `Hello, Ada`, and assert the captured
> stdout artifact exists. First run is RED: `greet` prints `Hello,` without the
> name. Fix, re-run to GREEN, show the stdout to the director (human).

> **Worked example (AutoInfo).** The minimal scenario is a 22-line YAML:
> `name`, `description`, `category`, `requires_env: []`, and two steps, each
> with `tool`, `arguments`, `expect{success, data_has}` (`src/autoinfo/mcp/scenarios/meta-validation.yaml:4-22`).
> Missing env vars make the scenario `unconfigured` (`src/autoinfo/mcp/validation.py:1356-1367`);
> a run is one `scenarios.json` under `validation-runs/<timestamp>/` plus a
> refreshed `latest.txt` pointer (`src/autoinfo/mcp/validation.py:88`).

### §7.3 Phase 2: honest evidence plumbing (1 day)

**Goal.** Every GREEN step has a real artifact on disk, and the engine enforces
it. The validator agent's memory is not evidence.
**Steps.**

1. Wire artifact collection into the adapter: after each step, capture the real
 output or state (stdout, exit code, response payload, DB row count, log
 line) and write it under the run record, keyed by scenario and step.
2. Enforce artifact existence in the engine: a step that succeeds with no
 artifact cannot grade GREEN. The engine refuses; the validator agent's
 memory does not count.
3. Attach per-step trace fields to every graded step: index, duration, one run
 trace id, so a verdict walks back to the raw observation (see §4).
4. Extend `expect` to assert artifact existence, not just response fields.
5. Declare recovery steps for primaries that can retry after a transient
 failure; a failed-then-recovered step records recovered and never re-grades
 another step.
6. Pair every mutating step with a cleanup step that runs on pass and fail, so
 the next run starts from the same pre-flight baseline.
7. Label local capture endpoints explicitly as sinks in the artifact. A local
 listener is acceptable real-surface evidence of dispatch, never presented as
 a production channel.

**Outcome check.** Every GREEN step names an artifact path that exists on disk.

> **Worked example (AutoInfo).** Every proof follows the five-part evidence
> contract: surface, real call, expect, actual, artifact-to-show
> (`docs/dev/validation-scenario-contract.md:391-403`). Steps carry per-step
> trace fields: 1-based step index, duration, arguments, one run trace id
> (`src/autoinfo/mcp/validation.py:901-923`). Real-surface evidence means real MCP,
> CLI, REST, LLM, and network calls, no mocks, no seeded stores
> (`docs/dev/acceptance-framework.md:86`).

### §7.4 Phase 3: coverage audit (1 day)

**Goal.** A declared surface, a three-set audit, and a committed, deterministic result.
**Steps.**

1. Declare the surface: enumerate every tool, command, endpoint, and CLI verb
 the product claims, in one machine-readable manifest.
2. Implement the three-set audit:
 | Set | Definition |
 |-----|------------|
 | covered | declared surfaces that appear in used steps |
 | missing | declared minus covered |
 | phantom | used surfaces that are not declared, never counted |
3. Print missing. That line is the gap report the director (human) reads.
4. Commit the audit script and a snapshot of its output, so the result is
 deterministic and reviewable.
5. Re-run the audit after every scenario authoring session and whenever the
 surface changes.

**Outcome check.** The audit output is deterministic and committed, and
missing = declared minus used is printed.

> **Worked example (AutoInfo).** The audit counts `declared` from tool
> declarations, `scenario_used` from `kind: mcp` steps, `covered = declared ∩
> scenario_used`, `missing = declared - covered`, `phantom = scenario_used -
> declared` (never counted) (`scripts/coverage_audit.py:8-20`). Set operations
> are plain intersections (`scripts/coverage_audit.py:54-73`), the regression
> count is filtered on the `regression` flag (`scripts/coverage_audit.py:95-97`),
> and a partial-pass policy still surfaces failing rows while the audit counts
> steps exercised, so partial-pass never inflates coverage (see §5).

### §7.5 Phase 4: regression flywheel (1 day)

**Goal.** One real open bug fixed and locked as a regression scenario with
two-run evidence.
**Steps.**

1. Update the bug-report template to demand a mandatory regression-scenario
 field: the reporter names the reproducing scenario before any fix lands.
2. Pick one real open bug that touches the declared surface.
3. Capture RED: author the scenario, run it against pre-fix code, keep the
 failing run record. A regression scenario starts from this negative evidence.
4. Fix the bug.
5. Re-run to GREEN. Show the director (human) both runs: RED pre-fix, GREEN
 post-fix.
6. Mark it `regression: true` plus `regression_issue: "#NN"` and place it in a
 `regression/` subdirectory the loader picks up automatically.

**Outcome check.** One regression scenario in the `regression/` subdirectory
with two-run evidence (RED before, GREEN after).

> **Worked example (AutoInfo).** The bug-report template demands a mandatory
> regression-scenario field naming a scenario in `scenarios/regression/`
> (`.github/ISSUE_TEMPLATE/bug_report.md:42-48`). A regression scenario carries
> boolean `regression: true` plus `regression_issue: "#104"`
> (`src/autoinfo/mcp/scenarios/regression/collect-int-id.yaml:17-18`); the file
> is `collect-int-id.yaml` in `regression/`, `regression-collect-int-id` is
> only the `name:` field. The recursive glob pulls it in
> (`src/autoinfo/mcp/validation.py:809`).

### §7.6 Phase 5: director loop (half a day)

**Goal.** A report that renders verdicts, failures, blockers, and a per-step
trace; one 10-minute director (human) review; sign-off recorded as a decision.
**Steps.**

1. Make the report render four blocks: a verdicts table, an executive summary
 with a regression-failure count, blockers with reasons, and a per-step trace.
2. The director (human) does one 10-minute review: open the artifacts behind
 GREEN, read the evidence contract, and check that unconfigured scenarios are
 listed, not passed.
3. Record the sign-off as a decision: the accepted run record, stamped and
 archived. The agent grades; the human disposes.
4. Schedule a second run for one week later.
5. Diff the second run against the first: new passes, new failures, regressions.

**Outcome check.** One accepted run record; a second run one week later diffed
against it.

> **Worked example (AutoInfo).** The report renders `## Verdicts`
> (`scripts/validation_report.py:111`), an executive summary with totals and a
> regression-failure count (`scripts/validation_report.py:123`), `## Regression
> failures` (`scripts/validation_report.py:145`), `## Blockers`
> (`scripts/validation_report.py:178`), and `## Per-step trace`
> (`scripts/validation_report.py:203`). Verdicts are PASS / FAIL / RISK /
> unconfigured, never a pass (`docs/dev/acceptance-framework.md:325-328`); the
> validator agent executes and drafts while the director (human) adjudicates
> and signs off (`docs/dev/acceptance-framework.md:88`). Diffing needs two
> persisted runs (`scripts/validation_diff.py:31-55`), and the run dir is
> gitignored, so treat the trend diff as a live-checkout tool.

### §7.7 Phase 6: acceptance as executable specification (ongoing)

**Goal.** Release gates consult the coverage audit and the regression-failure
count; the scenario set is versioned and reviewed like code.
**Steps.**

1. Wire every release gate to the coverage audit and the regression-failure
 count. No release while a declared surface is uncovered or a regression
 scenario fails.
2. Require that PRs touching the surface do not reduce the covered/declared
 ratio.
3. Version the scenario set and review it like code. Scenarios are acceptance
 criteria.
4. Keep the two-role model: the validator agent executes and drafts; the
 director (human) adjudicates and signs off. Blockers stay findings (see §6).
5. Add one regression scenario per bug from the flywheel onward; the set grows
 with the product.

**Outcome check.** No release proceeds with an uncovered declared surface or a
failing regression scenario.

> **Worked example (AutoInfo).** The 68-scenario suite, 62 functional plus
> 6 regression, is the executable specification of the validation layer,
> retained as positive acceptance evidence
> (`docs/dev/acceptance-framework.md:370-377`). Gates consult the regression
> count (`scripts/coverage_audit.py:95-97`), and acceptance pins evidence
> to real calls (`docs/dev/acceptance-framework.md:86`).

### §7.8 Common failure modes

Watch for these in the first two months. Every one has happened in a real
adoption.

- **GREEN claimed with no artifact shown.** GREEN means the call succeeded, the
 artifact exists, and the artifact was shown to the director (human) (see §4).
 A report whose GREEN steps name no path is not GREEN.
- **unconfigured treated as pass.** Missing credentials are recorded as
 unconfigured with the reason, never silently skipped or counted GREEN; a run
 with unconfigured scenarios cannot reach sign-off until each is resolved.
- **Coverage audit omitted.** Without the declared manifest and three-set audit,
 scenarios drift from the surface, missing tools go unnoticed, and phantom
 coverage creeps in.
- **Regression scenario written after the fix.** Authored post-fix it has no RED
 evidence: it proves the code passes now, not that the scenario catches the
 bug. Capture the failing run against pre-fix code first.
- **Director rubber-stamps without opening artifacts.** Sign-off means the
 director (human) read the verdicts and artifacts. A signed run with unopened
 artifacts is a ceremony, not a decision.
- **Phantom coverage inflating numbers.** Steps naming undeclared surfaces are
 reported and excluded, never counted as covered.
- **Scenarios sharing mutable state.** Scenarios that depend on state left by
 another become order-dependent; the suite passes by sort order, not by the
 product. Every scenario starts from the same pre-flight baseline.
- **Cleanup steps skipped.** Mutating steps without paired cleanup pollute the
 environment, so later runs fail for the wrong reason and RED evidence loses
 meaning.

Run the checklist and the layer pays for itself in the first regression it
catches. The habit that matters is the loop, not the scripts: real calls, honest
grades, artifacts shown, RED before GREEN, and a director (human) who reads the
evidence. Keep the loop and the machinery can be swapped at any time.

## §8 Worked-example map: AutoInfo

### §8.1 AutoInfo in one paragraph

A worked example maps each generic mechanism from this guide onto one concrete
implementation. Use it as a Rosetta stone when implementing your own: every
concept in the map below has a home file you can open and read, so the abstract
pattern and the real code stay in lockstep. This section assumes you already
hold the mechanisms from earlier sections (see §1-§7); it does not re-explain them,
it only tells you where each one lives in AutoInfo. Every path and line number
below was verified directly against the repository on 2026-08-14; nothing here
is inferred from memory. The citation traps at the end mark the lookalikes that
look right but are wrong, and the deep-read order at the end gives the
recommended traversal when you want to study the whole system.

AutoInfo is a universal information-tracking and knowledge-base platform: you
configure sources and topics, and it handles collection, LLM-based structured
extraction, summarization, and a queryable knowledge base. It exposes one
product as three surfaces (an MCP server over stdio, a CLI that mirrors it, and
a REST API), and its validation layer is a scenario library of 68 YAML files
under `src/autoinfo/mcp/scenarios/`: 62 functional scenarios in the root plus 6
regression scenarios in the `regression/` subdirectory. A validator agent runs
those scenarios against the real MCP surface through the `list_validation_scenarios`
and `run_validation_scenario` MCP tools, and a director (human) reviews the
resulting report and delivery package before signing off. The layer sits on top
of the ordinary unit and integration test suite; it proves the shipped surface,
not the internals.

### §8.2 The map

One table, two columns. The left column names the guide concept; the right
points at the file (and line range) that implements it, with the verified key
fact in parentheses. Read it as a lookup: find the concept, open the file, read
the lines. Every path and line below was verified directly against the
repository on 2026-08-14; if a fact disagrees with what you see in the code,
trust the code and re-verify before citing anything.

| Guide concept | Where it lives in AutoInfo |
|---|---|
| Scenario library | `src/autoinfo/mcp/scenarios/` (directory: 68 YAML files, 62 functional in root + 6 regression in `regression/` subdir) |
| Scenario schema | `src/autoinfo/mcp/scenarios/meta-validation.yaml` (lines 4-22: minimal worked example with `name`/`description`/`category: system`/`requires_env: []`/`steps` carrying `tool` + `arguments` + `expect{success, data_has}`) |
| Scenario auto-load (recursive glob) | `src/autoinfo/mcp/validation.py` (line 809: `for yaml_path in sorted(sd.rglob("*.yaml"))`, pulls in `scenarios/regression/` automatically) |
| Engine entry (run_scenario) | `src/autoinfo/mcp/validation.py` (line 1275: returns `{scenario, status, summary, steps, trace_id, cleanup}`) |
| Environment gating (unconfigured) | `src/autoinfo/mcp/validation.py` (lines 1356-1367: missing env vars turn the whole scenario `unconfigured` via `_unconfigured_scenario_result`, never a silent pass or fail) |
| Per-step trace (step_index/duration/arguments/trace_id) | `src/autoinfo/mcp/validation.py` (lines 901-923: `_decorate_step_result` attaches 1-based `step_index`, `duration`, `arguments`, and one UUID `trace_id` per run) |
| Per-step timeout | `src/autoinfo/mcp/validation.py` (line 1084: `_execute_step_timed`, default 180s, wall-clock `time.monotonic`; `llm_assert` steps embed `llm_meta` with model/tokens/duration) |
| Recovery steps | `src/autoinfo/mcp/validation.py` (line 1142: `_execute_step_with_recovery` runs `recovery_steps` after a primary failure; failed-then-recovered counts as `recovered`, not `failed`) |
| Partial-pass policies | `src/autoinfo/mcp/validation.py` (lines 1441-1462: `min_passing` int / `pass_ratio` float; absent both, the scenario is all-or-nothing) |
| Cleanup steps | `src/autoinfo/mcp/validation.py` (lines 1486-1509: best-effort after main steps regardless of outcome, reported under `cleanup`, never influence `status`) |
| Run persistence + latest pointer | `src/autoinfo/mcp/validation.py` (lines 54-89: `save_scenario_results` writes `validation-runs/<ts>/scenarios.json` then refreshes `latest.txt` at line 88; `VALIDATION_RUNS_DIR` at repo root, line 37) |
| Run listing + trend diff | `src/autoinfo/mcp/validation.py` (lines 92-101: `list_validation_runs` newest-first, filtered to dirs with `scenarios.json`; line 115: `diff_scenario_runs`) + `scripts/validation_diff.py` (lines 31-55: defaults to two newest runs, prints `new passes`/`new failures`/`regressed`) |
| Real-surface dispatch (mcp steps hit the real call_tool) | `src/autoinfo/mcp/server.py` (lines 6243-6245: `_validation_dispatch` calls the REAL module-level `call_tool(name, arguments)`, the `@app.call_tool()` dispatcher at line 10921; mcp-kind steps hit the actual tool surface, no mock) |
| MCP tool declarations | `src/autoinfo/mcp/server.py` (lines 10712-10719: `Tool(name="list_validation_scenarios")`; 10720-10757: `Tool(name="run_validation_scenario")` with schema `scenario` required / `steps` / `save_results` / `timeout` default 180.0; 11347-11350: dispatch table routing; 10781: in `_LLM_REQUIRED_TOOLS`, 17 tools) |
| Coverage audit | `scripts/coverage_audit.py` (lines 8-20: `declared` = `Tool(name="...")` regex, `scenario_used` = `kind: mcp` steps, `covered` = intersection, `missing` = declared minus covered, `phantom` = scenario_used minus declared, never counted; lines 54-73: `compute_coverage`; lines 95-97: `Regression scenarios: N (issues:...)` line) |
| Regression marker | `src/autoinfo/mcp/scenarios/regression/collect-int-id.yaml` (lines 17-18: `regression: true` + `regression_issue: "#104"`; scenario `name:` is `regression-collect-int-id` at line 14) |
| Bug-report regression field | `.github/ISSUE_TEMPLATE/bug_report.md` (lines 42-48: mandatory `id: regression-scenario` field, label `回归场景 (regression scenario)`, placeholder naming the scenario in `scenarios/regression/`) |
| Validation report | `scripts/validation_report.py` (line 111 `## Verdicts` with regression rows tagged; line 123 `## Executive summary` pass/fail/unconfigured totals; line 145 `## Regression failures` with `regression_issue` refs; line 178 `## Blockers` with `step_index`/`llm_reason`/`llm_meta`, findings only; line 203 `## Per-step trace` table) |
| Delivery package (01-RAW/02-PROCESSED/03-KB/04-MATRIX/06-REJECTED + validation-report.md + manifest.json) | `scripts/validation_delivery.py` (lines 7-13 layout docstring; 939-942 `_package` creates staged dirs; 1078-1086 base `manifest.json`; 1146-1147 report + final manifest into the staged package) |
| Acceptance principles (P3 real-surface evidence, P5 agent grades / human disposes) | `docs/dev/acceptance-framework.md` (line 86 P3: real MCP/CLI/REST/LLM/network calls, no mocks, no seeded stores; line 88 P5: the agent executes and drafts verdicts, the human adjudicates and signs off, blockers are findings only) |
| Verdict semantics | `docs/dev/acceptance-framework.md` (lines 325-328: PASS / FAIL / RISK / `unconfigured`; `unconfigured` is never a pass, re-run once configured) |
| AC9 validation layer as executable spec + evidence catalog A1-A24 | `docs/dev/acceptance-framework.md` (lines 370-377: AC9, the validation layer with 68 scenarios and agent as tester is the executable specification, retained as positive acceptance evidence; line 443: Appendix A Evidence Catalog A1-A24 header; line 472: A24 scenario pass-rate baseline) |
| Five-part evidence contract | `docs/dev/validation-scenario-contract.md` (lines 391-403: `(surface, real call, expect, actual, artifact-to-show)` with a per-part rule table) |

Three rows carry the guide's honesty rules and are worth reading first. The
real-surface dispatch row is the `adapter`: `_validation_dispatch`
calls the same module-level `call_tool` a live client hits, so every mcp-kind
step is a `real call` on the shipped `surface`, no mocks. The environment gating
row is the `pre-flight baseline`: missing env vars turn the whole
scenario `unconfigured` via `_unconfigured_scenario_result`, never a silent pass
or fail, so the RED-before-configure state is recorded honestly. The coverage
audit row is where `phantom coverage` is caught: `scenario_used -
declared` is computed and never counted as coverage. The delivery package row
closes the loop to `GREEN`: it carries the concrete artifacts to the
director, so the call-succeeded state becomes a state that was actually shown,
which is the difference between a passing run and a GREEN one.

### §8.3 Citation traps

> **Five citation traps.** Every one of these looks correct and is wrong; do not
> cite any of them.
>
> 1. `src/autoinfo/mcp/scenarios/regression/regression-collect-int-id.yaml`
> does not exist. The FILE is `collect-int-id.yaml` inside `regression/`;
> only the scenario's `name:` field is `regression-collect-int-id`. The same
> file-vs-name split holds for all 6 regression files.
> 2. `validation-runs/latest.json` does not exist. The actual pointer is
> `latest.txt` (refreshed at validation.py line 88).
> 3. There is no `REGRESSION:` keyword field. The YAML marker is the boolean
> `regression: true` plus `regression_issue: "#NN"` (see `collect-int-id.yaml`
> lines 17-18).
> 4. The doc path is `docs/dev/validation-scenario-contract.md`, not
> `docs/dev/specs/validation-scenario-contract.md`. The evidence contract is
> not under `specs/`.
> 5. `scripts/validation_diff.py` needs at least 2 persisted runs, and
> `validation-runs/` is runtime-gitignored. Cite it as a trend tool over an
> existing local history, not as always-runnable on a fresh clone.

### §8.4 Deep-read order

Open the files in this order to study the whole system end to end. Each step
names what to look for; by the end you can trace any mechanism back to its
implementation without the map.

1. `src/autoinfo/mcp/scenarios/meta-validation.yaml` (lines 4-22). The minimal
 scenario: `name`, `description`, `category: system`, `requires_env: []`, and
 two `steps` each carrying `tool` + `arguments` + `expect{success, data_has}`.
 This is the schema grammar in 22 lines, and it is the file to open first
 because every other file operates on shapes defined here.
2. `src/autoinfo/mcp/validation.py` (line 809). See `sorted(sd.rglob("*.yaml"))`:
 the recursive glob that auto-loads `scenarios/regression/` with no extra
 registration. This is how the scenario library stays in sync with the
 filesystem, and it is the mechanism behind the auto-load concept.
3. `src/autoinfo/mcp/validation.py` (line 1275). Read `run_scenario`, the
 step-execution entry, and the shape it returns: `{scenario, status, summary,
 steps, trace_id, cleanup}`. Everything downstream (report, delivery, diff)
 consumes this shape, so it is the contract of the engine.
4. `src/autoinfo/mcp/validation.py` (lines 901-923, 1084, 1142, 1441-1462,
 1486-1509). The honesty machinery in one pass: per-step trace fields, the
 per-step timeout, recovery steps, partial-pass derivation, and cleanup steps.
 Watch how failed-then-recovered counts as `recovered`, not `failed`, and how
 cleanup runs best-effort without touching `status`.
5. `src/autoinfo/mcp/validation.py` (lines 1356-1367). Environment gating: how
 a missing prerequisite produces `unconfigured` and never a silent pass. This
 is the `pre-flight baseline` in code, and it is the rule that keeps a suite
 honest before credentials exist.
6. `src/autoinfo/mcp/validation.py` (lines 54-89, 37, 92-101, 115). Run
 persistence: `validation-runs/<ts>/scenarios.json`, the `latest.txt` pointer,
 newest-first listing, and the `diff_scenario_runs` trend function. Together
 these form the `run record`.
7. `src/autoinfo/mcp/server.py` (lines 6243-6245). The `adapter`:
 `_validation_dispatch` calling the real `call_tool`. This is the moment a
 scenario step becomes a real call on the shipped `surface`, and it is the
 linchpin of real-surface evidence.
8. `src/autoinfo/mcp/server.py` (lines 10712-10757, 11347-11350, 10781). The
 two MCP tool declarations, their dispatch routing, and `run_validation_scenario`
 inside `_LLM_REQUIRED_TOOLS`. This shows how the validation layer is itself
 exposed as ordinary MCP tools.
9. `scripts/coverage_audit.py` (lines 8-20, 54-73, 95-97). The `coverage audit`
 semantics: declared vs scenario_used vs covered vs missing vs phantom, and
 the regression count line. This is where `phantom coverage` is named and
 excluded.
10. `scripts/validation_report.py` (lines 111, 123, 145, 178, 203). The report
 a director reads: verdicts, executive summary, regression failures, blockers
 (findings only, no auto-fix), and the per-step trace table. This is the
 primary `artifact` shown at sign-off time.
11. `scripts/validation_delivery.py` (lines 7-13, 939-942, 1078-1086,
 1146-1147). The delivery package: staged directories, base manifest, and
 the report plus final manifest written into the package. This is the
 complete evidence bundle a director can archive.
12. `docs/dev/acceptance-framework.md` (lines 86, 88, 325-328, 370-377, 443,
 472). Close the loop with the acceptance principles (P3 real-surface
 evidence, P5 the agent grades and the human disposes), `verdict` semantics,
 AC9, and the A1-A24 evidence catalog. Then read one regression scenario
 such as `src/autoinfo/mcp/scenarios/regression/collect-int-id.yaml` and the
 matching `.github/ISSUE_TEMPLATE/bug_report.md` field to see a bug become a
 pinned `regression scenario` that must stay green forever.
