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
| `approve_gate` | Approve a paused gate — pipeline resumes automatically |
| `reject_gate` | Reject a paused gate — triggers failure handling (retry or stop) |
| `get_pending_approvals` | List all gates currently awaiting human approval |

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
# Use MCP approve_gate/reject_gate to continue.
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
