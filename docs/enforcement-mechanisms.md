---
title: Enforcement Mechanisms
description: Six enforcement mechanisms ensuring Decision Layer outputs are complete, verified, and properly routed.
---

# Enforcement Mechanisms

Six enforcement mechanisms ensure that Decision Layer outputs are complete,
verified, and properly routed before entering the Production Layer. They
restore **hard enforcement** in an agent-agnostic architecture.

---

## Enforcement Levels

| Level | Name | Behaviour |
|-------|------|-----------|
| **HARD** | Pipeline STOP | Blocks pipeline execution until resolved |
| **MEDIUM** | CLI advisory + exit code 1 | Blocks `next-node` in CI/CD flows |
| **SOFT** | CLI optional check | Reports issues but does not block |
| **SOFTEST** | Documentation convention | Recommended but not enforced by tooling |

---

## 1. D0 Gate — Decision Provenance Gate (HARD)

**Red Line 9**: Decision Layer outputs must never bypass the Production Layer.

```
Pipeline.run_full_pipeline()
    │
    ▼
┌────────────────────────────────┐
│         D0 Gate                │
│                                │
│  ┌──────────────────────────┐  │
│  │ .solution-state.yaml     │  │
│  │   exists?                │  │
│  │   ┌── No ──► STOP       │  │
│  │   │        rl9_violation │  │
│  │   │                     │  │
│  │   └── Yes               │  │
│  │       ┌── Missing nodes │  │
│  │       │   ──► STOP      │  │
│  │       │   rl9_violation │  │
│  │       │                 │  │
│  │       └── All complete  │  │
│  │           ──► Pass      │  │
│  │           rl9_compliant │  │
│  │                         │  │
│  │  force_provenance=true? │  │
│  │   ──► Bypass + audit    │  │
│  └──────────────────────────┘  │
│                                │
│  Output: provenance metadata   │
│  injected into pipeline context│
└────────────────────────────────┘
    │
    ▼
  [Production Gates G0–G7, V0–V7, L1–L3]
```

### How It Works

`D0Gate` checks for `.solution-state.yaml` at startup:

1. **File missing** → `rl9_violation` + pipeline abort
2. **Required nodes missing** → `rl9_violation` + missing node names in error
3. **All required nodes complete** → `rl9_compliant` + provenance context
4. **`--force-provenance --confirm-bypass-rl9`** → bypass + audit log entry

### Required Nodes by Mode

| Mode | Required Nodes Count | Key Nodes |
|------|---------------------|-----------|
| **Build** | 11 | brand_questionnaire, brand_positioning, market_research, audience_segmentation, competitor_analysis, product_optimization_strategy, content_marketing_strategy, asset_blueprint_planning, content_calendar_generation + routing/confirmation |
| **Scale** | 12 | Same as Build + brand_health_diagnosis, market_revalidation, audience_deepening, competitor_tracking, content_asset_audit |

### CLI Usage

```bash
# Bypass the D0 Gate (with audit trail)
automedia run --topic "..." --brand EcoBrand --force-provenance --confirm-bypass-rl9

# Check solution state
cat .solution-state.yaml
```

### Solution State Format

```yaml
# .solution-state.yaml
mode: build
brand: EcoBrand
completed_nodes:
  - brand_questionnaire
  - brand_positioning
  - market_research
  - audience_segmentation
  - competitor_analysis
  - product_optimization_strategy
  - content_marketing_strategy
completions:
  - node: brand_questionnaire
    by: user@example.com
    timestamp: "2025-07-09T10:30:00+00:00"
```

---

## 2. HITL Approval Gate (SOFT/MEDIUM)

Human nodes must be explicitly approved before the pipeline can proceed.

```
automedia solution next-node --mode build --block-on-hitl
    │
    ▼
┌────────────────────────────────┐
│  Check HITL config             │
│  for next pending node         │
│                                │
│  ┌── Agent node ──► OK        │
│  │                 (exit 0)   │
│  │                            │
│  └── Human node ──► BLOCK     │
│                      (exit 1) │
└────────────────────────────────┘
```

### CLI Usage

```bash
# Approve a human node
automedia solution approve-node --node brand_positioning --by "alice@corp.com"

# Check if next node blocks on HITL (CI gating)
automedia solution next-node --mode build --block-on-hitl
echo $?  # 0 = agent, 1 = requires human

# List pending nodes
automedia solution next-node --mode build
```

### Skip Mechanism

Human nodes that are not critical can be skipped:

```python
executor.skip_node("brand_positioning")
# Artifact is returned with metadata["human_skipped"] = True
```

Skipped nodes still count as completed for dependency graph purposes but are
marked in the audit trail.

---

## 3. Schema Validation (SOFT)

Every Decision Agent output is validated against a JSON Schema.

```
DecisionAgent output (YAML/JSON)
    │
    ▼
┌────────────────────────────────┐
│  validate-artifact             │
│  --schema <name> <path>       │
│                                │
│  ┌── Valid ──► exit 0         │
│  │           "valid"          │
│  │                            │
│  └── Invalid ──► exit 1      │
│                + error list   │
└────────────────────────────────┘
```

