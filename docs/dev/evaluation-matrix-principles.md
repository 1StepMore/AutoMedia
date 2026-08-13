# Evaluation Matrix — Principles & Protocol

> **Purpose:** This is a **diagnostic toolkit**, not a scorecard.
>
> The goal is to systematically surface problems → fix them → re-evaluate → ship.
> Scores are a secondary signal (a thermometer), not the target. The real output
> is a prioritized, evidence-backed issue list that drives action.
>
> Any agent or human can run this evaluation to assess production readiness,
> find regressions, and track progress over time.

---

## Table of Contents

1. [Core Philosophy](#1-core-philosophy)
2. [The Eight Dimensions](#2-the-eight-dimensions)
3. [How to Run an Evaluation](#3-how-to-run-an-evaluation)
4. [Dimension 1: Agent Readiness](#4-agent-readiness)
5. [Dimension 2: Production Readiness + Observability](#5-production-readiness--observability)
6. [Dimension 3: Documentation (Quality + Accuracy)](#6-documentation-quality--accuracy)
7. [Dimension 4: Robustness](#7-robustness)
8. [Dimension 5: Design](#8-design)
9. [Dimension 6: End-to-End Integration](#9-end-to-end-integration)
10. [Dimension 7: Security](#10-security)
11. [Dimension 8: Performance & Cost](#11-performance--cost)
12. [Data Collection Protocol](#12-data-collection-protocol)
13. [Evidence Requirements](#13-evidence-requirements)
14. [Baseline & Trend Tracking](#14-baseline--trend-tracking)

---

## 1. Core Philosophy

### The Diagnostic Loop

```
  ┌─────────────────────────────────────────────────┐
  │  1. EVALUATE  →  2. FIND PROBLEMS  →  3. FIX    │
  │       ↑                            │             │
  │       └──────── 4. RE-EVALUATE  ←──┘             │
  └─────────────────────────────────────────────────┘
```

The matrix exists to power this loop. Each pass should:
1. **Surface concrete issues** with file paths and evidence
2. **Classify by severity** (P0–P5) so you know what to fix first
3. **Track delta** from the previous pass — are we getting better or worse?
4. **Identify blind spots** — areas the last fix cycle missed

### What Matters

| Priority | Focus | Example |
|----------|-------|---------|
| **🔴 P0** | Blocks shipping | Pipeline crashes, data loss, security hole |
| **🟠 P1** | Major risk | Silent failures, no retry, stale critical docs |
| **🟡 P2** | Quality | Missing tests, broad exception handlers |
| **🔵 P3** | Polish | Type hygiene, dead code, docstring gaps |
| **🟤 P4** | Ops | Docker HEALTHCHECK, logrotate |
| **⚪ P5** | Future | Video synthesis full version, HTTP transport |

### Scoring: Hard Blocker Model (Not Weighted)

This matrix does **not** use weighted averages. It uses **hard blocking conditions**:

```
Any 🔴P0 finding in a dimension → dimension score = 0
Any 🟠P1 finding → dimension score capped at 5
No P0/P1 → dimension score based on remaining issue density
```

Why? Because weighted averages hide problems. A single 🔴P0 (e.g., "pipeline crashes on all inputs") makes the entire dimension untrustworthy, regardless of how many green checks pass. The score exists only to answer one question: *"Is this dimension safe to ignore for the current sprint?"*

| Score | Meaning for the Sprint |
|-------|----------------------|
| **9–10** | No action needed. All critical checks pass. |
| **7–8** | Pay down P2/P3 issues when convenient. |
| **5–6** | P1 issues exist. Fix before next deploy. |
| **1–4** | P0 issues exist. Stop and fix immediately. |
| **0** | At least one 🔴P0 blocker. **Cannot ship.** |

### What the Score Tells You

- **Score improving** → fix loop is working
- **Score flat** → fixing in wrong areas or regressions offset gains
- **Score dropping** → regressions outpacing fixes
- **Score = 0 on any dimension** → 🔴P0 blocker. Ship blocked.

---

## 2. The Eight Dimensions

Eight orthogonal views. Each covers a distinct risk area so no single blind spot
can hide. Three were added after production experience revealed gaps in the
original five.

| # | Dimension | Detects | Added When |
|---|-----------|---------|-----------|
| 1 | **Agent Readiness** | Things that break CI/agent workflows | v1 (original) |
| 2 | **Production Readiness + Observability** | Things that break deployment & debugging | v1 (original) |
| 3 | **Documentation (Quality + Accuracy)** | Things that make the project confusing | v1 (original, refined v2) |
| 4 | **Robustness** | Things that crash in production | v1 (original) |
| 5 | **Design** | Things that make the codebase hard to change | v1 (original) |
| 6 | **End-to-End Integration** | Things that make the system not actually work | v2 (gap) |
| 7 | **Security** | Things that make the system exploitable | v2 (gap) |
| 8 | **Performance & Cost** | Things that make the system too expensive or slow | v2 (gap) |

### Overlap Is Intentional

A missing Docker HEALTHCHECK could be flagged under Production Readiness,
Robustness, or Security. This is fine. The overlap ensures nothing slips
through. Deduplicate when fixing, not when finding.

---

## 3. How to Run an Evaluation

### One-Time Setup

```bash
pip install -e ".[dev]"
pip install vulture interrogate pip-audit safety  # optional evaluation tools
```

### Execution Flow

```
Step 1 — Check blocking conditions
    If any blocking condition (§13) is met → STOP.
    Fix the blocker first, then restart the evaluation.

Step 2 — Collect raw data
    Run all commands in §12 Data Collection Protocol.
    Output to .omo/evaluation-data-{date}.json.

Step 3 — Check each dimension
    For each of the 8 dimensions:
      a. Run the automated metrics (§4–§11)
      b. Check hard blockers first — any 🔴P0?
      c. Note every FAIL or WARN
      d. Assign severity (P0–P5)
      e. Record evidence (file:line, command output)

Step 4 — Compute scores
    Any 🔴P0 → dimension = 0
    Any 🟠P1 → dimension ≤ 5
    Otherwise → 10 - (issue_count * 0.5), clamped to [0, 10]

Step 5 — Prioritize the issue list
    Sort ALL issues across ALL dimensions by severity.
    🔴P0 → must fix before next deploy
    🟠P1 → fix now
    🟡P2 → this sprint
    🔵P3+ → backlog

Step 6 — Compare to baseline
    issue_delta = current_issue_count - baseline_issue_count
    p0_delta = current_p0_count - baseline_p0_count
```

### What a Good Evaluation Produces

```json
{
  "evaluated_at": "2026-07-14",
  "baseline": "2026-07-07",
  "blocking_conditions_met": false,
  "dimensions": {
    "agent_readiness": {
      "score": 8.5,
      "p0_count": 0,
      "p1_count": 1,
      "total_issues": 3,
      "issues": [
        {
          "severity": "P1",
          "title": "gates/__init__.py missing __all__",
          "evidence": "grep showed no __all__ in gates/__init__.py",
          "file": "src/automedia/gates/__init__.py"
        }
      ]
    }
  },
  "total_issues": 12,
  "p0_count": 1,
  "p1_count": 3,
  "ship_blocked": true,
  "summary": "1 🔴P0 blocker found. Cannot ship until resolved."
}
```

---

## 4. Agent Readiness

*Detects things that break CI, agents, and automated tooling.*

### Why This Exists

If an AI agent or CI pipeline can't trust the codebase, every interaction is
slower and more error-prone. Clean exports, type annotations, and a healthy test
suite are the foundation for automated work.

### Metrics

| # | Check | How to Measure | Pass | Warn | Fail |
|---|-------|---------------|------|------|------|
| AR1 | `type:ignore` count | `grep -rn "type:.*ignore" src/automedia/ --include="*.py" \| wc -l` | ≤5 | 6–15 | >15 |
| AR2 | Pre-commit active | `ls .pre-commit-config.yaml` | exists | — | missing |
| AR3 | `__all__` in packages | Grep `^__all__` in each `__init__.py` | ≥80% | 50–80% | <50% |
| AR4 | Return type annotations | `grep -c "def.*->"` vs `grep -c "^def "` | ≥70% | 40–70% | <40% |
| AR5 | Test infrastructure | `pytest --collect-only --quiet 2>&1 \| tail -3` | collects clean | warnings | errors |
| AR6 | Test pass rate | `pytest --tb=short -q 2>&1 \| tail -1` | ≥99% | 90–99% | <90% |
| AR7 | Coverage rate | `coverage report \| tail -1` | ≥80% | 65–80% | <65% |

### Problem Discovery

| Condition | Severity | Why |
|-----------|----------|-----|
| Test collection fails | `🔴P0` | Entire test suite is broken |
| Test pass rate <90% | `🔴P0` | Regressions are being merged |
| No pre-commit | `🟠P1` | No automated quality gate on commit |
| Coverage <65% | `🟠P1` | Large untested areas will break silently |
| `type:ignore` without comment | `🟡P2` | Future maintainers won't know why |
| Missing `__all__` in package | `🟡P2` | Public API surface is ambiguous |

---

## 5. Production Readiness + Observability

*Detects things that break deployment, operation, and debugging in production.*

### Why This Exists

Production is where theory meets reality. Deployment configs, CI pipelines,
environment management, monitoring, and **debuggability** are what separate a
working project from a broken deployment. Observability is merged here because
a system that deploys perfectly but can't be debugged in production is still
not production-ready.

### Metrics

| # | Check | How to Measure | Pass | Warn | Fail |
|---|-------|---------------|------|------|------|
| PR1 | Dockerfile | `ls Dockerfile` | exists | — | missing |
| PR2 | Docker HEALTHCHECK | `grep HEALTHCHECK Dockerfile` | present | — | missing |
| PR3 | docker-compose | `ls docker-compose.yml` | exists | — | missing |
| PR4 | Systemd service count | `ls deploy/systemd/*.service \| wc -l` | ≥2 | 1 | 0 |
| PR5 | Systemd hardening | `grep "NoNewPrivileges\|PrivateTmp\|ProtectSystem" deploy/systemd/*.service` | all 3 | 1–2 | 0 |
| PR6 | CI workflows | `ls .github/workflows/*.yml \| wc -l` | ≥5 | 2–4 | <2 |
| PR7 | CI coverage threshold | Check ci.yml for `--cov-fail-under` | ≥75% | exists, lower | missing |
| PR8 | `.env.example` vars | `grep -c "^#\|^[A-Z]" .env.example` | ≥25 | 10–24 | <10 |
| PR9 | Startup validation | `automedia doctor` works | command exists | — | missing |
| PR10 | Logrotate | `ls deploy/logrotate/` | exists | — | missing |
| PR11 | Cron jobs | `ls src/automedia/cron/jobs.yaml` | ≥2 jobs | 1 job | none |
| PR12 | Health check tool | MCP `health_check` or process check | exists | partial | missing |
| PR13 | Graceful shutdown | Signal handlers in MCP/server | yes | — | missing |
| **O1** | **Log format compatible with aggregators** | Check structlog config for JSON output | JSON format | text only | no output |
| **O2** | **Correlation ID through pipeline** | `grep -rn "correlation_id\|request_id\|trace_id" src/automedia/ --include="*.py"` | consistent | partial | missing |
| **O3** | **Pipeline resume works** | Test `resume_from` parameter | tested, works | exists, untested | missing |
| **O4** | **MD5 audit trail** | `grep -rn "pipeline_md5" src/automedia/ --include="*.py"` | exists as hook | partial | missing |

### Problem Discovery

| Condition | Severity | Why |
|-----------|----------|-----|
| No CI | `🔴P0` | Can't merge safely, no quality gate |
| No `.env.example` | `🔴P0` | Can't configure the project |
| Pipeline resume untested | `🟠P1` | Long pipelines restart from scratch on crash |
| No correlation ID | `🟠P1` | Can't trace a single request across logs |
| Log format not JSON | `🟡P2` | Hard to ingest into log aggregators |
| No HEALTHCHECK | `🟡P2` | Ops won't know when the service dies |

---

## 6. Documentation (Quality + Accuracy)

*Detects things that make the project confusing or misleading.*

### Why This Exists

Documentation is the user interface for understanding. For an AI agent, **stale
docs are worse than no docs** — they cause incorrect decisions that waste time
and break things. This dimension measures both **coverage** (quantity) and
**correctness** (accuracy). The accuracy checks are weighted higher because
wrong docs actively harm.

### Metrics: Coverage (Quantity)

| # | Check | How to Measure | Pass | Warn | Fail |
|---|-------|---------------|------|------|------|
| DC1 | README length | `wc -l README.md` | ≥100 | 50–99 | <50 |
| DC2 | Doc files in `docs/` | `ls docs/user/*.md docs/dev/*.md 2>/dev/null \| wc -l` | ≥10 | 5–9 | <5 |
| DC3 | Runbook / troubleshooting files | `ls docs/dev/gate-failure-modes.md docs/dev/cron-troubleshooting.md docs/dev/api-gotchas.md 2>/dev/null \| wc -l` | ≥3 | 1–2 | 0 |
| DC4 | Docstring density | grep triples vs defs+classes | ≥80% | 60–80% | <60% |
| DC5 | CONTRIBUTING.md | `ls CONTRIBUTING*` | exists | — | missing |
| DC6 | CHANGELOG.md active | Check for `[Unreleased]` | active | exists, stale | missing |
| DC7 | mkdocs/sphinx | `ls mkdocs.yml` or `docs/conf.py` | configured | — | missing |

### Metrics: Accuracy (Cross-Reference)

| # | Check | How to Measure | Pass | Warn | Fail |
|---|-------|---------------|------|------|------|
| DA1 | **CLI docs vs actual** | `automedia --help` vs `docs/user/cli-reference.md` — every command must match | 100% match | names match, desc differ | stale commands |
| DA2 | **AGENTS.md layout current** | Cross-ref directory listing vs actual `src/automedia/` | 100% match | minor path errors | stale sections |
| DA3 | **Code snippets in docs** | Extract ``` blocks from markdown, run `python -c` on each | all run | 1–2 fail | >2 fail |
| DA4 | **README example API** | Extract `from automedia import` or `run_full_pipeline(` from README, verify | works | minor diff | broken |
| DA5 | **TODO/FIXME count** | `grep -rn "TODO\|FIXME\|HACK\|XXX" src/automedia/ --include="*.py" \| grep -v test \| wc -l` | ≤5 | 6–20 | >20 |

### Problem Discovery

| Condition | Severity | Why |
|-----------|----------|-----|
| CLI doc has stale commands | `🔴P0` | Agent reads doc, calls nonexistent command |
| AGENTS.md layout is wrong | `🟠P1` | Agent navigates to wrong paths |
| Code snippets fail to run | `🟠P1` | Examples in docs are misleading |
| Docstring density <60% | `🟡P2` | Code is harder to navigate |
| README example API broken | `🔴P0` | First impression is broken code |
| TODO/FIXME >20 | `🟡P2` | Code debt embedded in source |

---

## 7. Robustness

*Detects things that crash in production or silently lose data.*

### Why This Exists

Robustness is what separates "works on my machine" from "works in production."
Bare excepts, no retry, and no validation are the #1 cause of production
incidents that are hard to diagnose.

### Metrics

| # | Check | How to Measure | Pass | Warn | Fail |
|---|-------|---------------|------|------|------|
| RB1 | Bare `except:` count | `grep -rn "^\s*except:" src/ --include="*.py" \| wc -l` minus named types | 0 | 1–3 | >3 |
| RB2 | `except Exception` density | `grep -c "except Exception"` / total except blocks | ≤40% | 40–60% | >60% |
| RB3 | Retry systems (tenacity) | `grep -rn "from tenacity import\|@retry" src/ --include="*.py"` | ≥3 | 1–2 | 0 |
| RB4 | Structured logging | `grep -rn "structlog\|configure_structlog" src/ --include="*.py"` | consistent | partial | missing |
| RB5 | Schema validation | `grep -rn "BaseModel\|@dataclass" src/ --include="*.py" \| grep -v test \| wc -l` | ≥20 | 10–19 | <10 |
| RB6 | Exception hierarchy | `grep -rn "class.*Exception\|class.*Error" src/ --include="*.py" \| grep -v test` | ≥5 types | 2–4 | <2 |
| RB7 | Timeout on externals | `grep -rn "timeout" src/ --include="*.py" \| grep -v test` | consistent | partial | missing |
| RB8 | Input validation at all boundaries | CLI (typer), MCP params, API inputs | all | most | few |

### Problem Discovery

| Condition | Severity | Why |
|-----------|----------|-----|
| Bare `except:` >0 | `🟠P1` | Silently swallows errors, nearly impossible to debug |
| No structured logging | `🔴P0` | Production incidents are blind |
| No retry on network calls | `🟠P1` | Transient failures crash the pipeline |
| `except Exception` >60% | `🟡P2` | Too broad, masks bugs |
| No schema validation | `🟠P1` | Bad data propagates silently |

---

## 8. Design

*Detects things that make the codebase hard to change.*

### Why This Exists

Design quality determines how fast you can ship changes. A codebase with clean
abstractions, no circular imports, and consistent patterns can be modified
quickly and safely. A tangled codebase slows every change to a crawl.

### Metrics

| # | Check | How to Measure | Pass | Warn | Fail |
|---|-------|---------------|------|------|------|
| DS1 | Module count | `find src/automedia -name "*.py" \| wc -l` | 20–60 | 61–100 or 10–19 | >100 or <10 |
| DS2 | ABC/Protocol usage | `grep -rn "ABC\|abstractmethod\|Protocol" src/ --include="*.py" \| grep -v test` | ≥5 | 2–4 | 0–1 |
| DS3 | Circular imports | `python -c "from automedia import run_full_pipeline"` | 0 | — | >0 |
| DS4 | Config layers | Manual inspection | ≥4 | 2–3 | 0–1 |
| DS5 | Direct dependencies | Check `[project.dependencies]` in pyproject.toml | ≤20 | 21–30 | >30 |
| DS6 | Pydantic/dataclass count | `grep -rn "BaseModel\|@dataclass" src/ --include="*.py" \| grep -v test \| wc -l` | ≥20 | 10–19 | <10 |
| DS7 | Dead code | `vulture src/ --min-confidence 80` | ≤10 items | 11–30 | >30 |
| DS8 | Public API discipline | `__all__` pattern consistent across packages | consistent | mixed | none |

### Problem Discovery

| Condition | Severity | Why |
|-----------|----------|-----|
| Circular imports >0 | `🔴P0` | Import-time crashes, hard to fix |
| <2 config layers | `🟠P1` | Inflexible deployment, can't override per environment |
| Dead code >30 items | `🟡P2` | Maintenance burden, confusion |
| No ABC/Protocol use | `🟡P2` | Hard to extend, no interface contracts |
| Dependencies >30 | `🟡P2` | Supply chain risk, slow CI |

---

## 9. End-to-End Integration

*Detects things that make the system not actually work, even though all
unit tests pass.*

### Why This Exists

This is the **single biggest blind spot** of any static evaluation. A project
can have 100% coverage, perfect types, zero lint errors, and beautiful
documentation — and still crash on `automedia run --mode auto` because the
gate ordering in config doesn't match the runner, or the MCP tool serializes
a response differently than the client expects.

Unit tests test components. This dimension tests **the system**.

### Metrics

| # | Check | How to Measure | Pass | Warn | Fail |
|---|-------|---------------|------|------|------|
| E1 | **CLI: `automedia doctor` works** | Run command, check exit code 0 | exit 0 | warnings | crash |
| E2 | **CLI: `automedia --help` shows all commands** | `automedia --help \| grep -c "^ "` vs registered count | match | 1–2 missing | >2 missing |
| E3 | **MCP: server starts** | `timeout 5 python -m automedia.mcp.server 2>&1` | starts clean | warnings | crash |
| E4 | **MCP: `health_check` responds** | Via MCP client or stdio test | valid response | slow response | timeout |
| E5 | **SDK: `from automedia import run_full_pipeline`** | `python -c "from automedia import run_full_pipeline; print('OK')"` | imports clean | warnings | ImportError |
| E6 | **Pipeline: `text_only` mode runs (mock)** | `automedia run --mode text_only --topic "test" --brand test` with mock LLM | completes | partial | fails |
| E7 | **Pipeline: resume_from works** | `automedia run --resume-from V3 --topic "test" --brand test` | resumes | skips gates | crash |
| E8 | **MCP: `get_pipeline_progress` works** | Check tool returns valid progress shape | valid schema | missing fields | broken |

### Problem Discovery

| Condition | Severity | Why |
|-----------|----------|-----|
| Any CLI command crashes | `🔴P0` | Users can't run the tool |
| MCP server won't start | `🔴P0` | All MCP integrations broken |
| SDK import fails | `🔴P0` | Python API completely broken |
| Pipeline text_only fails | `🔴P0` | Core feature doesn't work |
| MCP health check fails | `🟠P1` | Can't verify server is alive |
| resume_from doesn't work | `🟠P1` | Long pipelines can't recover from failure |

### What Makes This Different From Unit Tests

Unit tests verify that `GateEngine.run_gate()` returns the right type. E2E tests
verify that `automedia run --mode text_only` actually produces a valid `.md`
file in the output directory. These are different things.

---

## 10. Security

*Detects things that make the system exploitable.*

### Why This Exists

Security touches every layer — dependencies (CVEs), infrastructure (MCP path
allowlist, systemd hardening), data (credential encryption), and application
(prompt injection, input validation). A single dimension dedicated to security
ensures these risks aren't scattered across other dimensions where they might
be missed.

### Metrics

| # | Check | How to Measure | Pass | Warn | Fail |
|---|-------|---------------|------|------|------|
| S1 | **Dependency audit** | `pip-audit --fail-on CRITICAL 2>&1 \| tail -5` | 0 critical | 1 | >1 |
| S2 | **Safety check** | `safety check 2>&1 \| tail -10` (if configured) | 0 vulns | 1–3 | >3 |
| S3 | **MCP path allowlist locked** | `mcp_allowlist.yaml` restricts to minimal paths | locked | too broad | missing |
| S4 | **No secrets in code** | `grep -rn "api_key\|password\|secret\|token" src/automedia/ --include="*.py" \| grep -v test \| grep -v ".pyc" \| grep -v "AUTOMEDIA_\|os.getenv\|\.env"` | 0 false positives | 1–2 | >2 |
| S5 | **Credential encryption** | Check accounts/store.py for AES/SHA-256 | encrypted | plaintext with obfuscation | plaintext |
| S6 | **Systemd NoNewPrivileges** | Already checked in PR5, but re-verify | set | — | missing |
| S7 | **Logs don't contain secrets** | `grep -rn "credentials\|password\|token\|secret" src/automedia/ --include="*.py" \| grep -i log` | 0 matches | 1 | >1 |
| S8 | **Git secrets prevented** | `.gitignore` covers `.env`, `*credentials*`, `*.key`, `*.pem`, `*.token` | all covered | partial | none |

### Problem Discovery

| Condition | Severity | Why |
|-----------|----------|-----|
| Critical CVE in dependency | `🔴P0` | Exploitable vulnerability in production |
| Secrets in source code | `🔴P0` | Credentials will be committed to git |
| MCP allowlist too broad | `🟠P1` | Path traversal or unauthorized file access |
| Credentials stored in plaintext | `🔴P0` | Encryption is the minimum for credential storage |
| Logs contain secrets | `🟠P1` | Credentials leaked to log aggregators |
| Gitignore missing secret patterns | `🟡P2` | Accidental commit risk |

### Security-Specific Data Collection

```bash
# Dependency audit
pip-audit --fail-on CRITICAL 2>&1 | tail -10

# Secret scanning (source code)
grep -rn "api_key\|password\|secret\|token" src/automedia/ --include="*.py" | \
  grep -v test | grep -v ".pyc" | grep -v "AUTOMEDIA_\|os.getenv\|\.env\|mock"

# Git secrets check
grep -E "\.env$|\*credentials\*|\*\.key$|\*\.pem$|\*\.token$" .gitignore

# MCP path boundary test
python -c "
from automedia.mcp.allowlist import check_path_allowed
# Should fail
try:
    check_path_allowed('/etc/passwd')
    print('FAIL: /etc/passwd should be rejected')
except PermissionError:
    print('PASS: /etc/passwd correctly rejected')
"
```

---

## 11. Performance & Cost

*Detects things that make the system too expensive, slow, or resource-hungry
to run in production.*

### Why This Exists

For a media pipeline that calls LLM APIs and renders video, performance and cost
are not optional — they determine whether the system is usable at all. A pipeline
that costs $5/run and takes 15 minutes will not be used. This dimension catches
regressions in cost, speed, and resource usage before they become habits.

### Metrics

| # | Check | How to Measure | Pass | Warn | Fail |
|---|-------|---------------|------|------|------|
| PC1 | **LLM token cost per run** | Track via logger or estimate from prompt sizes | <$1 | $1–$3 | >$3 |
| PC2 | **Pipeline wall-clock time** | Time a full `text_only` run | <2 min | 2–5 min | >5 min |
| PC3 | **Video synthesis memory** | Run with `ulimit -v` or monitor RSS | <2GB | 2–4GB | >4GB |
| PC4 | **Video render time** | Time a video-only run for 3-slide input | <3 min | 3–8 min | >8 min |
| PC5 | **Disk usage per project** | `du -sh projects/<id>/` | <100MB | 100–500MB | >500MB |
| PC6 | **No disk cleanup mechanism** | Check for archive or cleanup commands | archiver exists | manual cleanup | none |
| PC7 | **LLM token trend** | Compare current vs baseline token count per gate | same or less | +10–25% | >+25% |
| PC8 | **Unbounded loops in gates** | `grep -rn "while True\|for.*in.*range(1000000)" src/automedia/ --include="*.py" \| grep -v test` | 0 | 1 with guard | 1 no guard |

### Problem Discovery

| Condition | Severity | Why |
|-----------|----------|-----|
| Cost >$3/run | `🟠P1` | Economically unsustainable at scale |
| No archive/cleanup | `🟡P2` | Disk will fill up, no recovery path |
| Memory >4GB | `🟠P1` | Won't run on small VMs or edge devices |
| Token usage +25% from baseline | `🟡P2` | Bloat creeping in, find the per-gate regression |
| Unbounded loop | `🔴P0` | Will hang production indefinitely |

### Performance-Specific Data Collection

```bash
# Disk usage
du -sh output/ projects/ 2>/dev/null

# LLM token trend
grep -rn "total_tokens\|prompt_tokens\|completion_tokens" .omo/evaluation-trend.csv 2>/dev/null

# Check for unbounded loops
grep -rn "while True\|while 1\|while True:" src/automedia/ --include="*.py" | grep -v test | grep -v "_test\|test_"

# Pipeline timing (synthetic run)
time automedia run --mode text_only --topic "test timing" --brand test-bench 2>&1 | tail -5
```

---

## 12. Data Collection Protocol

### Full Automated Collection

Run everything from project root. Output to `.omo/evaluation-data-{date}.json`.

```bash
#!/usr/bin/env bash
# AutoMedia Evaluation Data Collector
# Run from project root: bash scripts/evaluate.sh

set -e
DATE=$(date +%Y-%m-%d)
OUT=".omo/evaluation-data-${DATE}.json"

echo "{" > "$OUT"
echo '  "evaluated_at": "'"$DATE"'",' >> "$OUT"
echo '  "data": {' >> "$OUT"

# === AR: AGENT READINESS ===
echo '    "agent_readiness": {' >> "$OUT"

echo "      \"type_ignore_count\": $(grep -rn 'type:.*ignore' src/automedia/ --include='*.py' 2>/dev/null | wc -l)," >> "$OUT"

echo "      \"pre_commit_exists\": $(ls .pre-commit-config.yaml 2>/dev/null && echo 'true' || echo 'false')," >> "$OUT"

ALL_ALL=$(grep -rn '^__all__' src/automedia/*/__init__.py 2>/dev/null | wc -l)
echo "      \"packages_with_all\": $ALL_ALL," >> "$OUT"

ANNOTATED=$(grep -c 'def.*->' src/automedia/ --include='*.py' 2>/dev/null || echo 0)
echo "      \"return_annotated_functions\": $ANNOTATED," >> "$OUT"

echo '      "test_collect_status": "'"$(pytest --collect-only --quiet 2>&1 | tail -1 | head -c 200)"'",' >> "$OUT"

TEST_RESULT=$(pytest --tb=short -q 2>&1 | tail -3)
echo "      \"test_result\": \"${TEST_RESULT//\"/\\\"}\"," >> "$OUT"

COVERAGE=$(coverage report --skip-covered --skip-empty 2>&1 | tail -3)
echo "      \"coverage\": \"${COVERAGE//\"/\\\"}\"" >> "$OUT"

echo '    },' >> "$OUT"

# === PR: PRODUCTION READINESS + OBSERVABILITY ===
echo '    "production_readiness": {' >> "$OUT"

echo "      \"dockerfile\": $(ls Dockerfile 2>/dev/null && echo 'true' || echo 'false')," >> "$OUT"
echo "      \"healthcheck\": $(grep -q HEALTHCHECK Dockerfile 2>/dev/null && echo 'true' || echo 'false')," >> "$OUT"
echo "      \"docker_compose\": $(ls docker-compose.yml 2>/dev/null && echo 'true' || echo 'false')," >> "$OUT"
echo "      \"systemd_services\": $(ls deploy/systemd/*.service 2>/dev/null | wc -l)," >> "$OUT"
echo "      \"ci_workflows\": $(ls .github/workflows/*.yml 2>/dev/null | wc -l)," >> "$OUT"
echo "      \"env_example_lines\": $(wc -l < .env.example 2>/dev/null || echo 0)," >> "$OUT"
echo "      \"doctor_exists\": $(automedia doctor --help >/dev/null 2>&1 && echo 'true' || echo 'false')," >> "$OUT"
echo "      \"logrotate_exists\": $(ls deploy/logrotate/ 2>/dev/null | wc -l)," >> "$OUT"
echo "      \"correlation_id_used\": $(grep -rn 'correlation_id\|request_id\|trace_id' src/automedia/ --include='*.py' 2>/dev/null | wc -l)," >> "$OUT"
echo "      \"resume_from_implemented\": $(grep -rn 'resume_from' src/automedia/pipelines/ --include='*.py' 2>/dev/null | wc -l)" >> "$OUT"

echo '    },' >> "$OUT"

# === DC + DA: DOCUMENTATION ===
echo '    "documentation": {' >> "$OUT"

echo "      \"readme_lines\": $(wc -l < README.md 2>/dev/null || echo 0)," >> "$OUT"
echo "      \"doc_files\": $(ls docs/user/*.md docs/dev/*.md 2>/dev/null | wc -l)," >> "$OUT"
echo "      \"runbook_files\": $(ls docs/dev/gate-failure-modes.md docs/dev/cron-troubleshooting.md docs/dev/api-gotchas.md 2>/dev/null | wc -l)," >> "$OUT"
echo "      \"contributing_exists\": $(ls CONTRIBUTING* 2>/dev/null && echo 'true' || echo 'false')," >> "$OUT"
echo "      \"changelog_active\": $(grep -q 'Unreleased' CHANGELOG.md 2>/dev/null && echo 'true' || echo 'false')," >> "$OUT"
echo "      \"todo_fixme_count\": $(grep -rn 'TODO\|FIXME\|HACK\|XXX' src/automedia/ --include='*.py' 2>/dev/null | grep -v test | grep -v '.pyc' | wc -l)," >> "$OUT"

CLI_MISMATCH=$(comm -3 <(automedia --help 2>/dev/null | grep -oP '(?<=^  )[a-z][a-z-]+' | sort) <(grep -oP '(?<=\| )automedia [a-z][a-z-]+' docs/user/cli-reference.md 2>/dev/null | sed 's/automedia //' | sort) 2>/dev/null | wc -l)
echo "      \"cli_doc_mismatches\": $CLI_MISMATCH" >> "$OUT"

echo '    },' >> "$OUT"

# === RB: ROBUSTNESS ===
echo '    "robustness": {' >> "$OUT"

BARE_EXCEPT=$(grep -rn '^\s*except:' src/automedia/ --include='*.py' 2>/dev/null | grep -v 'Exception\|ValueError\|TypeError\|KeyError\|OSError\|ImportError\|FileNotFoundError\|RuntimeError\|PermissionError\|NotImplementedError\|LookupError\|ConnectionError\|TimeoutError' | wc -l)
echo "      \"bare_except_count\": $BARE_EXCEPT," >> "$OUT"

EXCEPT_EXCEPTION=$(grep -rn 'except Exception' src/automedia/ --include='*.py' 2>/dev/null | wc -l)
echo "      \"except_exception_count\": $EXCEPT_EXCEPTION," >> "$OUT"

RETRY=$(grep -rn '@retry\|from tenacity' src/automedia/ --include='*.py' 2>/dev/null | wc -l)
echo "      \"retry_systems\": $RETRY," >> "$OUT"

PYDANTIC=$(grep -rn 'BaseModel\|@dataclass' src/automedia/ --include='*.py' 2>/dev/null | grep -v test | wc -l)
echo "      \"pydantic_dataclass_count\": $PYDANTIC," >> "$OUT"

echo "      \"structlog_enabled\": $(grep -q 'structlog\|configure_structlog' src/automedia/core/logging.py 2>/dev/null && echo 'true' || echo 'false')" >> "$OUT"

echo '    },' >> "$OUT"

# === DS: DESIGN ===
echo '    "design": {' >> "$OUT"

echo "      \"module_count\": $(find src/automedia -name '*.py' 2>/dev/null | wc -l)," >> "$OUT"
echo "      \"package_count\": $(find src/automedia -type d 2>/dev/null | wc -l)," >> "$OUT"
echo "      \"total_loc\": $(find src/automedia -name '*.py' 2>/dev/null | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}')," >> "$OUT"
echo "      \"abc_protocol_count\": $(grep -rn 'ABC\|abstractmethod\|Protocol' src/automedia/ --include='*.py' 2>/dev/null | grep -v test | wc -l)," >> "$OUT"
echo "      \"dead_code_items\": $(vulture src/automedia/ --min-confidence 80 2>/dev/null | wc -l)" >> "$OUT"

echo '    },' >> "$OUT"

# === E2E: END-TO-END INTEGRATION ===
echo '    "e2e_integration": {' >> "$OUT"

timeout 5 python -m automedia.mcp.server 2>&1 &
MCP_PID=$!
sleep 1
MCP_OK=$(kill -0 $MCP_PID 2>/dev/null && echo 'true' || echo 'false')
kill $MCP_PID 2>/dev/null
echo "      \"mcp_server_starts\": $MCP_OK," >> "$OUT"

SDK_OK=$(python -c 'from automedia import run_full_pipeline; print("OK")' 2>&1)
echo "      \"sdk_imports\": \"${SDK_OK//\"/\\\"}\"," >> "$OUT"

CLI_OK=$(automedia doctor 2>&1 | head -3)
echo "      \"cli_doctor\": \"${CLI_OK//\"/\\\"}\"" >> "$OUT"

echo '    },' >> "$OUT"

# === SECURITY ===
echo '    "security": {' >> "$OUT"

PIP_AUDIT=$(pip-audit --fail-on CRITICAL 2>&1 | tail -3)
echo "      \"pip_audit\": \"${PIP_AUDIT//\"/\\\"}\"," >> "$OUT"

SECRETS_IN_CODE=$(grep -rn 'api_key\|password\|secret\|token' src/automedia/ --include='*.py' 2>/dev/null | grep -v test | grep -v '.pyc' | grep -v 'AUTOMEDIA_\|os.getenv\|\.env\|mock\|PlaceholderToken' | wc -l)
echo "      \"secrets_in_code\": $SECRETS_IN_CODE," >> "$OUT"

MCP_ALLOWLIST=$(wc -l < src/automedia/mcp/mcp_allowlist.yaml 2>/dev/null || echo 0)
echo "      \"mcp_allowlist_entries\": $MCP_ALLOWLIST" >> "$OUT"

echo '    },' >> "$OUT"

# === PC: PERFORMANCE & COST ===
echo '    "performance_cost": {' >> "$OUT"

echo "      \"disk_usage_output_mb\": $(du -sm output/ 2>/dev/null | cut -f1 || echo 0)," >> "$OUT"
echo "      \"archive_mechanism\": $(grep -rn 'archive\|cleanup' src/automedia/cli/commands/ --include='*.py' 2>/dev/null | grep -v test | wc -l)," >> "$OUT"
echo "      \"unbounded_loops\": $(grep -rn 'while True\|while 1' src/automedia/ --include='*.py' 2>/dev/null | grep -v test | grep -v '.pyc' | grep -v 'while True:' | wc -l)" >> "$OUT"

echo '    }' >> "$OUT"

echo '  }' >> "$OUT"
echo '}' >> "$OUT"

echo "Done. Wrote $OUT"
```

### Semi-Automated Checks

```bash
# Dead code check
vulture src/ --min-confidence 80 2>/dev/null || echo "vulture not installed"

# Circular import check
python -c "
import sys
try:
    from automedia import run_full_pipeline
    print('OK: import successful')
except Exception as e:
    print(f'IMPORT ERROR (possible circular): {e}')
    sys.exit(1)
"

# Code snippet validation
python -c "
import re, sys, subprocess
with open('README.md') as f:
    content = f.read()
# Extract python code blocks
blocks = re.findall(r'```python\n(.*?)```', content, re.DOTALL)
failures = 0
for i, block in enumerate(blocks):
    # Skip blocks with shell commands or placeholders
    if '...' in block or 'sk-' in block:
        continue
    try:
        compile(block, f'<readme-block-{i}>', 'exec')
    except SyntaxError as e:
        print(f'BLOCK {i} SYNTAX ERROR: {e}')
        failures += 1
print(f'Code blocks: {len(blocks)}, syntax failures: {failures}')
sys.exit(1 if failures > 0 else 0)
"

# MCP path boundary test
python -c "
try:
    from automedia.mcp.allowlist import check_path_allowed
    # Should be rejected
    try:
        check_path_allowed('/etc/passwd')
        print('WARN: /etc/passwd not rejected')
    except PermissionError:
        print('PASS: /etc/passwd rejected')
    # Should be rejected
    try:
        check_path_allowed('../../../etc/shadow')
        print('WARN: path traversal not rejected')
    except (PermissionError, ValueError):
        print('PASS: path traversal rejected')
except ImportError:
    print('SKIP: allowlist module not available')
"

# Pipeline E2E test (synthetic)
automedia run --mode text_only --topic "E2E test topic" --brand e2e-test-bench 2>&1 | tail -5
```

### Manual Checks

These need human judgment:

- **README quality** — TOC? Install instructions? Quick start? Architecture diagram?
- **AGENTS.md accuracy** — Every directory path listed matches real code?
- **CLI docs vs reality** — Run `automedia --help` and tick each command against `docs/user/cli-reference.md`
- **Error consistency** — Trigger 3 MCP errors, check response dict has same shape
- **Logging quality** — `logger.error` vs `logger.warning` — are levels used correctly?
- **Config layer test** — Override at each of 6 layers, verify merge order
- **Doc examples run** — Copy 3 doc code snippets into `python -c` and run

---

## 13. Evidence Requirements

Every issue in the evaluation **must** be backed by evidence. No speculation.

### Evidence Types

| Type | How to Produce | Example |
|------|---------------|---------|
| Raw command output | Run the command, capture stdout | `grep` output showing 3 `type:ignore` |
| File:line reference | `grep -rn` with file paths | `src/automedia/gates/base.py:120` |
| Error reproduction | Sequence of commands to trigger failure | `pytest test_gates/X.py -v` shows assertion error |
| Summary statistic | Counts or percentages | `82 except Exception blocks (44%)` |
| Runtime observation | `time`, `du`, `ps` output during run | `Pipeline completed in 47s, 1.2GB RSS` |

### Acceptable Estimates

If a tool is not available, a rough estimate is acceptable but **must be
marked as `⚠️ estimated`**:

```
Docstring coverage: ~68.9% (⚠️ estimated — docstring line count vs
function count, not a proper interrogate run)
```

### Blocking Conditions (STOP and Fix First)

The evaluation **must stop** immediately if any of these are true. Fix the
blocker before continuing.

1. **`pytest --collect-only` fails** — test infrastructure is broken
2. **`python -c "from automedia import run_full_pipeline"` fails** — import system is broken
3. **`.env.example` is missing** — can't configure the project
4. **`git status` shows uncommitted changes** — evaluation would be inaccurate
5. **`automedia --help` crashes** — CLI is completely broken
6. **`pip-audit --fail-on CRITICAL` finds critical CVEs** — exploitable in production

---

## 14. Baseline & Trend Tracking

### Baseline Registration

Store the first evaluation at `.omo/evaluation-baseline.json`. Each subsequent
evaluation compares against it:

```text
issue_delta = current_total_issues - baseline_total_issues
p0_delta = current_p0_count - baseline_p0_count
```

### Delta Interpretation

| Signal | Meaning | Action |
|--------|---------|--------|
| **issue_delta < 0, p0_delta = 0** | Fixing effectively | ✅ Continue |
| **issue_delta < 0, p0_delta < 0** | P0 blockers being eliminated | ✅ High priority fixes working |
| **issue_delta > 0** | Regressions > fixes | ⚠️ Investigate what regressed |
| **p0_delta > 0** | New blockers introduced | 🛑 Stop, fix new P0s |

### Trend Tracking

`.omo/evaluation-trend.csv`:

```csv
date,dimension,issue_count,p0_count,p1_count,score
2026-07-07,agent_readiness,7,2,1,8.2
2026-07-14,agent_readiness,3,0,1,8.5
```

### When to Re-Evaluate

| Trigger | Scope | Output |
|---------|-------|--------|
| After any major feature merge | All 8 dimensions | Trend update + new issues |
| Before production release | All 8 + strict P0 check | Go/no-go |
| After CI pipeline changes | Production Readiness + Security | CI section diff |
| After large refactoring | Design + Robustness + E2E | Architecture diff |
| After LLM provider change | Performance & Cost | Token usage diff |
| **On agent confusion** | Documentation | Doc accuracy audit |
| Quarterly | All 8 + trend analysis | Improvement roadmap |

### Exit Criteria (When to Ship)

The evaluate-fix loop is complete when **all** conditions are met:

1. **0 🔴P0 issues across all 8 dimensions** — no blockers
2. **No dimension has a P1 count > 3** — manageable risk
3. **E2E Integration dimension has 0 P0/P1 issues** — system works
4. **Security dimension has 0 P0/P1 issues** — no exploitable vulnerabilities
5. **Trend is negative for 2 consecutive evaluations** — issues consistently decreasing
6. **The issue list has plateaued** — 3 evaluations surface no new P0/P1 issues

At this point: **ship**. The next evaluation is triggered by production usage
data and real-world incidents.
