---
title: HITL Framework
description: Human-In-The-Loop framework — control which decision nodes require human approval vs. AI execution.
---

# HITL Framework

Human-In-The-Loop (HITL) lets operators control which decision nodes are
executed by AI (agent) and which require human approval (human).

---

## Concept

The 27-node Decision Layer workflow has a **fixed thought chain** — every node
must execute, but the *executor* is configurable per node. Three node classes
determine the appropriate default:

| Class | Description | Examples |
|-------|-------------|---------|
| **Decision** | Needs human judgment. LLM suggests, human decides. | Brand positioning, strategy approval, mode confirmation |
| **Preference** | Brand aesthetic / creative taste. Human may have opinions. | Audience segmentation, content calendar, persona tuning |
| **Execution** | Pure automation, no judgment needed. | Pipeline execution, file archiving, MD5 checks |

---

## Presets

Two built-in presets ship with AutoMedia:

### `automated` (Fully Automated)

```
brand_questionnaire  ─► human  (initial input must be human)
all other nodes      ─► agent
```

Suitable for power users who trust AI and value speed.

### `semi-automated` (Semi-Automated)

```
decision nodes       ─► human
preference nodes     ─► human
execution nodes      ─► agent
```

Suitable for teams that want quality control while keeping execution fast.

### `director` (Human-in-the-Loop Gate Approval)

```
gate_nodes              ─► human  (topic, content, brand, wechat,
                                    vision, tts, subtitle, publish)
all other nodes         ─► agent
```

Specifically designed for pipeline **gate-level** human-in-the-loop approval.
The pipeline executes all gates automatically but **pauses** at configurable
review points. A human operator inspects the output and **approves** or
**rejects** each gate via dedicated MCP tools:

| MCP Tool | Description |
|----------|-------------|
| `approve_gate` | Approve a paused gate — pipeline resumes automatically (dormant `pause_on_approval` mechanism; never fires in a default run) |
| `reject_gate` | Reject a paused gate — triggers failure handling (dormant mechanism, as above) |
| `review_decision` | **The LIVE approval path for H0 pauses**: approve or reject a pipeline paused at a HITL review gate. Approve resumes; reject converts the H0 result to a stop-failure and the pipeline halts. `show_diff=True` attaches a unified diff from the latest `.automedia/gate_diffs/` record. Same-process only: pipelines started via MCP (`run_pipeline` daemon threads); CLI-started pipelines run in a separate process and cannot be resumed here (fast structured error, no deadlock) |
| `get_pending_approvals` | List all gates currently awaiting human approval |

Beyond the MCP tools, a paused H0 review can be resolved through two more
channels:

- **Interactive prompt**: `automedia run ... --wait-for-review` prompts on
  stdin when H0 pauses (`[a]pprove` / `[r]eject`). It forces the run to block
  even when stdin is not a TTY, where the prompt cannot run and the decision
  must arrive out-of-band.
- **Cross-process CLI**: `automedia hitl pending` lists projects awaiting a
  decision, and `automedia hitl approve <project_id>` /
  `automedia hitl reject <project_id>` write the decision into the project
  directory. Both accept `--base-dir`.

On an interactive terminal an undecided pause waits
`gate_engine.hitl_timeout_s` seconds (default `3600`, one hour) before
`gate_engine.hitl_on_timeout` applies. The default policy is `reject`, so the
pipeline fails rather than shipping unreviewed content. Set
`gate_engine.hitl_on_timeout: approve` (or pass `automedia run
--hitl-on-timeout approve`) to auto-approve at timeout. `automedia run
--hitl-timeout SECONDS` overrides the budget for a single run.

When stdin is not a TTY and neither `--wait-for-review` nor `--hitl-block` is
given, the run does not block at all: it parks immediately, returns
`status="awaiting_review"`, and exits 3 in seconds rather than waiting out the
review budget. `--hitl-block` opts back into the blocking behaviour for a human
tailing the logs. `--skip-review` and `--wait-for-review` are mutually
exclusive; `--skip-review` and `--hitl-block` are too.

A parked run is resumed by passing its project id, which preserves the decision
already delivered to the project directory:

```bash
automedia run --topic "..." --brand my-brand          # non-interactive: parks, exits 3
automedia hitl pending                                # see what is waiting
automedia hitl approve <project_id>                   # a human decides later
automedia run --project-id <project_id> --resume-from H0
```

