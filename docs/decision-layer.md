---
title: Decision Layer
description: Decision orchestration layer above the production pipeline — what to produce and why.
---

# Decision Layer

The Decision Layer sits **above** the Production Layer (PRD-1) and the Omni
Adapter Layer (PRD-2). It answers *what* to produce and *why*, leaving the
Production Layer to answer *how*.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                      DECISION LAYER                               │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                Diagnostic Agent (Phase 0)                  │   │
│  │  Smart questionnaire → Build/Scale routing → Asset scan    │   │
│  └────────────────────┬─────────────────────────────────────┘   │
│                       │                                         │
│         ┌─────────────┴─────────────┐                           │
│         ▼                           ▼                           │
│  ┌─────────────────┐  ┌─────────────────────────┐               │
│  │ Build Engine     │  │ Scale Engine             │               │
│  │ (Phase 1-B)      │  │ (Phase 1-S)              │               │
│  │ 4 parallel agents│  │ 5 parallel agents        │               │
│  └────────┬─────────┘  └──────────┬──────────────┘               │
│           └──────────┬────────────┘                              │
│                      ▼                                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Strategy Engine (Phase 2)                     │   │
│  │  Product Optimization + Content Marketing (merge)         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                      │                                           │
│                      ▼                                           │
│  Output: Brief │ Brand DNA │ Market Report │ Persona Map │      │
│          Competitor Matrix │ Strategy Doc │ Asset Blueprint     │
└──────────────────────────────────────────────────────────────────┘
```

## Build Mode vs Scale Mode

| Aspect | Build Mode | Scale Mode |
|--------|-----------|------------|
| **Input** | Brand idea + target market | Existing brand name |
| **When** | New brand / product from scratch | Brand already in market |
| **Phase 1 agents** | 4: BrandPositioning, MarketResearch, AudienceSegmentation, CompetitorAnalysis | 5: BrandHealthDiagnosis, MarketRevalidation, AudienceDeepening, CompetitorTracking, ContentAssetAudit |
| **Output** | Full brand DNA, market entry strategy | Health report, optimisation roadmap |
| **Strategy** | Converged (same Strategy Engine) | Converged (same Strategy Engine) |

---

## All 11 Agents

### Diagnostic Agent (1)

- **`DiagnosticAgent`** — Phase 0. Runs the smart questionnaire, routes to
  Build or Scale mode, and performs an initial asset inventory scan.

### Build Agents (4)

- **`BrandPositioningAgent`** — Produces brand DNA: vision, mission, values,
  personality, tone of voice, multilingual taglines.

- **`MarketResearchAgent`** — Searches web (Tavily/SerpAPI) for market size,
  consumer behaviour, cultural taboos, and compliance requirements.

- **`AudienceSegmentationAgent`** — Outputs 3-5 buyer personas with
  demographics, psychographics, pain points, and content resonance maps.

- **`CompetitorAnalysisAgent`** — Generates SWOT for 5 competitors, content
  benchmarks, and differentiation whitespace recommendations.

### Scale Agents (5)

- **`BrandHealthDiagnosisAgent`** — Scores brand awareness, consistency, and
  competitiveness; suggests positioning refresh.

- **`MarketRevalidationAgent`** — Re-analyses category trends and identifies
  adjacent-market opportunities.

- **`AudienceDeepeningAgent`** — Clusters existing customers, identifies best
  customer profiles, and finds expansion personas.

- **`CompetitorTrackingAgent`** — Monitors competitor content strategy changes
  since last analysis; outputs counter-positioning suggestions.

- **`ContentAssetAuditAgent`** — Scans historical content, auto-tags, rates by
  performance (hero/needs-update/stale), outputs an optimization list.

### Strategy Engine (2)

- **`ProductOptimizationAgent`** — Build mode: product positioning, feature
  priorities, localisation. Scale mode: iteration recommendations based on
  feedback and returns.

- **`ContentMarketingStrategyAgent`** — Core message house, content pillars
  (3-5), channel matrix, content calendar framework.

---

## DecisionOrchestrator API

The `DecisionOrchestrator` is the top-level entry point for the Decision Layer.

```python
from automedia.decision import DecisionOrchestrator

orch = DecisionOrchestrator()

# Build mode — from idea
artifacts = orch.run_build_mode(
    idea="Eco-friendly water bottle for SEA market",
    brand="EcoBrand",
    market="Southeast Asia",
)

# Scale mode — existing brand
artifacts = orch.run_scale_mode(
    brand_name="EcoBrand",
    market="Thailand",
)

# Convert to pipeline input
pipeline_input = orch.convert_to_pipeline_input(artifacts)
# => {"topic": "...", "brand": "EcoBrand", "mode": "build"}
```

### With HITL

```python
from automedia.decision import DecisionOrchestrator
from automedia.hitl import HITLConfig

cfg = HITLConfig(preset_name="semi-automated")
orch = DecisionOrchestrator(hitl_config=cfg)

artifacts = orch.run_build_mode("Organic skincare for Japan", "GlowBrand")
# Human-mode nodes are stored as pending; call approve_node() to release
```

### Configuration

Decision Layer behaviour can be tuned through:

- **`~/.automedia/config.yaml`** — brand defaults, mode hints
- **`~/.automedia/hitl/overrides/*.yaml`** — per-node executor overrides
- Environment variable `AUTOMEDIA_LICENSE_KEY` — enables commercial features

### Artifact Outputs

Each agent produces a `DecisionArtifact` dataclass:

```python
@dataclass
class DecisionArtifact:
    artifact_type: str       # "brief", "brand_dna", "market_report", etc.
    content: dict            # Structured payload
    format: str              # "yaml", "markdown", or "csv"
    metadata: dict           # Provenance info
    created_at: datetime     # ISO-8601 timestamp
```

---

## CLI Usage

```bash
# Run the full Decision Layer (Build mode)
automedia decision run --mode build --idea "Eco water bottle" --brand EcoBrand

# Run Scale mode
automedia decision run --mode scale --brand EcoBrand

# Complete a node manually
automedia solution complete-node --node brand_positioning --brand EcoBrand

# Check next pending node
automedia solution next-node --mode build

# Validate an artifact against schema
automedia solution validate-artifact --schema brand_dna output/artifacts/brand_dna.yaml

# Preflight check before phase transition
automedia solution preflight-check --next-phase 2 --mode build
```

---

## Dependency Graph

The 27-node workflow is defined in `solution-wise/process/dependency-graph.yaml`.
Nodes are organised into phases (0, 1b, 1s, 2, 2.5, 3, 4) with explicit
prerequisites. The `next-node` CLI and `preflight-check` CLI enforce these
dependencies automatically.

---

## Enforcement Integration

The Decision Layer feeds into the Enforcement Layer via:

1. **D0 Gate** — validates `.solution-state.yaml` before Production Layer runs
2. **Schema Validation** — 12 JSON Schema files verify artifact structure
3. **Preflight Checks** — phase transition validation before proceeding

See [enforcement-mechanisms.md](enforcement-mechanisms.md) for details.
