# AutoMedia Master Validation Plan

## Result-Oriented · User-Centric · All Scenarios & Boundaries

**For:** OpenCode, Claude Code, Codex CLI, Hermes Agent — any AI agent validating AutoMedia
**Date:** 2026-07-17
**Strategy:** Every section asks a user question → executes scenarios → reports a binary verdict
**Current Baseline:** evaluation-matrix.md 7.9/10 composite, ~2,955 tests (1 pre-existing failure)

---

## How to Use This Plan

```yaml
1. Pick a USER QUESTION from the table of contents
2. Read the scenarios under it
3. Execute each scenario (CLI, MCP, or Python)
4. Record the ACTUAL RESULT
5. Compare ACTUAL vs EXPECTED
6. Report the VERDICT at the end of the section
```

The plan is designed so that any AI agent can execute it independently and report: **"✅ All PASS"** or **"❌ These N items FAILED"**.

---

## Verdict Legend

| Symbol | Meaning |
|--------|---------|
| ✅ PASS | All scenarios in this section match expected results |
| ❌ FAIL | One or more scenarios did NOT match expected results |
| ⚠️ PARTIAL | Some scenarios pass, some fail (list which ones) |
| ➖ SKIP | Scenarios intentionally skipped (reason documented) |

---

## Prerequisites

Before running validation, ensure:

```bash
# 1. Install the package with dev dependencies
pip install -e ".[dev]"

# 2. Verify test infrastructure
pytest --collect-only -q  # Should collect without errors

# 3. Set minimum env vars
export AUTOMEDIA_LLM_API_KEY="sk-dummy-for-testing"
export AUTOMEDIA_DATA_DIR="/tmp/automedia-test"
export AUTOMEDIA_OUTPUT_DIR="/tmp/automedia-test/output"
export AUTOMEDIA_PROJECTS_DIR="/tmp/automedia-test/projects"

# 4. Set fake modes for deterministic testing
export AUTOMEDIA_FAKE_LLM=1       # Use deterministic LLM responses
export AUTOMEDIA_FAKE_VIDEO=1     # Skip real video rendering
export AUTOMEDIA_FAKE_TTS=1       # Skip real TTS audio generation
```

---

## Table of Contents

### Part 1: Core Pipeline Journeys
- **Q1:** Can I run a full `auto` pipeline end-to-end?
- **Q2:** Can I run `text_only`, `video_only`, `qa_only` modes (plus new `repurpose` mode)?
- **Q3:** Can I run batch pipeline for multiple topics?
- **Q4:** Can I resume a pipeline from a specific gate?
- **Q5:** Can I skip/pause/resume/cancel a running pipeline?
- **Q5b:** Does content distribution via D-gates work? (`automedia distribute` CLI + `distribute_content` MCP)

### Part 2: MCP & CLI Surface Mastery
- **Q6:** Does every MCP tool work correctly? (52 tools + 13 error codes)
- **Q7:** Does every CLI command work correctly? (16 commands)
- **Q8:** Are CLI and MCP outputs equivalent for overlapping functionality?

### Part 3: Gate System Validation
- **Q9:** Does each gate pass/fail correctly?
- **Q10:** Do failure modes work correctly (stop/retry)?
- **Q11:** Does human-in-the-loop (HITL) integration work?
- **Q11B:** Do gate modifier YAML overrides work correctly?

### Part 4: Error & Boundary Matrix
- **Q12:** What happens with missing/corrupt/empty inputs?
- **Q13:** What happens at security boundaries (path traversal, allowlist)?
- **Q14:** What happens with concurrent/parallel calls?
- **Q15:** What happens with configuration edge cases?

### Part 5: Production Trust
- **Q16:** Is the pipeline deterministic? (FAKE_LLM mode)
- **Q17:** Are hooks readonly and correctly dispatched?
- **Q18:** Are MD5 checksums recorded and verifiable?
- **Q19:** Are production metrics recorded correctly?

### Part 6: Account & Credential Management
- **Q20:** Can I connect/list/health/disconnect accounts?
- **Q21:** Are credentials encrypted at rest correctly?
- **Q22:** Does OAuth2 flow work?
- **Q23:** Does SessionManager handle TTL and rate limits?

### Part 7: HITL Framework
- **Q24:** Can I configure HITL presets?
- **Q25:** Does NodeExecutor route correctly (agent vs human)?
- **Q26:** Can humans approve/skip nodes correctly?

### Part 8: Decision Layer
- **Q27:** Does DecisionOrchestrator produce valid artifacts?
- **Q28:** Does force-provenance audit logging work?
- **Q29:** Does schema validation work for decision artifacts?

### Part 9: Pipeline Infrastructure & Resilience
- **Q30:** Does GateEngine retry logic work correctly?
- **Q31:** Can the system recover after partial failure?
- **Q32:** Are the 6-layer config merge and env var mapping correct?
- **Q33:** Is project lifecycle management correct?
- **Q34:** Are pre-commit hooks working?
- **Q35:** Is CLI help output format stable?

### Part 10: Production Validation (Real LLM · Real Deps · Performance)
- **Q36:** Does real LLM produce acceptable quality?
- **Q37:** Do real external tools work (FFmpeg, Whisper, HyperFrames)?
- **Q38:** Does performance meet production thresholds?
- **Q39:** Does multi-provider failover work?
- **Q40:** Does the real MCP server work via stdio process?
- **Q41:** Can the system run continuously without degradation?

### Part 11: Final Verdict
- Overall PASS/FAIL summary
- Production gap checklist
- Sign-off criteria

---

# Part 1: Core Pipeline Journeys

---

## Q1: Can I run a full `auto` pipeline end-to-end?

**User says:** "I have a topic and a brand. I want to run the full production pipeline — topic selection, content writing, gates, and publishing."

**Why this matters:** This is the most common user workflow. If `auto` mode doesn't work end-to-end, nothing else matters.

### Prerequisites
```bash
cd /path/to/AutoMedia && pip install -e ".[dev]"
export AUTOMEDIA_FAKE_LLM=1 AUTOMEDIA_FAKE_VIDEO=1 AUTOMEDIA_FAKE_TTS=1
```

### Scenarios

#### 1.1 🟢 Happy Path — Full `auto` pipeline via CLI
```bash
automedia run --topic "AI Video Tools Comparison 2026" --brand test-brand --mode auto --verbose
```
**Expected Result:**
- ✅ Exit code 0
- ✅ Output shows pipeline started with project_id
- ✅ Pipeline completes with status "success" or "partial"
- ✅ Project directory created under $AUTOMEDIA_PROJECTS_DIR with standard subdirs
- ✅ `00_project_info.json` exists with valid project metadata
- ✅ `pipeline_md5.json` exists with gate checksums

**Actual Result:** _________ **PASS / FAIL:** _________

#### 1.2 🟢 Happy Path — Full `auto` pipeline via SDK
```python
from automedia import run_full_pipeline
result = run_full_pipeline(topic="AI Video Tools Comparison 2026", brand="test-brand", mode="auto")
print(f"Status: {result.status}, Project: {result.project_id}, Duration: {result.total_duration_s}s")
```
**Expected Result:**
- ✅ `result.status` is "success" or "partial"
- ✅ `result.project_id` is a valid 12-char hex string
- ✅ `result.total_duration_s` > 0
- ✅ `result.gates_log` contains entries for all 22 standard gates in auto mode (plus D1-D7 available as standalone distribution gates)
- ✅ Each `GateLogEntry` has `gate_name`, `status`, `duration_s`

**Actual Result:** _________ **PASS / FAIL:** _________

#### 1.3 🟢 Happy Path — Project structure verification
```python
from pathlib import Path; from automedia import run_full_pipeline
result = run_full_pipeline(topic="Auto Pipeline Test", brand="test-brand", mode="text_only")
project_dir = Path(result.project_dir)
assert project_dir.exists()
assert (project_dir / "00_project_info.json").exists()
assert (project_dir / "pipeline_md5.json").exists()
subdirs = [d.name for d in project_dir.iterdir() if d.is_dir()]
assert "01_content" in subdirs
```
**Expected Result:** ✅ Standard directory structure created, project metadata valid.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 1.4 🟢 Pipeline with `resume_from` — no-op when first run
```bash
automedia run --topic "Test Resume" --brand test-brand --mode text_only --resume-from G0
```
**Expected Result:** ✅ Pipeline runs successfully (resume_from ignored on first run, no prior MD5).

**Actual Result:** _________ **PASS / FAIL:** _________

#### 1.5 🔴 Pipeline with empty topic
```bash
automedia run --topic "" --brand test-brand --mode text_only
```
**Expected Result:** ❌ Exit code != 0. Error message mentions "topic" is required or empty.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 1.6 🔴 Pipeline with empty brand
```bash
automedia run --topic "Test" --brand "" --mode text_only
```
**Expected Result:** ❌ Exit code != 0. Error message mentions "brand" is required.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 1.7 🔴 Pipeline with invalid mode
```bash
automedia run --topic "Test" --brand test-brand --mode invalid_mode
```
**Expected Result:** ❌ Exit code != 0. Error mentions invalid mode, lists valid modes.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 1.8 🔴 Pipeline with invalid `resume_from` gate name
```bash
automedia run --topic "Test" --brand test-brand --mode text_only --resume-from NONEXISTENT_GATE
```
**Expected Result:** ❌ Pipeline may fail or skip unknown gate ref. Does NOT crash with unhandled exception.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q1 Verdict

| Scenario | Result |
|----------|--------|
| 1.1 Happy path (CLI, auto) | ⬜ |
| 1.2 Happy path (SDK, auto) | ⬜ |
| 1.3 Project structure | ⬜ |
| 1.4 Resume from (first run) | ⬜ |
| 1.5 Empty topic | ⬜ |
| 1.6 Empty brand | ⬜ |
| 1.7 Invalid mode | ⬜ |
| 1.8 Invalid resume gate | ⬜ |

