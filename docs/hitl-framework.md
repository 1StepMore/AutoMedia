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
automedia solution approve-node --node brand_positioning --by "alice@example.com"

# Show next pending node (exit code 1 if node requires HITL)
automedia solution next-node --mode build --block-on-hitl
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

## Integration with DecisionOrchestrator

```python
from automedia.hitl import HITLConfig
from automedia.decision import DecisionOrchestrator

cfg = HITLConfig(preset_name="semi-automated")
orch = DecisionOrchestrator(hitl_config=cfg)

artifacts = orch.run_build_mode("Product idea", "BrandName")
# Human nodes block until approved via CLI or API
```