`--resume-from H0` requires `--project-id`; without a project id the runner
starts a brand-new project instead of the parked one.

The director preset defines 8 review nodes for gate-level oversight:

| Review Node | Gate | What's Reviewed |
|-------------|------|----------------|
| topic | Pre-gate | Topic selection and validation |
| content | CW | Written content draft quality |
| brand | G3 | Brand CTA compliance |
| wechat | G4 | WeChat-specific formatting checks |
| vision | V1 | Vision QA — image/video quality |
| tts | V4 | TTS audio quality and brand asset check |
| subtitle | V6 | Subtitle rendering accuracy |
| publish | L1 | Publish log review before platform distribution |

### Usage

```bash
# Run pipeline in director mode (CLI)
automedia run --topic "..." --brand my-brand --director

# Decide the H0 pause interactively in this terminal
automedia run --topic "..." --brand my-brand --director --wait-for-review

# Or via MCP
# Call run_pipeline with director=true, then poll get_pending_approvals
# Approve passing gates: approve_gate(gate_name="V1")
# Reject failing gates: reject_gate(gate_name="V1")
```

The director mode is also accessible via `python`:

```python
from automedia import run_full_pipeline

result = run_full_pipeline(
    topic="AI tools",
    brand="my-brand",
    director=True,
)
# Pipeline runs until H0, then pauses.
# Use the review_decision MCP tool to continue (approve) or halt (reject).
# approve_gate/reject_gate target the dormant pause_on_approval mechanism,
# NOT the live H0 pause.
```

Suitable for teams that want full pipeline automation but require a
human sign-off before content goes live.

---

## NodeExecutor

The `NodeExecutor` routes execution based on the active HITL configuration:

```python
from automedia.hitl import HITLConfig, NodeExecutor
from automedia.decision.diagnostic import DiagnosticAgent

# Load the semi-automated preset
cfg = HITLConfig(preset_name="semi-automated")
executor = NodeExecutor(cfg)

agent = DiagnosticAgent()

# Agent-mode node → artifact returned immediately
result = executor.execute("build_scale_routing", agent, context)

# Human-mode node → returns None, stored as pending
result = executor.execute("brand_questionnaire", agent, context)
# result is None; suggestion stored internally

# Approve the pending node
artifact = executor.approve_node("brand_questionnaire")

# Or skip it (artifact marked with human_skipped=True)
artifact = executor.skip_node("brand_questionnaire")
```

### Pending Node Lifecycle

```
execute("human_node", agent, context)
    │
    ▼
┌──────────────────────┐
│  pending_nodes()      │  ← "human_node" listed here
│  ["human_node"]       │
└──────────┬───────────┘
           │
    ┌──────┴──────┐
    ▼             ▼
approve()      skip()
    │             │
    ▼             ▼
Artifact     Artifact with
returned     human_skipped=True
```

---

## CLI Commands

```bash
# List available presets
automedia hitl preset --list

# Activate a preset
automedia hitl preset --set semi-automated

# Show current HITL configuration summary
automedia hitl config

# List pipelines parked waiting for a human decision
automedia hitl pending

# Deliver a decision to a pipeline parked in another process
automedia hitl approve <project_id>
automedia hitl reject <project_id>

# Record human approval for a node
# (use the Decision Layer SDK: automedia.decision.orchestrator.approve_node)
```

---

## Override Mechanism

Users can fine-tune preset behaviour with override YAML files:

```yaml
# ~/.automedia/hitl/overrides/custom.yaml
brand_positioning:
  autoset: human              # Override from agent → human
  type: decision
```

Overrides are merged after the preset is loaded, so they take precedence.
Multiple override files can coexist — they are applied in alphabetical order.

### Override Resolution Order

```
1. Built-in preset (e.g. "automated")
2. Filesystem preset (e.g. ~/.automedia/hitl/presets/my-preset.yaml)
3. Per-node overrides (sorted *.yaml in overrides directory)
```

---

## Integration with HITL SDK

```python
from automedia.hitl import HITLConfig, NodeExecutor
from automedia.decision.base import BaseDecisionAgent

cfg = HITLConfig(preset_name="semi-automated")
executor = NodeExecutor(cfg)

agent = BaseDecisionAgent()
result = executor.execute("my_node", agent, context)
# Human-approved nodes block until manually approved via CLI
```