**OVERALL: ⬜** (✅ if all pass, ❌ if any fail)

---

## Q2: Can I run `text_only`, `video_only`, `qa_only` modes?

**User says:** "Sometimes I only need text content (for WeChat/Zhihu), sometimes only video, sometimes just quality checks."

**Why this matters:** Each mode selects different gates. Mode switching is core feature that must preserve correct gate ordering.

### Scenarios

#### 2.1 🟢 `text_only` mode — only copy gates run
```bash
automedia run --topic "Text Only Test" --brand test-brand --mode text_only --verbose
```
**Expected Result:**
- ✅ Pipeline completes
- ✅ Gates executed: CW, G0, G1, G2, G3, G4, G5, H0, L1, L2, L3, L4 (12 gates)
- ✅ Video gates V0-V7 NOT in gate log
- ✅ `01_content/drafts/` directory has draft content

**Actual Result:** _________ **PASS / FAIL:** _________

#### 2.2 🟢 `video_only` mode — only video gates run
```bash
automedia run --topic "Video Only Test" --brand test-brand --mode video_only --verbose
```
**Expected Result:**
- ✅ Pipeline completes
- ✅ Gates executed: V0-V7, L1-L4 (12 gates)
- ✅ Content gates G0-G6 NOT in gate log
- ✅ `03_video/` assets present

**Actual Result:** _________ **PASS / FAIL:** _________

#### 2.3 🟢 `qa_only` mode — only QA gates run
```bash
automedia run --topic "QA Only Test" --brand test-brand --mode qa_only --verbose
```
**Expected Result:** ✅ Gates: G0, G2, G3, V1, V6 (5 gates). Gate log shows exactly 5 entries.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 2.4 🟢 `image-carousel` mode
```bash
automedia run --topic "Carousel Test" --brand test-brand --mode image-carousel --verbose
```
**Expected Result:** ✅ Gates: CW, G0-G6, L1-L4 (12 gates). Image carousel assets generated in `02_images/`.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 2.5 🟢 `social-thread` mode
```bash
automedia run --topic "Social Thread Test" --brand test-brand --mode social-thread --verbose
```
**Expected Result:** ✅ Gates: CW, G0-G6, L1-L4 (12 gates). Content formatted as social thread.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 2.7 🟢 `repurpose` mode — full pipeline + P-gates
```bash
automedia run --topic "Repurpose Test" --brand test-brand --mode repurpose --verbose
```
**Expected Result:** ✅ Pipeline completes. Gate log includes standard gates + P1-P4 at end. `04_repurpose/` directory created with subdirectories for each platform (wechat, twitter, newsletter, bilibili).

**Actual Result:** _________ **PASS / FAIL:** _________

#### 2.6 🔴 Mode switching — no cross-contamination
```bash
automedia run --topic "No Cross Contam" --brand test-brand --mode text_only
automedia run --topic "No Cross Contam" --brand test-brand --mode video_only
```
**Expected Result:** ✅ Both complete independently. Second run has different project_id. No file locking.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q2 Verdict

| Scenario | Result |
|----------|--------|
| 2.1 text_only mode | ⬜ |
| 2.2 video_only mode | ⬜ |
| 2.3 qa_only mode | ⬜ |
| 2.4 image-carousel mode | ⬜ |
| 2.5 social-thread mode | ⬜ |
| 2.6 No cross-contamination | ⬜ |
| 2.7 repurpose mode | ⬜ |

**OVERALL: ⬜**

---

## Q3: Can I run batch pipeline for multiple topics?

**User says:** "I have 5 articles to produce. I don't want to run them one at a time."

### Scenarios

#### 3.1 🟢 Batch run 3 topics sequentially
```bash
automedia run --topics "Topic A,Topic B,Topic C" --brand test-brand --mode text_only
```
**Expected Result:** ✅ All 3 topics processed. Each has unique project_id. One failure does not stop batch.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 3.2 🟢 Batch with one failing topic — isolation
```bash
automedia run --topics "Good Topic,,Bad Topic (empty)" --brand test-brand --mode text_only
```
**Expected Result:** ⚠️ Empty topic may fail. Non-empty topics still process. No crash from malformed topic.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q3 Verdict | Scenario | Result | |----------|--------| | 3.1 Batch 3 topics | ⬜ | | 3.2 Failure isolation | ⬜ |

**OVERALL: ⬜**

---

## Q4: Can I resume a pipeline from a specific gate?

**User says:** "My pipeline failed at G3. Can I resume from G3 without re-running everything?"

#### 4.1 🟢 Resume from G0 — skips pre-gate and CW
```python
from automedia import run_full_pipeline
r1 = run_full_pipeline(topic="Resume Test", brand="test-brand", mode="text_only")
assert r1.status == "success"
r2 = run_full_pipeline(topic="Resume Test", brand="test-brand", mode="text_only", resume_from="G0")
```
**Expected Result:** ✅ Second run gate log starts from G0 (no pre-gate/CW). Prior MD5 verified. Output valid.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 4.2 🔴 Resume with missing prior MD5 — warning logged
```bash
rm /path/to/project/pipeline_md5.json
automedia run --topic "MD5 Test" --brand test-brand --mode text_only --resume-from G3
```
**Expected Result:** ⚠️ Pipeline may still run best-effort. Warning logged about missing/invalid MD5. No crash.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 4.3 🔴 Resume from gate not in mode's list
```bash
automedia run --topic "Test" --brand test-brand --mode qa_only --resume-from V0
```
**Expected Result:** ❌ V0 not in qa_only gate list. Graceful error/warning. No crash.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q4 Verdict | Scenario | Result | |----------|--------| | 4.1 Resume from G0 | ⬜ | | 4.2 Resume with missing MD5 | ⬜ | | 4.3 Resume from gate not in mode | ⬜ |

**OVERALL: ⬜**

---

## Q5: Can I skip/pause/resume/cancel a running pipeline?

**User says:** "I started a pipeline but I need to skip a gate, pause it, or cancel it."

**Why this matters:** Runtime pipeline control is essential for production operations.

#### 5.1 🟢 Skip a gate during pipeline execution
```python
# Via MCP: skip_gate(project_id="xxx", gate_name="G1")
```
**Expected Result:** ✅ Pipeline skips specified gate. Gate log marks as "skipped". Pipeline continues.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 5.2 🟢 Cancel a running pipeline
```python
# Via MCP: cancel_pipeline(project_id="xxx")
```
**Expected Result:** ✅ Pipeline stops at next gate boundary. `cancelled` flag set. No corrupted output files.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 5.3 🟢 Pause and resume a running pipeline
```python
# Via MCP: pause_pipeline(project_id="xxx") -> {paused: True}
# Via MCP: resume_pipeline(project_id="xxx") -> {resumed: True}
```
**Expected Result:** ✅ Pipeline pauses between gates. Resumes from where paused. No duplicate gate execution.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 5.4 🔴 Cancel non-existent pipeline
```python
# Via MCP: cancel_pipeline(project_id="nonexistent")
```
**Expected Result:** ❌ Returns NOT_FOUND error. Does NOT crash.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q5 Verdict | Scenario | Result | |----------|--------| | 5.1 Skip gate | ⬜ | | 5.2 Cancel pipeline | ⬜ | | 5.3 Pause/resume | ⬜ | | 5.4 Cancel non-existent | ⬜ |

**OVERALL: ⬜**

---

## Q5b: Does content distribution via D-gates work?

**User says:** "I finished my article. Now I want to distribute it to WeChat and Twitter."

**Why this matters:** Distribution gates decouple content production from platform-specific formatting. They must produce correct platform-adapted output.

### 5b.1 🟢 `automedia distribute --dry-run` shows plan
```bash
automedia distribute test-project --platforms wechat,twitter --dry-run
```
**Expected Result:** ✅ Prints "Would run D1 (WeChat), D2 (Twitter/X)" without executing. Exit code 0.

**Actual Result:** _________ **PASS / FAIL:** _________

### 5b.2 🟢 `automedia distribute --all --dry-run` covers all 7 platforms
```bash
automedia distribute test-project --all --dry-run
```
**Expected Result:** ✅ Prints plan for all 7 platforms (wechat, twitter, zhihu, xiaohongshu, bilibili, youtube, tiktok). Exit code 0.

**Actual Result:** _________ **PASS / FAIL:** _________

### 5b.3 🔴 Invalid platform name returns error
```bash
automedia distribute test-project --platforms nonexistent_platform
```
**Expected Result:** ❌ Error message mentions invalid platform, lists valid options. Exit code != 0.

**Actual Result:** _________ **PASS / FAIL:** _________

### 5b.4 🟢 Distribution log tracked in asset_library
```bash
# After successful distribution — check the distribution log
```
**Expected Result:** ✅ `DistributionLog` entries exist in asset library with project_id, platform, timestamp, and status.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q5b Verdict | Scenario | Result | |----------|--------| | 5b.1 Dry-run with platforms | ⬜ | | 5b.2 Dry-run with --all | ⬜ | | 5b.3 Invalid platform | ⬜ | | 5b.4 Distribution log | ⬜ |

**OVERALL: ⬜**

---

# Part 2: MCP & CLI Surface Mastery

---

## Q6: Does every MCP tool work correctly? (52 tools + 13 error codes)

**User says:** "I'm connecting via MCP protocol. I need all 52 tools to work as documented."

**Why this matters:** MCP is the primary integration surface for AI agents. Broken tools break automation.

### 6.1 🟢 Health check + onboarding tools (4 tools)
```python
from automedia.mcp.server import create_server; import json
server = create_server()
# health_check — now includes first_run and version
r = json.loads(server.call_tool("health_check", {}).content[0].text)
assert r["status"] == "healthy" and r["version"] != "" and r["tools_count"] > 0
assert "first_run" in r  # Boolean: True if no config initialized yet
# engine_health
r = json.loads(server.call_tool("engine_health", {}).content[0].text)
assert "engines" in r and r["healthy_count"] >= 0
# onboard — guided setup for first-time users
r = json.loads(server.call_tool("onboard", {}).content[0].text)
assert "steps" in r and "status" in r
```
**Expected Result:** ✅ All 4 return success with expected fields. `health_check.first_run` reflects real config state. `onboard()` returns structured setup steps.