### Available Schemas

| Schema Name | Validates |
|-------------|-----------|
| `brand_dna` | Brand positioning output |
| `market_report` | Market research output |
| `persona_map` | Audience segmentation output |
| `competitor_matrix` | Competitor analysis output |
| `strategy_doc` | Strategy engine output |
| `asset_blueprint` | Asset library planning output |
| `content_calendar` | Content calendar output |
| `brief` | Diagnostic brief output |
| `health_report` | Brand health diagnosis (Scale) |
| `asset_audit` | Content asset audit (Scale) |
| `ab_test_config` | A/B test configuration |
| `execution_handbook` | SOP runner output |

### CLI Usage

```bash
automedia solution validate-artifact --schema brand_dna output/brand_dna.yaml
# => Artifact 'output/brand_dna.yaml' is valid against schema 'brand_dna'.
```

Schema files live in `solution-wise/schemas/*.json` and enforce required
fields and type constraints.

---

## 4. Dependency Graph (MEDIUM)

The 27-node dependency graph defines execution order. The `next-node` CLI
enforces prerequisites before allowing a node to proceed.

```
Node execution order (example for Build mode):

brand_questionnaire  ──► assign_mode  ──► brand_positioning
                                                │
                                                ▼
                                         market_research
                                                │
                                          ┌─────┴─────┐
                                          ▼           ▼
                                   audience_seg  competitor_analysis
                                          │           │
                                          └─────┬─────┘
                                                ▼
                                         product_optimization_strategy
                                                │
                                                ▼
                                         content_marketing_strategy
```

### CLI Usage

```bash
# See what node should run next
automedia solution next-node --mode build

# Preflight check before phase transition
automedia solution preflight-check --next-phase 2 --mode build
```

The graph is defined in `solution-wise/process/dependency-graph.yaml`:

```yaml
nodes:
  - node_id: 5
    name: brand_positioning
    phase: "1b"
    mode: build
    dependencies: [1, 2, 4]  # Requires nodes 1, 2, 4
    optional: false
```

---

## 5. Preflight Phase Boundary Checks (SOFT)

Before transitioning between phases, a preflight check verifies that all
artifacts from the previous phase are complete and approved.

### CLI Usage

```bash
automedia solution preflight-check --next-phase 2 --mode build
# => Preflight OK — all prerequisites for phase 2 (build) are complete.
```

The check validates:

- All nodes in the prior phase are marked completed
- Human approvals are recorded where required
- The phase transition sequence is correct

### Phase Progression

```
Phase 0 (Diagnostic) ──► Phase 1b/1s (Analysis) ──► Phase 2 (Strategy)
    ──► Phase 2.5 (Asset Library) ──► Phase 3 (Content Factory)
    ──► Phase 4 (SOP & Execution)
```

---

## 6. Provenance Metadata (SOFTEST)

Every Decision Layer artifact includes provenance metadata in its YAML
frontmatter. This ensures traceability across the entire workflow.

### Format

```yaml
---
artifact_type: brand_dna
node: brand_positioning
phase: 1b
mode: build
agent: BrandPositioningAgent
created_at: "2025-07-09T10:30:00"
checksum: a1b2c3d4e5f6...
version: 1.0
---
```

### Included Fields

| Field | Description |
|-------|-------------|
| `artifact_type` | One of the 8 standard artifact types |
| `node` | Source node name |
| `phase` | Workflow phase number |
| `mode` | `build` or `scale` |
| `agent` | Agent class that produced the artifact |
| `created_at` | ISO-8601 timestamp |
| `checksum` | MD5 of the artifact content |
| `version` | Schema version |

This metadata enables:

- **Audit trails** — trace which agent produced what and when
- **Debugging** — identify stale or incorrectly routed artifacts
- **Compliance** — prove Decision Layer ran before Production Layer

---

## Troubleshooting

### D0 Gate Failures

**Problem**: `rl9_violation` when starting a pipeline.
**Solution**: Run the Decision Layer first, or bypass:
```bash
automedia run --topic "..." --brand EcoBrand --force-provenance --confirm-bypass-rl9
```

**Problem**: Missing nodes in `.solution-state.yaml`.
**Solution**: Complete the missing nodes:
```bash
automedia solution complete-node --node brand_positioning --brand EcoBrand
```

### HITL Blocking

**Problem**: `next-node --block-on-hitl` exits with code 1.
**Solution**: Approve the pending human node:
```bash
automedia solution approve-node --node brand_positioning --by "user@corp.com"
```

### Schema Validation Failures

**Problem**: Artifact validation fails.
**Solution**: Check the error list for missing or incorrectly typed fields.
Schema files are in `solution-wise/schemas/`.

### Preflight Failure

**Problem**: Preflight check reports missing nodes.
**Solution**: Complete all nodes in the prior phase. Use `next-node` to find
the next pending node.