**Actual Result:** _________ **PASS / FAIL:** _________

### 6.2 🟢 Pipeline tools (9 tools)
| Tool | Args | Expected |
|------|------|----------|
| `run_pipeline` | topic="MCP Test", brand="test-brand", mode="text_only" | `{project_id, status: "started"}` |
| `get_pipeline_progress` | project_id | `{gates_done, gates_remaining, total_gates}` |
| `get_pipeline_status` | project_id, base_dir | `{project: {...}, subdirs: [...]}` |
| `cancel_pipeline` | project_id | `{cancelled: True}` |
| `pause_pipeline` | project_id | `{paused: True}` |
| `resume_pipeline` | paused project_id | `{resumed: True}` |
| `retry_gate` | project_id, gate_name | `{retrying: True}` |
| `skip_gate` | project_id, gate_name | `{skipping: True}` |
| `list_active_pipelines` | no args | `{pipelines: [...], count}` |

**Expected Result:** ✅ All 9 return success. Error tools on non-existent project return NOT_FOUND. Invalid mode returns INVALID_PARAM. `list_active_pipelines` returns running/paused/lost pipelines read from `~/.automedia/active_pipelines.json`.

**Actual Result:** _________ **PASS / FAIL:** _________

### 6.3 🟢 Project tools (5 tools)
| Tool | Args | Expected |
|------|------|----------|
| `list_projects` | base_dir=".", status="" | `{projects: [...], count}` |
| `get_project_assets` | project_dir | `{assets: [...], count}` |
| `archive_project` | published project_id | `{archived: True}` |
| `publish_content` | project_id, platform | `{published, platform, url}` |
| `batch_run` | topics=[], brand, mode | `{results: [...], total, passed, failed}` |

**Expected Result:** ✅ All 5 return success. archive_project on non-published returns INVALID_PARAM (Red Line 8).

**Actual Result:** _________ **PASS / FAIL:** _________

### 6.4 🟢 Topic pool tools (3 tools)
| Tool | Args | Expected |
|------|------|----------|
| `pool_add_topic` | title="Test", category="tech" | `{id, title, status: "pending"}` |
| `list_topic_pool` | status="pending", category="tech" | `{topics: [...], count}` |
| `select_topic` | category="tech" | `{selected: {...}}` or `{selected: null}` |

**Expected Result:** ✅ All 3 return success. Empty title returns INVALID_PARAM. No pending topics returns `selected: null`.

**Actual Result:** _________ **PASS / FAIL:** _________

### 6.5 🟢 Research/Strategy tools (3 tools)
| Tool | Args | Expected Structure |
|------|------|-------------------|
| `research_topics` | category="tech", count=3 | `{topics: [...], total_found}` |
| `run_brand_strategy` | brand_name, industry, target_audience | 5-field strategy object |
| `run_pipeline_from_strategy` | topic, brand, mode, strategy_context | `{strategy: {...}, pipeline_result: {...}}` |

**Expected Result:** ✅ All 3 succeed. In FAKE_LLM mode, return deterministic mock data.

**Actual Result:** _________ **PASS / FAIL:** _________

### 6.6 🟢 Omni Triad tools (4 tools)
| Tool | Args | Expected |
|------|------|----------|
| `extract_brief` | file_path, source_lang, target_lang | `{md_content, manifest_json, warnings}` |
| `localize_content` | md_content, source_lang, target_lang | `{translated_md, xliff_path, warnings}` |
| `localize_output` | project_dir, target_langs | `{results: {lang: [files]}, warnings}` |
| `format_output` | content, target_format | `{output_path, output_format}` |

**Expected Result:** ✅ All 4 succeed. Unsupported format returns INVALID_PARAM. Non-existent file returns UNKNOWN gracefully.

**Actual Result:** _________ **PASS / FAIL:** _________

### 6.7 🟢 Content quality + analytics tools (2 tools)
```python
r = json.loads(server.call_tool("evaluate_content_quality", {
    "content": "# Test\n\nParagraph.", "criteria": "general", "brand": "test-brand",
}).content[0].text)
assert "quality_score" in r and "issues" in r and "suggestions" in r
# analyze_content — compute content analytics stats
r = json.loads(server.call_tool("analyze_content", {
    "project_id": "test-project",
}).content[0].text)
assert "word_count" in r and "sentiment_score" in r and "readability_index" in r
```
**Expected Result:** ✅ `evaluate_content_quality` returns `{quality_score, issues, suggestions, overall_assessment}`. Score is numeric. `analyze_content` returns stats with word_count, sentiment_score, readability_index, brand_mention_frequency, seo_score_aggregation.

**Actual Result:** _________ **PASS / FAIL:** _________

### 6.8 🟢 Brand/Asset/Workflow/Cron/Account/Distribution tools (18 tools)
| Tool | Happy Path | Expected | Error Path | Expected |
|------|-----------|----------|------------|----------|
| `list_brands` | no args | `{brands: [...], total}` | | |
| `search_assets` | query="test", brand="test-brand" | `{results: [...], count}` | | |
| `list_overridable_templates` | no args | `{templates: [...], count}` | | |
| `list_workflows` | no args | `{workflows: [...], count}` | | |
| `add_cron_schedule` | name="test-job", expression="0 * * * *" | `{added: True, name}` | invalid expression | INVALID_PARAM |
| `list_cron_schedules` | no args | `{schedules: [...], count}` | | |
| `remove_cron_schedule` | name="test-job" | `{removed: True, name}` | non-existent | NOT_FOUND |
| `test_cron_schedule` | expression="0 * * * *", count=3 | `{valid, next_triggers}` | invalid expr | INVALID_PARAM |
| `get_cron_health` | no args | `{jobs_valid, schedule_count}` | | |
| `distribute_content` | project_id="test", platforms="wechat,twitter" | `{platforms: {...}, summary}` | invalid platform | INVALID_PARAM |
| `connect_account` | platform="test", auth_type="api_key" | `{success: True, account: {...}}` | empty creds | INVALID_PARAM |
| `list_accounts` | no args | `{accounts: [...], count}` | empty list | ok (not error) |
| `get_account_health` | account_id | `{status, platform, expires_in}` | non-existent | NOT_FOUND |
| `disconnect_account` | account_id | `{success: True, account_id}` | non-existent | NOT_FOUND |
| `approve_gate` | project_id, gate_name | `{approved: True, artifact: {...}}` | non-pending | INVALID_PARAM |
| `reject_gate` | project_id, gate_name | `{rejected: True, reason: "..."}` | non-pending | INVALID_PARAM |
| `get_pending_approvals` | project_id | `{pending: [...], count}` | | |

**Expected Result:** ✅ All 18 tools succeed with expected shapes. Error paths return proper error codes. `distribute_content` returns platform→status mapping.

**Actual Result:** _________ **PASS / FAIL:** _________

### 6.9 🟢 Register platform adapter (1 tool)
```python
r = json.loads(server.call_tool("register_platform_adapter", {
    "platform_name": "test-platform", "adapter_class": "automedia.adapters.base.BasePlatformAdapter",
}).content[0].text)
assert r.get("registered") or r.get("stub")
```
**Expected Result:** ✅ Returns registered/stub response. Empty name returns INVALID_PARAM. Invalid class returns error.

**Actual Result:** _________ **PASS / FAIL:** _________

### 6.10 🔴 MCP error codes — all 13 error codes
| Error Code | Trigger | Expected Response Shape |
|-----------|---------|------------------------|
| `INVALID_PARAM` | `run_pipeline` with invalid mode | `{"success": false, "error": {"code": "INVALID_PARAM", "message": "...", "resolution": "..."}}` |
| `NOT_FOUND` | `archive_project` non-existent project | same shape, code="NOT_FOUND" |
| `PIPELINE_ERROR` | pipeline runtime failure | same shape, code="PIPELINE_ERROR" |
| `ENGINE_ERROR` | engine health/dependency failure | same shape, code="ENGINE_ERROR" |
| `ALLOWLIST_DENIED` | access path outside allowlist | same shape, code="ALLOWLIST_DENIED" |
| `AUTH_ERROR` | invalid/expired platform credentials | same shape, code="AUTH_ERROR" |
| `RATE_LIMITED` | too many concurrent pipelines (max 3) | same shape, code="RATE_LIMITED" |
| `TIMEOUT` | pipeline or gate timeout | same shape, code="TIMEOUT" |
| `CONFIG_ERROR` | missing/invalid configuration | same shape, code="CONFIG_ERROR" |
| `DEPENDENCY_ERROR` | missing external dependency (bun, ffmpeg, etc.) | same shape, code="DEPENDENCY_ERROR" |
| `GATE_ERROR` | gate execution failure | same shape, code="GATE_ERROR" |
| `CANCELLED` | pipeline was cancelled | same shape, code="CANCELLED" |
| `UNKNOWN` | unhandled exception | same shape, code="UNKNOWN" |

**Expected Result:** ✅ Each returns proper MCPErrorCode. Error response has success=False + error.code/message/resolution. No Python traceback leaked.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q6 Verdict

| Tool Group | Count | Result |
|-----------|-------|--------|
| 6.1 Health check + onboarding | 4 | ⬜ |
| 6.2 Pipeline tools | 9 | ⬜ |
| 6.3 Project tools | 5 | ⬜ |
| 6.4 Topic pool | 3 | ⬜ |
| 6.5 Research/Strategy | 3 | ⬜ |
| 6.6 Omni Triad | 4 | ⬜ |
| 6.7 Content quality + analytics | 2 | ⬜ |
| 6.8 Brand/Asset/Workflow/Cron/Account/Distribution | 18 | ⬜ |
| 6.9 Register adapter | 1 | ⬜ |
| 6.10 Error codes | 13 | ⬜ |

**Total: 61 scenarios across 52 tools + 13 error codes**

**OVERALL: ⬜**

---

## Q7: Does every CLI command work correctly? (16 commands)

**User says:** "I prefer using the terminal. I need all 16 CLI commands to work."

### 7.1 🟢 Main help + version
```bash
automedia --help; automedia --version
```
**Expected Result:** ✅ `--help` shows all commands. `--version` shows version string. `--json` accepted.

**Actual Result:** _________ **PASS / FAIL:** _________

### 7.2 🟢 Each command's help works
```bash
for cmd in run pool projects distribute effects adapter cron archive init doctor omni hitl onboard account; do automedia $cmd --help; done
```
**Expected Result:** ✅ Every command has help output. No crashes.

**Actual Result:** _________ **PASS / FAIL:** _________

### 7.3 🟢 `doctor` — dependency check
```bash
automedia doctor; automedia doctor --json
```
**Expected Result:** ✅ Runs all checks. Structured output for each dep. `--json` outputs machine-readable JSON.

**Actual Result:** _________ **PASS / FAIL:** _________

### 7.4 🟢 `init` — configuration init
```bash
automedia init --template minimal
```
**Expected Result:** ✅ Creates `.automedia/` directory with default config. Does NOT overwrite existing config.

**Actual Result:** _________ **PASS / FAIL:** _________

### 7.5 🟢 `archive` — Red Line 8 enforcement
```bash
automedia run --topic "Archive Test" --brand test-brand --mode text_only
# Get project_id, then:
automedia archive PROJECT_ID --base-dir $AUTOMEDIA_PROJECTS_DIR
```
**Expected Result:** ❌ If not published: exit != 0, error about status. ✅ If published: exit 0. ✅ With --force: exit 0 (but agent MUST NOT use --force — RL8).

**Actual Result:** _________ **PASS / FAIL:** _________

### 7.6 🟢 `pool` — topic pool management
```bash
automedia pool list; automedia pool add "Test CLI Topic" --category tech; automedia pool list --status pending
```
**Expected Result:** ✅ `pool list` returns topics. `pool add` adds, returns id. `pool list --status pending` shows new topic.

**Actual Result:** _________ **PASS / FAIL:** _________

### 7.7 🟢 `projects` — project listing
```bash
automedia projects list; automedia projects get PROJECT_ID
```
**Expected Result:** ✅ Both work. `projects list` shows projects with status. `projects get` shows detailed info.

**Actual Result:** _________ **PASS / FAIL:** _________

### 7.8 🟢 `cron` — cron health
```bash
automedia cron check-health
```
**Expected Result:** ✅ Runs without crashing. Returns health status.

**Actual Result:** _________ **PASS / FAIL:** _________

### 7.9 🟢 `omni` — Omni Triad help
```bash
automedia omni --help
```
**Expected Result:** ✅ Shows subcommands: start-all, start, localize, format-output, ingest. Each has proper docs.

**Actual Result:** _________ **PASS / FAIL:** _________

### 7.10 🟢 `account` — account management
```bash
automedia account list; automedia account health ACCOUNT_ID
```
**Expected Result:** ✅ `list` returns accounts (may be empty). `health` with valid ID returns status; invalid ID returns error.

**Actual Result:** _________ **PASS / FAIL:** _________

### 7.11 🟢 `hitl` — HITL config
```bash
automedia hitl preset list; automedia hitl config list
```
**Expected Result:** ✅ Both work without crashing. Returns structured config info.

**Actual Result:** _________ **PASS / FAIL:** _________

### 7.12 🟢 `onboard` — onboarding wizard
```bash
automedia onboard status; automedia onboard list
```
**Expected Result:** ✅ Both work. Returns onboarding status/progress info.

**Actual Result:** _________ **PASS / FAIL:** _________

### 7.13 🟢 `distribute` — content distribution
```bash
automedia distribute --help
automedia distribute test-project --platforms wechat,twitter --dry-run
automedia distribute test-project --all --dry-run
```
**Expected Result:** ✅ `--help` shows options (--platforms, --all, --dry-run, --cron). `--dry-run` with --platforms prints plan for specified platforms. `--all --dry-run` prints plan for all 7 D-gate platforms (wechat, twitter, zhihu, xiaohongshu, bilibili, youtube, tiktok). Exit code 0.

**Actual Result:** _________ **PASS / FAIL:** _________

### 7.14 🟢 `effects` — content analytics
```bash
automedia effects --help
automedia effects test-project --output json
```
**Expected Result:** ✅ `--help` lists options (--output). `--output json` returns JSON with word_count, sentiment_score, readability_index, brand_mention_frequency, seo_score_aggregation. Exit code 0.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q7 Verdict

| # | Command | Result |
|---|---------|--------|
| 7.1 | Main help + version | ⬜ |
| 7.2 | Each command help | ⬜ |
| 7.3 | doctor | ⬜ |
| 7.4 | init | ⬜ |
| 7.5 | archive (RL8) | ⬜ |
| 7.6 | pool | ⬜ |
| 7.7 | projects | ⬜ |
| 7.8 | cron | ⬜ |
| 7.9 | omni | ⬜ |
| 7.10 | account | ⬜ |
| 7.11 | hitl | ⬜ |
| 7.12 | onboard | ⬜ |
| 7.13 | distribute | ⬜ |
| 7.14 | effects | ⬜ |

**OVERALL: ⬜**

---

## Q8: Are CLI and MCP outputs equivalent for overlapping functionality?

**User says:** "Does it matter whether I use CLI or MCP API? Will I get the same result?"

**Why this matters:** Both interfaces share `run_full_pipeline()` backend. Should produce equivalent results.

### 8.1 🟢 Pipeline output: CLI vs SDK
```python
# CLI: automedia run --topic "Equiv Test" --brand test-brand --mode text_only
# SDK:
from automedia import run_full_pipeline
result = run_full_pipeline(topic="Equiv Test", brand="test-brand", mode="text_only")
```
**Expected Result:** ✅ Both produce valid pipeline output. Both create project directories with same structure. Both write pipeline_md5.json and 00_project_info.json. ⚠️ Compare structure, not byte content (timestamps differ).

**Actual Result:** _________ **PASS / FAIL:** _________

### 8.2 🟢 Project listing: CLI vs MCP
```bash
automedia projects list --json
# vs. MCP: list_projects(base_dir=".", status="")
```
**Expected Result:** ✅ Both return project lists with same structure. Both handle empty dir gracefully.

**Actual Result:** _________ **PASS / FAIL:** _________

### 8.3 🟢 Archive: CLI vs MCP — both enforce Red Line 8
**Expected Result:** ✅ Both refuse non-published without --force. Both succeed with --force or published. Both produce same archive structure.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q8 Verdict | Scenario | Result | |----------|--------| | 8.1 Pipeline CLI vs SDK | ⬜ | | 8.2 Project listing CLI vs MCP | ⬜ | | 8.3 Archive CLI vs MCP | ⬜ |

**OVERALL: ⬜**

---

# Part 3: Gate System Validation

---

## Q9: Does each gate pass/fail correctly?

**User says:** "I need each quality gate to work correctly — passing good content and flagging bad content."

### 9.1 🟢 Existing gate test suite passes (baseline)
```bash
pytest tests/test_gates/ -v --timeout 60
pytest tests/test_gate_base.py tests/test_gate_engine.py tests/test_gate_hooks.py tests/test_gate_retry.py -v --timeout 60
```
**Expected Result:** ✅ All gate tests pass. No regressions. Known pre-existing failures unchanged.

**Actual Result:** _________ **PASS / FAIL:** _________

### 9.2 🟢 All 21 auto-mode gates execute
```python
from automedia import run_full_pipeline
result = run_full_pipeline(topic="All Gates Test", brand="test-brand", mode="auto")
auto_gates = ["pre-gate", "CW", "G0", "G1", "G2", "G3", "G4", "G5",
              "V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7",
              "H0", "L1", "L2", "L3", "L4"]
gate_names = [g.gate_name for g in result.gates_log]
for g in auto_gates:
    assert g in gate_names, f"Gate {g} missing"
```
**Expected Result:** ✅ All 21 auto-mode gates execute. Each has status passed/skipped/failed. No gate raises unhandled exception.

**Actual Result:** _________ **PASS / FAIL:** _________

### 9.3 🟢 Gates produce expected output artifacts
| Gate | Expected Artifact | Check |
|------|------------------|-------|
| CW | `01_content/drafts/*.md` | Non-empty markdown |
| V4 | `04_subtitle/*.mp3` | TTS audio file |
| V5 | `04_subtitle/*.srt` | Subtitle file |

**Expected Result:** ✅ All expected artifacts produced and non-empty.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q9 Verdict | Scenario | Result | |----------|--------| | 9.1 Gate test suite | ⬜ | | 9.2 All gates in auto | ⬜ | | 9.3 Gate artifacts | ⬜ |

**OVERALL: ⬜**

---

## Q10: Do failure modes work correctly (stop/retry)?

**User says:** "When a gate fails, what happens? Does it stop the pipeline or retry?"

### 10.1 🟢 `stop` gate failure halts pipeline
Mock a stop-mode gate returning passed=False. Verify GateEngine.run() returns early.
**Expected Result:** ✅ Pipeline stops at failing gate. Subsequent gates NOT executed. Result status is "partial".

**Actual Result:** _________ **PASS / FAIL:** _________

### 10.2 🟢 `retry` gate triggers Level 1 quality retry
Mock G1 (retry-mode) to fail first, pass second.
**Expected Result:** ✅ Gate retried exactly once. `_quality_retry_count` increments. After max_quality_retries (default 3) -> gate fails permanently. If pass on retry -> continues.

**Actual Result:** _________ **PASS / FAIL:** _________

### 10.3 🟢 `retry` gate Level 2 triggers content regeneration
After exhausting Level 1 retries, system regenerates content from CW.
**Expected Result:** ✅ CW re-executed, then failing gate re-executed. `_level2_exhausted` if max_regenerations (default 2) exhausted.

**Actual Result:** _________ **PASS / FAIL:** _________

### 10.4 🔴 Transient exception triggers Level 0 tenacity retry
Mock gate raising ConnectionError.
**Expected Result:** ✅ Tenacity retry with exponential backoff (1s, 2s, 4s). After 3 failures -> gate fails.

**Actual Result:** _________ **PASS / FAIL:** _________

### 10.5 🟢 Configurable retry thresholds from brand profile
**Expected Result:** ✅ Brand profile `gate_engine.max_quality_retries` overrides default 3. Missing config -> defaults used.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q10 Verdict | Scenario | Result | |----------|--------| | 10.1 stop halts | ⬜ | | 10.2 retry L1 quality retry | ⬜ | | 10.3 retry L2 regeneration | ⬜ | | 10.4 L0 tenacity retry | ⬜ | | 10.5 Configurable thresholds | ⬜ |

**OVERALL: ⬜**

---

## Q11: Does HITL integration work?

**User says:** "I want to review content before production. Can I pause the pipeline for human review?"

### 11.1 🟢 H0 gate in pipeline
```python
from automedia import run_full_pipeline
result = run_full_pipeline(topic="HITL Test", brand="test-brand", mode="text_only")
for g in result.gates_log:
    if g.gate_name == "H0": print(f"H0 status: {g.status}")
```
**Expected Result:** ✅ H0 executes. Pipeline continues after approval. When awaiting HITL, pipeline pauses.

**Actual Result:** _________ **PASS / FAIL:** _________

### 11.2 🟢 HITL approve/skip operations
```python
# executor.approve_node(node_name) — returns stored artifact
# executor.skip_node(node_name) — returns artifact with human_skipped=True
```
**Expected Result:** ✅ approve_node returns pending artifact. skip_node returns with human_skipped=True. Non-pending node raises ValueError.

**Actual Result:** _________ **PASS / FAIL:** _________

### 11.3 🟢 HITL preset configuration
```bash
automedia hitl preset list; automedia hitl config list
```
**Expected Result:** ✅ Built-in presets (automated, semi-automated) available. Each defines agent/human routing. Override capability works.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q11 Verdict | Scenario | Result | |----------|--------| | 11.1 H0 gate | ⬜ | | 11.2 Approve/skip | ⬜ | | 11.3 HITL presets | ⬜ |

**OVERALL: ⬜**

---

## Q11B: Do gate modifier YAML overrides work correctly?

**User says:** "I want to customize which gates run for specific platforms. Can I exclude some gates, include extra ones, or change failure modes per platform?"

**Why this matters:** Gate modifiers allow per-platform workflow customization without code changes. This is the primary mechanism for platform-aware pipeline tailoring.

### Prerequisites
```bash
# Create an override rule with gate modifiers
mkdir -p ~/.automedia/overrides/rules
cat > ~/.automedia/overrides/rules/gate-override.yaml << 'EOF'
gates:
  include: ["G0", "G1", "G2", "G3", "G4", "G5"]
  exclude: ["V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7"]
  override_failure_mode:
    G0: "retry"    # Change stop → retry for fact check
    G3: "stop"     # Change retry → stop for brand CTA
EOF
```

### Scenarios

#### 11B.1 🟢 Override rule `gates.include` adds gates to pipeline
```python
from automedia.core.overrides import load_gate_modifiers
modifiers = load_gate_modifiers(brand="test-brand", platform="wechat")
# If wechat override includes G0-G5, modifier dict contains them
assert "include" in modifiers or modifiers == {}  # empty if no override
```
**Expected Result:** ✅ `load_gate_modifiers()` returns parsed gate modifiers from YAML override rules. Include/exclude/override_failure_mode keys present when configured. Missing override returns empty dict.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 11B.2 🟢 `validate_gate_modifiers()` returns tuple with override_failure_mode
```python
from automedia.pipelines.runner import validate_gate_modifiers
gate_list, override_fm = validate_gate_modifiers(
    {"include": ["G0", "G1"], "override_failure_mode": {"G0": "retry"}},
    base=["CW", "G0", "G1", "G2"],
)
assert "G0" in gate_list and "G1" in gate_list
assert "CW" not in gate_list  # excluded since not in include
assert override_fm["G0"] == "retry"
```
**Expected Result:** ✅ Returns `(gate_names_list, override_failure_mode_dict)`. CW/L1-L4 lifecycle gates are always preserved regardless of modifiers. Invalid gate names raise ValueError.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 11B.3 🟢 `_collect_platform_gate_modifiers()` merges platform-level config
```python
from automedia.pipelines.runner import _collect_platform_gate_modifiers
result = _collect_platform_gate_modifiers(brand_dict={"platforms": {"wechat": {"gates": {"include": ["G0"]}}}})
assert result is not None
assert "G0" in result.get("include", [])
```
**Expected Result:** ✅ Platform-level gate configuration in brand profiles is read and merged. Last platform wins for conflicting `override_failure_mode` keys.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 11B.4 🟢 `override_failure_mode` applied per-instance (no class mutation)
```python
from automedia.pipelines.runner import _build_gates_from_names
from automedia.gates.base import GateRegistry
gates = _build_gates_from_names(["G0", "G1"], override_failure_mode={"G0": "retry"})
assert gates[0]._failure_mode == "retry"    # overridden
assert gates[1]._failure_mode != "retry"    # unaffected
# Verify class-level failure_mode is unchanged
assert GateRegistry.get("G0")._failure_mode != "retry"
```
**Expected Result:** ✅ `override_failure_mode` applied per gate instance via `object.__setattr__`. Class-level `_failure_mode` on the registered gate class remains untouched. Only the pipeline instance is affected.

**Actual Result:** _________ **PASS / FAIL:** _________

#### 11B.5 🔴 Invalid override_failure_mode value raises error
**Expected Result:** ❌ `validate_gate_modifiers()` raises ValueError for invalid failure mode strings (not "stop" or "retry"). No silent fallback to default.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q11B Verdict | Scenario | Result | |----------|--------| | 11B.1 Override YAML loading | ⬜ | | 11B.2 validate_gate_modifiers | ⬜ | | 11B.3 Platform gate merge | ⬜ | | 11B.4 Per-instance override | ⬜ | | 11B.5 Invalid failure mode | ⬜ |

**OVERALL: ⬜**

---

# Part 4: Error & Boundary Matrix

---

## Q12: Missing/corrupt/empty inputs

**User says:** "What if I pass a wrong file path? What if config is corrupted?"

### 12.1 🔴 Missing project base directory
```bash
automedia projects list --base-dir /nonexistent/path
```
**Expected Result:** ❌ Exit != 0 or warning. No traceback. No crash.

**Actual Result:** _________ **PASS / FAIL:** _________

### 12.2 🔴 Missing env vars (LLM API key)
```bash
unset AUTOMEDIA_LLM_API_KEY; automedia run --topic "Test" --brand test-brand --mode text_only
```
**Expected Result:** ❌ Pipeline fails. Error clearly states LLM API key required with setup instructions. No crash.

**Actual Result:** _________ **PASS / FAIL:** _________

### 12.3 🔴 Invalid config file (YAML syntax error)
```bash
echo "invalid: yaml: :::: broken" > /tmp/broken_config.yaml
AUTOMEDIA_CONFIG_DIR=/tmp/broken_config automedia run --topic "Test" --brand test-brand --mode text_only
```
**Expected Result:** ❌ May fail or skip broken file. No crash. YAML parsing error logged.

**Actual Result:** _________ **PASS / FAIL:** _________

### 12.4 🟢 Doctor handles missing deps gracefully
```bash
export PATH=$(echo $PATH | tr ':' '\n' | grep -v bun | tr '\n' ':')
automedia doctor
```
**Expected Result:** ✅ Doctor reports bun unavailable. Provides install instructions. No crash.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q12 Verdict | Scenario | Result | |----------|--------| | 12.1 Missing base dir | ⬜ | | 12.2 Missing env vars | ⬜ | | 12.3 Invalid config | ⬜ | | 12.4 Missing dep (doctor) | ⬜ |

**OVERALL: ⬜**

---

## Q13: Security boundaries

**User says:** "Can someone use MCP tools to read files outside the allowlist? Can agents bypass Red Line 8?"

### 13.1 🔴 MCP path allowlist — file outside allowed dirs
```python
from automedia.mcp.allowlist import check_path_allowed
assert check_path_allowed("/tmp/test.txt") == True         # inside
assert check_path_allowed("/etc/passwd") == False           # outside
# Symlink outside
import os; os.symlink("/etc/passwd", "/tmp/evil_symlink.txt")
assert check_path_allowed("/tmp/evil_symlink.txt") == False  # follows symlinks!
```
**Expected Result:** ✅ Inside allowed. Outside rejected. Symlinks to disallowed targets rejected. Path traversal rejected.

**Actual Result:** _________ **PASS / FAIL:** _________

### 13.2 🔴 Empty allowlist = deny all
```python
assert check_path_allowed("/tmp/test.txt") == False  # empty allowlist
```
**Expected Result:** ✅ Empty allowlist -> all paths denied (secure default).

**Actual Result:** _________ **PASS / FAIL:** _________

### 13.3 🔴 Red Line 8 — archive refuses unless published
```bash
automedia run --topic "RL8 Test" --brand test-brand --mode text_only
# get project_id, then:
automedia archive PROJECT_ID  # Should fail (not published)
```
**Expected Result:** ❌ Exit != 0. Error message: cannot archive until published. With --force: succeeds (but agent must NOT use force).

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q13 Verdict | Scenario | Result | |----------|--------| | 13.1 Path allowlist | ⬜ | | 13.2 Empty allowlist deny all | ⬜ | | 13.3 Red Line 8 | ⬜ |

**OVERALL: ⬜**

---

## Q14: Concurrent/parallel calls

**User says:** "I need to process 10 documents simultaneously. Will the system handle it?"

### 14.1 🟢 Run 3 pipelines concurrently (text_only) — respects concurrency semaphore
Use asyncio.gather or background processes to run 3 pipelines simultaneously.
**Expected Result:** ✅ All 3 complete independently (up to `max_concurrent_pipelines` default of 3). When a 4th is submitted, it is queued or receives `RATE_LIMITED` error. No race conditions on `active_pipelines.json`. Each produces valid project with correct metadata.

**Actual Result:** _________ **PASS / FAIL:** _________

### 14.2 🔴 Concurrent archive operations
**Expected Result:** ✅ Both succeed or one succeeds and other returns NOT_FOUND (after first archives). No data corruption.

**Actual Result:** _________ **PASS / FAIL:** _________

### 14.3 🟢 Session recovery via `active_pipelines.json`
Start a pipeline, check the session tracker, then cancel/complete and verify cleanup.
```python
import json
from pathlib import Path
tracker_path = Path("~/.automedia/active_pipelines.json").expanduser()
assert tracker_path.exists()
data = json.loads(tracker_path.read_text())
assert "pipelines" in data
```
**Expected Result:** ✅ `active_pipelines.json` exists at `~/.automedia/`. Active pipelines appear with project_id/pid/started_at. Cancelled pipelines are removed. Stale entries >24h tagged `"lost"` on next MCP server start. File is protected by `fcntl.flock` against concurrent write corruption.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q14 Verdict | Scenario | Result | |----------|--------| | 14.1 Concurrent pipelines | ⬜ | | 14.2 Concurrent archives | ⬜ | | 14.3 Session recovery | ⬜ |

**OVERALL: ⬜**

---

## Q15: Configuration edge cases

**User says:** "What if I set conflicting env variables? What if the config directory is a file?"

### 15.1 🟢 6-layer config merge — env var overrides project config
```bash
export AUTOMEDIA_LLM_MODEL="env-override-model"
# Create a project config with different LLM model
mkdir -p .automedia && echo "llm:\n  text_generation:\n    model: project-model" > .automedia/config.yaml
# Run doctor or LLM check; verify env var takes precedence
```
**Expected Result:** ✅ Config loader gives env var higher priority than project .automedia/ config.

**Actual Result:** _________ **PASS / FAIL:** _________

### 15.2 🔴 Config directory is a file (not directory)
```bash
touch /tmp/config_file
AUTOMEDIA_CONFIG_DIR=/tmp/config_file automedia run --topic "Test" --brand test-brand --mode text_only
```
**Expected Result:** ❌ May fail. No crash with unhandled exception.

**Actual Result:** _________ **PASS / FAIL:** _________

### 15.3 🟢 deep_merge is non-destructive (does not mutate inputs)
Test that deep_merge creates new dict without modifying inputs.
**Expected Result:** ✅ deep_merge returns new dict. Input dicts unchanged after merge.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q15 Verdict | Scenario | Result | |----------|--------| | 15.1 Env overrides project config | ⬜ | | 15.2 Config dir is file | ⬜ | | 15.3 deep_merge non-destructive | ⬜ |

**OVERALL: ⬜**

---

# Part 5: Production Trust

---

## Q16: Is the pipeline deterministic? (FAKE_LLM mode)

**User says:** "If I run the same topic twice with same settings, will I get the same output?"

### 16.1 🟢 Same pipeline twice -> identical gate results
Run same topic twice. Compare gate result structures.
**Expected Result:** ✅ Both produce same gate sequence. Same pass/fail decisions. ⚠️ Content may differ if LLM has randomness even in FAKE mode. At minimum, gate count and order are identical.

**Actual Result:** _________ **PASS / FAIL:** _________

### 16.2 🟢 Same config produces same project structure
Run twice, compare directory structures.
**Expected Result:** ✅ Same subdirectory layout. Same file naming pattern. Same metadata schema.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q16 Verdict | Scenario | Result | |----------|--------| | 16.1 Same pipeline twice | ⬜ | | 16.2 Same config structure | ⬜ |

**OVERALL: ⬜**

---

## Q17: Are hooks readonly and correctly dispatched?

**User says:** "Do hooks observe without mutating? Are all 3 lifecycle methods called?"

### 17.1 🟢 Hook dispatch order: before -> gate -> after/failed
Use mock hook that records calls.
**Expected Result:** ✅ `before_gate` called before each gate. `after_gate` called after passing gates. `on_gate_failed` called after failing gates. All hooks return None.

**Actual Result:** _________ **PASS / FAIL:** _________

### 17.2 🔴 Hook cannot mutate context — Protocol enforcement
A hook that tries to mutate context dict should be rejected by type checker.
**Expected Result:** ✅ GateHook Protocol declares methods return None. Type checker catches mutation attempts.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q17 Verdict | Scenario | Result | |----------|--------| | 17.1 Hook dispatch order | ⬜ | | 17.2 Hook readonly | ⬜ |

**OVERALL: ⬜**

---

## Q18: Are MD5 checksums recorded and verifiable?

**User says:** "Can I verify that my project files haven't been tampered with?"

### 18.1 🟢 MD5 recorded for each gate's output
```python
from automedia.hooks.md5_tracker import record_md5, get_pipeline_md5
record_md5(project_dir, "G0", "/path/to/file.md")
md5_data = get_pipeline_md5(project_dir)
assert "G0" in md5_data.get("gates", {})
```
**Expected Result:** ✅ MD5 recorded for each gate. pipeline_md5.json has valid JSON structure. Each entry has file_path, md5, recorded_at.

**Actual Result:** _________ **PASS / FAIL:** _________

### 18.2 🟢 verify_md5 returns True for unchanged files
```python
from automedia.hooks.md5_tracker import verify_md5
assert verify_md5(project_dir, "G0", "/path/to/file.md") == True
```
**Expected Result:** ✅ verify_md5 returns True for recorded+unchanged files. Returns False for missing records.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q18 Verdict | Scenario | Result | |----------|--------| | 18.1 MD5 recorded | ⬜ | | 18.2 MD5 verifiable | ⬜ |

**OVERALL: ⬜**

---

## Q19: Are production metrics recorded correctly?

**User says:** "I need to monitor pipeline performance over time."

### 19.1 🟢 MetricsHook records gate timing
```python
from automedia.hooks.metrics import MetricsHook
hook = MetricsHook()
# After running pipeline, verify production_metrics.json exists
```
**Expected Result:** ✅ production_metrics.json exists in project dir. Contains entries with gate, status, duration_s, timestamp.

**Actual Result:** _________ **PASS / FAIL:** _________

### 19.2 🟢 Cost/token data on pipeline result
```python
from automedia import run_full_pipeline
result = run_full_pipeline(topic="Cost Test", brand="test-brand", mode="text_only")
# Each gate's result may include token/cost data from _UsageTracker
if hasattr(result, 'gates_log') and result.gates_log:
    for gate in result.gates_log:
        if hasattr(gate, 'metadata') and gate.metadata:
            print(f"{gate.gate_name}: {gate.metadata.get('cost', 'N/A')}")
        break  # check first gate only
```
**Expected Result:** ✅ Pipeline result includes per-thread cost/token data where available (depends on LLM provider). `_UsageTracker` data is exposed but not aggregated across pipelines. Missing data does NOT cause errors — fields are absent rather than null/None.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q19 Verdict | Scenario | Result | |----------|--------| | 19.1 Metrics recorded | ⬜ | | 19.2 Cost/token data | ⬜ |

**OVERALL: ⬜**

---

# Part 6: Account & Credential Management

---

## Q20: Connect/list/health/disconnect accounts

**User says:** "I need to manage my platform accounts. Can I connect, check health, and disconnect?"

### 20.1 🟢 Full account lifecycle via MCP
```python
# Connect
r = server.call_tool("connect_account", {"platform": "test", "auth_type": "api_key", "credentials": {"key": "test123"}})
account_data = json.loads(r.content[0].text)
assert account_data["success"]
account_id = account_data["account"]["id"]

# List
r = server.call_tool("list_accounts", {})
list_data = json.loads(r.content[0].text)
assert len(list_data["accounts"]) >= 1

# Health
r = server.call_tool("get_account_health", {"account_id": account_id})
health_data = json.loads(r.content[0].text)
assert "status" in health_data

# Disconnect
r = server.call_tool("disconnect_account", {"account_id": account_id})
disconnect_data = json.loads(r.content[0].text)
assert disconnect_data["success"]
```
**Expected Result:** ✅ Full lifecycle works. Invalid account_id returns NOT_FOUND. Empty credentials returns INVALID_PARAM.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q20 Verdict | Scenario | Result | |----------|--------| | 20.1 Account lifecycle | ⬜ |

**OVERALL: ⬜**

---

## Q21: Are credentials encrypted at rest?

### 21.1 🟢 AccountStore encrypts and decrypts round-trip
```python
from automedia.accounts.store import AccountStore
from pathlib import Path
import tempfile
with tempfile.TemporaryDirectory() as td:
    store = AccountStore(storage_dir=td, master_key="test-key-32bytes!")
    # Save and load credentials
    store.save(account_id="test", account_info={...}, credentials={"key": "secret123"})
    loaded = store.load(account_id="test")
    assert loaded["key"] == "secret123"  # round-trip works
```
**Expected Result:** ✅ Encryption/decryption round-trip is idempotent. Wrong key raises InvalidTag. Credential file on disk is encrypted (not plaintext).

**Actual Result:** _________ **PASS / FAIL:** _________

### 21.2 🔴 Missing `AUTOMEDIA_MASTER_KEY` raises ValueError
**Expected Result:** ❌ AccountStore initialization without master_key raises ValueError.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q21 Verdict | Scenario | Result | |----------|--------| | 21.1 Encrypt/decrypt round-trip | ⬜ | | 21.2 Missing master key | ⬜ |

**OVERALL: ⬜**

---

## Q22: Does OAuth2 flow work?

### 22.1 🟢 OAuth2ClientCredentialsFlow
```python
from automedia.accounts.auth.oauth2 import OAuth2ClientCredentialsFlow
flow = OAuth2ClientCredentialsFlow(client_id="id", client_secret="secret", token_url="https://example.com/oauth/token")
```
**Expected Result:** ✅ Flow initializes correctly. Returns valid SessionToken when API responds. Handles HTTP errors gracefully.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q22 Verdict | Scenario | Result | |----------|--------| | 22.1 Client credentials flow | ⬜ |

**OVERALL: ⬜**

---

## Q23: Does SessionManager handle TTL and rate limits?

### 23.1 🟢 Token TTL refresh works
```python
from automedia.accounts.session import SessionManager
sm = SessionManager()
sm.set_token(account_id="test", token="abc", expires_in=3600)
token = sm.get_token(account_id="test")
assert token == "abc"  # Valid token returned
```
**Expected Result:** ✅ Token returned before expiry. Threshold-triggered refresh fires before expiry. Rate limit backoff returns stale tokens with warning.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q23 Verdict | Scenario | Result | |----------|--------| | 23.1 Token TTL refresh | ⬜ |

**OVERALL: ⬜**

---

# Part 7: HITL Framework

---

## Q24: Can I configure HITL presets?

### 24.1 🟢 Preset loading works
```python
from automedia.hitl.config import HITLConfig
cfg = HITLConfig(preset_name="automated")
nodes = cfg.list_nodes()
assert len(nodes) > 0
```
**Expected Result:** ✅ Both built-in presets (automated, semi-automated) load correctly. Unknown preset raises FileNotFoundError.

**Actual Result:** _________ **PASS / FAIL:** _________

### 24.2 🟢 Override merging works
```python
# Create override YAML and verify it merges with preset
```
**Expected Result:** ✅ Override updates existing nodes only. Does not add new nodes. Invalid override values rejected.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q24 Verdict | Scenario | Result | |----------|--------| | 24.1 Preset loading | ⬜ | | 24.2 Override merging | ⬜ |

**OVERALL: ⬜**

---

## Q25: Does NodeExecutor route correctly (agent vs human)?

### 25.1 🟢 Agent mode executes immediately
```python
from automedia.hitl.executor import NodeExecutor
executor = NodeExecutor(hitl_config)
# Execute agent-mode node
result = executor.execute("some_agent_node", agent=..., context=...)
assert result is not None  # Agent returns immediately
```
**Expected Result:** ✅ Agent-mode nodes execute and return immediately. Human-mode nodes return None (pending).

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q25 Verdict | Scenario | Result | |----------|--------| | 25.1 Agent vs human routing | ⬜ |

**OVERALL: ⬜**

---

## Q26: Can humans approve/skip nodes?

### 26.1 🟢 Approve and skip operations
```python
executor = NodeExecutor(hitl_config)
# Execute human node -> pending
result = executor.execute("some_human_node", agent=..., context=...)
assert result is None  # pending

# Approve
artifact = executor.approve_node("some_human_node")
assert artifact is not None

# Skip
artifact = executor.skip_node("some_human_node")  # after re-pending
assert artifact.metadata.get("human_skipped")
```
**Expected Result:** ✅ approve_node returns stored artifact. skip_node returns artifact with human_skipped=True. Non-pending node raises ValueError.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q26 Verdict | Scenario | Result | |----------|--------| | 26.1 Approve/skip | ⬜ |

**OVERALL: ⬜**

---

# Part 8: Decision Layer

---

## Q27: Does DecisionOrchestrator produce valid artifacts?

### 27.1 🟢 DecisionArtifact serialization
```python
from automedia.decision.base import DecisionArtifact
artifact = DecisionArtifact(type="brief", content={"key": "value"}, format="yaml")
serialized = artifact.serialize()
# Verify round-trip
deserialized = DecisionArtifact.deserialize(serialized)
assert deserialized.content == artifact.content
```
**Expected Result:** ✅ Artifact serializes/deserializes correctly. All 8 types supported. yaml/markdown/csv formats work.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q27 Verdict | Scenario | Result | |----------|--------| | 27.1 Artifact serialization | ⬜ |

**OVERALL: ⬜**

---

## Q28: Does force-provenance audit logging work?

### 28.1 🟢 Audit log written on force action
```python
from automedia.decision.audit import log_force_provenance
log_force_provenance(action="force_archive", reason="Testing", agent="test")
# Verify audit file exists and has entry
```
**Expected Result:** ✅ Audit entry written to ~/.automedia/audit/force_provenance.log. Entry has timestamp, action, reason, agent.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q28 Verdict | Scenario | Result | |----------|--------| | 28.1 Audit log written | ⬜ |

**OVERALL: ⬜**

---

## Q29: Does schema validation work?

### 29.1 🟢 Schema validation passes for valid data
```python
from automedia.decision.schema_validator import validate_artifact
result = validate_artifact("brief", {"key": "value"})
assert result["valid"] == True
```
**Expected Result:** ✅ Known schemas accept valid data. Missing schemas return error gracefully.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q29 Verdict | Scenario | Result | |----------|--------| | 29.1 Schema validation | ⬜ |

**OVERALL: ⬜**

---

# Part 9: Pipeline Infrastructure & Resilience

---

## Q30: Does GateEngine retry logic work correctly?

### 30.1 🟢 Level 0: tenacity retry
```python
# Existing test: test_gate_retry.py
pytest tests/test_gate_retry.py -v --timeout 30
```
**Expected Result:** ✅ Tenacity retries on transient exceptions. Exponential backoff. After max retries, gate fails.

**Actual Result:** _________ **PASS / FAIL:** _________

### 30.2 🟢 Level 1 & 2 retry chain
```python
pytest tests/test_gate_engine.py -v --timeout 30
```
**Expected Result:** ✅ Quality retry and content regeneration both work. Retry counts configurable.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q30 Verdict | Scenario | Result | |----------|--------| | 30.1 Tenacity retry | ⬜ | | 30.2 Quality + regeneration | ⬜ |

**OVERALL: ⬜**

---

## Q31: Can the system recover after partial failure?

### 31.1 🟢 Resume after stop-failure
Run pipeline that fails at a stop gate. Verify resume_from works to skip completed gates.
**Expected Result:** ✅ After stop-failure, can resume from the failed gate or later gate. Prior gate outputs preserved (verified by MD5).

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q31 Verdict | Scenario | Result | |----------|--------| | 31.1 Resume after failure | ⬜ |

**OVERALL: ⬜**

---

## Q32: Are 6-layer config merge and env var mapping correct?

### 32.1 🟢 Config merge order
```python
from automedia.core.config_loader import load_config
# Without overrides, built-in defaults should produce known structure
config = load_config()
assert "llm" in config
assert "gate_engine" in config
assert "engines" in config
```
**Expected Result:** ✅ Default config has all expected top-level keys. Env var `AUTOMEDIA_LLM_MODEL` maps to `config["llm"]["text_generation"]["model"]`.

**Actual Result:** _________ **PASS / FAIL:** _________

### 32.2 🟢 Env var to config mapping
```bash
export AUTOMEDIA_LLM_TEMPERATURE=0.5
python -c "from automedia.core.config_loader import load_config; c=load_config(); print(c['llm']['text_generation']['temperature'])"
```
**Expected Result:** ✅ AUTOMEDIA_LLM_TEMPERATURE correctly sets float value. AUTOMEDIA_DATA_DIR maps correctly. Unknown AUTOMEDIA_* vars handled gracefully.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q32 Verdict | Scenario | Result | |----------|--------| | 32.1 Config merge order | ⬜ | | 32.2 Env var mapping | ⬜ |

**OVERALL: ⬜**

---

## Q33: Is project lifecycle management correct?

### 33.1 🟢 Project.init creates standard structure
```python
from automedia.core.project import Project
proj = Project.init(topic="Lifecycle Test", brand="test-brand")
assert proj.project_dir.exists()
subdirs = [d.name for d in proj.project_dir.iterdir() if d.is_dir()]
assert "01_content" in subdirs and "02_images" in subdirs
assert (proj.project_dir / "00_project_info.json").exists()
```
**Expected Result:** ✅ 6 standard subdirectories created. 00_project_info.json has valid metadata.

**Actual Result:** _________ **PASS / FAIL:** _________

### 33.2 🔴 Empty slug (all CJK stripped) -> ValueError
```python
try:
    Project.init(topic="全部中文", brand="test-brand")
    assert False, "Should have raised ValueError"
except ValueError:
    pass
```
**Expected Result:** ❌ ValueError raised for empty slug.

**Actual Result:** _________ **PASS / FAIL:** _________

### 33.3 🔴 Path traversal in brand -> ValueError
```python
try:
    Project.init(topic="Test", brand="../../../etc/passwd")
    assert False, "Should have raised ValueError"
except ValueError:
    pass
```
**Expected Result:** ❌ ValueError raised for path traversal in brand.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q33 Verdict | Scenario | Result | |----------|--------| | 33.1 Standard structure | ⬜ | | 33.2 Empty slug | ⬜ | | 33.3 Path traversal | ⬜ |

**OVERALL: ⬜**

---

## Q34: Are pre-commit hooks working?

### 34.1 🟢 Pre-commit runs without errors
```bash
pre-commit run --all-files
```
**Expected Result:** ✅ All hooks pass or skip. No blocking failures.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q34 Verdict | Scenario | Result | |----------|--------| | 34.1 Pre-commit hooks | ⬜ |

**OVERALL: ⬜**

---

## Q35: Is CLI help output format stable?

### 35.1 🟢 Help output matches documented format
```bash
automedia --help
automedia run --help
automedia pool --help
```
**Expected Result:** ✅ Help output is consistent across commands. All options documented. No orphaned options (options that exist in code but not in help).

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q35 Verdict | Scenario | Result | |----------|--------| | 35.1 CLI help format | ⬜ |

**OVERALL: ⬜**

---

# Part 10: Production Validation (Real LLM · Real Deps · Performance)

---

## Q36: Does real LLM produce acceptable quality?

**Prerequisites:** Real LLM API key configured (not FAKE_LLM mode).

### 36.1 🟢 Existing LLM test suite passes
```bash
unset AUTOMEDIA_FAKE_LLM
pytest tests/test_llm_client.py -v --timeout 120
```
**Expected Result:** ✅ All LLM client tests pass. Structured output works. Retry on transient errors.

**Actual Result:** _________ **PASS / FAIL:** _________

### 36.2 🟢 Real LLM produces actual content
```python
from automedia.core.llm_client import llm_complete
response = llm_complete(prompt="Say 'Hello World'")
assert "Hello" in response
```
**Expected Result:** ✅ Returns actual LLM response (not mock). Response is coherent text.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q36 Verdict | Scenario | Result | |----------|--------| | 36.1 LLM test suite | ⬜ | | 36.2 Real LLM output | ⬜ |

**OVERALL: ⬜**

---

## Q37: Do real external tools work?

### 37.1 🟢 `automedia doctor` with real deps
```bash
automedia doctor
```
**Expected Result:** ✅ Most deps report available. Missing deps provide install instructions. No crashes.

**Actual Result:** _________ **PASS / FAIL:** _________

### 37.2 🟢 HyperFrames check works
**Expected Result:** ✅ doctor reports HyperFrames status. If missing, provides npm install instructions.

**Actual Result:** _________ **PASS / FAIL:** _________

### 37.3 🟢 Docker Compose `mcp-full` profile builds and starts
```bash
docker compose --profile mcp-full build
docker compose --profile mcp-full up -d
docker compose --profile mcp-full ps
docker compose --profile mcp-full down
```
**Expected Result:** ✅ `mcp-full` profile builds without errors. Container starts with bun, edge-tts, whisper, chromium pre-installed. `docker compose ps` shows all services healthy. Container can run `automedia doctor` successfully.

**Actual Result:** _________ **PASS / FAIL:** _________

### 37.4 🟢 Windows setup script (`scripts/setup.ps1`) validates
```powershell
# On Windows (or cross-platform syntax check):
python -c "import ast; ast.parse(open('scripts/setup.ps1').read())" 2>&1 || echo "PowerShell syntax checked manually"
```
**Expected Result:** ✅ `setup.ps1` exists and is syntactically valid PowerShell. Covers: venv creation, pip install, `automedia init`, `automedia doctor`. [Windows Deployment Guide](docs/user/windows-deployment.md) documents WSL2, Docker Desktop, and native Windows paths.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q37 Verdict | Scenario | Result | |----------|--------| | 37.1 Doctor with real deps | ⬜ | | 37.2 HyperFrames check | ⬜ | | 37.3 Docker mcp-full profile | ⬜ | | 37.4 Windows setup.ps1 | ⬜ |

**OVERALL: ⬜**

---

## Q38: Does performance meet production thresholds?

### 38.1 🟢 Existing performance test suite
```bash
pytest tests/test_benchmarks/ -v --timeout 300 2>/dev/null || echo "No benchmark dir"
```
**Expected Result:** ✅ If benchmarks exist: they run and report throughput. If no benchmarks: note that performance benchmarking is not yet automated.

**Actual Result:** _________ **PASS / FAIL:** _________

### 38.2 🟢 Pipeline completes within reasonable time (text_only)
```bash
time automedia run --topic "Perf Test" --brand test-brand --mode text_only
```
**Expected Result:** ⚠️ With FAKE_LLM: < 30s. With real LLM: < 5min for short content.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q38 Verdict | Scenario | Result | |----------|--------| | 38.1 Performance tests | ⬜ | | 38.2 Pipeline timing | ⬜ |

**OVERALL: ⬜**

---

## Q39: Does multi-provider failover work?

### 39.1 🟢 LLM client fails over on connection error
```python
from automedia.core.llm_client import llm_complete
# With wrong API key
import os; os.environ["AUTOMEDIA_LLM_API_KEY"] = "wrong-key"
try:
    response = llm_complete(prompt="Hello")
    # Should fail with LLMError
except Exception as e:
    print(f"Expected error: {e}")
```
**Expected Result:** ✅ LLMError raised with clear message. Error includes provider name and mitigation steps. Does NOT crash with unhandled exception.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q39 Verdict | Scenario | Result | |----------|--------| | 39.1 Provider failover | ⬜ |

**OVERALL: ⬜**

---

## Q40: Does the real MCP server work via stdio process?

**User says:** "I've been testing MCP tools in-process. But in production, MCP runs as a separate process. Does the stdio protocol work?"

### 40.1 🟢 MCP server starts and responds to health check
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"ping","params":{}}' | timeout 10 python -m automedia.mcp.server 2>/dev/null
```
**Expected Result:** ✅ Server starts. Responds to JSON-RPC ping. No immediate crash.

**Actual Result:** _________ **PASS / FAIL:** _________

### 40.2 🔴 MCP server rejects invalid JSON-RPC
```bash
echo 'invalid json' | timeout 5 python -m automedia.mcp.server 2>/dev/null; echo "Exit: $?"
```
**Expected Result:** ❌ Server does NOT crash. Returns JSON-RPC error response (parse error). No Python traceback.

**Actual Result:** _________ **PASS / FAIL:** _________

### 40.3 🟢 Existing MCP test suite
```bash
pytest tests/test_mcp/ -v --timeout 120
```
**Expected Result:** ✅ All MCP tests pass.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q40 Verdict | Scenario | Result | |----------|--------| | 40.1 MCP server stdio | ⬜ | | 40.2 Invalid JSON-RPC | ⬜ | | 40.3 MCP test suite | ⬜ |

**OVERALL: ⬜**

---

## Q41: Can the system run continuously without degradation?

### 41.1 🟢 5 consecutive pipeline runs — no crash
```bash
for i in $(seq 1 5); do
    automedia run --topic "Stress Test $i" --brand test-brand --mode text_only
    echo "Run $i: $?"
done
```
**Expected Result:** ✅ All 5 runs succeed (exit 0). No crash, no file handle leak.

**Actual Result:** _________ **PASS / FAIL:** _________

### 41.2 🟢 File handle leak check — still works after stress
```bash
# After 5 runs, run one more
automedia run --topic "Final Check" --brand test-brand --mode text_only
echo "Final: $?"
```
**Expected Result:** ✅ Still works. No "too many open files" errors.

**Actual Result:** _________ **PASS / FAIL:** _________

---

### 📊 Q41 Verdict | Scenario | Result | |----------|--------| | 41.1 5 consecutive runs | ⬜ | | 41.2 No file leak | ⬜ |

**OVERALL: ⬜**

---

# Part 11: Final Verdict

---

## Overall PASS/FAIL Summary

| Part | Section | Verdict |
|------|---------|---------|
| 1 | Core Pipeline Journeys | ⬜ |
| 2 | MCP & CLI Surface Mastery | ⬜ |
| 3 | Gate System Validation (incl. modifiers) | ⬜ |
| 4 | Error & Boundary Matrix | ⬜ |
| 5 | Production Trust | ⬜ |
| 6 | Account & Credential Management | ⬜ |
| 7 | HITL Framework | ⬜ |
| 8 | Decision Layer | ⬜ |
| 9 | Pipeline Infrastructure & Resilience | ⬜ |
| 10 | Production Validation | ⬜ |

**GRAND TOTAL: ⬜ / 43 Questions**

**OVERALL VERDICT: ⬜**

---

## Production Gap Checklist

| Criteria | Status | Notes |
|----------|--------|-------|
| All 52 MCP tools respond correctly | ⬜ | Q6 |
| All 16 CLI commands work | ⬜ | Q7 |
| `auto` mode pipeline completes | ⬜ | Q1 |
| All 9 modes (incl. repurpose) select correct gates | ⬜ | Q2 |
| Red Line 8 enforced | ⬜ | Q13 |
| Path allowlist blocks unauthorized access | ⬜ | Q13 |
| MD5 integrity tracking works | ⬜ | Q18 |
| Hooks readonly + correctly dispatched | ⬜ | Q17 |
| Credentials encrypted at rest | ⬜ | Q21 |
| HITL presets load correctly | ⬜ | Q24 |
| Gate modifier YAML overrides work | ⬜ | Q11B |
| Distribution D-gates produce correct output | ⬜ | Q5b |
| GateEngine retry logic correct | ⬜ | Q30 |
| Config merge order correct | ⬜ | Q32 |
| Project lifecycle correct | ⬜ | Q33 |
| Pre-commit hooks pass | ⬜ | Q34 |
| Performance meets thresholds | ⬜ | Q38 |

---

## Sign-off Criteria

| Level | Requirements | Met? |
|-------|-------------|------|
| **CI Gate** | All 43 questions answered + Q11B. No P0 failures. | ⬜ |
| **Release Candidate** | CI Gate + Q1-Q15 all PASS + Q36-Q37 all PASS | ⬜ |
| **Production Deploy** | Release Candidate + Q38-Q41 all PASS + no outstanding P0/P1 issues | ⬜ |

---

*Plan generated: 2026-07-17*
*Based on: Omni Suite validation plan structure · AutoMedia codebase analysis (33,619 LOC core, 145+ test files, 52 MCP tools, 16 CLI commands, 33 gates, 9 pipeline modes)*
